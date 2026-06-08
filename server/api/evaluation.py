"""Evaluation API for comparing base and fine-tuned model outputs."""

from __future__ import annotations

import asyncio
import json
import uuid
import re
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Literal
from contextlib import asynccontextmanager
import aiofiles

from fastapi import APIRouter, BackgroundTasks, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from core.config import get_settings

router = APIRouter()

class RefCountedLock:
    def __init__(self):
        self.lock = asyncio.Lock()
        self.count = 0

_run_locks: dict[str, RefCountedLock] = {}
_run_events: dict[str, asyncio.Event] = {}

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
    auto_merge_adapter: bool = True
    test_dataset_id: str | None = None
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
    """Run batch inference call directly via the ModelScheduler."""
    from api.inference.scheduler import get_scheduler
    from api.inference.backends.base import GenerationConfig

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
        except Exception as exc:
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
    for p, b_out, f_out, e_out in zip(prompts, base_outputs, finetuned_outputs, expected_outputs):
        judge_prompts.append(f"""请作为一名严谨的大模型评估专家，对两个模型的回答质量进行对比。
原始问题：
{p}

参考答案：
{e_out or "无"}

基础模型回答：
{b_out}

微调模型回答：
{f_out}

请评估“微调模型”相较于“基础模型”是否更好地回答了问题（或者在没有基础模型时，微调模型自身是否回答完美）。
只允许输出三个单词之一，不要有任何其他字符：
good - 微调模型明显更好，或完美回答了问题
neutral - 两者差不多，或者各有千秋
bad - 微调模型明显更差，或者存在严重事实错误

输出：""")

    try:
        results = await run_model_inference_batch_with_retry(
            max_retries=1,
            model=judge_model,
            prompts=judge_prompts,
            backend=backend,
            max_tokens=10,
            temperature=0.1,
        )
        scores: list[Literal["good", "neutral", "bad"]] = []
        for result in results:
            result_lower = result.strip().lower()
            if re.search(r'\bgood\b', result_lower):
                scores.append("good")
            elif re.search(r'\bbad\b', result_lower):
                scores.append("bad")
            else:
                scores.append("neutral")
        return scores
    except Exception as exc:
        raise RuntimeError(str(exc))
        return "neutral"
    except Exception:
        return "neutral"


async def _flush_progress(run_id: str, case_payloads: list[dict[str, Any]]):
    """Safely flush current cases to disk during an ongoing run."""
    try:
        async with _get_run_lock(run_id):
            path = _run_path(run_id)
            if not path.exists():
                return
            async with aiofiles.open(path, "r", encoding="utf-8") as f:
                payload = json.loads(await f.read())
            payload["cases"] = case_payloads
            async with aiofiles.open(path, "w", encoding="utf-8") as f:
                await f.write(json.dumps(payload, ensure_ascii=False, indent=2))
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
    finetuned_backend = request.backend
    lora_adapter = None

    if request.run_inference and not finetuned_model and request.adapter_path:
        finetuned_model = request.base_model
        finetuned_backend = "huggingface"
        lora_adapter = request.adapter_path
        request.backend = "huggingface" # 强制基础模型也使用 HuggingFace 保证对比公平性
        warnings.append("已采用动态加载方式挂载 adapter，并使用 HuggingFace 后端进行基础/微调模型评估。")
        adapter_merge = {
            "merged_model_path": request.base_model,
            "adapter_path": request.adapter_path,
            "backend": "huggingface"
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
                prompts = [_build_prompt(c, request.scenario) for c in unprocessed]
                try:
                    outputs = await run_model_inference_batch_with_retry(
                        max_retries=2,
                        model=request.base_model,
                        prompts=prompts,
                        backend=request.backend,
                        max_tokens=request.max_tokens,
                        temperature=request.temperature,
                        response_format=response_format,
                    )
                    for c, out in zip(unprocessed, outputs):
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
                    prompts = [_build_prompt(c, request.scenario) for c in unprocessed]
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
                        for c, out in zip(unprocessed, outputs):
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
    try:
        path = _run_path(run_id)
        if not path.exists():
            return

        async with _get_run_lock(run_id):
            async with aiofiles.open(path, "r", encoding="utf-8") as f:
                payload = json.loads(await f.read())

            payload["status"] = "running"
            async with aiofiles.open(path, "w", encoding="utf-8") as f:
                await f.write(json.dumps(payload, ensure_ascii=False, indent=2))
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
                            prompts.append(_build_prompt(case, scenario))
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
                        for i, score in zip(unprocessed_indices, scores):
                            case_payloads[i]["human_score"] = {
                                "case_index": i,
                                "score": score,
                                "notes": "LLM Auto Evaluated",
                                "updated_at": datetime.now().isoformat(),
                            }
                    except Exception as exc:
                        warnings.append(f"LLM 裁判批处理执行失败：{exc}")

                    # Incremental flush
                    await _flush_progress(run_id, case_payloads)

            chunk_indices_list = [list(range(i, min(i+batch_size, len(case_payloads)))) for i in range(0, len(case_payloads), batch_size)]
            await asyncio.gather(*(evaluate_batch_judge(idx_list) for idx_list in chunk_indices_list))

        async with _get_run_lock(run_id):
            async with aiofiles.open(path, "r", encoding="utf-8") as f:
                payload = json.loads(await f.read())
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
            async with aiofiles.open(path, "w", encoding="utf-8") as f:
                await f.write(json.dumps(payload, ensure_ascii=False, indent=2))
        if run_id in _run_events:
            _run_events[run_id].set()

    except Exception as exc:
        async with _get_run_lock(run_id):
            if path.exists():
                async with aiofiles.open(path, "r", encoding="utf-8") as f:
                    payload = json.loads(await f.read())
                payload["status"] = "failed"
                payload["error"] = f"裁判引擎执行异常: {str(exc)}"
                async with aiofiles.open(path, "w", encoding="utf-8") as f:
                    await f.write(json.dumps(payload, ensure_ascii=False, indent=2))
        if run_id in _run_events:
            _run_events[run_id].set()


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


async def _run_evaluation_task(request: EvaluationRunRequest, run_id: str, case_payloads: list[dict[str, Any]]):
    try:
        async with _get_run_lock(run_id):
            async with aiofiles.open(_run_path(run_id), "r", encoding="utf-8") as f:
                payload = json.loads(await f.read())
            payload["status"] = "running"
            async with aiofiles.open(_run_path(run_id), "w", encoding="utf-8") as f:
                await f.write(json.dumps(payload, ensure_ascii=False, indent=2))

        inference_warnings, adapter_merge = await _populate_inference_outputs(request, case_payloads, run_id)
        metrics, failed_cases = _compute_metrics(request.scenario, case_payloads)
        status = "completed_with_warnings" if inference_warnings else "completed"

        async with _get_run_lock(run_id):
            async with aiofiles.open(_run_path(run_id), "r", encoding="utf-8") as f:
                payload = json.loads(await f.read())

            payload["status"] = status
            payload["finetuned_model"] = request.finetuned_model or (adapter_merge or {}).get("merged_model_path")
            payload["adapter_merge"] = adapter_merge
            payload["warnings"] = inference_warnings
            payload["base_outputs"] = [case.get("base_output") for case in case_payloads]
            payload["finetuned_outputs"] = [case.get("finetuned_output") for case in case_payloads]
            payload["cases"] = case_payloads
            payload["metrics"] = metrics
            payload["failed_cases"] = failed_cases

            async with aiofiles.open(_run_path(run_id), "w", encoding="utf-8") as f:
                await f.write(json.dumps(payload, ensure_ascii=False, indent=2))

        # 抛出后台裁判任务
        if request.scenario == "qa_assistant" and request.judge_model:
            asyncio.create_task(_run_judge_task(run_id, request.judge_model, request.backend, request.scenario, force_rejudge=False))
        elif run_id in _run_events:
            _run_events[run_id].set()

    except Exception as exc:
        async with _get_run_lock(run_id):
            async with aiofiles.open(_run_path(run_id), "r", encoding="utf-8") as f:
                payload = json.loads(await f.read())
            payload["status"] = "failed"
            payload["error"] = str(exc)
            async with aiofiles.open(_run_path(run_id), "w", encoding="utf-8") as f:
                await f.write(json.dumps(payload, ensure_ascii=False, indent=2))


@router.get("/runs")
async def list_evaluation_runs():
    eval_dir = _evaluation_dir()
    runs = []
    for path in eval_dir.glob("*.json"):
        try:
            async with aiofiles.open(path, encoding="utf-8") as f:
                payload = json.loads(await f.read())
                runs.append({
                    "run_id": payload.get("run_id"),
                    "status": payload.get("status"),
                    "scenario": payload.get("scenario"),
                    "base_model": payload.get("base_model"),
                    "created_at": payload.get("created_at"),
                })
        except Exception:
            continue
    runs.sort(key=lambda x: x.get("created_at") or "", reverse=True)
    return runs


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

    async with aiofiles.open(_run_path(run_id), "w", encoding="utf-8") as f:
        await f.write(json.dumps(payload, ensure_ascii=False, indent=2))

    background_tasks.add_task(_run_evaluation_task, request, run_id, case_payloads)

    return payload


@router.get("/runs/{run_id}")
async def get_evaluation_run(run_id: str):
    path = _run_path(run_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail="评估任务不存在")
    async with _get_run_lock(run_id):
        async with aiofiles.open(path, encoding="utf-8") as f:
            return json.loads(await f.read())


@router.get("/runs/{run_id}/stream")
async def stream_evaluation_run(run_id: str):
    """SSE endpoint for streaming evaluation progress updates."""
    path = _run_path(run_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail="评估任务不存在")

    async def event_generator():
        last_cases_str = ""
        event = _run_events.setdefault(run_id, asyncio.Event())

        try:
            while True:
                if not path.exists():
                    break

                try:
                    async with _get_run_lock(run_id):
                        async with aiofiles.open(path, "r", encoding="utf-8") as f:
                            payload = json.loads(await f.read())
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
                try:
                    await asyncio.wait_for(event.wait(), timeout=3.0)
                except asyncio.TimeoutError:
                    pass
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
    path = _run_path(run_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail="评估任务不存在")

    async with _get_run_lock(run_id):
        async with aiofiles.open(path, encoding="utf-8") as f:
            payload = json.loads(await f.read())

        if payload.get("scenario") != "qa_assistant":
            raise HTTPException(status_code=400, detail="只有 qa_assistant 场景支持模型判卷")

        if payload.get("status") in ("running", "pending"):
            raise HTTPException(status_code=400, detail="任务仍在运行中，无法触发裁判模型。")

        payload["status"] = "running"
        async with aiofiles.open(path, "w", encoding="utf-8") as f:
            await f.write(json.dumps(payload, ensure_ascii=False, indent=2))

    if run_id in _run_events:
        _run_events[run_id].set()

    background_tasks.add_task(_run_judge_task, run_id, request.judge_model, request.backend, "qa_assistant", True)
    return {"message": "裁判模型后台任务已启动", "run_id": run_id}


@router.post("/runs/{run_id}/score")
async def score_evaluation_case(run_id: str, request: EvaluationScoreRequest):
    async with _get_run_lock(run_id):
        path = _run_path(run_id)
        if not path.exists():
            raise HTTPException(status_code=404, detail="评估任务不存在")
        async with aiofiles.open(path, encoding="utf-8") as f:
            payload = json.loads(await f.read())

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

        async with aiofiles.open(path, "w", encoding="utf-8") as f:
            await f.write(json.dumps(payload, ensure_ascii=False, indent=2))

        return payload
