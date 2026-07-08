"""Inference execution gateway.

This module abstracts the two local inference execution modes:

- ``in_process``: inference runs inside the API process via ``api.inference``.
- ``service``: inference is delegated to a separate ``server.inference_server``
  process through ``inference_provider.client``.

Code that needs to perform inference should use the gateway rather than
branching on ``inference_execution_mode`` directly.
"""

from __future__ import annotations

import asyncio
import json
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from core.config import settings


class InferenceGateway(ABC):
    """Abstract local inference gateway."""

    @abstractmethod
    async def chat_completions(self, request, raw_request=None) -> Any:
        """Run a chat completion request."""
        ...

    @abstractmethod
    async def list_models(self, backend: str | None = None) -> Any:
        """Return the list of available models."""
        ...

    @abstractmethod
    async def openai_list_models(self) -> Any:
        """Return the OpenAI-compatible model list."""
        ...

    @abstractmethod
    async def list_backends(self) -> Any:
        """Return runtime backend information."""
        ...

    @abstractmethod
    async def ollama_status(self) -> Any:
        """Return Ollama backend status."""
        ...

    @abstractmethod
    async def generate(self, request) -> Any:
        """Run a raw generate request."""
        ...

    @abstractmethod
    async def chat_completions_batch(
        self,
        *,
        model: str,
        prompts: list[str],
        backend: str,
        max_tokens: int,
        temperature: float,
        response_format: str | None = None,
        lora_adapter: str | None = None,
    ) -> list[str]:
        """Run a batch of chat completion prompts and return the text results."""
        ...

    @abstractmethod
    async def generate_stream(self, request) -> Any:
        """Run a raw generation request with streaming."""
        ...

    @abstractmethod
    async def chat(self, request) -> Any:
        """Run a chat request."""
        ...

    @abstractmethod
    async def chat_stream(self, request) -> Any:
        """Run a chat request with streaming."""
        ...

    @abstractmethod
    async def get_cache_status(self) -> Any:
        """Return inference cache status."""
        ...

    @abstractmethod
    async def clear_cache(self) -> Any:
        """Clear the inference cache."""
        ...

    @abstractmethod
    async def get_performance_stats(self, model_id: str | None = None) -> Any:
        """Return inference performance statistics."""
        ...

    @abstractmethod
    async def get_performance_recommendations(self) -> Any:
        """Return performance recommendations."""
        ...

    @abstractmethod
    async def clear_performance_history(self) -> Any:
        """Clear the performance history."""
        ...

    @abstractmethod
    async def get_performance_prometheus(self) -> Any:
        """Return Prometheus-compatible performance metrics."""
        ...

    @abstractmethod
    async def get_metrics_alias(self) -> Any:
        """Alias for Prometheus-compatible metrics."""
        ...


class LocalInferenceGateway(InferenceGateway):
    """Inference gateway that calls the in-process scheduler directly."""

    async def chat_completions(self, request, raw_request=None) -> Any:
        from api.inference.openai_routes import chat_completions

        return await chat_completions(request, raw_request)

    async def list_models(self, backend: str | None = None) -> Any:
        from api.inference.routes import list_models

        return await list_models(backend)

    async def openai_list_models(self) -> Any:
        from api.inference.openai_routes import list_models

        return await list_models()

    async def list_backends(self) -> Any:
        from api.inference.routes import list_backends

        return await list_backends()

    async def ollama_status(self) -> Any:
        from api.inference.routes import get_ollama_status

        return await get_ollama_status()

    async def generate(self, request) -> Any:
        from api.inference.routes import generate

        return await generate(request)

    async def generate_stream(self, request) -> Any:
        from api.inference.routes import generate_stream

        return await generate_stream(request)

    async def chat(self, request) -> Any:
        from api.inference.routes import chat

        return await chat(request)

    async def chat_stream(self, request) -> Any:
        from api.inference.routes import chat_stream

        return await chat_stream(request)

    async def get_cache_status(self) -> Any:
        from api.inference.routes import get_cache_status

        return await get_cache_status()

    async def clear_cache(self) -> Any:
        from api.inference.routes import clear_cache

        return await clear_cache()

    async def get_performance_stats(self, model_id: str | None = None) -> Any:
        from api.inference.routes import get_performance_stats

        return await get_performance_stats(model_id)

    async def get_performance_recommendations(self) -> Any:
        from api.inference.routes import get_performance_recommendations

        return await get_performance_recommendations()

    async def clear_performance_history(self) -> Any:
        from api.inference.routes import clear_performance_history

        return await clear_performance_history()

    async def get_performance_prometheus(self) -> Any:
        from api.inference.routes import get_performance_prometheus

        return await get_performance_prometheus()

    async def get_metrics_alias(self) -> Any:
        from api.inference.routes import get_metrics_alias

        return await get_metrics_alias()

    async def chat_completions_batch(
        self,
        *,
        model: str,
        prompts: list[str],
        backend: str,
        max_tokens: int,
        temperature: float,
        response_format: str | None = None,
        lora_adapter: str | None = None,
    ) -> list[str]:
        from api.inference.backends.base import GenerationConfig
        from api.inference.scheduler import get_scheduler

        scheduler = get_scheduler()
        backend_instance = await scheduler.get_backend(backend)
        leased_model = None

        if backend != "cloud":
            model_path = (
                scheduler.resolve_model_path(model, backend)
                if hasattr(scheduler, "resolve_model_path")
                else model
            )
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

            sem = asyncio.Semaphore(10)

            async def _single(msgs):
                async with sem:
                    response = await backend_instance.chat(msgs, config)
                    return response.text if hasattr(response, "text") else str(response)

            return await asyncio.gather(*(_single(msgs) for msgs in messages_list))
        finally:
            if leased_model is not None and hasattr(scheduler, "release_model"):
                await scheduler.release_model(model)


class ServiceInferenceGateway(InferenceGateway):
    """Inference gateway that delegates to the local inference service."""

    def __init__(self):
        from inference_provider.client import get_inference_service_client

        self._client = get_inference_service_client()

    @staticmethod
    def _json_response(response) -> Any:
        return json.loads(response.content)

    @staticmethod
    def _unavailable_status(exc: Exception) -> dict[str, Any]:
        return {
            "available": False,
            "code": getattr(exc, "code", "inference_service_unavailable"),
            "message": str(exc) or "Local inference service unavailable",
        }

    async def chat_completions(self, request, raw_request=None) -> Any:
        import json as _json

        body = _json.dumps(request.model_dump() if hasattr(request, "model_dump") else dict(request))
        headers = {"Content-Type": "application/json"}
        if raw_request is not None:
            headers["X-Backend"] = raw_request.headers.get("X-Backend") or ""
        response = await self._client.request(
            "POST",
            "/v1/chat/completions",
            content=body.encode("utf-8"),
            headers=headers,
        )
        return self._json_response(response)

    async def list_models(self, backend: str | None = None) -> Any:
        params = {}
        if backend:
            params["backend"] = backend
        response = await self._client.request("GET", "/inference/models", params=params)
        return self._json_response(response)

    async def openai_list_models(self) -> Any:
        response = await self._client.request("GET", "/v1/models")
        return self._json_response(response)

    async def list_backends(self) -> Any:
        from inference_provider.client import InferenceServiceTimeout, InferenceServiceUnavailable

        try:
            response = await self._client.request("GET", "/inference/backends")
            return self._json_response(response)
        except (InferenceServiceTimeout, InferenceServiceUnavailable) as exc:
            return {
                "current": None,
                "backends": [],
                "service": self._unavailable_status(exc),
            }

    async def ollama_status(self) -> Any:
        response = await self._client.request("GET", "/inference/ollama/status")
        return self._json_response(response)

    async def generate(self, request) -> Any:
        import json as _json

        body = _json.dumps(request.model_dump() if hasattr(request, "model_dump") else dict(request))
        response = await self._client.request(
            "POST",
            "/inference/generate",
            content=body.encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        return self._json_response(response)

    async def generate_stream(self, request) -> Any:
        import json as _json

        from fastapi.responses import StreamingResponse

        body = _json.dumps(request.model_dump() if hasattr(request, "model_dump") else dict(request))
        response = await self._client.open_stream(
            "POST",
            "/inference/generate/stream",
            content=body.encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        return StreamingResponse(
            response.aiter_raw(),
            status_code=response.status_code,
            headers={k: v for k, v in response.headers.items() if k.lower() in {"content-type"}},
        )

    async def chat(self, request) -> Any:
        import json as _json

        body = _json.dumps(request.model_dump() if hasattr(request, "model_dump") else dict(request))
        response = await self._client.request(
            "POST",
            "/inference/chat",
            content=body.encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        return self._json_response(response)

    async def chat_stream(self, request) -> Any:
        import json as _json

        from fastapi.responses import StreamingResponse

        body = _json.dumps(request.model_dump() if hasattr(request, "model_dump") else dict(request))
        response = await self._client.open_stream(
            "POST",
            "/inference/chat/stream",
            content=body.encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        return StreamingResponse(
            response.aiter_raw(),
            status_code=response.status_code,
            headers={k: v for k, v in response.headers.items() if k.lower() in {"content-type"}},
        )

    async def get_cache_status(self) -> Any:
        return await self._client.get_json("/inference/cache/status")

    async def clear_cache(self) -> Any:
        import json as _json

        response = await self._client.request("POST", "/inference/cache/clear")
        return _json.loads(response.content)

    async def get_performance_stats(self, model_id: str | None = None) -> Any:
        from inference_provider.client import InferenceServiceTimeout, InferenceServiceUnavailable

        params = {}
        if model_id:
            params["model_id"] = model_id
        try:
            return await self._client.get_json("/inference/performance", params=params)
        except (InferenceServiceTimeout, InferenceServiceUnavailable) as exc:
            return {
                "inference": {},
                "streaming": {},
                "service": self._unavailable_status(exc),
            }

    async def get_performance_recommendations(self) -> Any:
        from inference_provider.client import InferenceServiceTimeout, InferenceServiceUnavailable

        try:
            return await self._client.get_json("/inference/performance/recommendations")
        except (InferenceServiceTimeout, InferenceServiceUnavailable) as exc:
            return {
                "recommendations": [],
                "device_info": {},
                "hardware_profile": {},
                "service": self._unavailable_status(exc),
            }

    async def clear_performance_history(self) -> Any:
        import json as _json

        response = await self._client.request("POST", "/inference/performance/clear")
        return _json.loads(response.content)

    async def get_performance_prometheus(self) -> Any:
        from fastapi.responses import StreamingResponse

        response = await self._client.open_stream("GET", "/inference/performance/prometheus")
        return StreamingResponse(
            response.aiter_raw(),
            status_code=response.status_code,
            headers={k: v for k, v in response.headers.items() if k.lower() in {"content-type"}},
        )

    async def get_metrics_alias(self) -> Any:
        return await self._client.get_json("/inference/metrics")

    async def chat_completions_batch(
        self,
        *,
        model: str,
        prompts: list[str],
        backend: str,
        max_tokens: int,
        temperature: float,
        response_format: str | None = None,
        lora_adapter: str | None = None,
    ) -> list[str]:
        import json as _json

        from inference_provider.client import InferenceServiceError

        client = self._client
        canonical_model = model if "/" in model else f"{backend}/{model}"
        semaphore = asyncio.Semaphore(10)

        async def remote_call(prompt: str) -> str:
            async with semaphore:
                remote_model = model
                headers = {"Content-Type": "application/json", "X-Backend": backend}
                model_path_obj = Path(model)
                if model_path_obj.exists():
                    remote_model = model_path_obj.name
                    headers["X-Model-Path"] = str(model)
                if lora_adapter:
                    headers["X-LoRA-Adapter"] = lora_adapter
                request_payload = {
                    "model": remote_model if model_path_obj.exists() else canonical_model,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_completion_tokens": max_tokens,
                    "temperature": temperature,
                    "stream": False,
                }
                response = await client.request(
                    "POST",
                    "/v1/chat/completions",
                    content=_json.dumps(request_payload, ensure_ascii=False).encode(),
                    headers=headers,
                )
                if response.status_code >= 400:
                    raise InferenceServiceError(
                        f"Inference service returned HTTP {response.status_code}: "
                        f"{response.content.decode(errors='replace')}"
                    )
                payload = _json.loads(response.content)
                choices = payload.get("choices") or []
                return str((choices[0].get("message") or {}).get("content") or "") if choices else ""

        return await asyncio.gather(*(remote_call(prompt) for prompt in prompts))




def get_inference_gateway() -> InferenceGateway:
    """Return the active inference gateway based on current settings."""
    if settings.inference_execution_mode == "service":
        return ServiceInferenceGateway()
    return LocalInferenceGateway()
