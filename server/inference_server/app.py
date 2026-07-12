from __future__ import annotations

import hmac
import logging
from contextlib import asynccontextmanager
from datetime import datetime

import torch
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from core.config import settings

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    from security.runtime_policy import assert_inference_internal_key_safe

    # Fail-closed for production/staging default keys (shared policy with control plane).
    assert_inference_internal_key_safe(settings)
    settings.models_dir_resolved.mkdir(parents=True, exist_ok=True)
    settings.outputs_dir_resolved.mkdir(parents=True, exist_ok=True)
    logger.info("Isolated inference service initialized")
    grpc_server = None
    if settings.enable_inference_grpc:
        from api.inference.grpc_server import get_inference_grpc_server

        grpc_server = get_inference_grpc_server(
            settings.inference_grpc_host,
            settings.inference_grpc_port,
        )
        await grpc_server.start()
    try:
        yield
    finally:
        if grpc_server is not None:
            await grpc_server.stop()
        from api.inference.pipeline import get_local_inference_pipeline
        from api.inference.routes import get_scheduler

        await get_local_inference_pipeline().shutdown()
        await get_scheduler().shutdown()
        logger.info("Isolated inference service shutdown complete")


app = FastAPI(
    title="Finetune Platform Local Inference Service",
    version="1.0.0",
    docs_url=None,
    redoc_url=None,
    lifespan=lifespan,
)


@app.middleware("http")
async def internal_authentication(request: Request, call_next):
    if request.url.path == "/health":
        return await call_next(request)
    authorization = request.headers.get("Authorization", "")
    expected = f"Bearer {settings.inference_internal_api_key}"
    if not hmac.compare_digest(authorization, expected):
        return JSONResponse(
            status_code=401,
            content={
                "error": {
                    "message": "Invalid internal inference credential",
                    "type": "authentication_error",
                    "param": None,
                    "code": "invalid_internal_api_key",
                }
            },
            headers={"WWW-Authenticate": "Bearer"},
        )
    return await call_next(request)


@app.exception_handler(HTTPException)
async def http_exception_handler(_request: Request, exc: HTTPException):
    if isinstance(exc.detail, dict) and "error" in exc.detail:
        return JSONResponse(status_code=exc.status_code, content=exc.detail)
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "message": str(exc.detail),
                "type": "server_error" if exc.status_code >= 500 else "invalid_request_error",
                "param": None,
                "code": "http_error",
            }
        },
    )


@app.exception_handler(RequestValidationError)
async def validation_error_handler(_request: Request, exc: RequestValidationError):
    error = exc.errors()[0] if exc.errors() else {}
    return JSONResponse(
        status_code=400,
        content={
            "error": {
                "message": str(error.get("msg") or "Invalid request"),
                "type": "invalid_request_error",
                "param": ".".join(str(item) for item in error.get("loc", ()) if item != "body") or None,
                "code": str(error.get("type") or "validation_error"),
            }
        },
    )


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "service": "local-inference",
        "timestamp": datetime.now().isoformat(),
        "cuda_available": bool(torch.cuda.is_available()),
    }


@app.get("/internal/capabilities")
async def capabilities():
    from agent_session.model_capabilities import build_inference_tool_calling_features
    from api.inference.openai_routes import list_models
    from api.inference.routes import list_backends

    backend_payload = await list_backends()
    try:
        model_payload = (await list_models()).model_dump()
    except Exception as exc:
        logger.warning("Inference model capability discovery failed: %s", exc)
        model_payload = {"object": "list", "data": []}
    tool_features = build_inference_tool_calling_features(settings)
    return {
        "schema_version": "inference.capabilities.v1",
        "api": {
            "chat_completions": "/v1/chat/completions",
            "models": "/v1/models",
            "streaming": True,
            "batch": True,
        },
        "features": {
            "chat": True,
            "streaming": True,
            "tool_calling": tool_features["tool_calling"],
            "tool_calling_by_backend": tool_features["tool_calling_by_backend"],
            "tool_calling_details": tool_features["tool_calling_details"],
            "vision": False,
            "json_mode": False,
        },
        "limits": {
            "max_read_timeout_seconds": settings.inference_service_read_timeout_seconds,
            "network_scope": "loopback_or_private_container_network",
        },
        "backends": backend_payload,
        "models": model_payload.get("data", []),
    }


from api.inference.routes import router as inference_router  # noqa: E402
from api.inference.openai_routes import router as openai_router  # noqa: E402
from api.inference_engine import router as inference_engine_router  # noqa: E402
from api.model_runtime import router as model_runtime_router  # noqa: E402

app.include_router(openai_router)
app.include_router(inference_router, prefix="/inference")
app.include_router(model_runtime_router, prefix="/model-runtime")
app.include_router(inference_engine_router)


__all__ = ["app"]
