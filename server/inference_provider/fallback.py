from __future__ import annotations

import json
import time
import uuid
from collections.abc import AsyncIterator
from typing import Any

from core.config import get_settings
from security.encryption import secure_storage


def _configuration():
    settings = get_settings()
    provider_id = settings.inference_cloud_fallback_provider
    model = settings.inference_cloud_fallback_model
    if not settings.inference_cloud_fallback_enabled or not provider_id or not model:
        return None
    key_data = secure_storage.get(f"cloud_{provider_id}_key") or {}
    if not isinstance(key_data, dict) or not key_data.get("api_key"):
        return None
    from ai.providers import resolve_saved_provider

    provider = resolve_saved_provider(provider_id, key_data)
    if provider is None:
        return None
    return provider, provider_id, model, key_data


async def cloud_fallback_response(payload: dict[str, Any]) -> dict[str, Any] | None:
    configured = _configuration()
    if configured is None:
        return None
    provider, provider_id, model, key_data = configured
    result = await provider.chat(
        messages=payload.get("messages") or [],
        model=model,
        api_key=key_data["api_key"],
        temperature=payload.get("temperature", 0.7),
        max_tokens=payload.get("max_completion_tokens") or payload.get("max_tokens") or 2000,
        timeout=get_settings().inference_service_read_timeout_seconds,
    )
    content = str(result.get("content") or "") if isinstance(result, dict) else str(result)
    return {
        "id": f"chatcmpl-fallback-{uuid.uuid4().hex}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        "fallback": {"provider": provider_id, "reason": "local_service_unavailable"},
    }


async def cloud_fallback_stream(payload: dict[str, Any]) -> AsyncIterator[bytes] | None:
    configured = _configuration()
    if configured is None:
        return None
    provider, provider_id, model, key_data = configured
    completion_id = f"chatcmpl-fallback-{uuid.uuid4().hex}"

    async def generate() -> AsyncIterator[bytes]:
        try:
            async for chunk in provider.chat_stream(
                messages=payload.get("messages") or [],
                model=model,
                api_key=key_data["api_key"],
                temperature=payload.get("temperature", 0.7),
                max_tokens=payload.get("max_completion_tokens") or payload.get("max_tokens") or 2000,
                timeout=get_settings().inference_service_read_timeout_seconds,
            ):
                content = chunk.get("content") if isinstance(chunk, dict) else str(chunk)
                if not content:
                    continue
                event = {
                    "id": completion_id,
                    "object": "chat.completion.chunk",
                    "created": int(time.time()),
                    "model": model,
                    "choices": [{"index": 0, "delta": {"content": content}, "finish_reason": None}],
                    "fallback": {"provider": provider_id, "reason": "local_service_unavailable"},
                }
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n".encode()
            yield b"data: [DONE]\n\n"
        except Exception as exc:
            error = {
                "error": {
                    "message": str(exc),
                    "type": "server_error",
                    "param": None,
                    "code": "cloud_fallback_failed",
                }
            }
            yield f"data: {json.dumps(error, ensure_ascii=False)}\n\n".encode()

    return generate()


__all__ = ["cloud_fallback_response", "cloud_fallback_stream"]
