"""
推理模块路由 - 参考 Ollama server/routes.go 设计模式
"""
import logging
import time
import json
from typing import Any

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
from core.config import get_settings

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
    from context.unified_manager import ContextOptions, get_unified_context_manager

    context_manager = get_unified_context_manager()
    context_options = ContextOptions(
        use_memory=request.memory.enabled and request.memory.auto_retrieve,
        use_knowledge=request.knowledge.use_knowledge,
        use_project_context=request.context.use_context,
        memory_top_k=request.memory.top_k,
        memory_include_types=request.memory.include_types,
        knowledge_collection_id=request.knowledge.collection_id,
        knowledge_top_k=request.knowledge.top_k,
        knowledge_auto_retrieve=request.knowledge.auto_retrieve,
        project_path=request.context.project_path,
        project_max_length=request.context.max_context_length,
    )

    unified_context = await context_manager.build_context(
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

        unified_context_info = UnifiedContextInfo(
            total_sources=unified_context.total_sources,
            memory_count=unified_context.memory_count,
            knowledge_count=unified_context.knowledge_count,
            project_count=unified_context.project_count,
            retrieval_time=unified_context.retrieval_time,
        )

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

    backend_name = request.options.backend or "default"

    async def _do_generate():
        scheduler = get_scheduler()
        backend = await scheduler.get_backend(request.options.backend)
        return await backend.generate(request)

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
            return await backend.generate(cloud_request)
        raise HTTPException(503, "所有后端不可用")

    try:
        return await circuit_breaker.execute_with_protection(
            backend_name,
            _do_generate,
            _fallback_generate
        )

    except CircuitBreakerOpenError:
        raise HTTPException(503, "服务暂时不可用，请稍后重试")
    except APIError:
        raise
    except Exception as e:
        logger.error(f"生成失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"生成失败: {str(e)}")


@router.post("/generate/stream")
async def generate_stream(request: GenerateRequest):
    """流式生成 - 参考 Ollama 流式生成"""
    if not request.prompt or not request.prompt.strip():
        raise InvalidInputError("prompt", "提示内容不能为空")

    if detect_prompt_injection(request.prompt):
        raise MaliciousInputError()

    request.prompt = sanitize_input(request.prompt)

    try:
        scheduler = get_scheduler()
        backend = await scheduler.get_backend(request.options.backend)

        return StreamingResponse(
            backend.generate_stream(request),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no"
            }
        )

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

    try:
        scheduler = get_scheduler()
        backend = await scheduler.get_backend(request.options.backend)

        backend_name = request.options.backend or "ollama"
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
            result = await backend.chat(request)
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

            result = await backend.chat(
                messages,
                GenerationConfig(
                    max_tokens=request.options.max_tokens,
                    temperature=request.options.temperature,
                    top_p=request.options.top_p,
                    top_k=request.options.top_k,
                    repetition_penalty=request.options.repetition_penalty,
                ),
            )

        logger.info(f"Chat result type: {type(result)}, isinstance GenerationResult: {isinstance(result, GenerationResult)}")
        if hasattr(result, 'text'):
            logger.info(f"Result text: {result.text[:100] if result.text else 'empty'}...")
        if hasattr(result, 'metadata'):
            logger.info(f"Result metadata: {result.metadata}")

        if isinstance(result, GenerationResult):
            from api.types import Message, MessageRole, TokenUsage
            response = ChatResponse(
                message=Message(
                    role=MessageRole.ASSISTANT,
                    content=result.text
                ),
                model=result.model,
                backend=request.options.backend or "ollama",
                done=result.finish_reason == "stop",
                usage=TokenUsage(
                    prompt_tokens=result.prompt_tokens,
                    completion_tokens=result.tokens_generated,
                    total_tokens=result.total_tokens
                ),
                total_duration=result.latency_ms / 1000.0 if result.latency_ms else None,
                duration_ms=int(result.latency_ms) if result.latency_ms is not None else None,
                raw_response={
                    "model": result.model,
                    "finish_reason": result.finish_reason,
                    "tokens_generated": result.tokens_generated,
                    "prompt_tokens": result.prompt_tokens,
                    "total_tokens": result.total_tokens,
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
                from context.unified_manager import get_unified_context_manager

                context_manager = get_unified_context_manager()
                await context_manager.extract_and_store_memory(
                    message=last_user_message,
                    role="user",
                    user_id=request.session.user_id,
                    session_id=request.session.session_id
                )
            except Exception as e:
                logger.warning(f"记忆提取失败: {e}")

        return response

    except APIError:
        raise
    except Exception as e:
        logger.error(f"聊天失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"聊天失败: {str(e)}")


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

    try:
        scheduler = get_scheduler()
        backend = await scheduler.get_backend(request.options.backend)

        backend_name = request.options.backend or "ollama"
        model_name = request.model
        messages = [
            {
                "role": msg.role.value if hasattr(msg.role, "value") else msg.role,
                "content": msg.content,
            }
            for msg in request.messages
        ]
        messages = _inject_system_prompt_dict(messages, system_prompt)
        if backend_name == "ollama":
            messages = enforce_fast_ollama_response(messages, model_name, settings.ollama_fast_mode)

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
                if memory_context_info:
                    metadata_payload["memory_context"] = _model_to_dict(memory_context_info)
                if unified_context_info:
                    metadata_payload["unified_context"] = _model_to_dict(unified_context_info)

                yield f"data: {json.dumps(metadata_payload, ensure_ascii=False)}\n\n"

                async for chunk in backend.chat_stream(messages, generation_config):
                    if not chunk:
                        continue
                    if first_token_time is None:
                        first_token_time = time.time()
                        ttft_ms = int((first_token_time - started_at) * 1000)
                        if ttft_ms > 3000:
                            logger.warning(f"[WARNING] High TTFT detected: {ttft_ms}ms, possible blocking operation or fake streaming.")
                        else:
                            logger.info(f"TTFT (Time To First Token): {ttft_ms}ms")
                            
                    yield f"data: {json.dumps({'type': 'delta', 'content': chunk}, ensure_ascii=False)}\n\n"

                duration_ms = int((time.time() - started_at) * 1000)
                if request.memory.enabled and request.memory.auto_extract and last_user_message:
                    try:
                        from context.unified_manager import get_unified_context_manager

                        manager = get_unified_context_manager()
                        await manager.extract_and_store_memory(
                            message=last_user_message,
                            role="user",
                            user_id=request.session.user_id,
                            session_id=request.session.session_id,
                        )
                    except Exception as memory_error:
                        logger.warning(f"流式聊天记忆提取失败: {memory_error}")

                yield f"data: {json.dumps({'type': 'metadata', 'model': model_name, 'backend': backend_name, 'duration_ms': duration_ms}, ensure_ascii=False)}\n\n"
                yield f"data: {json.dumps({'type': 'done'}, ensure_ascii=False)}\n\n"
                yield "data: [DONE]\n\n"
            except Exception as stream_error:
                logger.error(f"流式聊天输出失败: {stream_error}", exc_info=True)
                yield f"data: {json.dumps({'type': 'error', 'error': str(stream_error)}, ensure_ascii=False)}\n\n"
                yield "data: [DONE]\n\n"

        return StreamingResponse(
            generate(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no"
            }
        )

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
    return await scheduler.get_stats()


@router.post("/cache/clear")
async def clear_cache():
    """清除模型缓存"""
    scheduler = get_scheduler()
    await scheduler.unload_all()
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
    from core.utils import get_device_info

    monitor = get_performance_monitor()
    device_info = get_device_info()
    vram_total = device_info.get("memory_total", 0)

    recommendations = monitor.get_recommendations(vram_total)

    return {
        "recommendations": recommendations,
        "device_info": device_info,
    }
