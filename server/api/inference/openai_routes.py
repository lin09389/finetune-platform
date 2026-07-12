"""OpenAI-compatible facade for the platform's unified local model runtime."""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from collections import Counter
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from api.inference.backends.base import GenerationConfig, GenerationResult
from api.inference.openai_schemas import (
    ChatCompletionMessage,
    ChatCompletionRequest,
    ChatCompletionResponse,
    ChatCompletionStreamResponse,
    Choice,
    DeltaMessage,
    ModelCard,
    ModelListResponse,
    StreamChoice,
    Usage,
)
from api.inference.scheduler import BackendType, ModelScheduler, get_scheduler

logger = logging.getLogger(__name__)

router = APIRouter(tags=["OpenAI Compatible API"])

_LOCAL_BACKENDS = {
    BackendType.HUGGINGFACE.value,
    BackendType.OLLAMA.value,
    BackendType.LLAMACPP.value,
}


@dataclass(slots=True)
class RuntimeTarget:
    requested_model: str
    model_name: str
    backend_name: str
    model_path: str
    lease_name: str
    backend: Any
    scheduler: ModelScheduler


def _openai_http_error(
    status_code: int,
    message: str,
    *,
    error_type: str,
    code: str,
    param: str | None = None,
) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={
            "error": {
                "message": message,
                "type": error_type,
                "param": param,
                "code": code,
            }
        },
    )


def _stream_error_payload(message: str, code: str = "inference_error") -> str:
    return json.dumps(
        {
            "error": {
                "message": message,
                "type": "server_error",
                "param": None,
                "code": code,
            }
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )


async def _list_runtime_models() -> list[dict[str, Any]]:
    """Use the product inference catalog, including deployment aliases."""
    from api.inference.routes import list_models as list_inference_models

    models = await list_inference_models(None)
    return [model for model in models if isinstance(model, dict)]


def _normalize_catalog(models: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for model in models:
        model_name = str(model.get("id") or model.get("name") or "").strip()
        backend = str(model.get("backend") or "").strip()
        if not model_name or backend not in _LOCAL_BACKENDS:
            continue
        key = (backend, model_name)
        if key in seen:
            continue
        seen.add(key)
        normalized.append(
            {
                **model,
                "name": model_name,
                "backend": backend,
                "canonical_id": f"{backend}/{model_name}",
            }
        )
    return normalized


@router.get("/v1/models", response_model=ModelListResponse)
async def list_models() -> ModelListResponse:
    """List all discoverable local models without inventing unusable aliases."""
    catalog = _normalize_catalog(await _list_runtime_models())
    name_counts = Counter(model["name"] for model in catalog)
    cards = [
        ModelCard(
            id=model["canonical_id"] if name_counts[model["name"]] > 1 else model["name"],
            backend=model["backend"],
            canonical_id=model["canonical_id"],
            source=str(model.get("source") or "local"),
        )
        for model in catalog
    ]
    return ModelListResponse(data=cards)


def _split_canonical_model(model: str) -> tuple[str | None, str]:
    prefix, separator, model_name = model.partition("/")
    if separator and prefix in _LOCAL_BACKENDS and model_name:
        return prefix, model_name
    return None, model


def _active_runtime_selection() -> dict[str, str | None]:
    from api.model_runtime import get_active_model_runtime_selection

    return get_active_model_runtime_selection()


async def _resolve_runtime_target(
    requested_model: str,
    explicit_backend: str | None,
) -> tuple[str, str, str | None, str | None]:
    canonical_backend, model_name = _split_canonical_model(requested_model)
    if explicit_backend and explicit_backend not in _LOCAL_BACKENDS:
        raise _openai_http_error(
            400,
            f"Unsupported local inference backend: {explicit_backend}",
            error_type="invalid_request_error",
            code="unsupported_backend",
            param="x-backend",
        )
    if canonical_backend and explicit_backend and canonical_backend != explicit_backend:
        raise _openai_http_error(
            400,
            "The model's canonical backend conflicts with the X-Backend header.",
            error_type="invalid_request_error",
            code="backend_conflict",
            param="model",
        )

    deployment_target = None
    try:
        from api.deployment import resolve_deployed_model

        deployment_target = resolve_deployed_model(model_name)
    except Exception:
        logger.debug("Failed to resolve deployment alias %s", model_name, exc_info=True)

    catalog = _normalize_catalog(await _list_runtime_models())
    matches = [model for model in catalog if model["name"] == model_name]
    candidate_backends = {model["backend"] for model in matches}

    active_selection = _active_runtime_selection()
    active_backend = active_selection.get("backend")
    active_model = active_selection.get("model_id")
    default_backend = get_scheduler().get_stats().get("default_backend")

    backend_name = canonical_backend or explicit_backend
    if deployment_target:
        deployment_backend = str(deployment_target.get("backend") or BackendType.HUGGINGFACE.value)
        if backend_name and backend_name != deployment_backend:
            raise _openai_http_error(
                400,
                "The deployment alias cannot run on the requested backend.",
                error_type="invalid_request_error",
                code="backend_conflict",
                param="model",
            )
        backend_name = deployment_backend
    elif backend_name is None and active_model == model_name and active_backend in candidate_backends:
        backend_name = active_backend
    elif backend_name is None and len(candidate_backends) == 1:
        backend_name = next(iter(candidate_backends))
    elif backend_name is None and default_backend in candidate_backends:
        backend_name = str(default_backend)

    if not deployment_target and not matches:
        # Ollama models live in the Ollama daemon, not the HF disk catalog. When the
        # caller explicitly targets the ollama backend (canonical id or X-Backend),
        # accept the tag name and let Ollama validate existence at request time.
        ollama_backend = BackendType.OLLAMA.value
        if (canonical_backend or explicit_backend or backend_name) == ollama_backend and model_name:
            return model_name, ollama_backend, None, None
        raise _openai_http_error(
            404,
            f"The local model '{model_name}' was not found. Use GET /v1/models to list available models.",
            error_type="invalid_request_error",
            code="model_not_found",
            param="model",
        )
    if backend_name is None:
        choices = ", ".join(sorted(candidate_backends))
        raise _openai_http_error(
            409,
            f"Model '{model_name}' exists in multiple backends ({choices}); use its canonical_id.",
            error_type="invalid_request_error",
            code="ambiguous_model",
            param="model",
        )
    if backend_name not in _LOCAL_BACKENDS:
        raise _openai_http_error(
            400,
            f"Backend '{backend_name}' is not a local inference backend.",
            error_type="invalid_request_error",
            code="unsupported_backend",
            param="model",
        )
    if matches and backend_name not in candidate_backends:
        raise _openai_http_error(
            404,
            f"Model '{model_name}' is not available in backend '{backend_name}'.",
            error_type="invalid_request_error",
            code="model_not_found",
            param="model",
        )

    selected = next((model for model in matches if model["backend"] == backend_name), None)
    model_path = (
        str(deployment_target.get("model_path"))
        if deployment_target and deployment_target.get("model_path")
        else str(selected.get("path"))
        if selected and selected.get("path")
        else None
    )
    lora_adapter = (
        str(deployment_target.get("lora_adapter"))
        if deployment_target and deployment_target.get("lora_adapter")
        else None
    )
    return model_name, backend_name, model_path, lora_adapter


async def _prepare_runtime(
    requested_model: str,
    explicit_backend: str | None,
    max_tokens: int,
    *,
    model_path_override: str | None = None,
    lora_adapter_override: str | None = None,
) -> RuntimeTarget:
    if model_path_override:
        canonical_backend, model_name = _split_canonical_model(requested_model)
        backend_name = explicit_backend or canonical_backend
        if backend_name not in _LOCAL_BACKENDS:
            raise _openai_http_error(
                400,
                "X-Model-Path requires an explicit supported local backend.",
                error_type="invalid_request_error",
                code="unsupported_backend",
                param="x-backend",
            )
        model_path = model_path_override
        lora_adapter = lora_adapter_override
    else:
        model_name, backend_name, model_path, lora_adapter = await _resolve_runtime_target(
            requested_model,
            explicit_backend,
        )
        lora_adapter = lora_adapter_override or lora_adapter
    scheduler = get_scheduler()
    try:
        backend_available = await scheduler.is_backend_available(backend_name)
    except Exception as exc:
        logger.error("Failed to inspect inference backend %s", backend_name, exc_info=True)
        raise _openai_http_error(
            503,
            f"Could not inspect local inference backend '{backend_name}'.",
            error_type="server_error",
            code="backend_unavailable",
        ) from exc
    if not backend_available:
        raise _openai_http_error(
            503,
            f"Local inference backend '{backend_name}' is unavailable.",
            error_type="server_error",
            code="backend_unavailable",
        )

    resolved_path = model_path or scheduler.resolve_model_path(model_name, backend_name)
    try:
        leased_model = await scheduler.acquire_model(
            model_name,
            resolved_path,
            backend_name,
            max_tokens=max_tokens,
            lora_adapter=lora_adapter,
        )
    except Exception as exc:
        logger.error("Failed to acquire local model %s", model_name, exc_info=True)
        raise _openai_http_error(
            503,
            f"Failed to load local model '{model_name}' on backend '{backend_name}'.",
            error_type="server_error",
            code="model_load_failed",
            param="model",
        ) from exc
    if leased_model is None:
        raise _openai_http_error(
            503,
            f"Failed to load local model '{model_name}' on backend '{backend_name}'.",
            error_type="server_error",
            code="model_load_failed",
            param="model",
        )

    try:
        backend = await scheduler.get_backend(backend_name)
    except Exception as exc:
        await _release_model(scheduler, model_name)
        raise _openai_http_error(
            503,
            f"Failed to initialize local inference backend '{backend_name}'.",
            error_type="server_error",
            code="backend_unavailable",
        ) from exc
    if hasattr(backend, "model_name"):
        backend.model_name = model_name
    return RuntimeTarget(
        requested_model=requested_model,
        model_name=model_name,
        backend_name=backend_name,
        model_path=resolved_path,
        lease_name=model_name,
        backend=backend,
        scheduler=scheduler,
    )


async def _release_model(scheduler: ModelScheduler, lease_name: str) -> None:
    try:
        await scheduler.release_model(lease_name)
    except Exception:
        logger.error("Failed to release model lease %s", lease_name, exc_info=True)


def _request_requires_tools(request: ChatCompletionRequest) -> bool:
    from api.inference.openai_tool_bridge import request_requires_tools

    return request_requires_tools(
        tools=request.tools,
        tool_choice=request.tool_choice,
        messages=request.messages,
        parallel_tool_calls=request.parallel_tool_calls,
    )


def _validate_supported_features(
    request: ChatCompletionRequest,
    *,
    backend_name: str | None = None,
) -> None:
    """Validate OpenAI-compatible features for the resolved local backend.

    Tool fields are allowed only when ``backend_name`` is Ollama (Phase 2 passthrough).
    HuggingFace / llama-cpp remain fail-closed for tools.
    """
    from api.inference.openai_tool_bridge import backend_allows_tools, tools_denied_message

    requires_tools = _request_requires_tools(request)
    tools_allowed = backend_allows_tools(backend_name)

    if requires_tools and not tools_allowed:
        # Prefer the most specific param for diagnostics.
        if request.tools:
            param = "tools"
        elif request.tool_choice not in (None, "none"):
            param = "tool_choice"
        elif request.parallel_tool_calls is not None:
            param = "parallel_tool_calls"
        elif any(message.tool_calls for message in request.messages):
            param = "messages"
        elif any(message.role in {"tool", "function"} for message in request.messages):
            param = "messages"
        else:
            param = "tools"
        raise _openai_http_error(
            400,
            tools_denied_message(backend_name),
            error_type="invalid_request_error",
            code="unsupported_tools",
            param=param,
        )

    if requires_tools and request.stream:
        raise _openai_http_error(
            400,
            "Streaming tool calls are not supported on the local Ollama path yet; set stream=false.",
            error_type="invalid_request_error",
            code="unsupported_stream_tools",
            param="stream",
        )

    # Non-tool messages must still have text content. Tool-loop assistant/tool
    # messages may legally omit content when tool_calls / tool results are present.
    if not requires_tools:
        empty_message = next((message for message in request.messages if message.content is None), None)
        if empty_message:
            raise _openai_http_error(
                400,
                "Each local inference message must contain text content.",
                error_type="invalid_request_error",
                code="unsupported_message_content",
                param="messages",
            )
    else:
        for message in request.messages:
            if message.role in {"tool", "function"}:
                continue
            if message.role == "assistant" and message.tool_calls:
                continue
            if message.content is None:
                raise _openai_http_error(
                    400,
                    "Non-tool messages must contain text content.",
                    error_type="invalid_request_error",
                    code="unsupported_message_content",
                    param="messages",
                )

    if request.presence_penalty != 0 or request.frequency_penalty != 0:
        raise _openai_http_error(
            400,
            "presence_penalty and frequency_penalty are not supported by local backends.",
            error_type="invalid_request_error",
            code="unsupported_penalty",
            param="presence_penalty",
        )
    if request.seed is not None or request.logit_bias is not None:
        param = "seed" if request.seed is not None else "logit_bias"
        raise _openai_http_error(
            400,
            f"{param} is not supported by local backends.",
            error_type="invalid_request_error",
            code="unsupported_parameter",
            param=param,
        )
    if request.n != 1:
        raise _openai_http_error(
            400,
            "Only n=1 is supported by the local runtime.",
            error_type="invalid_request_error",
            code="unsupported_parameter",
            param="n",
        )
    if request.response_format and request.response_format.get("type", "text") != "text":
        raise _openai_http_error(
            400,
            "Only response_format.type='text' is supported by the local runtime.",
            error_type="invalid_request_error",
            code="unsupported_response_format",
            param="response_format",
        )
    if request.stream_options is not None and not request.stream:
        raise _openai_http_error(
            400,
            "stream_options can only be used when stream=true.",
            error_type="invalid_request_error",
            code="invalid_stream_options",
            param="stream_options",
        )


def _messages_for_backend(
    messages: list[ChatCompletionMessage],
    *,
    include_tools: bool = False,
) -> list[dict[str, Any]]:
    converted: list[dict[str, Any]] = []
    for message in messages:
        role = "system" if message.role == "developer" else message.role
        item: dict[str, Any] = {
            "role": role,
            "content": message.content if message.content is not None else "",
        }
        if include_tools:
            if message.tool_calls:
                item["tool_calls"] = message.tool_calls
            if message.tool_call_id:
                item["tool_call_id"] = message.tool_call_id
            if message.name:
                item["name"] = message.name
        converted.append(item)
    return converted


def _stop_sequences(stop: list[str] | str | None) -> list[str]:
    if stop is None:
        return []
    return [stop] if isinstance(stop, str) else stop


def _generation_config(request: ChatCompletionRequest, *, stream: bool) -> GenerationConfig:
    return GenerationConfig(
        max_tokens=request.resolved_max_tokens,
        temperature=0.7 if request.temperature is None else request.temperature,
        top_p=0.9 if request.top_p is None else request.top_p,
        repetition_penalty=request.repetition_penalty,
        stop_sequences=_stop_sequences(request.stop),
        stream=stream,
    )


def _raise_for_failed_result(result: GenerationResult) -> None:
    if result.finish_reason != "error" and not result.metadata.get("error"):
        return
    message = str(result.metadata.get("error") or "Local inference failed")
    raise _openai_http_error(
        502,
        message,
        error_type="server_error",
        code="inference_error",
    )


async def _count_stream_usage(
    runtime: RuntimeTarget,
    messages: list[dict[str, str]],
    completion: str,
) -> Usage:
    prompt = "\n".join(f"{message['role']}: {message['content']}" for message in messages)
    try:
        prompt_tokens, completion_tokens = await asyncio.gather(
            runtime.backend.count_tokens(prompt),
            runtime.backend.count_tokens(completion),
        )
    except Exception:
        logger.debug("Token counting failed for OpenAI stream", exc_info=True)
        prompt_tokens = max(len(prompt) // 4, 0)
        completion_tokens = max(len(completion) // 4, 0)
    return Usage(
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=prompt_tokens + completion_tokens,
    )


async def _stream_generator(
    runtime: RuntimeTarget,
    request: ChatCompletionRequest,
    messages: list[dict[str, str]],
    completion_id: str,
    created: int,
) -> AsyncGenerator[str, None]:
    collected: list[str] = []
    try:
        role_chunk = ChatCompletionStreamResponse(
            id=completion_id,
            created=created,
            model=request.model,
            choices=[StreamChoice(index=0, delta=DeltaMessage(role="assistant"))],
        )
        yield f"data: {role_chunk.model_dump_json(exclude_none=True)}\n\n"

        async for content in runtime.backend.chat_stream(
            messages,
            _generation_config(request, stream=True),
        ):
            if not content:
                continue
            collected.append(content)
            chunk = ChatCompletionStreamResponse(
                id=completion_id,
                created=created,
                model=request.model,
                choices=[StreamChoice(index=0, delta=DeltaMessage(content=content))],
            )
            yield f"data: {chunk.model_dump_json(exclude_none=True)}\n\n"

        finish_chunk = ChatCompletionStreamResponse(
            id=completion_id,
            created=created,
            model=request.model,
            choices=[StreamChoice(index=0, delta=DeltaMessage(), finish_reason="stop")],
        )
        yield f"data: {finish_chunk.model_dump_json(exclude_none=True)}\n\n"

        if request.stream_options and request.stream_options.include_usage:
            usage = await _count_stream_usage(runtime, messages, "".join(collected))
            usage_chunk = ChatCompletionStreamResponse(
                id=completion_id,
                created=created,
                model=request.model,
                choices=[],
                usage=usage,
            )
            yield f"data: {usage_chunk.model_dump_json(exclude_none=True)}\n\n"
        yield "data: [DONE]\n\n"
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        logger.error("OpenAI-compatible stream failed", exc_info=True)
        yield f"data: {_stream_error_payload(str(exc))}\n\n"
    finally:
        await _release_model(runtime.scheduler, runtime.lease_name)


@router.post("/v1/chat/completions")
async def chat_completions(request: ChatCompletionRequest, raw_request: Request):
    """Run an OpenAI-compatible completion on the unified local scheduler."""
    # Fail-closed early when the client forces a non-Ollama backend with tools
    # (avoids model_not_found masking unsupported_tools).
    explicit_backend = raw_request.headers.get("x-backend")
    if explicit_backend and _request_requires_tools(request):
        _validate_supported_features(request, backend_name=explicit_backend)

    runtime = await _prepare_runtime(
        request.model,
        explicit_backend,
        request.resolved_max_tokens,
        model_path_override=raw_request.headers.get("x-model-path"),
        lora_adapter_override=raw_request.headers.get("x-lora-adapter"),
    )
    try:
        _validate_supported_features(request, backend_name=runtime.backend_name)
    except HTTPException:
        await _release_model(runtime.scheduler, runtime.lease_name)
        raise

    requires_tools = _request_requires_tools(request)
    messages = _messages_for_backend(request.messages, include_tools=requires_tools)
    completion_id = f"chatcmpl-{uuid.uuid4().hex}"
    created = int(time.time())

    # Stream path owns lease release inside _stream_generator.
    if request.stream:
        return StreamingResponse(
            _stream_generator(runtime, request, messages, completion_id, created),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    try:
        config = _generation_config(request, stream=False)
        if requires_tools and runtime.backend_name == BackendType.OLLAMA.value:
            result = await runtime.backend.chat(
                messages,
                config,
                tools=request.tools,
                tool_choice=request.tool_choice,
            )
        else:
            result = await runtime.backend.chat(messages, config)
        _raise_for_failed_result(result)
        usage = Usage(
            completion_tokens=result.tokens_generated,
            prompt_tokens=result.prompt_tokens,
            total_tokens=result.total_tokens or result.prompt_tokens + result.tokens_generated,
        )
        tool_calls = None
        if isinstance(result.metadata, dict):
            tool_calls = result.metadata.get("tool_calls")
        assistant_message = ChatCompletionMessage(
            role="assistant",
            content=result.text if result.text is not None else "",
            tool_calls=tool_calls or None,
        )
        finish_reason = result.finish_reason
        if tool_calls and finish_reason == "stop":
            finish_reason = "tool_calls"
        return ChatCompletionResponse(
            id=completion_id,
            created=created,
            model=request.model,
            choices=[
                Choice(
                    index=0,
                    message=assistant_message,
                    finish_reason=finish_reason,
                )
            ],
            usage=usage,
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("OpenAI-compatible completion failed", exc_info=True)
        raise _openai_http_error(
            502,
            str(exc),
            error_type="server_error",
            code="inference_error",
        ) from exc
    finally:
        await _release_model(runtime.scheduler, runtime.lease_name)
