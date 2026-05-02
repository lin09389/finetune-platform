"""统一本地推理服务层。"""
from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator
from typing import Any

from api.inference.backends.base import GenerationConfig
from api.inference.pipeline import get_local_inference_pipeline
from api.inference.scheduler import BackendType, get_scheduler
from core.offline_cache import get_offline_cache
from inference_service.callbacks import CancellationToken, ProgressCallback
from inference_service.types import LocalInferenceProgress, LocalInferenceRequest, LocalInferenceResponse


class LocalInferenceService:
    async def generate(
        self,
        request: LocalInferenceRequest,
        progress_callback: ProgressCallback | None = None,
        cancellation_token: CancellationToken | None = None,
    ) -> LocalInferenceResponse:
        request_id = request.request_id or str(uuid.uuid4())
        scheduler = get_scheduler()
        backend_name = request.backend or scheduler.get_stats().get("default_backend", BackendType.HUGGINGFACE.value)
        backend = await scheduler.get_backend(backend_name)
        model_path = scheduler.resolve_model_path(request.model, backend_name)
        lease = None

        try:
            if backend_name != BackendType.CLOUD.value:
                lease = await scheduler.acquire_model(
                    request.model,
                    model_path,
                    backend_name,
                    **request.options,
                )
                if lease is None:
                    raise RuntimeError(f"模型加载失败: {request.model}")

            if hasattr(backend, "model_name"):
                backend.model_name = request.model

            config = GenerationConfig(
                max_tokens=request.options.get("max_tokens", 256),
                temperature=request.options.get("temperature", 0.7),
                top_p=request.options.get("top_p", 0.9),
                top_k=request.options.get("top_k", 50),
                repetition_penalty=request.options.get("repetition_penalty", 1.0),
                stop_sequences=request.options.get("stop", []) or [],
                stream=request.stream,
            )

            if progress_callback:
                await _emit_progress(
                    progress_callback,
                    LocalInferenceProgress(
                        request_id=request_id,
                        backend=backend_name,
                        model=request.model,
                        status="started",
                    ),
                )

            if request.messages:
                result = await backend.chat(request.messages, config)
            else:
                result = await backend.generate(request.prompt or "", config)

            if cancellation_token and cancellation_token.cancelled:
                raise asyncio.CancelledError()

            if progress_callback:
                await _emit_progress(
                    progress_callback,
                    LocalInferenceProgress(
                        request_id=request_id,
                        backend=backend_name,
                        model=request.model,
                        status="completed",
                        emitted_tokens=result.tokens_generated,
                        metadata=result.metadata or {},
                    ),
                )

            return LocalInferenceResponse(
                request_id=request_id,
                backend=backend_name,
                model=result.model or request.model,
                content=result.text,
                metadata=result.metadata or {},
            )
        finally:
            if lease is not None:
                await scheduler.release_model(request.model)

    async def generate_stream(
        self,
        request: LocalInferenceRequest,
        progress_callback: ProgressCallback | None = None,
        cancellation_token: CancellationToken | None = None,
    ) -> AsyncIterator[str]:
        request_id = request.request_id or str(uuid.uuid4())
        scheduler = get_scheduler()
        backend_name = request.backend or scheduler.get_stats().get("default_backend", BackendType.HUGGINGFACE.value)
        backend = await scheduler.get_backend(backend_name)
        model_path = scheduler.resolve_model_path(request.model, backend_name)
        lease = None
        emitted_tokens = 0

        try:
            if backend_name != BackendType.CLOUD.value:
                lease = await scheduler.acquire_model(
                    request.model,
                    model_path,
                    backend_name,
                    **request.options,
                )
                if lease is None:
                    raise RuntimeError(f"模型加载失败: {request.model}")

            if hasattr(backend, "model_name"):
                backend.model_name = request.model

            config = GenerationConfig(
                max_tokens=request.options.get("max_tokens", 256),
                temperature=request.options.get("temperature", 0.7),
                top_p=request.options.get("top_p", 0.9),
                top_k=request.options.get("top_k", 50),
                repetition_penalty=request.options.get("repetition_penalty", 1.0),
                stop_sequences=request.options.get("stop", []) or [],
                stream=True,
            )

            if progress_callback:
                await _emit_progress(
                    progress_callback,
                    LocalInferenceProgress(
                        request_id=request_id,
                        backend=backend_name,
                        model=request.model,
                        status="started",
                    ),
                )

            iterator = backend.chat_stream(request.messages, config) if request.messages else backend.generate_stream(request.prompt or "", config)
            async for chunk in iterator:
                if cancellation_token and cancellation_token.cancelled:
                    raise asyncio.CancelledError()
                emitted_tokens += 1
                if progress_callback:
                    await _emit_progress(
                        progress_callback,
                        LocalInferenceProgress(
                            request_id=request_id,
                            backend=backend_name,
                            model=request.model,
                            status="streaming",
                            emitted_tokens=emitted_tokens,
                        ),
                    )
                yield chunk

            if progress_callback:
                await _emit_progress(
                    progress_callback,
                    LocalInferenceProgress(
                        request_id=request_id,
                        backend=backend_name,
                        model=request.model,
                        status="completed",
                        emitted_tokens=emitted_tokens,
                    ),
                )
        finally:
            if lease is not None:
                await scheduler.release_model(request.model)

    async def generate_cached(self, request: LocalInferenceRequest) -> LocalInferenceResponse:
        cache = get_offline_cache()
        cache_key = cache.build_key(
            "local-inference",
            {
                "backend": request.backend,
                "model": request.model,
                "prompt": request.prompt,
                "messages": request.messages,
                "options": request.options,
            },
        )
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

        response = await self.generate(request)
        cache.set(cache_key, response)
        return response

    async def submit_batched(self, request: LocalInferenceRequest) -> LocalInferenceResponse:
        async def executor():
            response = await self.generate(request)
            return response

        response = await get_local_inference_pipeline().submit(
            pipeline_key=f"{request.backend}:{request.model}:service",
            prompt=request.prompt or (request.messages[-1]["content"] if request.messages else ""),
            max_batch_size=min(request.options.get("num_batch", 1), 8),
            max_wait_ms=50,
            timeout=90.0,
            executor=executor,
        )
        return response


async def _emit_progress(callback: ProgressCallback, payload: LocalInferenceProgress) -> None:
    result = callback(payload)
    if asyncio.iscoroutine(result):
        await result


_service: LocalInferenceService | None = None


def get_local_inference_service() -> LocalInferenceService:
    global _service
    if _service is None:
        _service = LocalInferenceService()
    return _service
