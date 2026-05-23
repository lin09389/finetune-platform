"""
推理模块路由 - 参考 Ollama server/routes.go 设计模式
"""
import logging
import time
import json
from typing import Any

def _fast_dumps(data: dict) -> str:
    return json.dumps(data, ensure_ascii=False, separators=(", ", ": "))

import psutil

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse

from api.errors import (
    APIError,
    InvalidInputError,
    MaliciousInputError,
)
from api.inference.backends.base import GenerationConfig, GenerationResult
from api.inference.circuit_breaker import CircuitBreakerOpenError, get_circuit_breaker
from api.inference.scheduler import BackendType, get_scheduler
from api.types import (
    BackendInfo,
    BackendListResponse,
    BackendSwitchRequest,
    ChatRequest,
    ChatResponse,
    GenerateRequest,
    GenerateResponse,
    KnowledgeSource,
)
from api.inference.pipeline import get_local_inference_pipeline
from core.config import get_settings
from core.logging import log_inference_event
from core.offline_cache import get_offline_cache
from core.performance import get_performance_monitor, PerformanceMetrics, StreamingMetrics
from core.utils import get_device_info as get_runtime_device_info
from core.kv_cache import get_kv_cache

logger = logging.getLogger(__name__)

router = APIRouter()

logger.info("=== Loading inference routes module ===")

settings = get_settings()
circuit_breaker = get_circuit_breaker()

PROMPT_INJECTION_PATTERNS = [
    r"ignore\s+(all\s+)?previous\s+instructions?",
    r"ignore\s+(all\s+)?(the\s+)?above",
    r"disregard\s+(all\s+)?previous",
    r"forget\s+(all\s+)?(previous\s+)?instructions?",
    r"you\s+are\s+now\s+",
    r"new\s+instructions?:",
    r"system:\s*you\s+are",
    r"<\|im_start\|>system",
    r"jailbreak",
    r"dan\s+mode",
    r"developer\s+mode",
    r"sudo\s+mode",
]

MAX_MESSAGE_LENGTH = 10000
MAX_MESSAGES_COUNT = 100
NO_THINK_SYSTEM_PROMPT = "请直接给出最终回答，不要输出思考过程、推理步骤或草稿。"


def _current_backend_name(explicit_backend: str | None) -> str:
    scheduler = get_scheduler()
    return explicit_backend or scheduler.get_stats().get("default_backend", "huggingface")


def _resource_snapshot() -> dict[str, float]:
    runtime_info = get_runtime_device_info(use_cache=False)
    memory = psutil.virtual_memory()
    return {
        "vram_used_gb": float(runtime_info.get("memory_allocated", 0.0) or 0.0),
        "memory_used_gb": memory.used / (1024 ** 3),
        "memory_peak_gb": memory.used / (1024 ** 3),
        "cpu_percent": psutil.cpu_percent(interval=None),
        "gpu_util_percent": 0.0,
    }


def _record_request_metrics(
    *,
    backend_name: str,
    model_id: str,
    result: GenerationResult,
    first_token_latency_ms: float | None = None,
    load_duration_ms: float = 0.0,
    queue_wait_ms: float = 0.0,
    retry_count: int = 0,
    fallback_used: bool = False,
    cache_hit: bool = False,
    cancelled: bool = False,
    error_type: str | None = None,
) -> None:
    if not result.latency_ms:
        return

    snapshot = _resource_snapshot()
    tps = (result.tokens_generated / (result.latency_ms / 1000.0)) if result.latency_ms > 0 else 0.0
    get_performance_monitor().record(
        PerformanceMetrics(
            tokens_per_second=tps,
            latency_ms=result.latency_ms,
            first_token_latency_ms=first_token_latency_ms if first_token_latency_ms is not None else result.latency_ms,
            vram_used_gb=snapshot["vram_used_gb"],
            model_id=model_id,
            engine_type=backend_name,
            batch_size=1,
            prompt_tokens=result.prompt_tokens,
            completion_tokens=result.tokens_generated,
            total_tokens=result.total_tokens,
            load_duration_ms=load_duration_ms,
            queue_wait_ms=queue_wait_ms,
            memory_used_gb=snapshot["memory_used_gb"],
            memory_peak_gb=snapshot["memory_peak_gb"],
            cpu_percent=snapshot["cpu_percent"],
            gpu_util_percent=snapshot["gpu_util_percent"],
            retry_count=retry_count,
            fallback_used=fallback_used,
            cache_hit=cache_hit,
            cancelled=cancelled,
            error_type=error_type,
        )
    )


def _should_use_batching(backend_name: str) -> bool:
    settings = get_settings()
    return settings.enable_batching and backend_name != BackendType.CLOUD.value


def _should_use_offline_cache(backend_name: str, temperature: float, stream: bool = False) -> bool:
    return backend_name != BackendType.CLOUD.value and not stream and temperature <= 0.3


def _should_use_kv_cache(temperature: float) -> bool:
    """Deterministic requests (temperature near 0) can use the fast in-memory KV cache."""
    return temperature <= 0.1


_inference_kv_cache = get_kv_cache(
    "inference",
    max_size=256 * 1024 * 1024,  # 256 MB
    max_entries=2000,
    default_ttl=600.0,  # 10 min
)


def _build_generate_cache_key(request: GenerateRequest, backend_name: str) -> str:
    return get_offline_cache().build_key(
        "generate",
        {
            "backend": backend_name,
            "model": request.model,
            "prompt": request.prompt,
            "temperature": request.options.temperature,
            "top_p": request.options.top_p,
            "top_k": request.options.top_k,
            "max_tokens": request.options.max_tokens,
            "stop": request.options.stop or [],
        },
    )


def _build_chat_cache_key(request: ChatRequest, backend_name: str) -> str:
    return get_offline_cache().build_key(
        "chat",
        {
            "backend": backend_name,
            "model": request.model,
            "messages": [
                {
                    "role": msg.role.value if hasattr(msg.role, "value") else msg.role,
                    "content": msg.content,
                }
                for msg in request.messages
            ],
            "temperature": request.options.temperature,
            "top_p": request.options.top_p,
            "top_k": request.options.top_k,
            "max_tokens": request.options.max_tokens,
            "stop": request.options.stop or [],
        },
    )


def detect_prompt_injection(text: str) -> bool:
    """检测潜在的 Prompt 注入"""
    import re
    text_lower = text.lower()
    for pattern in PROMPT_INJECTION_PATTERNS:
        if re.search(pattern, text_lower, re.IGNORECASE):
            logger.warning(f"检测到潜在的 Prompt 注入: {pattern}")
            return True
    return False


def sanitize_input(text: str) -> str:
    """清理输入文本"""
    if not text:
        return text
    text = text.strip()
    if len(text) > MAX_MESSAGE_LENGTH:
        text = text[:MAX_MESSAGE_LENGTH]
    return text


def build_attachment_context(attachments: list) -> str:
    """Build a lightweight attachment context block for prompt injection."""
    if not attachments:
        return ""

    lines: list[str] = ["Attached context:"]
    for attachment in attachments:
        attachment_type = getattr(attachment, "type", "text")
        name = getattr(attachment, "name", "attachment")
        mime_type = getattr(attachment, "mime_type", "")
        content = getattr(attachment, "content", "") or ""

        if attachment_type == "image":
            raise InvalidInputError(
                "attachments",
                "Image attachments are not supported by the local inference endpoint.",
            )

        snippet = sanitize_input(content)
        if len(snippet) > 2000:
            snippet = snippet[:2000] + "..."

        descriptor = f"{name} ({mime_type})" if mime_type else name
        lines.append(f"[{descriptor}]\n{snippet or 'No readable text content provided.'}")

    return "\n\n".join(lines)


def enforce_fast_ollama_response(
    messages: list[dict[str, str]],
    model_name: str | None,
    fast_mode: bool,
) -> list[dict[str, str]]:
    """For Qwen3-like local models, force concise non-thinking output by default."""
    if not fast_mode:
        return messages

    if not model_name:
        return messages

    lowered = model_name.lower()
    if "qwen3" not in lowered:
        return messages

    patched = [dict(message) for message in messages]
    if patched and patched[0].get("role") == "system":
        existing = patched[0].get("content", "")
        if NO_THINK_SYSTEM_PROMPT not in existing:
            patched[0]["content"] = f"{NO_THINK_SYSTEM_PROMPT}\n\n{existing}".strip()
    else:
        patched.insert(0, {"role": "system", "content": NO_THINK_SYSTEM_PROMPT})
    return patched


def _message_role_value(message) -> str:
    role = getattr(message, "role", "user")
    return role.value if hasattr(role, "value") else str(role)


def _model_to_dict(model: Any) -> dict[str, Any]:
    if hasattr(model, "model_dump"):
        return model.model_dump()
    if hasattr(model, "dict"):
        return model.dict()
    return dict(model)


def _inject_system_prompt_message(request: ChatRequest, system_prompt: str) -> None:
    if not system_prompt:
        return

    from api.types import Message, MessageRole

    if request.messages and _message_role_value(request.messages[0]) == "system":
        existing = request.messages[0].content or ""
        if system_prompt not in existing:
            request.messages[0].content = f"{system_prompt}\n\n{existing}".strip()
        return

    request.messages.insert(
        0,
        Message(role=MessageRole.SYSTEM, content=system_prompt),
    )


def _inject_system_prompt_dict(messages: list[dict[str, str]], system_prompt: str) -> list[dict[str, str]]:
    if not system_prompt:
        return messages

    if messages and messages[0].get("role") == "system":
        existing = messages[0].get("content", "")
        if system_prompt not in existing:
            messages[0]["content"] = f"{system_prompt}\n\n{existing}".strip()
        return messages

    return [{"role": "system", "content": system_prompt}, *messages]


def _format_deep_context(active_context: dict[str, Any] | None, explicit_context: list[dict[str, Any]] | None) -> str:
    sections: list[str] = []
    if active_context:
        file_path = active_context.get("file_path") or "unknown"
        cursor = active_context.get("cursor") or {}
        selection = active_context.get("selection") or {}
        lines = [
            f"Current file: {file_path}",
            f"Cursor: line {cursor.get('line', 1)}, column {cursor.get('column', 1)}",
        ]
        selected_text = str(selection.get("text") or "").strip()
        if selected_text:
            lines.append(
                "Selected code:\n```text\n"
                + selected_text[:4000]
                + "\n```"
            )
        else:
            preview = str(active_context.get("content_preview") or "").strip()
            if preview:
                lines.append("File preview:\n```text\n" + preview[:4000] + "\n```")
        sections.append("\n".join(lines))
    mention_lines = []
    for item in explicit_context or []:
        label = item.get("label") or item.get("path") or "context"
        kind = item.get("type") or "context"
        path = item.get("path")
        line = item.get("line")
        location = f"{path or ''}{':' + str(line) if line else ''}".strip()
        mention_lines.append(f"- @{label} ({kind}) {location}".strip())
        content = str(item.get("content") or "").strip()
        if content:
            mention_lines.append(f"  context: {content[:1200]}")
    if mention_lines:
        sections.append("Explicit @ context:\n" + "\n".join(mention_lines))
    if not sections:
        return ""
    return "Deep Context Retrieval:\n" + "\n\n".join(sections)


async def _build_unified_context_payload(
    request: ChatRequest,
    last_user_message: str | None,
    base_system_prompt: str,
) -> tuple[
    str,
    list[KnowledgeSource] | None,
    dict[str, Any] | None,
    Any | None,
    Any | None,
]:
    from api.types import MemoryContextInfo, UnifiedContextInfo
    from context.builder import get_context_builder
    from context.budget import ContextBuildOptions

    max_context_tokens = max(
        512,
        int(request.options.num_ctx or 0)
        - int(request.options.max_tokens or 0)
        - int(request.options.num_keep or 0),
    )
    context_options = ContextBuildOptions(
        use_memory=request.memory.enabled and request.memory.auto_retrieve,
        use_knowledge=request.knowledge.use_knowledge,
        use_project_context=request.context.use_context,
        max_context_tokens=max_context_tokens,
        reserved_output_tokens=int(request.options.max_tokens or 0),
        max_total_sources=10,
        memory_top_k=request.memory.top_k,
        memory_include_types=request.memory.include_types,
        knowledge_collection_id=request.knowledge.collection_id,
        knowledge_top_k=request.knowledge.top_k,
        knowledge_auto_retrieve=request.knowledge.auto_retrieve,
        project_path=request.context.project_path,
        project_max_tokens=request.context.max_context_length,
    )

    unified_context = await get_context_builder().build(
        query=last_user_message or "",
        user_id=request.session.user_id,
        session_id=request.session.session_id,
        options=context_options,
    )

    system_prompt = base_system_prompt
    knowledge_sources_response = None
    retrieval_info = None
    memory_context_info = None
    unified_context_info = None

    if unified_context.total_sources > 0:
        system_prompt = unified_context.build_system_prompt(
            base_prompt=system_prompt or "你是一个有帮助的 AI 助手。"
        )

        if unified_context.knowledge_sources:
            knowledge_sources_response = [
                KnowledgeSource(
                    id=k.id,
                    source=k.source,
                    score=k.score,
                    content_preview=k.content[:100] + "..." if len(k.content) > 100 else k.content,
                )
                for k in unified_context.knowledge_sources
            ]

            retrieval_info = {
                "query": last_user_message,
                "method": "unified",
                "total_results": unified_context.knowledge_count,
                "retrieval_time": unified_context.knowledge_retrieval_time,
            }

        if unified_context.memory_count > 0:
            memory_context_info = MemoryContextInfo(
                retrieved=True,
                sources_count=unified_context.memory_count,
                context_preview=unified_context.context_text[:200] if unified_context.context_text else "",
            )

        context_payload = unified_context.to_dict()
        unified_context_info = UnifiedContextInfo(
            total_sources=unified_context.total_sources,
            memory_count=unified_context.memory_count,
            knowledge_count=unified_context.knowledge_count,
            project_count=unified_context.project_count,
            retrieval_time=unified_context.retrieval_time,
            budget=context_payload.get("budget"),
            warnings=getattr(unified_context, "warnings", None) or None,
            trace=context_payload.get("trace"),
        )

    deep_context_text = _format_deep_context(
        request.context.active_context,
        request.context.explicit_context,
    )
    if deep_context_text:
        try:
            from context.service import get_context_service
            related = get_context_service().expand_deep_context(
                request.context.active_context,
                request.context.explicit_context,
                request.context.project_path,
            )
            if related:
                related_lines = [
                    f"- {item.get('relation')}: {item.get('path')} {':' + str(item.get('line')) if item.get('line') else ''}\n  {str(item.get('content') or '')[:800]}"
                    for item in related
                ]
                deep_context_text = f"{deep_context_text}\n\nDependency topology expansion:\n" + "\n".join(related_lines)
        except Exception:
            logger.debug("failed to expand deep context topology", exc_info=True)
    if deep_context_text:
        system_prompt = f"{system_prompt or '你是一个有帮助的 AI 助手。'}\n\n{deep_context_text}"

    return (
        system_prompt,
        knowledge_sources_response,
        retrieval_info,
        memory_context_info,
        unified_context_info,
    )


@router.post("/generate", response_model=GenerateResponse)
async def generate(request: GenerateRequest):
    """生成文本 - 参考 Ollama /api/generate"""
    if not request.prompt or not request.prompt.strip():
        raise InvalidInputError("prompt", "提示内容不能为空")

    if detect_prompt_injection(request.prompt):
        raise MaliciousInputError()

    request.prompt = sanitize_input(request.prompt)

    scheduler = get_scheduler()
    backend_name = _current_backend_name(request.options.backend)
    leased_model = None
    load_duration_ms = 0.0
    cache_key = _build_generate_cache_key(request, backend_name)
    if _should_use_offline_cache(backend_name, request.options.temperature):
        cached_response = get_offline_cache().get(cache_key)
        if cached_response is not None:
            log_inference_event(
                logger,
                "offline cache hit",
                backend=backend_name,
                model=request.model,
                request_type="generate",
            )
            return GenerateResponse(**cached_response)

    # --- Fast KV cache for deterministic requests ---
    kv_cache_key = f"gen:{cache_key}"
    if _should_use_kv_cache(request.options.temperature):
        kv_hit = _inference_kv_cache.get(kv_cache_key)
        if kv_hit is not None:
            log_inference_event(
                logger,
                "kv cache hit",
                backend=backend_name,
                model=request.model,
                request_type="generate",
                cache_hit=True,
            )
            return GenerateResponse(**kv_hit)

    async def _do_generate():
        nonlocal leased_model, load_duration_ms
        backend = await scheduler.get_backend(backend_name)
        request_config = GenerationConfig(
            max_tokens=request.options.max_tokens,
            temperature=request.options.temperature,
            top_p=request.options.top_p,
            top_k=request.options.top_k,
            repetition_penalty=request.options.repetition_penalty,
            stop_sequences=request.options.stop or [],
        )
        if backend_name != BackendType.CLOUD.value:
            model_path = (
                scheduler.resolve_model_path(request.model, backend_name)
                if hasattr(scheduler, "resolve_model_path")
                else request.model
            )
            if hasattr(scheduler, "acquire_model"):
                leased_model = await scheduler.acquire_model(
                    request.model,
                    model_path,
                    backend_name,
                    num_ctx=request.options.num_ctx,
                    num_batch=request.options.num_batch,
                    max_tokens=request.options.max_tokens,
                )
                if leased_model is None:
                    raise HTTPException(status_code=503, detail=f"模型加载失败: {request.model}")
                load_duration_ms = float(leased_model.metadata.get("load_duration_ms", 0.0) or 0.0)

        if hasattr(backend, "model_name") and request.model:
            backend.model_name = request.model

        if _should_use_batching(backend_name):
            return await get_local_inference_pipeline().submit(
                pipeline_key=f"{backend_name}:{request.model}:generate",
                prompt=request.prompt,
                max_batch_size=min(request.options.num_batch, get_settings().max_batch_size),
                max_wait_ms=get_settings().max_batch_wait_ms,
                timeout=60.0,
                executor=lambda: backend.generate(request.prompt, request_config),
            )

        return await backend.generate(request.prompt, request_config)

    async def _fallback_generate():
        if request.options.backend != "cloud":
            logger.info("本地后端不可用，尝试云端AI降级")
            cloud_request = GenerateRequest(
                prompt=request.prompt,
                model=request.model,
                options=request.options
            )
            cloud_request.options.backend = "cloud"
            scheduler = get_scheduler()
            backend = await scheduler.get_backend("cloud")
            return await backend.generate(
                cloud_request.prompt,
                GenerationConfig(
                    max_tokens=cloud_request.options.max_tokens,
                    temperature=cloud_request.options.temperature,
                    top_p=cloud_request.options.top_p,
                    top_k=cloud_request.options.top_k,
                    repetition_penalty=cloud_request.options.repetition_penalty,
                    stop_sequences=cloud_request.options.stop or [],
                ),
            )
        raise HTTPException(503, "所有后端不可用")

    try:
        result = await circuit_breaker.execute_with_protection(
            backend_name,
            _do_generate,
            _fallback_generate
        )

        if isinstance(result, GenerationResult):
            queue_wait_ms = float(result.metadata.get("queue_wait_ms", 0.0) or 0.0)
            try:
                _record_request_metrics(
                    backend_name=backend_name,
                    model_id=result.model or request.model,
                    result=result,
                    load_duration_ms=load_duration_ms,
                    queue_wait_ms=queue_wait_ms,
                )
            except Exception as metric_err:
                logger.warning(f"记录性能指标失败: {metric_err}")

            response_payload = {
                "model": result.model or request.model,
                "response": result.text,
                "done": result.finish_reason == "stop",
                "usage": {
                    "prompt_tokens": result.prompt_tokens,
                    "completion_tokens": result.tokens_generated,
                    "total_tokens": result.total_tokens,
                },
                "total_duration": result.latency_ms / 1000.0 if result.latency_ms else None,
                "load_duration": load_duration_ms / 1000.0 if load_duration_ms else None,
                "eval_duration": result.latency_ms / 1000.0 if result.latency_ms else None,
            }
            if _should_use_offline_cache(backend_name, request.options.temperature):
                get_offline_cache().set(cache_key, response_payload)
            if _should_use_kv_cache(request.options.temperature):
                _inference_kv_cache.set(kv_cache_key, response_payload)
            log_inference_event(
                logger,
                "local generate completed",
                backend=backend_name,
                model=result.model or request.model,
                ttft_ms=round(result.latency_ms, 2),
                throughput_tps=round((result.tokens_generated / max(result.latency_ms / 1000.0, 0.001)), 2),
                queue_wait_ms=round(queue_wait_ms, 2),
                cache_hit=False,
            )

            return GenerateResponse(
                model=result.model or request.model,
                response=result.text,
                done=result.finish_reason == "stop",
                usage={
                    "prompt_tokens": result.prompt_tokens,
                    "completion_tokens": result.tokens_generated,
                    "total_tokens": result.total_tokens,
                },
                total_duration=result.latency_ms / 1000.0 if result.latency_ms else None,
                load_duration=load_duration_ms / 1000.0 if load_duration_ms else None,
                eval_duration=result.latency_ms / 1000.0 if result.latency_ms else None,
            )

        return result

    except CircuitBreakerOpenError:
        raise HTTPException(503, "服务暂时不可用，请稍后重试")
    except APIError:
        raise
    except Exception as e:
        logger.error(f"生成失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"生成失败: {str(e)}")
    finally:
        if leased_model is not None:
            await scheduler.release_model(request.model)


@router.post("/generate/stream")
async def generate_stream(request: GenerateRequest):
    """流式生成 - 参考 Ollama 流式生成"""
    if not request.prompt or not request.prompt.strip():
        raise InvalidInputError("prompt", "提示内容不能为空")

    if detect_prompt_injection(request.prompt):
        raise MaliciousInputError()

    request.prompt = sanitize_input(request.prompt)

    scheduler = get_scheduler()
    backend_name = _current_backend_name(request.options.backend)
    load_duration_ms = 0.0
    leased_model = None

    async def _do_generate_stream():
        nonlocal leased_model, load_duration_ms
        backend = await scheduler.get_backend(backend_name)
        if backend_name != BackendType.CLOUD.value:
            model_path = (
                scheduler.resolve_model_path(request.model, backend_name)
                if hasattr(scheduler, "resolve_model_path")
                else request.model
            )
            if hasattr(scheduler, "acquire_model"):
                leased_model = await scheduler.acquire_model(
                    request.model,
                    model_path,
                    backend_name,
                    num_ctx=request.options.num_ctx,
                    num_batch=request.options.num_batch,
                    max_tokens=request.options.max_tokens,
                )
                if leased_model is None:
                    raise HTTPException(status_code=503, detail=f"模型加载失败: {request.model}")
                load_duration_ms = float(leased_model.metadata.get("load_duration_ms", 0.0) or 0.0)
        if hasattr(backend, "model_name") and request.model:
            backend.model_name = request.model
        async for chunk in backend.generate_stream(
            request.prompt,
            GenerationConfig(
                max_tokens=request.options.max_tokens,
                temperature=request.options.temperature,
                top_p=request.options.top_p,
                top_k=request.options.top_k,
                repetition_penalty=request.options.repetition_penalty,
                stop_sequences=request.options.stop or [],
                stream=True,
            ),
        ):
            yield chunk

    async def _fallback_generate_stream():
        if request.options.backend != "cloud":
            logger.info("本地后端不可用，尝试云端AI降级 (流式)")
            import copy
            cloud_request = GenerateRequest(
                prompt=request.prompt,
                model=request.model,
                options=copy.deepcopy(request.options)
            )
            cloud_request.options.backend = "cloud"
            scheduler = get_scheduler()
            backend = await scheduler.get_backend("cloud")
            async for chunk in backend.generate_stream(
                cloud_request.prompt,
                GenerationConfig(
                    max_tokens=cloud_request.options.max_tokens,
                    temperature=cloud_request.options.temperature,
                    top_p=cloud_request.options.top_p,
                    top_k=cloud_request.options.top_k,
                    repetition_penalty=cloud_request.options.repetition_penalty,
                    stop_sequences=cloud_request.options.stop or [],
                    stream=True,
                ),
            ):
                yield chunk
        else:
            raise HTTPException(503, "所有后端不可用")

    try:
        async def instrumented_stream():
            started_at = time.time()
            first_token_time = None
            token_chunks = 0
            chunk_latencies: list[float] = []
            last_chunk_at = started_at
            try:
                protected_stream = circuit_breaker.execute_stream_with_protection(
                    backend_name,
                    _do_generate_stream,
                    _fallback_generate_stream
                )
                async for chunk in protected_stream:
                    now = time.time()
                    if first_token_time is None:
                        first_token_time = now
                    else:
                        chunk_latencies.append((now - last_chunk_at) * 1000)
                    last_chunk_at = now
                    token_chunks += 1
                    yield chunk
            finally:
                if first_token_time is not None:
                    try:
                        get_performance_monitor().record_streaming(
                            StreamingMetrics(
                                total_tokens=token_chunks,
                                total_time_ms=(time.time() - started_at) * 1000,
                                first_token_latency_ms=(first_token_time - started_at) * 1000,
                                avg_chunk_latency_ms=sum(chunk_latencies) / max(len(chunk_latencies), 1) if chunk_latencies else 0.0,
                                max_chunk_latency_ms=max(chunk_latencies) if chunk_latencies else 0.0,
                                min_chunk_latency_ms=min(chunk_latencies) if chunk_latencies else 0.0,
                                load_duration_ms=load_duration_ms,
                                model_id=request.model,
                                engine_type=backend_name,
                            )
                        )
                    except Exception as metric_err:
                        logger.warning(f"记录流式性能指标失败: {metric_err}")
                if leased_model is not None:
                    await scheduler.release_model(request.model)

        return StreamingResponse(
            instrumented_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no"
            }
        )

    except CircuitBreakerOpenError:
        raise HTTPException(503, "服务暂时不可用，请稍后重试")
    except APIError:
        raise
    except Exception as e:
        logger.error(f"流式生成失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"流式生成失败: {str(e)}")


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """聊天对话 - 参考 Ollama /api/chat，集成统一上下文管理"""
    import sys
    start_time = time.time()
    print(f"=== NEW /inference/chat called with model: {request.model}, backend: {request.options.backend if request.options else 'None'} ===", file=sys.stderr, flush=True)
    print(f"=== request.options: {request.options} ===", file=sys.stderr, flush=True)
    logger.info(f"=== NEW /inference/chat called with model: {request.model}, backend: {request.options.backend if request.options else 'None'} ===")
    logger.info(f"=== Request messages: {len(request.messages) if request.messages else 0} ===")
    if not request.messages or len(request.messages) == 0:
        raise InvalidInputError("messages", "消息列表不能为空")

    if len(request.messages) > MAX_MESSAGES_COUNT:
        raise InvalidInputError("messages", f"消息数量超过限制（最多 {MAX_MESSAGES_COUNT} 条）")

    for msg in request.messages:
        if not msg.content or not msg.content.strip():
            raise InvalidInputError("messages", "消息内容不能为空")

        if detect_prompt_injection(msg.content):
            raise MaliciousInputError()

        msg.content = sanitize_input(msg.content)

    # Fast mode: cap generated length to reduce latency variance.
    if settings.ollama_fast_mode:
        request.options.max_tokens = min(request.options.max_tokens, settings.ollama_fast_max_tokens)

    system_prompt = request.system_prompt or ""
    knowledge_sources_response = None
    retrieval_info = None
    memory_context_info = None
    unified_context_info = None

    last_user_message = request.get_last_user_message()
    attachment_context = build_attachment_context(request.attachments)
    if attachment_context and request.messages:
        request.messages[-1].content = f"{request.messages[-1].content}\n\n{attachment_context}".strip()
        last_user_message = request.get_last_user_message()

    (
        system_prompt,
        knowledge_sources_response,
        retrieval_info,
        memory_context_info,
        unified_context_info,
    ) = await _build_unified_context_payload(
        request=request,
        last_user_message=last_user_message,
        base_system_prompt=system_prompt,
    )

    _inject_system_prompt_message(request, system_prompt)

    scheduler = get_scheduler()
    backend_name = _current_backend_name(request.options.backend)
    leased_model = None
    load_duration_ms = 0.0

    async def _do_chat():
        nonlocal leased_model, load_duration_ms
        backend = await scheduler.get_backend(backend_name)
        chat_config = GenerationConfig(
            max_tokens=request.options.max_tokens,
            temperature=request.options.temperature,
            top_p=request.options.top_p,
            top_k=request.options.top_k,
            repetition_penalty=request.options.repetition_penalty,
        )

        if backend_name != BackendType.CLOUD.value:
            model_path = (
                scheduler.resolve_model_path(request.model, backend_name)
                if hasattr(scheduler, "resolve_model_path")
                else request.model
            )
            if hasattr(scheduler, "acquire_model"):
                leased_model = await scheduler.acquire_model(
                    request.model,
                    model_path,
                    backend_name,
                    num_ctx=request.options.num_ctx,
                    num_batch=request.options.num_batch,
                    max_tokens=request.options.max_tokens,
                )
                if leased_model is None:
                    raise HTTPException(status_code=503, detail=f"模型加载失败: {request.model}")
                load_duration_ms = float(leased_model.metadata.get("load_duration_ms", 0.0) or 0.0)

        if hasattr(backend, "model_name") and request.model:
            backend.model_name = request.model

        if backend_name == "ollama":
            as_dict_messages = [
                {
                    "role": msg.role.value if hasattr(msg.role, "value") else msg.role,
                    "content": msg.content,
                }
                for msg in request.messages
            ]
            patched_messages = enforce_fast_ollama_response(
                as_dict_messages,
                request.model,
                settings.ollama_fast_mode,
            )
            if patched_messages != as_dict_messages:
                from api.types import Message, MessageRole

                def _to_role(raw_role: str):
                    if raw_role == "system":
                        return MessageRole.SYSTEM
                    if raw_role == "assistant":
                        return MessageRole.ASSISTANT
                    return MessageRole.USER

                request.messages = [
                    Message(role=_to_role(str(message.get("role", "user"))), content=str(message.get("content", "")))
                    for message in patched_messages
                ]
            return await backend.chat(request)
        else:
            messages = [
                {
                    "role": msg.role.value if hasattr(msg.role, "value") else msg.role,
                    "content": msg.content,
                }
                for msg in request.messages
            ]
            if system_prompt and (not messages or messages[0]["role"] != "system"):
                messages = [{"role": "system", "content": system_prompt}, *messages]

            if _should_use_batching(backend_name):
                return await get_local_inference_pipeline().submit(
                    pipeline_key=f"{backend_name}:{request.model}:chat",
                    prompt=messages[-1]["content"] if messages else "",
                    max_batch_size=min(request.options.num_batch, get_settings().max_batch_size),
                    max_wait_ms=get_settings().max_batch_wait_ms,
                    timeout=90.0,
                    executor=lambda: backend.chat(messages, chat_config),
                )

            return await backend.chat(messages, chat_config)

    async def _fallback_chat():
        if request.options.backend != "cloud":
            logger.info("本地后端不可用，尝试云端AI降级 (Chat)")
            import copy
            cloud_request = ChatRequest(
                model=request.model,
                messages=copy.deepcopy(request.messages),
                options=copy.deepcopy(request.options)
            )
            cloud_request.options.backend = "cloud"
            scheduler = get_scheduler()
            backend = await scheduler.get_backend("cloud")
            messages = [
                {
                    "role": msg.role.value if hasattr(msg.role, "value") else msg.role,
                    "content": msg.content,
                }
                for msg in cloud_request.messages
            ]
            if system_prompt and (not messages or messages[0]["role"] != "system"):
                messages = [{"role": "system", "content": system_prompt}, *messages]

            return await backend.chat(
                messages,
                GenerationConfig(
                    max_tokens=cloud_request.options.max_tokens,
                    temperature=cloud_request.options.temperature,
                    top_p=cloud_request.options.top_p,
                    top_k=cloud_request.options.top_k,
                    repetition_penalty=cloud_request.options.repetition_penalty,
                ),
            )
        else:
            raise HTTPException(503, "所有后端不可用")

    try:
        result = await circuit_breaker.execute_with_protection(
            backend_name,
            _do_chat,
            _fallback_chat
        )

        logger.info(f"Chat result type: {type(result)}, isinstance GenerationResult: {isinstance(result, GenerationResult)}")
        if hasattr(result, 'text'):
            logger.info(f"Result text: {result.text[:100] if result.text else 'empty'}...")
        if hasattr(result, 'metadata'):
            logger.info(f"Result metadata: {result.metadata}")

        if isinstance(result, GenerationResult):
            from api.types import Message, MessageRole, TokenUsage
            
            if result.latency_ms:
                try:
                    _record_request_metrics(
                        backend_name=backend_name,
                        model_id=result.model or request.model,
                        result=result,
                        load_duration_ms=load_duration_ms,
                        queue_wait_ms=float(result.metadata.get("queue_wait_ms", 0.0) or 0.0),
                    )
                except Exception as metric_err:
                    logger.warning(f"记录性能指标失败: {metric_err}")
            log_inference_event(
                logger,
                "local chat completed",
                backend=backend_name,
                model=result.model or request.model,
                ttft_ms=round(result.latency_ms, 2),
                throughput_tps=round((result.tokens_generated / max(result.latency_ms / 1000.0, 0.001)), 2),
                queue_wait_ms=round(float(result.metadata.get("queue_wait_ms", 0.0) or 0.0), 2),
                cache_hit=False,
            )

            response = ChatResponse(
                message=Message(
                    role=MessageRole.ASSISTANT,
                    content=result.text
                ),
                model=result.model,
                backend=backend_name,
                done=result.finish_reason == "stop",
                usage=TokenUsage(
                    prompt_tokens=result.prompt_tokens,
                    completion_tokens=result.tokens_generated,
                    total_tokens=result.total_tokens
                ),
                total_duration=result.latency_ms / 1000.0 if result.latency_ms else None,
                load_duration=load_duration_ms / 1000.0 if load_duration_ms else None,
                duration_ms=int(result.latency_ms) if result.latency_ms is not None else None,
                raw_response={
                    "model": result.model,
                    "finish_reason": result.finish_reason,
                    "tokens_generated": result.tokens_generated,
                    "prompt_tokens": result.prompt_tokens,
                    "total_tokens": result.total_tokens,
                    "error": result.metadata.get("error") if result.metadata else None,
                    "metadata": result.metadata or {},
                },
            )
        else:
            response = result

        if knowledge_sources_response and request.knowledge.include_sources:
            from context.knowledge_integration import get_knowledge_integrator
            integrator = get_knowledge_integrator()
            from context.knowledge_integration import KnowledgeSource as KSSource
            sources = [
                KSSource(
                    id=s.id,
                    content=s.content_preview,
                    source=s.source,
                    score=s.score
                )
                for s in knowledge_sources_response
            ]
            response.message.content = integrator.enhance_response_with_sources(
                response=response.message.content,
                sources=sources,
                include_citation=True
            )

        response.knowledge_sources = knowledge_sources_response
        response.retrieval_info = retrieval_info
        response.memory_context = memory_context_info
        response.unified_context = unified_context_info
        if response.duration_ms is None:
            response.duration_ms = int((time.time() - start_time) * 1000)
        if response.raw_response is None:
            response.raw_response = {
                "message": {
                    "role": response.message.role,
                    "content": response.message.content,
                },
                "model": response.model,
                "backend": response.backend,
                "usage": response.usage.model_dump() if hasattr(response.usage, "model_dump") else {},
            }

        if request.memory.enabled and request.memory.auto_extract and last_user_message:
            try:
                from memory.service import extract_and_store_memory

                await extract_and_store_memory(
                    message=last_user_message,
                    role="user",
                    user_id=request.session.user_id,
                )
            except Exception as e:
                logger.warning(f"记忆提取失败: {e}")

        return response

    except CircuitBreakerOpenError:
        raise HTTPException(503, "服务暂时不可用，请稍后重试")
    except APIError:
        raise
    except Exception as e:
        logger.error(f"聊天失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"聊天失败: {str(e)}")
    finally:
        if leased_model is not None:
            await scheduler.release_model(request.model)


@router.post("/chat/stream")
async def chat_stream(request: ChatRequest):
    """流式聊天"""
    if not request.messages or len(request.messages) == 0:
        raise InvalidInputError("messages", "消息列表不能为空")

    for msg in request.messages:
        if detect_prompt_injection(msg.content):
            raise MaliciousInputError()
        msg.content = sanitize_input(msg.content)

    if settings.ollama_fast_mode:
        request.options.max_tokens = min(request.options.max_tokens, settings.ollama_fast_max_tokens)

    system_prompt = request.system_prompt or ""
    knowledge_sources_response = None
    retrieval_info = None
    memory_context_info = None
    unified_context_info = None

    last_user_message = request.get_last_user_message()
    attachment_context = build_attachment_context(request.attachments)
    if attachment_context and request.messages:
        request.messages[-1].content = f"{request.messages[-1].content}\n\n{attachment_context}".strip()
        last_user_message = request.get_last_user_message()

    (
        system_prompt,
        knowledge_sources_response,
        retrieval_info,
        memory_context_info,
        unified_context_info,
    ) = await _build_unified_context_payload(
        request=request,
        last_user_message=last_user_message,
        base_system_prompt=system_prompt,
    )

    scheduler = get_scheduler()
    backend_name = _current_backend_name(request.options.backend)
    model_name = request.model
    leased_model = None
    load_duration_ms = 0.0

    async def _do_chat_stream():
        nonlocal leased_model, load_duration_ms
        backend = await scheduler.get_backend(backend_name)

        if backend_name != BackendType.CLOUD.value:
            model_path = (
                scheduler.resolve_model_path(model_name, backend_name)
                if hasattr(scheduler, "resolve_model_path")
                else model_name
            )
            if hasattr(scheduler, "acquire_model"):
                leased_model = await scheduler.acquire_model(
                    model_name,
                    model_path,
                    backend_name,
                    num_ctx=request.options.num_ctx,
                    num_batch=request.options.num_batch,
                    max_tokens=request.options.max_tokens,
                )
                if leased_model is None:
                    raise HTTPException(status_code=503, detail=f"模型加载失败: {model_name}")
                load_duration_ms = float(leased_model.metadata.get("load_duration_ms", 0.0) or 0.0)

        messages = [
            {
                "role": msg.role.value if hasattr(msg.role, "value") else msg.role,
                "content": msg.content,
            }
            for msg in request.messages
        ]
        local_messages = _inject_system_prompt_dict(messages, system_prompt)
        if backend_name == "ollama":
            local_messages = enforce_fast_ollama_response(local_messages, model_name, settings.ollama_fast_mode)

        if hasattr(backend, "model_name") and model_name:
            backend.model_name = model_name

        generation_config = GenerationConfig(
            max_tokens=request.options.max_tokens,
            temperature=request.options.temperature,
            top_p=request.options.top_p,
            top_k=request.options.top_k,
            repetition_penalty=request.options.repetition_penalty,
            stop_sequences=request.options.stop or [],
            stream=True,
        )

        async for chunk in backend.chat_stream(local_messages, generation_config):
            yield chunk

    async def _fallback_chat_stream():
        if request.options.backend != "cloud":
            logger.info("本地后端不可用，尝试云端AI降级 (Chat流式)")
            import copy
            cloud_request = ChatRequest(
                model=request.model,
                messages=copy.deepcopy(request.messages),
                options=copy.deepcopy(request.options)
            )
            cloud_request.options.backend = "cloud"
            scheduler = get_scheduler()
            backend = await scheduler.get_backend("cloud")
            
            messages = [
                {
                    "role": msg.role.value if hasattr(msg.role, "value") else msg.role,
                    "content": msg.content,
                }
                for msg in cloud_request.messages
            ]
            local_messages = _inject_system_prompt_dict(messages, system_prompt)

            generation_config = GenerationConfig(
                max_tokens=cloud_request.options.max_tokens,
                temperature=cloud_request.options.temperature,
                top_p=cloud_request.options.top_p,
                top_k=cloud_request.options.top_k,
                repetition_penalty=cloud_request.options.repetition_penalty,
                stop_sequences=cloud_request.options.stop or [],
                stream=True,
            )

            async for chunk in backend.chat_stream(local_messages, generation_config):
                yield chunk
        else:
            raise HTTPException(503, "所有后端不可用")

    try:
        async def generate():
            started_at = time.time()
            first_token_time = None
            try:
                metadata_payload = {
                    "type": "metadata",
                    "model": model_name,
                    "backend": backend_name,
                }
                if knowledge_sources_response:
                    metadata_payload["knowledge_sources"] = [
                        _model_to_dict(source) for source in knowledge_sources_response
                    ]
                    metadata_payload["retrieval_info"] = retrieval_info
                    metadata_payload["sources"] = [
                        _model_to_dict(source) for source in knowledge_sources_response
                    ]
                if memory_context_info:
                    metadata_payload["memory_context"] = _model_to_dict(memory_context_info)
                if unified_context_info:
                    metadata_payload["unified_context"] = _model_to_dict(unified_context_info)

                yield f"data: {_fast_dumps(metadata_payload)}\n\n"

                buffer = []
                last_yield_time = time.time()
                total_chunks = 0
                chunk_latencies: list[float] = []

                protected_stream = circuit_breaker.execute_stream_with_protection(
                    backend_name,
                    _do_chat_stream,
                    _fallback_chat_stream
                )

                async for chunk in protected_stream:
                    if not chunk:
                        continue
                    total_chunks += 1
                    if first_token_time is None:
                        first_token_time = time.time()
                        ttft_ms = int((first_token_time - started_at) * 1000)
                        if ttft_ms > 3000:
                            logger.warning(f"[WARNING] High TTFT detected: {ttft_ms}ms, possible blocking operation or fake streaming.")
                        else:
                            logger.info(f"TTFT (Time To First Token): {ttft_ms}ms")
                            
                        yield f"data: {_fast_dumps({'type': 'delta', 'content': chunk})}\n\n"
                        last_yield_time = time.time()
                        continue

                    buffer.append(chunk)
                    now = time.time()
                    flush_interval_s = settings.stream_flush_interval_ms / 1000.0
                    if now - last_yield_time >= flush_interval_s or len(buffer) >= settings.stream_buffer_size:
                        content = "".join(buffer)
                        chunk_latencies.append((now - last_yield_time) * 1000)
                        yield f"data: {_fast_dumps({'type': 'delta', 'content': content})}\n\n"
                        buffer.clear()
                        last_yield_time = now

                if buffer:
                    content = "".join(buffer)
                    yield f"data: {_fast_dumps({'type': 'delta', 'content': content})}\n\n"

                duration_ms = int((time.time() - started_at) * 1000)
                if request.memory.enabled and request.memory.auto_extract and last_user_message:
                    try:
                        from memory.service import extract_and_store_memory

                        await extract_and_store_memory(
                            message=last_user_message,
                            role="user",
                            user_id=request.session.user_id,
                        )
                    except Exception as memory_error:
                        logger.warning(f"流式聊天记忆提取失败: {memory_error}")

                yield f"data: {_fast_dumps({'type': 'metadata', 'model': model_name, 'backend': backend_name, 'duration_ms': duration_ms})}\n\n"
                yield f"data: {_fast_dumps({'type': 'done'})}\n\n"
                yield "data: [DONE]\n\n"

                # Record metrics
                if first_token_time:
                    try:
                        get_performance_monitor().record_streaming(StreamingMetrics(
                            total_tokens=total_chunks, # Rough estimate (chunks usually = tokens)
                            total_time_ms=duration_ms,
                            first_token_latency_ms=(first_token_time - started_at) * 1000,
                            avg_chunk_latency_ms=sum(chunk_latencies) / max(len(chunk_latencies), 1) if chunk_latencies else 0.0,
                            max_chunk_latency_ms=max(chunk_latencies) if chunk_latencies else 0.0,
                            min_chunk_latency_ms=min(chunk_latencies) if chunk_latencies else 0.0,
                            backpressure_events=0,
                            load_duration_ms=load_duration_ms,
                            model_id=model_name,
                            engine_type=backend_name,
                        ))
                    except Exception as metric_err:
                        logger.warning(f"记录流式性能指标失败: {metric_err}")

            except Exception as stream_error:
                logger.error(f"流式聊天输出失败: {stream_error}", exc_info=True)
                yield f"data: {_fast_dumps({'type': 'error', 'error': str(stream_error)})}\n\n"
                yield "data: [DONE]\n\n"
            finally:
                if leased_model is not None:
                    await scheduler.release_model(model_name)

        return StreamingResponse(
            generate(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no"
            }
        )

    except CircuitBreakerOpenError:
        raise HTTPException(503, "服务暂时不可用，请稍后重试")
    except APIError:
        raise
    except Exception as e:
        logger.error(f"流式聊天失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"流式聊天失败: {str(e)}")


@router.get("/models")
async def list_models(backend: str | None = Query(None, description="后端类型")):
    """列出可用模型 - 参考 Ollama /api/tags"""
    try:
        scheduler = get_scheduler()
        models = await scheduler.list_models(backend)
        return models
    except Exception as e:
        logger.error(f"获取模型列表失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取模型列表失败: {str(e)}")


@router.get("/backends", response_model=BackendListResponse)
async def list_backends():
    """列出可用后端"""
    scheduler = get_scheduler()

    backends = [
        BackendInfo(
            id=BackendType.HUGGINGFACE.value,
            name="HuggingFace (本地模型)",
            available=await scheduler.is_backend_available(BackendType.HUGGINGFACE.value),
            description="使用下载的 HuggingFace 模型"
        ),
        BackendInfo(
            id=BackendType.OLLAMA.value,
            name="Ollama",
            available=await scheduler.is_backend_available(BackendType.OLLAMA.value),
            description="Ollama 本地部署"
        ),
        BackendInfo(
            id=BackendType.LLAMACPP.value,
            name="Llama.cpp (GGUF)",
            available=await scheduler.is_backend_available(BackendType.LLAMACPP.value),
            description="适合低显存设备的 GGUF 本地推理"
        ),
    ]

    return BackendListResponse(
        current=scheduler._default_backend,
        backends=backends
    )


@router.post("/backends/switch")
async def switch_backend(request: BackendSwitchRequest):
    """切换推理后端"""
    try:
        scheduler = get_scheduler()
        scheduler.set_default_backend(request.backend)
        return {"message": f"已切换到 {request.backend}", "current": request.backend}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/cache/status")
async def get_cache_status():
    """获取缓存状态"""
    scheduler = get_scheduler()
    cache_stats = scheduler.get_stats()
    cache_stats["batching"] = get_local_inference_pipeline().get_stats()
    cache_stats["offline_cache"] = get_offline_cache().get_stats()
    return cache_stats


@router.post("/cache/clear")
async def clear_cache():
    """清除模型缓存"""
    scheduler = get_scheduler()
    await scheduler.unload_all()
    get_offline_cache().clear()
    return {"message": "模型缓存已清除"}


@router.get("/ollama/status")
async def get_ollama_status():
    """获取 Ollama 状态"""
    scheduler = get_scheduler()
    available = await scheduler.is_backend_available(BackendType.OLLAMA.value)

    models = []
    if available:
        try:
            ollama_models = await scheduler.list_models(BackendType.OLLAMA.value)
            models = [{"name": m.get("name", ""), "size": m.get("size", 0)} for m in ollama_models]
        except Exception:
            pass

    return {
        "running": available,
        "base_url": settings.ollama_base_url,
        "models": models
    }


@router.get("/performance")
async def get_performance_stats(model_id: str | None = Query(None)):
    """获取性能统计"""
    from core.performance import get_performance_monitor

    monitor = get_performance_monitor()
    stats = monitor.get_stats(model_id)
    streaming_stats = monitor.get_streaming_stats()

    return {
        "inference": stats,
        "streaming": streaming_stats,
    }


@router.get("/performance/recommendations")
async def get_performance_recommendations():
    """获取性能优化建议"""
    from core.performance import get_performance_monitor
    from core.hardware_profile import build_hardware_profile
    from core.utils import get_device_info

    monitor = get_performance_monitor()
    device_info = get_device_info()
    vram_total = device_info.get("memory_total", 0)

    recommendations = monitor.get_recommendations(vram_total)

    return {
        "recommendations": recommendations,
        "device_info": device_info,
        "hardware_profile": build_hardware_profile(device_info),
    }


@router.post("/performance/clear")
async def clear_performance_history():
    """清空本地推理性能历史。"""
    get_performance_monitor().clear_history()
    return {"message": "推理性能历史已清除"}


@router.get("/performance/prometheus")
async def get_performance_prometheus():
    """导出 Prometheus 格式的本地推理指标。"""
    return StreamingResponse(
        iter([get_performance_monitor().export_prometheus()]),
        media_type="text/plain; version=0.0.4; charset=utf-8",
    )


@router.get("/metrics")
async def get_metrics_alias():
    """Prometheus 指标兼容入口。"""
    return await get_performance_prometheus()
