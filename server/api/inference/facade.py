"""Unified inference facade.

This module exposes the inference endpoints that are registered regardless of
whether the application is running in ``in_process`` or ``service`` mode. The
gateway dispatches to the correct implementation at runtime, which keeps router
registration independent of ``inference_execution_mode``.
"""

from __future__ import annotations

from fastapi import APIRouter, Query
from fastapi import Request as FastAPIRequest

from api.inference.openai_schemas import ChatCompletionRequest
from api.types import BackendSwitchRequest, ChatRequest, GenerateRequest
from core.inference_gateway import get_inference_gateway

router = APIRouter(tags=["Inference"])
openai_router = APIRouter(tags=["OpenAI Compatible API"])


@router.get("/models")
async def list_models():
    """List available models through the active inference gateway."""
    return await get_inference_gateway().list_models()


@router.get("/backends")
async def list_backends():
    """List available inference backends."""
    return await get_inference_gateway().list_backends()


@router.post("/backends/switch")
async def switch_backend(request: BackendSwitchRequest):
    """Switch the active inference backend."""
    from api.inference.routes import switch_backend

    return await switch_backend(request)


@router.get("/ollama/status")
async def ollama_status():
    """Return Ollama backend status."""
    return await get_inference_gateway().ollama_status()


@router.post("/generate")
async def generate(request: GenerateRequest):
    """Run a raw generation request through the active inference gateway."""
    return await get_inference_gateway().generate(request)


@router.post("/generate/stream")
async def generate_stream(request: GenerateRequest):
    """Run a raw generation request with streaming."""
    return await get_inference_gateway().generate_stream(request)


@router.post("/chat")
async def chat(request: ChatRequest):
    """Run a chat request through the active inference gateway."""
    return await get_inference_gateway().chat(request)


@router.post("/chat/stream")
async def chat_stream(request: ChatRequest):
    """Run a chat request with streaming."""
    return await get_inference_gateway().chat_stream(request)


@router.get("/cache/status")
async def get_cache_status():
    """Return inference cache status."""
    return await get_inference_gateway().get_cache_status()


@router.post("/cache/clear")
async def clear_cache():
    """Clear the inference cache."""
    return await get_inference_gateway().clear_cache()


@router.get("/performance")
async def get_performance_stats(model_id: str | None = Query(None)):
    """Return inference performance statistics."""
    return await get_inference_gateway().get_performance_stats(model_id)


@router.get("/performance/recommendations")
async def get_performance_recommendations():
    """Return performance recommendations."""
    return await get_inference_gateway().get_performance_recommendations()


@router.post("/performance/clear")
async def clear_performance_history():
    """Clear the performance history."""
    return await get_inference_gateway().clear_performance_history()


@router.get("/performance/prometheus")
async def get_performance_prometheus():
    """Return Prometheus-compatible performance metrics."""
    return await get_inference_gateway().get_performance_prometheus()


@router.get("/metrics")
async def get_metrics_alias():
    """Alias for Prometheus-compatible metrics."""
    return await get_inference_gateway().get_metrics_alias()


@openai_router.get("/v1/models")
async def openai_list_models():
    """OpenAI-compatible model list endpoint."""
    return await get_inference_gateway().openai_list_models()


@openai_router.post("/v1/chat/completions")
async def openai_chat_completions(request: ChatCompletionRequest, raw_request: FastAPIRequest):
    """OpenAI-compatible chat completions endpoint."""
    return await get_inference_gateway().chat_completions(request, raw_request)
