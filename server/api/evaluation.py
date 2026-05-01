"""Evaluation API for comparing base and fine-tuned model outputs."""

from __future__ import annotations

import asyncio
import json
import uuid
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from core.config import get_settings

router = APIRouter()

_run_locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

def _get_run_lock(run_id: str) -> asyncio.Lock:
    return _run_locks[run_id]


Scenario = Literal["qa_assistant", "structured_extraction"]


class EvaluationCase(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    prompt: str
    expected_output: Any | None = None
    schema_payload: dict[str, Any] | None = Field(default=None, alias="schema", serialization_alias="schema")
    base_output: Any | None = None
    finetuned_output: Any | None = None
    base_output_error: str | None = None
    finetuned_output_error: str | None = None


class EvaluationRunRequest(BaseModel):
    scenario: Scenario = "qa_assistant"
    base_model: str
    finetuned_model: str | None = None
    adapter_path: str | None = None
    auto_merge_adapter: bool = True
    test_dataset_id: str | None = None
    cases: list[EvaluationCase] = Field(default_factory=list)
    backend: str = "ollama"
    run_inference: bool = True
    max_tokens: int = Field(default=512, ge=1, le=4096)
    temperature: float = Field(default=0.2, ge=0, le=2)
    max_cases: int = Field(default=20, ge=1, le=100)


class EvaluationScoreRequest(BaseModel):
    case_index: int
    score: Literal["good", "neutral", "bad"]
    notes: str | None = None
    answer_covered: bool | None = None
    grounded_in_context: bool | None = None


def _evaluation_dir() -> Path:
    path = get_settings().outputs_dir_resolved / "evaluations"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _run_path(run_id: str) -> Path:
    return _evaluation_dir() / f"{run_id}.json"


def _parse_json(value: Any) -> tuple[bool, Any]:
    if isinstance(value, (dict, list)):
        return True, value
    if not isinstance(value, str):
        return False, None
    try:
        return True, json.loads(value)
    except json.JSONDecodeError:
        return False, None


def _schema_keys(schema: dict[str, Any] | None) -> set[str]:
    if not schema:
        return set()
    if isinstance(schema.get("properties"), dict):
        return set(schema["properties"].keys())
    return set(schema.keys())


def _compute_metrics(scenario: Scenario, cases: list[dict[str, Any]]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    failed_cases: list[dict[str, Any]] = []

    if scenario == "structured_extraction":
        valid_json = 0
        schema_match = 0
        field_total = 0
        field_present = 0

        for index, case in enumerate(cases):
            ok, parsed = _parse_json(case.get("finetuned_output"))
            if ok:
                valid_json += 1
            else:
                failed_cases.append({"case_index": index, "reason": "finetuned_output is not valid JSON"})
                continue

            keys = _schema_keys(case.get("schema"))
            if keys and isinstance(parsed, dict):
                present = sum(1 for key in keys if key in parsed)
                field_total += len(keys)
                field_present += present
                if present == len(keys):
                    schema_match += 1
                else:
                    failed_cases.append({"case_index": index, "reason": "missing schema fields"})
            elif not keys:
                schema_match += 1

        total = len(cases) or 1
        return {
            "json_valid_rate": round(valid_json / total, 4),
            "schema_match_rate": round(schema_match / total, 4),
            "field_completeness_rate": round(field_present / field_total, 4) if field_total else 0.0,
        }, failed_cases

    scores = [case.get("human_score", {}).get("score") for case in cases if case.get("human_score")]
    return {
        "human_score_count": len(scores),
        "good_rate": round(scores.count("good") / len(scores), 4) if scores else 0.0,
        "coverage_marked_count": sum(1 for case in cases if case.get("human_score", {}).get("answer_covered") is not None),
        "grounding_marked_count": sum(1 for case in cases if case.get("human_score", {}).get("grounded_in_context") is not None),
    }, failed_cases


def _build_prompt(case: dict[str, Any], scenario: Scenario) -> str:
    prompt = str(case.get("prompt") or "")
    schema = case.get("schema")
    if scenario == "structured_extraction" and schema:
        return (
            "请从下面输入中抽取信息，并严格输出合法 JSON。"
            f"\n字段/Schema：{json.dumps(schema, ensure_ascii=False)}"
            f"\n输入：{prompt}"
        )
    return prompt


async def _ensure_huggingface_model_loaded(model: str) -> None:
    """Load a local HuggingFace model path/name before calling the shared chat route."""
    from api.inference.scheduler import get_scheduler

    backend = await get_scheduler().get_backend("huggingface")
    current_model = getattr(backend, "_current_model_name", None)
    is_loaded = bool(getattr(backend, "_is_loaded", False))
    if is_loaded and current_model == model:
        return

    if is_loaded:
        await backend.unload_model()

    loaded = await backend.load_model(model)
    if not loaded:
        raise RuntimeError(f"HuggingFace 模型加载失败：{model}")
    setattr(backend, "_current_model_name", model)


async def run_model_inference(
    *,
    model: str,
    prompt: str,
    backend: str,
    max_tokens: int,
    temperature: float,
    response_format: str | None = None,
) -> str:
    """Run one inference call through the existing chat route."""
    if backend == "huggingface":
        await _ensure_huggingface_model_loaded(model)

    from api.inference.routes import chat as inference_chat
    from api.types import (
        ChatRequest,
        InferenceOptions,
        MemoryOptions,
        Message,
        MessageRole,
        ProjectContextOptions,
        KnowledgeRetrievalOptions,
        SessionOptions,
    )

    try:
        response = await inference_chat(
            ChatRequest(
                model=model,
                messages=[Message(role=MessageRole.USER, content=prompt)],
                options=InferenceOptions(
                    backend=backend,
                    max_tokens=max_tokens,
                    temperature=temperature,
                ),
                response_format=response_format,
                format=response_format,
                memory=MemoryOptions(enabled=False, auto_extract=False, auto_retrieve=False),
                knowledge=KnowledgeRetrievalOptions(use_knowledge=False, auto_retrieve=False),
                context=ProjectContextOptions(use_context=False),
                session=SessionOptions(user_id="evaluation"),
            )
        )
        
        if response.raw_response and response.raw_response.get("finish_reason") == "error":
            err_msg = response.raw_response.get("error") or "未知推理错误"
            raise RuntimeError(f"模型推理失败: {err_msg}")
            
        if not response.message.content and response.raw_response and response.raw_response.get("finish_reason") not in ("stop", "length"):
            raise RuntimeError(f"模型推理异常终止: finish_reason={response.raw_response.get('finish_reason')}")

        return response.message.content or ""
    except Exception as exc:
        raise RuntimeError(str(exc))


def _merge_adapter_for_evaluation(request: EvaluationRunRequest, run_id: str) -> dict[str, Any]:
    """Create a merged model artifact for adapter-only evaluation."""
    if not request.adapter_path:
        raise ValueError("缺少 adapter_path")

    from api.models import (
        _artifact_output_dir,
        _export_merged_lora_model,
        _model_path_or_404,
        _resolve_adapter_candidate,
        _write_export_manifest,
    )
    from core.utils import safe_filename

    model_path = _model_path_or_404(request.base_model)
    adapter_path = _resolve_adapter_candidate(request.adapter_path)
    if adapter_path is None:
        raise ValueError("未找到可用的 LoRA adapter")

    output_name = safe_filename(f"{request.base_model}-eval-{run_id}")
    output_dir = _artifact_output_dir("evaluation-merged", output_name)

    if not (output_dir / "config.json").exists():
        _export_merged_lora_model(model_path, adapter_path, output_dir)
        _write_export_manifest(
            output_dir=output_dir,
            model_id=request.base_model,
            source_path=model_path,
            target_format="lora-merged-evaluation",
            extra={
                "adapter_path": str(adapter_path),
                "evaluation_run_id": run_id,
                "implementation": "evaluation.auto_merge_adapter",
            },
        )

    return {
        "merged_model_path": str(output_dir),
        "adapter_path": str(adapter_path),
        "backend": "huggingface",
    }


async def _populate_inference_outputs(
    request: EvaluationRunRequest,
    case_payloads: list[dict[str, Any]],
    run_id: str,
) -> tuple[list[str], dict[str, Any] | None]:
    warnings: list[str] = []
    response_format = "json" if request.scenario == "structured_extraction" else None
    adapter_merge: dict[str, Any] | None = None
    finetuned_model = request.finetuned_model
    finetuned_backend = request.backend

    if request.run_inference and not finetuned_model and request.adapter_path and request.auto_merge_adapter:
        try:
            adapter_merge = _merge_adapter_for_evaluation(request, run_id)
            finetuned_model = adapter_merge["merged_model_path"]
            finetuned_backend = adapter_merge["backend"]
            warnings.append("已自动合并 adapter，并使用 HuggingFace 后端运行微调模型评估。")
        except Exception as exc:
            warnings.append(f"adapter 自动合并失败：{exc}")

    if request.run_inference:
        # Phase 1: Run all base model inferences to avoid model thrashing
        for case in case_payloads:
            if not case.get("base_output"):
                prompt = _build_prompt(case, request.scenario)
                try:
                    case["base_output"] = await run_model_inference(
                        model=request.base_model,
                        prompt=prompt,
                        backend=request.backend,
                        max_tokens=request.max_tokens,
                        temperature=request.temperature,
                        response_format=response_format,
                    )
                except Exception as exc:
                    case["base_output_error"] = str(exc)
                    warnings.append(f"基础模型推理失败：{exc}")

        # Phase 2: Run all finetuned model inferences
        if finetuned_model:
            for case in case_payloads:
                if not case.get("finetuned_output"):
                    prompt = _build_prompt(case, request.scenario)
                    try:
                        case["finetuned_output"] = await run_model_inference(
                            model=finetuned_model,
                            prompt=prompt,
                            backend=finetuned_backend,
                            max_tokens=request.max_tokens,
                            temperature=request.temperature,
                            response_format=response_format,
                        )
                    except Exception as exc:
                        case["finetuned_output_error"] = str(exc)
                        warnings.append(f"微调模型推理失败：{exc}")
        elif request.adapter_path:
            warnings.append("仅提供 adapter_path，但未能生成 merged model，本次未运行微调模型推理。")
            for case in case_payloads:
                if not case.get("finetuned_output"):
                    case["finetuned_output_error"] = "adapter 自动合并未成功，且未提供 finetuned_model。"

    return warnings, adapter_merge


def _load_cases_from_dataset(dataset_id: str | None, limit: int = 100) -> list[EvaluationCase]:
    if not dataset_id:
        return []

    dataset_path = get_settings().datasets_dir_resolved / dataset_id
    if not dataset_path.exists():
        raise HTTPException(status_code=404, detail="评估数据集不存在")

    data_file = next((path for path in dataset_path.glob("*.jsonl")), None) or next(
        (path for path in dataset_path.glob("*.json") if path.name != "info.json"),
        None,
    )
    if not data_file:
        return []

    cases: list[EvaluationCase] = []
    with open(data_file, encoding="utf-8") as f:
        if data_file.suffix == ".jsonl":
            raw = []
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    raw.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        else:
            try:
                raw = json.load(f)
            except json.JSONDecodeError:
                raise HTTPException(status_code=400, detail="数据集格式错误")

    for item in raw[:limit] if isinstance(raw, list) else [raw]:
        if not isinstance(item, dict):
            continue
        if isinstance(item.get("messages"), list):
            messages = [message for message in item["messages"] if isinstance(message, dict)]
            user_message = next((message for message in messages if message.get("role") in {"user", "human"}), {})
            assistant_message = next((message for message in reversed(messages) if message.get("role") in {"assistant", "gpt"}), {})
            prompt = str(user_message.get("content") or "")
            expected = assistant_message.get("content")
        else:
            prompt = str(item.get("question") or item.get("instruction") or item.get("input") or item.get("text") or "")
            expected = item.get("answer") or item.get("output")
        cases.append(EvaluationCase(
            prompt=prompt,
            expected_output=expected,
            schema=item.get("schema") or item.get("json_schema"),
        ))
    return cases


async def _run_evaluation_task(request: EvaluationRunRequest, run_id: str, case_payloads: list[dict[str, Any]]):
    try:
        async with _get_run_lock(run_id):
            with open(_run_path(run_id), "r", encoding="utf-8") as f:
                payload = json.load(f)
            payload["status"] = "running"
            with open(_run_path(run_id), "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)

        inference_warnings, adapter_merge = await _populate_inference_outputs(request, case_payloads, run_id)
        metrics, failed_cases = _compute_metrics(request.scenario, case_payloads)
        status = "completed_with_warnings" if inference_warnings else "completed"

        async with _get_run_lock(run_id):
            with open(_run_path(run_id), "r", encoding="utf-8") as f:
                payload = json.load(f)

            payload["status"] = status
            payload["finetuned_model"] = request.finetuned_model or (adapter_merge or {}).get("merged_model_path")
            payload["adapter_merge"] = adapter_merge
            payload["warnings"] = inference_warnings
            payload["base_outputs"] = [case.get("base_output") for case in case_payloads]
            payload["finetuned_outputs"] = [case.get("finetuned_output") for case in case_payloads]
            payload["cases"] = case_payloads
            payload["metrics"] = metrics
            payload["failed_cases"] = failed_cases

            with open(_run_path(run_id), "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
    except Exception as exc:
        async with _get_run_lock(run_id):
            with open(_run_path(run_id), "r", encoding="utf-8") as f:
                payload = json.load(f)
            payload["status"] = "failed"
            payload["error"] = str(exc)
            with open(_run_path(run_id), "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)


@router.post("/runs")
async def create_evaluation_run(request: EvaluationRunRequest, background_tasks: BackgroundTasks):
    cases = request.cases or _load_cases_from_dataset(request.test_dataset_id, request.max_cases)
    run_id = f"eval_{uuid.uuid4().hex[:12]}"
    case_payloads = [case.model_dump(by_alias=True) for case in cases[:request.max_cases]]

    payload = {
        "run_id": run_id,
        "scenario": request.scenario,
        "status": "pending",
        "created_at": datetime.now().isoformat(),
        "base_model": request.base_model,
        "finetuned_model": request.finetuned_model,
        "adapter_path": request.adapter_path,
        "adapter_merge": None,
        "test_dataset_id": request.test_dataset_id,
        "backend": request.backend,
        "run_inference": request.run_inference,
        "inference_options": {
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
            "max_cases": request.max_cases,
            "auto_merge_adapter": request.auto_merge_adapter,
        },
        "warnings": [],
        "base_outputs": [],
        "finetuned_outputs": [],
        "cases": case_payloads,
        "metrics": {},
        "failed_cases": [],
        "human_scores": [],
    }

    with open(_run_path(run_id), "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    background_tasks.add_task(_run_evaluation_task, request, run_id, case_payloads)

    return payload


@router.get("/runs/{run_id}")
async def get_evaluation_run(run_id: str):
    path = _run_path(run_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail="评估任务不存在")
    async with _get_run_lock(run_id):
        with open(path, encoding="utf-8") as f:
            return json.load(f)


@router.post("/runs/{run_id}/score")
async def score_evaluation_case(run_id: str, request: EvaluationScoreRequest):
    async with _get_run_lock(run_id):
        path = _run_path(run_id)
        if not path.exists():
            raise HTTPException(status_code=404, detail="评估任务不存在")
        with open(path, encoding="utf-8") as f:
            payload = json.load(f)
            
        cases = payload.get("cases", [])
        if request.case_index < 0 or request.case_index >= len(cases):
            raise HTTPException(status_code=400, detail="case_index 超出范围")

        score_payload = {
            "case_index": request.case_index,
            "score": request.score,
            "notes": request.notes,
            "answer_covered": request.answer_covered,
            "grounded_in_context": request.grounded_in_context,
            "updated_at": datetime.now().isoformat(),
        }
        cases[request.case_index]["human_score"] = score_payload
        payload["human_scores"] = [case["human_score"] for case in cases if case.get("human_score")]
        payload["metrics"], payload["failed_cases"] = _compute_metrics(payload["scenario"], cases)

        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

        return payload
