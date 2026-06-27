"""Deployment package API for fine-tuned model handoff."""

from __future__ import annotations

import json
import logging
import os
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, field_validator

from core.config import get_settings
from core.release_registry import get_release_registry
from core.training_context import get_training_context

router = APIRouter()
logger = logging.getLogger(__name__)


def _release_registry():
    return get_release_registry(str(get_settings().outputs_dir_resolved.parent / "data" / "app.db"))


class DeploymentPackageRequest(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    training_task_id: str
    base_model: str | None = None
    adapter_path: str | None = None
    merged_model_path: str | None = None
    evaluation_run_id: str | None = None
    service_base_url: str = "http://127.0.0.1:8010"
    model_alias: str | None = None

    @field_validator("model_alias")
    @classmethod
    def validate_model_alias(cls, value: str | None) -> str | None:
        if value is None:
            return value
        normalized = value.strip()
        if not normalized or len(normalized) > 96:
            raise ValueError("模型别名长度必须在 1-96 个字符之间")
        import re

        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", normalized):
            raise ValueError("模型别名只能包含字母、数字、点、下划线和短横线")
        return normalized


MIN_GOOD_RATE = 0.6
MIN_WIN_RATE = 0.5
MIN_SCHEMA_MATCH_RATE = 0.8
MIN_EVALUATION_CASES = 5
MIN_SCORE_COVERAGE = 0.9


def _deployment_dir() -> Path:
    path = get_settings().outputs_dir_resolved / "deployment_packages"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _package_path(package_id: str) -> Path:
    return _deployment_dir() / f"{package_id}.json"


def _evaluation_path(run_id: str) -> Path:
    return get_settings().outputs_dir_resolved / "evaluations" / f"{run_id}.json"


def _read_package_file(path: Path) -> dict[str, Any] | None:
    package_id = path.stem
    if package_id.startswith("deploy_"):
        stored = _release_registry().get("deployment", package_id)
        if stored is not None:
            return stored[0]
    try:
        with open(path, encoding="utf-8") as f:
            payload = json.load(f)
        if isinstance(payload, dict) and package_id.startswith("deploy_"):
            _release_registry().upsert("deployment", package_id, payload, expected_version=0)
        return payload if isinstance(payload, dict) else None
    except Exception:
        return None


def _list_package_payloads() -> list[dict[str, Any]]:
    registry = _release_registry()
    registry.migrate_json_directory("deployment", _deployment_dir(), "deploy_*.json")
    return registry.list("deployment")


def resolve_deployed_model(model_name: str) -> dict[str, Any] | None:
    """Resolve a deployment alias into a concrete local inference target."""
    candidates: list[dict[str, Any]] = []
    for payload in _list_package_payloads():
        if not payload:
            continue
        if payload.get("status") != "active":
            continue
        target = payload.get("inference_target") or {}
        alias = target.get("model_alias") or (payload.get("env_template") or {}).get("MODEL_NAME")
        if alias == model_name:
            candidates.append(payload)
    if not candidates:
        return None
    candidates.sort(key=lambda item: item.get("created_at") or "", reverse=True)
    payload = candidates[0]
    target = payload.get("inference_target") or {}
    return {
        "package_id": payload.get("package_id"),
        "model_alias": target.get("model_alias") or model_name,
        "model_path": target.get("model_path")
        or payload.get("merged_model_path")
        or payload.get("base_model"),
        "backend": target.get("backend") or "huggingface",
        "lora_adapter": target.get("lora_adapter") or payload.get("adapter_path") or None,
    }


def _get_config_value(config: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = config.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return None


def _resolve_existing_path(path_value: str | None) -> str | None:
    if not path_value:
        return None
    raw = Path(path_value)
    candidates = [raw]
    if not raw.is_absolute():
        settings = get_settings()
        candidates.extend([
            settings.outputs_dir_resolved / raw,
            Path.cwd() / raw,
        ])
    for candidate in candidates:
        if candidate.exists():
            resolved = candidate.resolve()
            settings = get_settings()
            allowed_roots = [settings.outputs_dir_resolved.resolve()]
            models_root = getattr(settings, "models_dir_resolved", None)
            if models_root is not None:
                allowed_roots.append(Path(models_root).resolve())
            if not any(resolved == root or root in resolved.parents for root in allowed_roots):
                raise HTTPException(status_code=400, detail="部署制品必须位于 outputs 或 models 目录内")
            return str(resolved)
    raise HTTPException(status_code=400, detail=f"部署产物路径不存在或不可访问：{path_value}")


def _paths_match(left: str | None, right: str | None) -> bool:
    if not left or not right:
        return True
    try:
        return Path(_resolve_existing_path(left) or "").resolve() == Path(_resolve_existing_path(right) or "").resolve()
    except HTTPException:
        return left == right


def _load_evaluation_run(run_id: str | None) -> dict[str, Any] | None:
    if not run_id:
        return None
    stored = _release_registry().get("evaluation", run_id)
    if stored is not None:
        return stored[0]
    path = _evaluation_path(run_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail="绑定的评估任务不存在")
    payload = _read_package_file(path)
    if not payload:
        raise HTTPException(status_code=500, detail="评估任务文件损坏")
    return payload


def _validate_evaluation_gate(
    *,
    request: DeploymentPackageRequest,
    record: Any,
    resolved: dict[str, str | None],
) -> dict[str, Any] | None:
    payload = _load_evaluation_run(request.evaluation_run_id)
    if not payload:
        raise HTTPException(status_code=400, detail="部署包必须绑定通过门禁的 evaluation_run_id")

    if payload.get("status") not in {"completed", "completed_with_warnings"}:
        raise HTTPException(status_code=400, detail="评估任务尚未完成，不能生成部署包")
    provenance = payload.get("data_provenance") or {}
    if not provenance.get("isolated_from_training"):
        raise HTTPException(status_code=400, detail="评估未使用独立测试快照或独立测试集，不能部署")

    if payload.get("training_task_id") and payload.get("training_task_id") != request.training_task_id:
        raise HTTPException(status_code=400, detail="评估任务与训练任务不匹配")
    release_id = getattr(record, "release_id", None) if record is not None else None
    if release_id and payload.get("release_id") and payload.get("release_id") != release_id:
        raise HTTPException(status_code=400, detail="评估任务与训练 release 不匹配")
    if payload.get("base_model") and payload.get("base_model") != resolved.get("base_model"):
        raise HTTPException(status_code=400, detail="评估基础模型与部署基础模型不一致")
    if payload.get("adapter_path") and resolved.get("adapter_path") and not _paths_match(payload.get("adapter_path"), resolved.get("adapter_path")):
        raise HTTPException(status_code=400, detail="评估 adapter 与部署 adapter 不一致")
    if (
        payload.get("finetuned_model")
        and resolved.get("merged_model_path")
        and not _paths_match(payload.get("finetuned_model"), resolved.get("merged_model_path"))
    ):
        raise HTTPException(status_code=400, detail="评估微调模型与部署合并模型不一致")
    from training_engine.reporter import hash_path

    deployed_artifact = resolved.get("adapter_path") or resolved.get("merged_model_path")
    evaluated_digest = payload.get("artifact_digest")
    if evaluated_digest and hash_path(deployed_artifact) != evaluated_digest:
        raise HTTPException(status_code=409, detail="待部署模型制品内容与评估时不一致")

    cases = payload.get("cases") or []
    if not cases:
        raise HTTPException(status_code=400, detail="评估任务没有有效样本，不能生成部署包")
    if len(cases) < MIN_EVALUATION_CASES:
        raise HTTPException(
            status_code=400,
            detail=f"评估样本不足：{len(cases)} < {MIN_EVALUATION_CASES}",
        )
    incomplete_cases = [
        index
        for index, case in enumerate(cases)
        if case.get("base_output") in (None, "")
        or case.get("finetuned_output") in (None, "")
        or case.get("base_output_error")
        or case.get("finetuned_output_error")
    ]
    if incomplete_cases:
        raise HTTPException(
            status_code=400,
            detail=f"评估存在未完成或失败样本，不能部署：{incomplete_cases[:10]}",
        )

    metrics = payload.get("metrics") or {}
    scenario = payload.get("scenario")
    passed = True
    reasons: list[str] = []
    if scenario == "structured_extraction":
        schema_rate = float(metrics.get("schema_match_rate", 0.0) or 0.0)
        schema_delta = float(metrics.get("schema_match_delta", 0.0) or 0.0)
        net_win_rate = float(metrics.get("net_win_rate", 0.0) or 0.0)
        expected_case_count = int(metrics.get("expected_case_count", 0) or 0)
        expected_rate = metrics.get("expected_match_rate")
        expected_delta = metrics.get("expected_match_delta")
        if schema_rate < MIN_SCHEMA_MATCH_RATE:
            passed = False
            reasons.append(f"schema_match_rate {schema_rate} < {MIN_SCHEMA_MATCH_RATE}")
        if schema_delta < 0 or net_win_rate < 0:
            passed = False
            reasons.append("微调模型相对基础模型出现结构化质量回归")
        if expected_case_count:
            if float(expected_rate or 0.0) < MIN_SCHEMA_MATCH_RATE:
                passed = False
                reasons.append(f"expected_match_rate {expected_rate} < {MIN_SCHEMA_MATCH_RATE}")
            if float(expected_delta or 0.0) < 0:
                passed = False
                reasons.append("结构化字段值正确率相对基础模型回归")
    else:
        good_rate = float(metrics.get("good_rate", 0.0) or 0.0)
        win_rate = float(metrics.get("win_rate", 0.0) or 0.0)
        net_win_rate = float(metrics.get("net_win_rate", 0.0) or 0.0)
        scored_count = int(
            metrics.get("scored_count", metrics.get("human_score_count", 0)) or 0
        )
        coverage = scored_count / len(cases)
        if coverage < MIN_SCORE_COVERAGE:
            passed = False
            reasons.append(f"评分覆盖率 {coverage:.0%} < {MIN_SCORE_COVERAGE:.0%}")
        if good_rate < MIN_GOOD_RATE and win_rate < MIN_WIN_RATE:
            passed = False
            reasons.append(f"good_rate {good_rate} / win_rate {win_rate} 未达到门禁")
        if net_win_rate <= 0:
            passed = False
            reasons.append(f"net_win_rate {net_win_rate} 必须大于 0")

    if not passed:
        raise HTTPException(status_code=400, detail="评估门禁未通过：" + "；".join(reasons))

    return {
        "evaluation_run_id": payload.get("run_id"),
        "status": payload.get("status"),
        "scenario": scenario,
        "metrics": metrics,
        "artifact_digest": payload.get("artifact_digest"),
        "data_provenance": provenance,
        "case_count": len(cases),
        "passed": True,
    }


def _find_training_record(training_task_id: str):
    try:
        for record in get_training_context().state.get_history():
            if record.id == training_task_id:
                return record
    except Exception:
        return None
    return None


def _sync_training_promotion(
    training_task_id: str | None,
    *,
    package_id: str | None,
    promotion_state: str,
    evaluation_run_id: str | None = None,
) -> str | None:
    if not training_task_id:
        return None
    record = _find_training_record(training_task_id)
    if record is None:
        return "未找到关联训练记录，release 状态未同步"
    try:
        from training_engine.reporter import write_training_artifact_manifest

        if evaluation_run_id:
            record.evaluation_run_id = evaluation_run_id
        record.deployment_package_id = package_id
        record.promotion_state = promotion_state
        write_training_artifact_manifest(record)
        get_training_context().state.add_to_history_sync(record)
        return None
    except Exception as exc:
        logger.exception("failed to sync training promotion for %s", training_task_id)
        return f"训练 release 状态同步失败：{exc}"


def _resolve_package_inputs(request: DeploymentPackageRequest) -> dict[str, str | None]:
    record = _find_training_record(request.training_task_id)
    config = getattr(record, "config", {}) or {}

    base_model = (
        request.base_model
        or getattr(record, "base_model_id", None)
        or _get_config_value(config, "model_id", "modelId")
        or getattr(record, "model_name", None)
    )
    is_full_training = getattr(record, "method", "") == "full"
    if is_full_training:
        adapter_path = request.adapter_path
        merged_model_path = (
            request.merged_model_path
            or getattr(record, "checkpoint_path", None)
            or getattr(record, "output_path", None)
        )
    else:
        adapter_path = (
            request.adapter_path
            or getattr(record, "adapter_path", None)
            or getattr(record, "checkpoint_path", None)
        )
        merged_model_path = request.merged_model_path

    if not base_model:
        raise HTTPException(status_code=400, detail="缺少基础模型，请填写 base_model 或提供有效训练任务 ID")
    if not adapter_path and not merged_model_path:
        raise HTTPException(status_code=400, detail="缺少 Adapter 或合并模型路径，请填写 adapter_path 或 merged_model_path")

    return {
        "base_model": base_model,
        "adapter_path": _resolve_existing_path(adapter_path),
        "merged_model_path": _resolve_existing_path(merged_model_path),
    }


def _build_examples(model_name: str, service_base_url: str, backend: str) -> dict[str, str]:
    payload_object = {
        "model": model_name,
        "prompt": "你好",
        "options": {"backend": backend, "temperature": 0.2, "max_tokens": 512},
    }
    payload = json.dumps(payload_object, ensure_ascii=False)
    windows_payload = payload.replace('"', '\\"')
    return {
        "curl": (
            f"curl.exe -X POST \"{service_base_url}/inference/generate\" "
            "-H \"Content-Type: application/json\" "
            f"-d \"{windows_payload}\""
        ),
        "python": (
            "import requests\n\n"
            f"payload = {payload_object!r}\n"
            f"response = requests.post(\"{service_base_url}/inference/generate\", json=payload)\n"
            "response.raise_for_status()\n"
            "print(response.json()[\"response\"])\n"
        ),
        "typescript": (
            f"const response = await fetch('{service_base_url}/inference/generate', {{\n"
            "  method: 'POST',\n"
            "  headers: { 'Content-Type': 'application/json' },\n"
            f"  body: JSON.stringify({payload}),\n"
            "});\n"
            "if (!response.ok) throw new Error(await response.text());\n"
            "console.log((await response.json()).response);\n"
        ),
    }


def _build_modelfile(model_name: str, adapter_path: str, merged_model_path: str | None) -> str:
    source = merged_model_path or model_name
    lines = [
        f"FROM {source}",
        "PARAMETER temperature 0.2",
        "PARAMETER top_p 0.9",
        "SYSTEM \"你是一个经过业务数据适配的本地 AI 助手。\"",
    ]
    if adapter_path and not merged_model_path:
        lines.append(f"# LoRA adapter: {adapter_path}")
        lines.append("# Merge the adapter before importing if your Ollama version does not support adapters.")
    return "\n".join(lines) + "\n"


@router.post("/packages")
async def create_deployment_package(request: DeploymentPackageRequest):
    record = _find_training_record(request.training_task_id)
    resolved = _resolve_package_inputs(request)
    evaluation_gate = _validate_evaluation_gate(request=request, record=record, resolved=resolved)
    base_model = resolved["base_model"] or ""
    adapter_path = resolved["adapter_path"] or ""
    merged_model_path = resolved["merged_model_path"]
    package_id = f"deploy_{uuid.uuid4().hex[:12]}"
    model_name = request.model_alias or merged_model_path or base_model
    inference_backend = "huggingface"
    examples = _build_examples(
        model_name=model_name,
        service_base_url=request.service_base_url.rstrip("/"),
        backend=inference_backend,
    )
    modelfile = _build_modelfile(
        model_name=base_model,
        adapter_path=adapter_path,
        merged_model_path=merged_model_path,
    )

    payload: dict[str, Any] = {
        "package_id": package_id,
        "training_task_id": request.training_task_id,
        "created_at": datetime.now().isoformat(),
        "created_order": time.time_ns(),
        "base_model": base_model,
        "adapter_path": adapter_path,
        "merged_model_path": merged_model_path,
        "evaluation_run_id": request.evaluation_run_id,
        "evaluation_gate": evaluation_gate,
        "status": "draft",
        "activated_at": None,
        "deactivated_at": None,
        "health": {"status": "not_checked", "checked_at": None, "detail": None},
        "audit": [
            {
                "action": "package_created",
                "at": datetime.now().isoformat(),
            }
        ],
        "inference_target": {
            "model_alias": model_name,
            "model_path": merged_model_path or base_model,
            "backend": inference_backend,
            "lora_adapter": None if merged_model_path else adapter_path or None,
        },
        "ollama_modelfile": modelfile,
        "openai_compatible_examples": examples,
        "env_template": {
            "FINETUNE_API_BASE_URL": request.service_base_url.rstrip("/"),
            "MODEL_NAME": model_name,
        },
    }

    _write_package(payload)

    persistence_warning = _sync_training_promotion(
        request.training_task_id,
        package_id=package_id,
        promotion_state="release_draft",
        evaluation_run_id=request.evaluation_run_id,
    )
    if persistence_warning:
        payload.setdefault("warnings", []).append(persistence_warning)
        _append_audit(payload, "release_sync_warning", detail=persistence_warning)
        _write_package(payload)

    return payload


def _write_package(payload: dict[str, Any]) -> None:
    package_id = str(payload.get("package_id") or "")
    if not package_id:
        raise HTTPException(status_code=500, detail="部署包缺少 package_id")
    _release_registry().upsert("deployment", package_id, payload)
    _export_package(payload)


def _export_package(payload: dict[str, Any]) -> None:
    package_id = str(payload.get("package_id") or "")
    path = _package_path(package_id)
    temporary = path.with_suffix(f".{os.getpid()}.{uuid.uuid4().hex}.tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, path)


def _append_audit(payload: dict[str, Any], action: str, **detail: Any) -> None:
    payload.setdefault("audit", []).append({
        "action": action,
        "at": datetime.now().isoformat(),
        **detail,
    })


async def _check_package_health(payload: dict[str, Any]) -> dict[str, Any]:
    target = payload.get("inference_target") or {}
    from training_engine.reporter import hash_path

    artifact_path = target.get("lora_adapter") or target.get("model_path")
    artifact_digest = hash_path(artifact_path)
    expected_digest = (payload.get("evaluation_gate") or {}).get("artifact_digest")
    if not artifact_digest and not Path(str(artifact_path or "")).exists():
        return {
            "status": "failed",
            "checked_at": datetime.now().isoformat(),
            "detail": "模型制品不存在或不可访问",
        }
    if expected_digest and artifact_digest != expected_digest:
        return {
            "status": "failed",
            "checked_at": datetime.now().isoformat(),
            "detail": "模型制品摘要与评估记录不一致",
        }
    return {
        "status": "healthy",
        "checked_at": datetime.now().isoformat(),
        "detail": "制品存在且身份校验通过",
        "artifact_digest": artifact_digest,
    }


@router.post("/packages/{package_id}/health")
async def check_deployment_package_health(package_id: str):
    payload = await get_deployment_package(package_id)
    payload["health"] = await _check_package_health(payload)
    _append_audit(payload, "health_checked", result=payload["health"]["status"])
    _write_package(payload)
    return payload


@router.post("/packages/{package_id}/activate")
async def activate_deployment_package(package_id: str):
    payload = await get_deployment_package(package_id)
    health = await _check_package_health(payload)
    payload["health"] = health
    if health["status"] != "healthy":
        _append_audit(payload, "activation_rejected", reason=health["detail"])
        _write_package(payload)
        raise HTTPException(status_code=409, detail=f"部署健康检查失败：{health['detail']}")

    alias = ((payload.get("inference_target") or {}).get("model_alias"))
    payload["status"] = "active"
    payload["activated_at"] = datetime.now().isoformat()
    payload["deactivated_at"] = None
    _append_audit(payload, "activated")
    changed = _release_registry().activate_deployment_exclusively(payload, str(alias or ""))
    for changed_payload in changed:
        _export_package(changed_payload)

    persistence_warning = _sync_training_promotion(
        payload.get("training_task_id"),
        package_id=package_id,
        promotion_state="active",
        evaluation_run_id=payload.get("evaluation_run_id"),
    )
    if persistence_warning:
        payload.setdefault("warnings", []).append(persistence_warning)
        _write_package(payload)
    return payload


@router.post("/packages/{package_id}/deactivate")
async def deactivate_deployment_package(package_id: str):
    payload = await get_deployment_package(package_id)
    payload["status"] = "inactive"
    payload["deactivated_at"] = datetime.now().isoformat()
    _append_audit(payload, "deactivated")
    persistence_warning = _sync_training_promotion(
        payload.get("training_task_id"),
        package_id=package_id,
        promotion_state="inactive",
        evaluation_run_id=payload.get("evaluation_run_id"),
    )
    if persistence_warning:
        payload.setdefault("warnings", []).append(persistence_warning)
    _write_package(payload)
    return payload


@router.post("/packages/{package_id}/rollback")
async def rollback_deployment_package(package_id: str):
    target = await get_deployment_package(package_id)
    alias = ((target.get("inference_target") or {}).get("model_alias"))
    candidates: list[dict[str, Any]] = []
    for payload in _list_package_payloads():
        if not payload or payload.get("package_id") == package_id:
            continue
        if ((payload.get("inference_target") or {}).get("model_alias")) != alias:
            continue
        if payload.get("status") in {"inactive", "draft"}:
            candidates.append(payload)
    candidates.sort(key=lambda item: item.get("activated_at") or item.get("created_at") or "", reverse=True)
    if not candidates:
        raise HTTPException(status_code=404, detail="没有可回滚的历史部署版本")
    previous = candidates[0]
    activated = await activate_deployment_package(str(previous["package_id"]))
    _append_audit(activated, "rollback_target", rolled_back_from=package_id)
    _write_package(activated)
    return activated


@router.get("/packages")
async def list_deployment_packages(limit: int = 20):
    packages: list[dict[str, Any]] = []
    payloads = sorted(
        (payload for payload in _list_package_payloads() if payload),
        key=lambda item: (
            item.get("created_at") or "",
            int(item.get("created_order") or 0),
        ),
        reverse=True,
    )
    for payload in payloads:
        if not payload:
            continue
        packages.append(
            {
                "package_id": payload.get("package_id"),
                "training_task_id": payload.get("training_task_id"),
                "created_at": payload.get("created_at"),
                "base_model": payload.get("base_model"),
                "adapter_path": payload.get("adapter_path"),
                "merged_model_path": payload.get("merged_model_path"),
                "evaluation_run_id": payload.get("evaluation_run_id"),
                "model_name": (payload.get("env_template") or {}).get("MODEL_NAME"),
                "status": payload.get("status", "draft"),
                "health": payload.get("health"),
                "activated_at": payload.get("activated_at"),
            }
        )

    return packages[: max(1, min(limit, 100))]


@router.get("/packages/{package_id}")
async def get_deployment_package(package_id: str):
    stored = _release_registry().get("deployment", package_id)
    payload = stored[0] if stored is not None else _read_package_file(_package_path(package_id))
    if not payload:
        raise HTTPException(status_code=404, detail="部署包不存在")
    return payload


@router.delete("/packages/{package_id}")
async def delete_deployment_package(package_id: str):
    path = _package_path(package_id)
    stored = _release_registry().get("deployment", package_id)
    payload = stored[0] if stored is not None else _read_package_file(path)
    if not payload:
        raise HTTPException(status_code=404, detail="部署包不存在")
    if payload and payload.get("status") == "active":
        raise HTTPException(status_code=409, detail="活动部署不能直接删除，请先停用")
    _release_registry().delete("deployment", package_id)
    path.unlink(missing_ok=True)
    if payload:
        _sync_training_promotion(
            payload.get("training_task_id"),
            package_id=None,
            promotion_state="evaluated",
            evaluation_run_id=payload.get("evaluation_run_id"),
        )
    return {"deleted": True, "package_id": package_id}
