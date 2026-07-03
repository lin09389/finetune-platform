"""Evaluation API for comparing base and fine-tuned model outputs."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import re
import uuid
from contextlib import asynccontextmanager, suppress
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, BackgroundTasks, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from core.config import get_settings
from core.db_manager import run_sync
from core.release_registry import get_release_registry, make_release_owner_id

router = APIRouter()
logger = logging.getLogger(__name__)


class RefCountedLock:
    def __init__(self):
        self.lock = asyncio.Lock()
        self.count = 0

_run_locks: dict[str, RefCountedLock] = {}
_run_events: dict[str, asyncio.Event] = {}
_worker_owner_id = make_release_owner_id()


def _release_registry():
    return get_release_registry(str(get_settings().outputs_dir_resolved.parent / "data" / "app.db"))

@asynccontextmanager
async def _get_run_lock(run_id: str):
    if run_id not in _run_locks:
        _run_locks[run_id] = RefCountedLock()
    lock_obj = _run_locks[run_id]
    lock_obj.count += 1
    try:
        async with lock_obj.lock:
            yield
    finally:
        lock_obj.count -= 1
        if lock_obj.count == 0:
            _run_locks.pop(run_id, None)


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
    training_task_id: str | None = None
    release_id: str | None = None
    system_prompt: str | None = None
    auto_merge_adapter: bool = True
    test_dataset_id: str | None = None
    evaluation_snapshot_path: str | None = None
    evaluation_snapshot_hash: str | None = None
    artifact_digest: str | None = None
    cases: list[EvaluationCase] = Field(default_factory=list)
    backend: str = "ollama"
    run_inference: bool = True
    max_tokens: int = Field(default=512, ge=1, le=4096)
    temperature: float = Field(default=0.2, ge=0, le=2)
    max_cases: int = Field(default=20, ge=1, le=100)
    judge_model: str | None = Field(default=None, description="The strong model to use for LLM-as-a-judge.")


class JudgeRequest(BaseModel):
    judge_model: str = Field(description="用于独立裁判任务的模型名称")
    backend: str = Field(default="huggingface", description="推理引擎后端类型")


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


def _export_run_payload(run_id: str, payload: dict[str, Any]) -> None:
    path = _run_path(run_id)
    temporary = path.with_suffix(f".{os.getpid()}.{uuid.uuid4().hex}.tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, path)


async def _read_run_payload(run_id: str) -> dict[str, Any] | None:
    registry = _release_registry()
    stored = await run_sync(registry.get, "evaluation", run_id)
    if stored is not None:
        return stored[0]
    path = _run_path(run_id)
    if not path.exists():
        return None
    try:
        payload = json.loads(await run_sync(path.read_text, encoding="utf-8"))
        await run_sync(registry.upsert, "evaluation", run_id, payload, expected_version=0)
        return payload
    except (OSError, json.JSONDecodeError):
        return None


async def _write_run_payload(run_id: str, payload: dict[str, Any]) -> None:
    registry = _release_registry()
    await run_sync(registry.upsert, "evaluation", run_id, payload)
    await run_sync(_export_run_payload, run_id, payload)


async def _mutate_run_payload(run_id: str, mutator) -> dict[str, Any] | None:
    registry = _release_registry()
    result = await run_sync(registry.mutate, "evaluation", run_id, mutator)
    if result is None:
        return None
    payload = result[0]
    await run_sync(_export_run_payload, run_id, payload)
    return payload


async def _heartbeat_lease(resource_id: str, ttl_seconds: int = 300) -> None:
    registry = _release_registry()
    try:
        while True:
            await asyncio.sleep(max(2, ttl_seconds // 3))
            if not await run_sync(
                registry.heartbeat,
                resource_id,
                _worker_owner_id,
                ttl_seconds,
            ):
                return
    except asyncio.CancelledError:
        return


def _find_training_record(training_task_id: str | None):
    try:
        if getattr(get_settings(), "training_execution_mode", "in_process") == "worker":
            from services.training.records import find_training_record

            return find_training_record(training_task_id)
        from core.training_context import get_training_context

        return next(
            (record for record in get_training_context().state.get_history() if record.id == training_task_id),
            None,
        )
    except Exception:
        return None


def _resolve_evaluation_request(request: EvaluationRunRequest) -> EvaluationRunRequest:
    """Resolve stable training artifacts and reject ambiguous training-linked evaluations."""
    if not request.training_task_id:
        return request

    record = _find_training_record(request.training_task_id)
    if record is None:
        raise HTTPException(status_code=404, detail="训练任务不存在，无法创建关联评估")
    if record.status != "completed":
        raise HTTPException(status_code=400, detail="只有已完成且已保存产物的训练任务可以创建评估")

    config = record.config or {}
    request.base_model = (
        request.base_model
        or getattr(record, "base_model_id", None)
        or config.get("model_id")
        or config.get("modelId")
        or record.model_name
    )
    request.release_id = request.release_id or getattr(record, "release_id", None)
    request.test_dataset_id = (
        request.test_dataset_id
        or config.get("test_dataset_id")
        or config.get("testDatasetId")
        or config.get("validation_dataset_id")
        or config.get("validationDatasetId")
    )
    request.evaluation_snapshot_path = getattr(record, "evaluation_snapshot_path", None)
    request.evaluation_snapshot_hash = getattr(record, "evaluation_snapshot_hash", None)
    request.artifact_digest = getattr(record, "artifact_digest", None)
    if not request.test_dataset_id and not request.evaluation_snapshot_path:
        raise HTTPException(
            status_code=400,
            detail="训练任务没有独立测试快照；请重新训练生成 held-out snapshot，或显式选择独立测试数据集",
        )
    training_dataset_id = (
        getattr(record, "dataset_id", None)
        or config.get("dataset_id")
        or config.get("datasetId")
    )
    if request.test_dataset_id and request.test_dataset_id == training_dataset_id:
        raise HTTPException(
            status_code=400,
            detail="评估数据集不能与训练数据集相同，请使用 held-out snapshot 或独立测试集",
        )
    request.scenario = getattr(record, "task_goal", None) or request.scenario

    if record.method == "full":
        request.finetuned_model = (
            request.finetuned_model
            or getattr(record, "checkpoint_path", None)
            or getattr(record, "output_path", None)
        )
    else:
        request.adapter_path = (
            request.adapter_path
            or getattr(record, "adapter_path", None)
            or getattr(record, "checkpoint_path", None)
        )

    artifact_path = request.finetuned_model if record.method == "full" else request.adapter_path
    if not artifact_path or not Path(artifact_path).exists():
        raise HTTPException(status_code=400, detail="训练产物不存在或不可访问，无法创建真实评估")
    return request


def _persist_evaluation_link(training_task_id: str | None, run_id: str) -> str | None:
    if not training_task_id:
        return None
    try:
        from training_engine.reporter import write_training_artifact_manifest

        worker_mode = getattr(get_settings(), "training_execution_mode", "in_process") == "worker"
        if worker_mode:
            from services.training.records import find_training_record

            record = find_training_record(training_task_id)
        else:
            from core.training_context import get_training_context

            state = get_training_context().state
            record = next((item for item in state.get_history() if item.id == training_task_id), None)
        if record is None:
            return "评估已完成，但未找到关联训练记录，release 状态未同步"
        record.evaluation_run_id = run_id
        record.promotion_state = "evaluated"
        write_training_artifact_manifest(record)
        if worker_mode:
            from services.training.records import save_training_record

            save_training_record(record)
        else:
            state.add_to_history_sync(record)
        return None
    except Exception as exc:
        logger.exception("failed to persist evaluation link for %s", training_task_id)
        return f"评估已完成，但训练 release 状态同步失败：{exc}"


def _parse_json(value: Any) -> tuple[bool, Any]:
    if isinstance(value, dict | list):
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


def _prompt_template_hash(scenario: Scenario, system_prompt: str | None) -> str:
    payload = json.dumps(
        {
            "scenario": scenario,
            "system_prompt": system_prompt or "",
            "structured_prefix": "extract_json_v1",
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _expected_json_type(schema_value: Any) -> str | None:
    if isinstance(schema_value, dict):
        value = schema_value.get("type")
        return str(value).lower() if value else None
    if isinstance(schema_value, str):
        mapping = {
            "str": "string",
            "text": "string",
            "int": "number",
            "float": "number",
            "num": "number",
            "bool": "boolean",
        }
        return mapping.get(schema_value.lower(), schema_value.lower())
    return None


def _value_matches_schema(value: Any, expected_type: str | None) -> bool:
    if expected_type in (None, "any"):
        return True
    if expected_type in {"number", "integer"}:
        return isinstance(value, int | float) and not isinstance(value, bool)
    if expected_type == "string":
        return isinstance(value, str)
    if expected_type == "boolean":
        return isinstance(value, bool)
    if expected_type == "array":
        return isinstance(value, list)
    if expected_type == "object":
        return isinstance(value, dict)
    return True


def _structured_quality(case: dict[str, Any], output_key: str) -> tuple[dict[str, Any], str | None]:
    ok, parsed = _parse_json(case.get(output_key))
    schema = case.get("schema") or {}
    keys = _schema_keys(schema)
    result = {
        "json_valid": ok,
        "schema_match": False,
        "field_total": len(keys),
        "field_present": 0,
        "type_match": False,
        "expected_available": False,
        "expected_match": False,
    }
    if not ok:
        return result, f"{output_key} is not valid JSON"
    if not keys:
        result["schema_match"] = True
        result["type_match"] = True
    expected_ok, expected = _parse_json(case.get("expected_output"))
    if expected_ok:
        result["expected_available"] = True
        result["expected_match"] = parsed == expected
    if not keys:
        return result, None
    if not isinstance(parsed, dict):
        return result, f"{output_key} JSON root is not an object"
    present = [key for key in keys if key in parsed]
    result["field_present"] = len(present)
    result["schema_match"] = len(present) == len(keys)
    properties = schema.get("properties") if isinstance(schema.get("properties"), dict) else schema
    type_checks = [
        _value_matches_schema(parsed[key], _expected_json_type(properties.get(key) if isinstance(properties, dict) else None))
        for key in present
    ]
    result["type_match"] = bool(type_checks) and all(type_checks) and result["schema_match"]
    if not result["schema_match"]:
        return result, f"{output_key} missing schema fields"
    if not result["type_match"]:
        return result, f"{output_key} schema field type mismatch"
    return result, None


def _compute_metrics(scenario: Scenario, cases: list[dict[str, Any]]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    failed_cases: list[dict[str, Any]] = []

    if scenario == "structured_extraction":
        base_valid_json = finetuned_valid_json = 0
        base_schema_match = finetuned_schema_match = 0
        base_type_match = finetuned_type_match = 0
        base_expected_match = finetuned_expected_match = expected_total = 0
        field_total = base_field_present = finetuned_field_present = 0
        wins = losses = ties = 0

        for index, case in enumerate(cases):
            base_quality, _ = _structured_quality(case, "base_output")
            fine_quality, fine_reason = _structured_quality(case, "finetuned_output")
            base_valid_json += int(base_quality["json_valid"])
            finetuned_valid_json += int(fine_quality["json_valid"])
            base_schema_match += int(base_quality["schema_match"])
            finetuned_schema_match += int(fine_quality["schema_match"])
            base_type_match += int(base_quality["type_match"])
            finetuned_type_match += int(fine_quality["type_match"])
            if fine_quality["expected_available"]:
                expected_total += 1
                base_expected_match += int(base_quality["expected_match"])
                finetuned_expected_match += int(fine_quality["expected_match"])
            field_total += int(fine_quality["field_total"])
            base_field_present += int(base_quality["field_present"])
            finetuned_field_present += int(fine_quality["field_present"])
            base_score = sum(int(base_quality[key]) for key in ("json_valid", "schema_match", "type_match"))
            fine_score = sum(int(fine_quality[key]) for key in ("json_valid", "schema_match", "type_match"))
            if fine_score > base_score:
                wins += 1
            elif fine_score < base_score:
                losses += 1
            else:
                ties += 1
            if fine_reason:
                failed_cases.append({"case_index": index, "reason": fine_reason})

        total = len(cases) or 1
        return {
            "json_valid_rate": round(finetuned_valid_json / total, 4),
            "schema_match_rate": round(finetuned_schema_match / total, 4),
            "field_completeness_rate": round(finetuned_field_present / field_total, 4) if field_total else 0.0,
            "type_match_rate": round(finetuned_type_match / total, 4),
            "expected_match_rate": round(finetuned_expected_match / expected_total, 4) if expected_total else None,
            "base_json_valid_rate": round(base_valid_json / total, 4),
            "base_schema_match_rate": round(base_schema_match / total, 4),
            "base_field_completeness_rate": round(base_field_present / field_total, 4) if field_total else 0.0,
            "base_type_match_rate": round(base_type_match / total, 4),
            "base_expected_match_rate": round(base_expected_match / expected_total, 4) if expected_total else None,
            "json_valid_delta": round((finetuned_valid_json - base_valid_json) / total, 4),
            "schema_match_delta": round((finetuned_schema_match - base_schema_match) / total, 4),
            "type_match_delta": round((finetuned_type_match - base_type_match) / total, 4),
            "expected_match_delta": round((finetuned_expected_match - base_expected_match) / expected_total, 4) if expected_total else None,
            "expected_case_count": expected_total,
            "finetuned_win_count": wins,
            "finetuned_loss_count": losses,
            "tie_count": ties,
            "win_rate": round(wins / total, 4),
            "net_win_rate": round((wins - losses) / total, 4),
        }, failed_cases

    scored_cases = [case for case in cases if case.get("human_score")]
    scores = [case.get("human_score", {}).get("score") for case in scored_cases]
    judge_score_count = sum(
        1
        for case in scored_cases
        if case.get("human_score", {}).get("source") == "llm_judge"
        or case.get("human_score", {}).get("notes") == "LLM Auto Evaluated"
    )
    human_score_count = len(scored_cases) - judge_score_count
    total_scored = len(scores) or 1
    wins = scores.count("good")
    losses = scores.count("bad")
    ties = scores.count("neutral")
    return {
        "scored_count": len(scores),
        "human_score_count": human_score_count,
        "judge_score_count": judge_score_count,
        "good_rate": round(wins / len(scores), 4) if scores else 0.0,
        "finetuned_win_count": wins,
        "finetuned_loss_count": losses,
        "tie_count": ties,
        "win_rate": round(wins / total_scored, 4) if scores else 0.0,
        "loss_rate": round(losses / total_scored, 4) if scores else 0.0,
        "net_win_rate": round((wins - losses) / total_scored, 4) if scores else 0.0,
        "coverage_marked_count": sum(1 for case in cases if case.get("human_score", {}).get("answer_covered") is not None),
        "grounding_marked_count": sum(1 for case in cases if case.get("human_score", {}).get("grounded_in_context") is not None),
    }, failed_cases


def _build_prompt(case: dict[str, Any], scenario: Scenario, system_prompt: str | None = None) -> str:
    prompt = str(case.get("prompt") or "")
    if system_prompt:
        prompt = f"{system_prompt}\n\n{prompt}"
    schema = case.get("schema")
    if scenario == "structured_extraction" and schema:
        return (
            "请从下面输入中抽取信息，并严格输出合法 JSON。"
            f"\n字段/Schema：{json.dumps(schema, ensure_ascii=False)}"
            f"\n输入：{prompt}"
        )
    return prompt


async def run_model_inference_batch(
    *,
    model: str,
    prompts: list[str],
    backend: str,
    max_tokens: int,
    temperature: float,
    response_format: str | None = None,
    lora_adapter: str | None = None,
) -> list[str]:
    """Run evaluation inference through the configured execution boundary."""
    if get_settings().inference_execution_mode == "service":
        from inference_provider.client import InferenceServiceError, get_inference_service_client

        client = get_inference_service_client()
        canonical_model = model if "/" in model else f"{backend}/{model}"
        semaphore = asyncio.Semaphore(10)

        async def remote_call(prompt: str) -> str:
            async with semaphore:
                remote_model = model
                headers = {"Content-Type": "application/json", "X-Backend": backend}
                model_path = Path(model)
                if model_path.exists():
                    remote_model = model_path.name
                    headers["X-Model-Path"] = str(model_path)
                if lora_adapter:
                    headers["X-LoRA-Adapter"] = lora_adapter
                request_payload = {
                    "model": remote_model if model_path.exists() else canonical_model,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_completion_tokens": max_tokens,
                    "temperature": temperature,
                    "stream": False,
                }
                response = await client.request(
                    "POST",
                    "/v1/chat/completions",
                    content=json.dumps(request_payload, ensure_ascii=False).encode(),
                    headers=headers,
                )
                if response.status_code >= 400:
                    raise InferenceServiceError(
                        f"Inference service returned HTTP {response.status_code}: "
                        f"{response.content.decode(errors='replace')}"
                    )
                payload = json.loads(response.content)
                choices = payload.get("choices") or []
                return str((choices[0].get("message") or {}).get("content") or "") if choices else ""

        return await asyncio.gather(*(remote_call(prompt) for prompt in prompts))

    """Compatibility path: execute directly via the ModelScheduler."""
    from api.inference.backends.base import GenerationConfig
    from api.inference.scheduler import get_scheduler

    try:
        scheduler = get_scheduler()
        backend_instance = await scheduler.get_backend(backend)
        leased_model = None

        if backend != "cloud":
            model_path = scheduler.resolve_model_path(model, backend) if hasattr(scheduler, "resolve_model_path") else model
            if hasattr(scheduler, "acquire_model"):
                leased_model = await scheduler.acquire_model(
                    model,
                    model_path,
                    backend,
                    num_ctx=max_tokens * 2,
                    num_batch=512,
                    max_tokens=max_tokens,
                    lora_adapter=lora_adapter,
                )
                if leased_model is None:
                    raise RuntimeError(f"模型加载失败: {model}")

        if hasattr(backend_instance, "model_name") and model:
            backend_instance.model_name = model

        messages_list = [[{"role": "user", "content": prompt}] for prompt in prompts]
        config = GenerationConfig(
            max_tokens=max_tokens,
            temperature=temperature,
        )

        try:
            if hasattr(backend_instance, "chat_batch"):
                try:
                    responses = await backend_instance.chat_batch(messages_list, config)
                    return [r.text if hasattr(r, "text") else str(r) for r in responses]
                except NotImplementedError:
                    pass

            # Fallback for non-batch backends
            sem = asyncio.Semaphore(10)
            async def _single(msgs):
                async with sem:
                    response = await backend_instance.chat(msgs, config)
                    return response.text if hasattr(response, "text") else str(response)

            return await asyncio.gather(*(_single(msgs) for msgs in messages_list))

        finally:
            if leased_model is not None and hasattr(scheduler, "release_model"):
                await scheduler.release_model(model)

    except Exception as exc:
        raise RuntimeError(str(exc))


async def run_model_inference_batch_with_retry(
    max_retries: int = 2,
    **kwargs,
) -> list[str]:
    """Run batch inference with automatic retry."""
    for attempt in range(max_retries + 1):
        try:
            return await run_model_inference_batch(**kwargs)
        except Exception:
            if attempt == max_retries:
                raise
            await asyncio.sleep(2 ** attempt)


async def _run_llm_judge_batch(
    judge_model: str,
    backend: str,
    prompts: list[str],
    base_outputs: list[str],
    finetuned_outputs: list[str],
    expected_outputs: list[str | None],
) -> list[Literal["good", "neutral", "bad"]]:
    judge_prompts = []
    swap_flags: list[bool] = []
    for p, b_out, f_out, e_out in zip(
        prompts,
        base_outputs,
        finetuned_outputs,
        expected_outputs,
        strict=False,
    ):
        swapped = hashlib.sha256(p.encode("utf-8")).digest()[0] % 2 == 1
        swap_flags.append(swapped)
        candidate_a, candidate_b = (f_out, b_out) if swapped else (b_out, f_out)
        judge_prompts.append(f"""请作为一名严谨的大模型评估专家，对两个匿名候选回答进行盲评。
请按照固定 rubric 判断，不要偏向更长或更自信的回答：
- correctness: 是否正确回答问题
- completeness: 是否覆盖关键点
- faithfulness: 是否忠于参考答案或上下文
- safety: 是否存在危险、不当或明显幻觉
- style: 是否符合用户问题的表达场景

原始问题：
{p}

参考答案：
{e_out or "无"}

候选回答 A：
{candidate_a}

候选回答 B：
{candidate_b}

请判断 A、B 哪个整体更好；两者相当时选择 tie。
只允许输出 JSON，不要有任何其他字符：
{{"winner":"a|b|tie","reason":"一句话说明主要依据"}}

输出：""")

    try:
        results = await run_model_inference_batch_with_retry(
            max_retries=1,
            model=judge_model,
            prompts=judge_prompts,
            backend=backend,
            max_tokens=128,
            temperature=0.1,
        )
        scores: list[Literal["good", "neutral", "bad"]] = []
        for result, swapped in zip(results, swap_flags, strict=False):
            result_lower = result.strip().lower()
            winner = None
            try:
                parsed = json.loads(result)
                if isinstance(parsed, dict):
                    raw = str(parsed.get("winner", "")).lower()
                    if raw in {"a", "b", "tie"}:
                        winner = raw
            except Exception:
                pass
            if winner is None:
                match = re.search(r'\b(a|b|tie)\b', result_lower)
                winner = match.group(1) if match else "tie"
            if winner == "tie":
                verdict = "neutral"
            else:
                fine_winner = (winner == "a" and swapped) or (winner == "b" and not swapped)
                verdict = "good" if fine_winner else "bad"
            scores.append(verdict)  # type: ignore[arg-type]
        return scores
    except Exception as exc:
        raise RuntimeError(str(exc))


async def _flush_progress(run_id: str, case_payloads: list[dict[str, Any]]):
    """Safely flush current cases during an ongoing run."""
    try:
        async with _get_run_lock(run_id):
            payload = await _mutate_run_payload(
                run_id,
                lambda current: {**current, "cases": case_payloads},
            )
            if payload is None:
                return
        if run_id in _run_events:
            _run_events[run_id].set()
    except Exception:
        pass


async def _populate_inference_outputs(
    request: EvaluationRunRequest,
    case_payloads: list[dict[str, Any]],
    run_id: str,
) -> tuple[list[str], dict[str, Any] | None]:
    warnings: list[str] = []
    response_format = "json" if request.scenario == "structured_extraction" else None
    adapter_merge: dict[str, Any] | None = None
    finetuned_model = request.finetuned_model
    base_backend = request.backend
    finetuned_backend = request.backend
    lora_adapter = None

    if (
        request.run_inference
        and request.auto_merge_adapter
        and not finetuned_model
        and request.adapter_path
    ):
        finetuned_model = request.base_model
        finetuned_backend = "huggingface"
        base_backend = "huggingface"
        lora_adapter = request.adapter_path
        adapter_merge = {
            "base_model_path": request.base_model,
            "adapter_path": request.adapter_path,
            "backend": "huggingface",
            "mode": "dynamic_lora",
        }

    if request.run_inference:
        batch_size = 8
        chunks = [case_payloads[i:i+batch_size] for i in range(0, len(case_payloads), batch_size)]

        # 限制并发 chunk 的数量（防止并发启动太多 batch）
        chunk_sem = asyncio.Semaphore(3)

        async def evaluate_batch_base(chunk: list[dict[str, Any]]):
            async with chunk_sem:
                unprocessed = [c for c in chunk if not c.get("base_output")]
                if not unprocessed:
                    return
                prompts = [_build_prompt(c, request.scenario, request.system_prompt) for c in unprocessed]
                try:
                    outputs = await run_model_inference_batch_with_retry(
                        max_retries=2,
                        model=request.base_model,
                        prompts=prompts,
                        backend=base_backend,
                        max_tokens=request.max_tokens,
                        temperature=request.temperature,
                        response_format=response_format,
                    )
                    for c, out in zip(unprocessed, outputs, strict=False):
                        c["base_output"] = out
                except Exception as exc:
                    for c in unprocessed:
                        c["base_output_error"] = str(exc)
                    warnings.append(f"基础模型批处理推理失败：{exc}")

                # Incremental flush
                await _flush_progress(run_id, case_payloads)

        # Phase 1: Run all base model inferences concurrently in batches
        await asyncio.gather(*(evaluate_batch_base(chunk) for chunk in chunks))

        # Phase 2: Run all finetuned model inferences concurrently in batches
        if finetuned_model:
            async def evaluate_batch_finetuned(chunk: list[dict[str, Any]]):
                async with chunk_sem:
                    unprocessed = [c for c in chunk if not c.get("finetuned_output")]
                    if not unprocessed:
                        return
                    prompts = [_build_prompt(c, request.scenario, request.system_prompt) for c in unprocessed]
                    try:
                        outputs = await run_model_inference_batch_with_retry(
                            max_retries=2,
                            model=finetuned_model,
                            prompts=prompts,
                            backend=finetuned_backend,
                            max_tokens=request.max_tokens,
                            temperature=request.temperature,
                            response_format=response_format,
                            lora_adapter=lora_adapter,
                        )
                        for c, out in zip(unprocessed, outputs, strict=False):
                            c["finetuned_output"] = out
                    except Exception as exc:
                        for c in unprocessed:
                            c["finetuned_output_error"] = str(exc)
                        warnings.append(f"微调模型批处理推理失败：{exc}")

                    # Incremental flush
                    await _flush_progress(run_id, case_payloads)

            await asyncio.gather(*(evaluate_batch_finetuned(chunk) for chunk in chunks))

        elif request.adapter_path:
            warnings.append("仅提供 adapter_path，但未能生成 merged model，本次未运行微调模型推理。")
            for case in case_payloads:
                if not case.get("finetuned_output"):
                    case["finetuned_output_error"] = "adapter 自动合并未成功，且未提供 finetuned_model。"

        # Phase 3 is decoupled to _run_judge_task

    return warnings, adapter_merge

async def _run_judge_task(run_id: str, judge_model: str, backend: str, scenario: str = "qa_assistant", force_rejudge: bool = False):
    """独立的后台判卷任务"""
    registry = _release_registry()
    lease_id = f"{run_id}:judge"
    claimed = await run_sync(registry.claim, lease_id, "evaluation_judge", _worker_owner_id, 30)
    if not claimed:
        return
    heartbeat_task = asyncio.create_task(_heartbeat_lease(lease_id, 30))
    try:
        payload = await _read_run_payload(run_id)
        if payload is None:
            return

        async with _get_run_lock(run_id):
            payload["status"] = "running"
            await _write_run_payload(run_id, payload)
        if run_id in _run_events:
            _run_events[run_id].set()

        case_payloads = payload.get("cases", [])
        if force_rejudge:
            for case in case_payloads:
                if "human_score" in case and case["human_score"].get("notes") == "LLM Auto Evaluated":
                    del case["human_score"]

        batch_size = 8
        chunk_sem = asyncio.Semaphore(10)
        warnings = payload.get("warnings", [])

        if scenario == "qa_assistant":
            async def evaluate_batch_judge(chunk_indices: list[int]):
                async with chunk_sem:
                    unprocessed_indices = []
                    prompts, base_outs, finetuned_outs, expected_outs = [], [], [], []
                    for i in chunk_indices:
                        case = case_payloads[i]
                        if case.get("human_score"):
                            continue
                        f_out = case.get("finetuned_output")
                        b_out = case.get("base_output", "")
                        if f_out and not case.get("finetuned_output_error"):
                            unprocessed_indices.append(i)
                            prompts.append(_build_prompt(case, scenario, payload.get("system_prompt")))
                            base_outs.append(b_out)
                            finetuned_outs.append(f_out)
                            expected_outs.append(case.get("expected_output"))

                    if not unprocessed_indices:
                        return

                    try:
                        scores = await _run_llm_judge_batch(
                            judge_model=judge_model,
                            backend=backend,
                            prompts=prompts,
                            base_outputs=base_outs,
                            finetuned_outputs=finetuned_outs,
                            expected_outputs=expected_outs,
                        )
                        for i, score in zip(unprocessed_indices, scores, strict=False):
                            case_payloads[i]["human_score"] = {
                                "case_index": i,
                                "score": score,
                                "notes": "LLM Auto Evaluated",
                                "source": "llm_judge",
                                "updated_at": datetime.now().isoformat(),
                            }
                    except Exception as exc:
                        warnings.append(f"LLM 裁判批处理执行失败：{exc}")

                    # Incremental flush
                    await _flush_progress(run_id, case_payloads)

            chunk_indices_list = [list(range(i, min(i+batch_size, len(case_payloads)))) for i in range(0, len(case_payloads), batch_size)]
            await asyncio.gather(*(evaluate_batch_judge(idx_list) for idx_list in chunk_indices_list))

        async with _get_run_lock(run_id):
            payload = await _read_run_payload(run_id) or payload
            payload["cases"] = case_payloads
            # 重新计算指标
            metrics, failed_cases = _compute_metrics(scenario, case_payloads)
            payload["metrics"] = metrics
            payload["failed_cases"] = failed_cases
            if warnings:
                payload["warnings"] = warnings
                payload["status"] = "completed_with_warnings"
            else:
                payload["status"] = "completed"
            await _write_run_payload(run_id, payload)
        if run_id in _run_events:
            _run_events[run_id].set()

    except Exception as exc:
        async with _get_run_lock(run_id):
            payload = await _read_run_payload(run_id)
            if payload is not None:
                payload["status"] = "failed"
                payload["error"] = f"裁判引擎执行异常: {str(exc)}"
                await _write_run_payload(run_id, payload)
        if run_id in _run_events:
            _run_events[run_id].set()
    finally:
        heartbeat_task.cancel()
        await asyncio.gather(heartbeat_task, return_exceptions=True)
        await run_sync(registry.release, lease_id, _worker_owner_id)


def _load_cases_from_file(data_file: Path, limit: int = 100) -> list[EvaluationCase]:
    if not data_file.exists():
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
        elif isinstance(item.get("conversations"), list):
            conversations = [conv for conv in item["conversations"] if isinstance(conv, dict)]
            user_message = next((conv for conv in conversations if conv.get("from") in {"human", "user"}), {})
            assistant_message = next((conv for conv in reversed(conversations) if conv.get("from") in {"gpt", "assistant"}), {})
            prompt = str(user_message.get("value") or "")
            expected = assistant_message.get("value")
        else:
            prompt = str(item.get("question") or item.get("instruction") or item.get("input") or item.get("text") or item.get("description") or "")
            expected = item.get("answer") or item.get("output") or item.get("code")

        prompt = prompt.strip()
        if not prompt:
            continue

        cases.append(EvaluationCase(
            prompt=prompt,
            expected_output=expected,
            schema=item.get("schema") or item.get("json_schema"),
        ))
    return cases


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
    return _load_cases_from_file(data_file, limit) if data_file else []


async def _run_evaluation_task(request: EvaluationRunRequest, run_id: str, case_payloads: list[dict[str, Any]]):
    registry = _release_registry()
    lease_id = f"{run_id}:run"
    claimed = False
    for _ in range(8):
        claimed = await run_sync(registry.claim, lease_id, "evaluation_run", _worker_owner_id, 30)
        if claimed:
            break
        current = await _read_run_payload(run_id)
        if current is None or current.get("status") in {"completed", "completed_with_warnings", "failed"}:
            return
        await asyncio.sleep(5)
    if not claimed:
        return
    heartbeat_task = asyncio.create_task(_heartbeat_lease(lease_id, 30))
    try:
        async with _get_run_lock(run_id):
            payload = await _read_run_payload(run_id)
            if payload is None:
                return
            payload["status"] = "running"
            payload["recovery"] = None
            await _write_run_payload(run_id, payload)

        inference_warnings, adapter_merge = await _populate_inference_outputs(request, case_payloads, run_id)
        metrics, failed_cases = _compute_metrics(request.scenario, case_payloads)
        status = "completed_with_warnings" if inference_warnings else "completed"

        async with _get_run_lock(run_id):
            payload = await _read_run_payload(run_id) or payload

            payload["status"] = status
            payload["finetuned_model"] = request.finetuned_model
            payload["adapter_merge"] = adapter_merge
            payload["execution"] = {
                "base_backend": "huggingface" if adapter_merge else request.backend,
                "finetuned_backend": (adapter_merge or {}).get("backend") or request.backend,
                "dynamic_adapter": bool(adapter_merge and request.adapter_path),
                "response_format": "json" if request.scenario == "structured_extraction" else None,
            }
            payload["warnings"] = inference_warnings
            payload["base_outputs"] = [case.get("base_output") for case in case_payloads]
            payload["finetuned_outputs"] = [case.get("finetuned_output") for case in case_payloads]
            payload["cases"] = case_payloads
            payload["metrics"] = metrics
            payload["failed_cases"] = failed_cases

            await _write_run_payload(run_id, payload)

        persistence_warning = _persist_evaluation_link(request.training_task_id, run_id)
        if persistence_warning:
            async with _get_run_lock(run_id):
                payload = await _read_run_payload(run_id) or payload
                payload.setdefault("warnings", []).append(persistence_warning)
                payload["status"] = "completed_with_warnings"
                await _write_run_payload(run_id, payload)

        # 抛出后台裁判任务
        if request.scenario == "qa_assistant" and request.judge_model:
            asyncio.create_task(_run_judge_task(run_id, request.judge_model, request.backend, request.scenario, force_rejudge=False))
        elif run_id in _run_events:
            _run_events[run_id].set()

    except Exception as exc:
        async with _get_run_lock(run_id):
            payload = await _read_run_payload(run_id)
            if payload is not None:
                payload["status"] = "failed"
                payload["error"] = str(exc)
                await _write_run_payload(run_id, payload)
    finally:
        heartbeat_task.cancel()
        await asyncio.gather(heartbeat_task, return_exceptions=True)
        await run_sync(registry.release, lease_id, _worker_owner_id)


@router.get("/runs")
async def list_evaluation_runs():
    registry = _release_registry()
    await run_sync(registry.migrate_json_directory, "evaluation", _evaluation_dir(), "eval_*.json")
    runs = []
    for payload in await run_sync(registry.list, "evaluation"):
        runs.append({
            "run_id": payload.get("run_id"),
            "status": payload.get("status"),
            "scenario": payload.get("scenario"),
            "base_model": payload.get("base_model"),
            "created_at": payload.get("created_at"),
        })
    runs.sort(key=lambda x: x.get("created_at") or "", reverse=True)
    return runs


@router.post("/runs")
async def create_evaluation_run(request: EvaluationRunRequest, background_tasks: BackgroundTasks):
    request = _resolve_evaluation_request(request)
    if (
        request.run_inference
        and request.adapter_path
        and not request.finetuned_model
        and not request.auto_merge_adapter
    ):
        raise HTTPException(
            status_code=400,
            detail="关闭 Adapter 动态挂载后必须提供已合并的 finetuned_model",
        )
    if request.cases:
        cases = request.cases
        evaluation_source = "manual_cases"
    elif request.evaluation_snapshot_path:
        snapshot_path = Path(request.evaluation_snapshot_path)
        from training_engine.reporter import hash_path

        actual_hash = hash_path(snapshot_path)
        if request.evaluation_snapshot_hash and actual_hash != request.evaluation_snapshot_hash:
            raise HTTPException(status_code=409, detail="训练测试快照内容已变化，拒绝运行不可复现评估")
        cases = _load_cases_from_file(snapshot_path, request.max_cases)
        evaluation_source = "training_held_out_snapshot"
    else:
        cases = _load_cases_from_dataset(request.test_dataset_id, request.max_cases)
        evaluation_source = "independent_dataset"
    if not cases:
        raise HTTPException(status_code=400, detail="评估样本为空，请选择有效测试数据集或填写单条测试样本")
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
        "training_task_id": request.training_task_id,
        "release_id": request.release_id,
        "adapter_merge": None,
        "test_dataset_id": request.test_dataset_id,
        "evaluation_snapshot_path": request.evaluation_snapshot_path,
        "evaluation_snapshot_hash": request.evaluation_snapshot_hash,
        "artifact_digest": request.artifact_digest,
        "data_provenance": {
            "source": evaluation_source,
            "isolated_from_training": evaluation_source in {
                "training_held_out_snapshot",
                "independent_dataset",
            },
        },
        "backend": request.backend,
        "system_prompt": request.system_prompt,
        "run_inference": request.run_inference,
        "reproducibility": {
            "prompt_template_hash": _prompt_template_hash(request.scenario, request.system_prompt),
            "prompt_builder_version": "evaluation_prompt_v2",
            "backend": request.backend,
            "judge_model": request.judge_model,
        },
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

    await _write_run_payload(run_id, payload)

    background_tasks.add_task(_run_evaluation_task, request, run_id, case_payloads)

    return payload


@router.get("/runs/{run_id}")
async def get_evaluation_run(run_id: str):
    async with _get_run_lock(run_id):
        payload = await _read_run_payload(run_id)
        if payload is None:
            raise HTTPException(status_code=404, detail="评估任务不存在")
        return payload


def _request_from_run_payload(payload: dict[str, Any]) -> EvaluationRunRequest:
    options = payload.get("inference_options") or {}
    reproducibility = payload.get("reproducibility") or {}
    return EvaluationRunRequest(
        scenario=payload.get("scenario") or "qa_assistant",
        base_model=payload.get("base_model") or "",
        finetuned_model=payload.get("finetuned_model"),
        adapter_path=payload.get("adapter_path"),
        training_task_id=payload.get("training_task_id"),
        release_id=payload.get("release_id"),
        system_prompt=payload.get("system_prompt"),
        auto_merge_adapter=bool(options.get("auto_merge_adapter", True)),
        test_dataset_id=payload.get("test_dataset_id"),
        evaluation_snapshot_path=payload.get("evaluation_snapshot_path"),
        evaluation_snapshot_hash=payload.get("evaluation_snapshot_hash"),
        artifact_digest=payload.get("artifact_digest"),
        cases=[EvaluationCase(**case) for case in payload.get("cases", [])],
        backend=payload.get("backend") or "ollama",
        run_inference=bool(payload.get("run_inference", True)),
        max_tokens=int(options.get("max_tokens", 512)),
        temperature=float(options.get("temperature", 0.2)),
        max_cases=int(options.get("max_cases", 20)),
        judge_model=reproducibility.get("judge_model"),
    )


async def recover_evaluation_runs_after_restart() -> dict[str, int]:
    """Resume durable runs that were pending or interrupted by process exit."""
    registry = _release_registry()
    await run_sync(registry.migrate_json_directory, "evaluation", _evaluation_dir(), "eval_*.json")
    scheduled = 0
    failed = 0
    for payload in await run_sync(registry.list, "evaluation", 5000):
        if payload.get("status") not in {"pending", "running", "recovering"}:
            continue
        run_id = str(payload.get("run_id") or "")
        if not run_id:
            continue
        try:
            request = _request_from_run_payload(payload)
            case_payloads = payload.get("cases") or []
            payload["status"] = "recovering"
            payload.setdefault("recovery_history", []).append({
                "scheduled_at": datetime.now().isoformat(),
                "reason": "process_restart",
            })
            await _write_run_payload(run_id, payload)
            asyncio.create_task(_run_evaluation_task(request, run_id, case_payloads))
            scheduled += 1
        except Exception as exc:
            payload["status"] = "failed"
            payload["error"] = f"启动恢复失败: {exc}"
            await _write_run_payload(run_id, payload)
            failed += 1
    return {"scheduled": scheduled, "failed": failed}


@router.post("/runs/{run_id}/retry")
async def retry_evaluation_run(run_id: str, background_tasks: BackgroundTasks):
    """Resume a failed/interrupted evaluation while reusing completed case outputs."""
    async with _get_run_lock(run_id):
        payload = await _read_run_payload(run_id)
        if payload is None:
            raise HTTPException(status_code=404, detail="评估任务不存在")
        if payload.get("status") in {"pending", "running"}:
            raise HTTPException(status_code=409, detail="评估任务正在运行")
        request = _request_from_run_payload(payload)
        case_payloads = payload.get("cases") or []
        payload["status"] = "pending"
        payload["error"] = None
        payload.setdefault("retry_history", []).append({
            "requested_at": datetime.now().isoformat(),
        })
        await _write_run_payload(run_id, payload)
    background_tasks.add_task(_run_evaluation_task, request, run_id, case_payloads)
    return payload


@router.get("/runs/{run_id}/stream")
async def stream_evaluation_run(run_id: str):
    """SSE endpoint for streaming evaluation progress updates."""
    if await _read_run_payload(run_id) is None:
        raise HTTPException(status_code=404, detail="评估任务不存在")

    async def event_generator():
        last_cases_str = ""
        event = _run_events.setdefault(run_id, asyncio.Event())

        try:
            while True:
                try:
                    async with _get_run_lock(run_id):
                        payload = await _read_run_payload(run_id)
                        if payload is None:
                            break
                except Exception:
                    await asyncio.sleep(1.0)
                    continue

                status = payload.get("status")
                cases = payload.get("cases", [])
                cases_str = json.dumps(cases, ensure_ascii=False)

                if cases_str != last_cases_str:
                    yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
                    last_cases_str = cases_str

                if status in ("completed", "completed_with_warnings", "failed"):
                    if cases_str == last_cases_str:
                        yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
                    break

                event.clear()
                with suppress(TimeoutError):
                    await asyncio.wait_for(event.wait(), timeout=3.0)
        finally:
            _run_events.pop(run_id, None)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )


@router.post("/runs/{run_id}/judge")
async def trigger_rejudge(run_id: str, request: JudgeRequest, background_tasks: BackgroundTasks):
    """独立的判卷触发接口，随时重置裁判打分"""
    async with _get_run_lock(run_id):
        payload = await _read_run_payload(run_id)
        if payload is None:
            raise HTTPException(status_code=404, detail="评估任务不存在")

        if payload.get("scenario") != "qa_assistant":
            raise HTTPException(status_code=400, detail="只有 qa_assistant 场景支持模型判卷")

        if payload.get("status") in ("running", "pending"):
            raise HTTPException(status_code=400, detail="任务仍在运行中，无法触发裁判模型。")

        payload["status"] = "running"
        await _write_run_payload(run_id, payload)

    if run_id in _run_events:
        _run_events[run_id].set()

    background_tasks.add_task(_run_judge_task, run_id, request.judge_model, request.backend, "qa_assistant", True)
    return {"message": "裁判模型后台任务已启动", "run_id": run_id}


@router.post("/runs/{run_id}/score")
async def score_evaluation_case(run_id: str, request: EvaluationScoreRequest):
    async with _get_run_lock(run_id):
        def apply_score(payload: dict[str, Any]) -> dict[str, Any]:
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
            return payload

        payload = await _mutate_run_payload(run_id, apply_score)
        if payload is None:
            raise HTTPException(status_code=404, detail="评估任务不存在")
        return payload
