"""Deployment package API for fine-tuned model handoff."""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict

from core.config import get_settings
from core.training_context import get_training_context

router = APIRouter()


class DeploymentPackageRequest(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    training_task_id: str
    base_model: str | None = None
    adapter_path: str | None = None
    merged_model_path: str | None = None
    evaluation_run_id: str | None = None
    require_evaluation: bool = True
    min_good_rate: float = 0.6
    min_win_rate: float = 0.5
    min_schema_match_rate: float = 0.8
    service_base_url: str = "http://127.0.0.1:8000"
    model_alias: str | None = None


def _deployment_dir() -> Path:
    path = get_settings().outputs_dir_resolved / "deployment_packages"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _package_path(package_id: str) -> Path:
    return _deployment_dir() / f"{package_id}.json"


def _evaluation_path(run_id: str) -> Path:
    return get_settings().outputs_dir_resolved / "evaluations" / f"{run_id}.json"


def _read_package_file(path: Path) -> dict[str, Any] | None:
    try:
        with open(path, encoding="utf-8") as f:
            payload = json.load(f)
        return payload if isinstance(payload, dict) else None
    except Exception:
        return None


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
            return str(candidate)
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
        if request.require_evaluation:
            raise HTTPException(status_code=400, detail="部署包必须绑定通过门禁的 evaluation_run_id")
        return None

    if payload.get("status") not in {"completed", "completed_with_warnings"}:
        raise HTTPException(status_code=400, detail="评估任务尚未完成，不能生成部署包")

    if payload.get("training_task_id") and payload.get("training_task_id") != request.training_task_id:
        raise HTTPException(status_code=400, detail="评估任务与训练任务不匹配")
    release_id = getattr(record, "release_id", None) if record is not None else None
    if release_id and payload.get("release_id") and payload.get("release_id") != release_id:
        raise HTTPException(status_code=400, detail="评估任务与训练 release 不匹配")
    if payload.get("base_model") and payload.get("base_model") != resolved.get("base_model"):
        raise HTTPException(status_code=400, detail="评估基础模型与部署基础模型不一致")
    if payload.get("adapter_path") and resolved.get("adapter_path") and not _paths_match(payload.get("adapter_path"), resolved.get("adapter_path")):
        raise HTTPException(status_code=400, detail="评估 adapter 与部署 adapter 不一致")

    metrics = payload.get("metrics") or {}
    scenario = payload.get("scenario")
    passed = True
    reasons: list[str] = []
    if scenario == "structured_extraction":
        schema_rate = float(metrics.get("schema_match_rate", 0.0) or 0.0)
        if schema_rate < request.min_schema_match_rate:
            passed = False
            reasons.append(f"schema_match_rate {schema_rate} < {request.min_schema_match_rate}")
    else:
        good_rate = float(metrics.get("good_rate", 0.0) or 0.0)
        win_rate = float(metrics.get("win_rate", 0.0) or 0.0)
        if good_rate < request.min_good_rate and win_rate < request.min_win_rate:
            passed = False
            reasons.append(f"good_rate {good_rate} / win_rate {win_rate} 未达到门禁")

    if not passed:
        raise HTTPException(status_code=400, detail="评估门禁未通过：" + "；".join(reasons))

    return {
        "evaluation_run_id": payload.get("run_id"),
        "status": payload.get("status"),
        "scenario": scenario,
        "metrics": metrics,
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


def _resolve_package_inputs(request: DeploymentPackageRequest) -> dict[str, str | None]:
    record = _find_training_record(request.training_task_id)
    config = getattr(record, "config", {}) or {}

    base_model = (
        request.base_model
        or getattr(record, "base_model_id", None)
        or _get_config_value(config, "model_id", "modelId")
        or getattr(record, "model_name", None)
    )
    adapter_path = (
        request.adapter_path
        or getattr(record, "adapter_path", None)
        or getattr(record, "checkpoint_path", None)
    )
    merged_model_path = request.merged_model_path
    if not merged_model_path and getattr(record, "method", "") == "full":
        merged_model_path = getattr(record, "output_path", None)

    if not base_model:
        raise HTTPException(status_code=400, detail="缺少基础模型，请填写 base_model 或提供有效训练任务 ID")
    if not adapter_path and not merged_model_path:
        raise HTTPException(status_code=400, detail="缺少 Adapter 或合并模型路径，请填写 adapter_path 或 merged_model_path")

    return {
        "base_model": base_model,
        "adapter_path": _resolve_existing_path(adapter_path),
        "merged_model_path": _resolve_existing_path(merged_model_path),
    }


def _build_examples(model_name: str, service_base_url: str) -> dict[str, str]:
    return {
        "curl": (
            f"curl -X POST {service_base_url}/inference/chat "
            "-H \"Content-Type: application/json\" "
            f"-d '{{\"model_id\":\"{model_name}\",\"messages\":[{{\"role\":\"user\",\"content\":\"你好\"}}]}}'"
        ),
        "python": (
            "from openai import OpenAI\n\n"
            f"client = OpenAI(base_url=\"{service_base_url}/v1\", api_key=\"local\")\n"
            "response = client.chat.completions.create(\n"
            f"    model=\"{model_name}\",\n"
            "    messages=[{\"role\": \"user\", \"content\": \"你好\"}],\n"
            ")\n"
            "print(response.choices[0].message.content)\n"
        ),
        "typescript": (
            "import OpenAI from 'openai';\n\n"
            f"const client = new OpenAI({{ baseURL: '{service_base_url}/v1', apiKey: 'local' }});\n"
            "const response = await client.chat.completions.create({\n"
            f"  model: '{model_name}',\n"
            "  messages: [{ role: 'user', content: '你好' }],\n"
            "});\n"
            "console.log(response.choices[0].message.content);\n"
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
    examples = _build_examples(model_name=model_name, service_base_url=request.service_base_url.rstrip("/"))
    modelfile = _build_modelfile(
        model_name=base_model,
        adapter_path=adapter_path,
        merged_model_path=merged_model_path,
    )

    payload: dict[str, Any] = {
        "package_id": package_id,
        "training_task_id": request.training_task_id,
        "created_at": datetime.now().isoformat(),
        "base_model": base_model,
        "adapter_path": adapter_path,
        "merged_model_path": merged_model_path,
        "evaluation_run_id": request.evaluation_run_id,
        "evaluation_gate": evaluation_gate,
        "ollama_modelfile": modelfile,
        "openai_compatible_examples": examples,
        "env_template": {
            "OPENAI_BASE_URL": f"{request.service_base_url.rstrip('/')}/v1",
            "OPENAI_API_KEY": "local",
            "MODEL_NAME": model_name,
        },
    }

    with open(_package_path(package_id), "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    return payload


@router.get("/packages")
async def list_deployment_packages(limit: int = 20):
    packages: list[dict[str, Any]] = []
    for path in _deployment_dir().glob("deploy_*.json"):
        payload = _read_package_file(path)
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
            }
        )

    packages.sort(key=lambda item: item.get("created_at") or "", reverse=True)
    return packages[: max(1, min(limit, 100))]


@router.get("/packages/{package_id}")
async def get_deployment_package(package_id: str):
    path = _package_path(package_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail="部署包不存在")
    payload = _read_package_file(path)
    if not payload:
        raise HTTPException(status_code=500, detail="部署包文件损坏")
    return payload


@router.delete("/packages/{package_id}")
async def delete_deployment_package(package_id: str):
    path = _package_path(package_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail="部署包不存在")
    path.unlink()
    return {"deleted": True, "package_id": package_id}
