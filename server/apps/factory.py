"""Shared FastAPI application factory for all backend deployment profiles."""

from __future__ import annotations

import json
import logging
import os
import re
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from core.config import settings
from core.logging import setup_logging
from core.tracing import trace_id_var, user_id_var
from security.rate_limiter import get_rate_limiter

from .lifespan import create_lifespan
from .profiles import ApplicationProfile, coerce_profile
from .routers import register_profile_routers


class UnicodeJSONResponse(JSONResponse):
    def render(self, content) -> bytes:
        return json.dumps(
            content,
            ensure_ascii=False,
            allow_nan=False,
            indent=None,
            separators=(",", ":"),
        ).encode("utf-8")


LOG_DIR = Path(__file__).resolve().parents[2] / "logs"
LOG_DIR.mkdir(exist_ok=True)
logger = setup_logging(
    log_dir=LOG_DIR,
    log_level=os.getenv("LOG_LEVEL", "INFO"),
    enable_json=os.getenv("LOG_FORMAT", "text") == "json",
)
logger.info("=" * 50)
logger.info("Finetune Platform Backend Starting")
logger.info("=" * 50)
logger.info("Python: %s", sys.version)
logger.info("Working Directory: %s", os.getcwd())
logger.info("Log Level: %s", logging.getLevelName(logger.level))

DEBUG_MODE = os.getenv("DEBUG", "false").lower() == "true"
_rate_limiter = get_rate_limiter()

_DEFAULT_DEV_CORS_ORIGINS = [
    "http://localhost:3000",
    "http://localhost:5173",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:5173",
]
_PUBLIC_PATHS = {
    "/",
    "/health",
    "/api/info",
    "/openapi.json",
    "/docs",
    "/redoc",
    "/auth/login",
    "/auth/register",
    "/auth/refresh",
}
_LOCAL_AGENT_AUTH_FALLBACK_PREFIXES = (
    "/agents",
    "/agent-sessions",
    "/agent-permissions",
    "/agent-actions",
)
IP_BLACKLIST = {"1.2.3.4", "5.6.7.8"}
WAF_RULES = [
    re.compile(r"union\s+select", re.I),
    re.compile(r"<script>.*?</script>", re.I),
    re.compile(r"(\.\./){3,}", re.I),
]
WAF_BODY_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
WAF_BODY_CONTENT_TYPES = (
    "application/json",
    "application/x-www-form-urlencoded",
    "text/plain",
    "application/xml",
    "text/xml",
)


def _build_cors_origins(origins) -> list[str]:
    if isinstance(origins, list):
        normalized = [origin for origin in origins if origin]
    elif isinstance(origins, str):
        normalized = [origins]
    else:
        normalized = list(_DEFAULT_DEV_CORS_ORIGINS)
    if "*" in normalized:
        return normalized
    if settings.environment == "development":
        for origin in _DEFAULT_DEV_CORS_ORIGINS:
            if origin not in normalized:
                normalized.append(origin)
    return normalized


_cors_origins = _build_cors_origins(settings.allowed_origins)
if "*" in _cors_origins:
    logger.warning(
        "SECURITY: CORS allow_origins contains wildcard '*'. "
        "Disabling allow_credentials to prevent security risks."
    )
    _allow_credentials = False
else:
    _allow_credentials = True


def check_rate_limit(client_ip: str, path: str = "") -> tuple[bool, dict]:
    if os.getenv("ENABLE_RATE_LIMIT", "true").lower() == "false":
        return True, {}
    return _rate_limiter.is_allowed(client_ip, endpoint=path)


def _cors_response_headers_for_request(request: Request) -> dict[str, str]:
    origin = request.headers.get("origin")
    if not origin:
        return {}
    if "*" not in _cors_origins and origin not in _cors_origins:
        return {}
    headers = {
        "Access-Control-Allow-Origin": (
            "*" if "*" in _cors_origins and not _allow_credentials else origin
        ),
        "Vary": "Origin",
    }
    if _allow_credentials:
        headers["Access-Control-Allow-Credentials"] = "true"
    return headers


def _allows_local_agent_auth_fallback(path: str) -> bool:
    return settings.environment == "development" and path.startswith(
        _LOCAL_AGENT_AUTH_FALLBACK_PREFIXES
    )


def _authentication_error_response(request: Request, message: str) -> JSONResponse:
    path = request.url.path.rstrip("/") or "/"
    content = (
        {
            "error": {
                "message": message,
                "type": "authentication_error",
                "param": None,
                "code": "invalid_api_key",
            }
        }
        if path.startswith("/v1/")
        else {"detail": message}
    )
    return JSONResponse(
        status_code=401,
        content=content,
        headers={
            "WWW-Authenticate": "Bearer",
            **_cors_response_headers_for_request(request),
        },
    )


async def authentication_middleware(request: Request, call_next):
    if not settings.enable_auth or request.method == "OPTIONS":
        return await call_next(request)
    path = request.url.path.rstrip("/") or "/"
    if (
        path in _PUBLIC_PATHS
        or path.startswith("/docs/")
        or path.startswith("/redoc/")
        or _allows_local_agent_auth_fallback(path)
    ):
        return await call_next(request)
    authorization = request.headers.get("Authorization", "")
    if not authorization.startswith("Bearer "):
        return _authentication_error_response(request, "Missing bearer token")
    from security.jwt_auth import get_jwt_auth

    try:
        payload = get_jwt_auth().verify_token(authorization[7:].strip())
    except Exception:
        payload = None
    if payload is None:
        return _authentication_error_response(request, "Invalid or expired token")
    return await call_next(request)


async def trace_middleware(request: Request, call_next):
    trace_id = request.headers.get("X-Trace-Id", str(uuid.uuid4()))
    trace_id_var.set(trace_id)
    user_id_var.set(request.headers.get("X-User-Id", "anonymous"))
    response = await call_next(request)
    response.headers["X-Trace-Id"] = trace_id
    return response


async def security_middleware(request: Request, call_next):
    client_ip = request.client.host if request.client else "unknown"
    path = request.url.path
    if client_ip in IP_BLACKLIST:
        logger.warning("Blocked request from blacklisted IP: %s", client_ip)
        return JSONResponse(
            status_code=403,
            content={"error": "Forbidden", "detail": "Your IP is blacklisted"},
        )

    payload = str(request.query_params)
    content_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if request.method.upper() in WAF_BODY_METHODS and content_type in WAF_BODY_CONTENT_TYPES:
        body = await request.body()
        if body:
            payload += body.decode("utf-8", errors="ignore")
    for rule in WAF_RULES:
        if rule.search(payload):
            logger.warning("Blocked malicious payload from IP: %s", client_ip)
            return JSONResponse(
                status_code=400,
                content={"error": "Bad Request", "detail": "Malicious payload detected"},
            )

    if path not in ["/health", "/", "/favicon.ico"]:
        allowed, rate_info = check_rate_limit(client_ip, path)
        if not allowed:
            retry_after = rate_info.get("retry_after", 60)
            return JSONResponse(
                status_code=429,
                content={
                    "error": rate_info.get("error", "rate_limit_exceeded"),
                    "detail": rate_info.get("message", "Too many requests"),
                    "retry_after": retry_after,
                },
                headers={
                    "Retry-After": str(retry_after),
                    "Access-Control-Allow-Origin": request.headers.get("origin", "*"),
                    "Access-Control-Allow-Credentials": "true",
                },
            )
    try:
        return await call_next(request)
    except Exception as exc:
        debug_mode = os.getenv("DEBUG", "false").lower() == "true"
        logger.error("Request error: %s", exc, exc_info=debug_mode)
        return JSONResponse(
            status_code=500,
            content={
                "error": "Internal server error",
                "detail": str(exc) if debug_mode else "An unexpected error occurred",
            },
            headers={
                "Access-Control-Allow-Origin": request.headers.get("origin", "*"),
                "Access-Control-Allow-Credentials": "true",
            },
        )


async def logging_middleware(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    response.headers["X-Process-Time"] = f"{time.time() - start_time:.4f}"
    return response


async def security_headers_middleware(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' 'unsafe-eval'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data: blob:; "
        "connect-src 'self' ws: wss: http: https:; "
        "font-src 'self' data:; "
        "frame-ancestors 'none'"
    )
    if not DEBUG_MODE and "server" in response.headers:
        del response.headers["server"]
    return response


async def root():
    return {
        "message": "Finetune Platform API",
        "version": "1.0.0",
        "api_version": "2.0.0",
        "docs": "/docs",
        "health": "/health",
    }


async def health_check():
    return await _health_payload(include_accelerator=True)


async def _health_payload(include_accelerator: bool) -> dict:
    health = {
        "status": "ok",
        "service_status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "version": "2.0.0",
        "cuda_available": False,
        "intent_backend_status": "disabled",
    }
    if not include_accelerator:
        return health
    import torch

    health["cuda_available"] = torch.cuda.is_available() if hasattr(torch, "cuda") else False
    if torch.cuda.is_available():
        try:
            properties = torch.cuda.get_device_properties(0)
            health["gpu_info"] = {
                "device_name": properties.name,
                "memory": {
                    "total_gb": round(properties.total_memory / (1024**3), 2),
                    "allocated_gb": round(torch.cuda.memory_allocated(0) / (1024**3), 2),
                    "reserved_gb": round(torch.cuda.memory_reserved(0) / (1024**3), 2),
                },
            }
        except Exception as exc:
            logger.warning("Failed to get GPU info: %s", exc)
            health["gpu_info"] = {"error": str(exc)}
    return health


async def api_info():
    return {
        "name": "Finetune Platform API",
        "version": "2.1.0",
        "description": "Finetune Platform backend API with core, beta, and experimental capability tiers",
        "features": [
            "LoRA/QLoRA fine-tuning",
            "Model and dataset lifecycle",
            "Inference service with backend switching",
            "Chat sessions and knowledge retrieval",
            "Workspace and local AI tooling",
        ],
        "capability_tiers": {
            "ga": [
                "device",
                "models",
                "datasets",
                "training",
                "inference",
                "chat_sessions",
                "knowledge_base",
            ],
            "beta": ["project_context", "memory", "model_center", "workspace"],
            "experimental": [
                "cua",
                "heartbeat",
                "mcp",
                "gateway",
                "ocr_fallbacks",
                "action_recorder",
            ],
        },
        "training_runtime": {
            "execution_mode": settings.training_execution_mode,
            "queue": "sqlite" if settings.training_execution_mode == "worker" else "in_process",
            "worker_command": "uv run python -m server.training_worker",
        },
        "inference_runtime": {
            "execution_mode": settings.inference_execution_mode,
            "service_url": settings.inference_service_url,
            "worker_command": "uv run python -m server.inference_server",
            "cloud_fallback_enabled": settings.inference_cloud_fallback_enabled,
        },
        "endpoints": {
            "device": "/device",
            "models": "/models",
            "datasets": "/datasets",
            "training": "/training",
            "inference": "/inference",
            "chat": "/chat/sessions",
            "knowledge": "/knowledge",
            "runtime": "/runtime/bootstrap",
            "memory": "/memory",
            "workspace": "/workspace",
            "context": "/context",
            "model_center": "/model-center",
            "experimental": {
                "cua": "/cua",
                "mcp": "/mcp",
                "gateway": "/gateway",
                "heartbeat": "/heartbeat",
                "ocr": "/ocr",
            },
        },
    }


async def custom_api_error_handler(request: Request, exc):
    logger.warning("API Error: %s - %s", exc.code, exc.message)
    return JSONResponse(status_code=exc.status_code, content=exc.to_dict())


async def request_validation_error_handler(request: Request, exc: RequestValidationError):
    if request.url.path.startswith("/v1/"):
        first_error = exc.errors()[0] if exc.errors() else {}
        location = [str(item) for item in first_error.get("loc", ()) if item != "body"]
        return JSONResponse(
            status_code=400,
            content={
                "error": {
                    "message": str(first_error.get("msg") or "Invalid request"),
                    "type": "invalid_request_error",
                    "param": ".".join(location) or None,
                    "code": str(first_error.get("type") or "validation_error"),
                }
            },
        )
    return await request_validation_exception_handler(request, exc)


async def http_exception_handler(request: Request, exc: HTTPException):
    logger.warning("HTTP Exception: %s - %s", exc.status_code, exc.detail)
    if isinstance(exc.detail, dict) and "error" in exc.detail:
        return JSONResponse(status_code=exc.status_code, content=exc.detail)
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": "http_error",
                "message": str(exc.detail),
                "details": {},
            }
        },
    )


async def general_exception_handler(request: Request, exc: Exception):
    logger.error("Unhandled exception: %s", exc, exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error", "detail": "服务器内部错误，请查看日志获取详情"},
    )


def _register_common_behavior(app: FastAPI, profile: ApplicationProfile) -> None:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins,
        allow_credentials=_allow_credentials,
        allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
        allow_headers=[
            "Authorization",
            "Content-Type",
            "X-Backend",
            "X-Requested-With",
            "X-Trace-Id",
        ],
    )
    app.middleware("http")(authentication_middleware)
    app.middleware("http")(trace_middleware)
    app.middleware("http")(security_middleware)
    app.middleware("http")(logging_middleware)
    app.middleware("http")(security_headers_middleware)

    app.add_api_route("/", root, methods=["GET"])
    profile_health = health_check
    if profile is ApplicationProfile.AGENT:
        async def agent_health_check():
            return await _health_payload(include_accelerator=False)

        profile_health = agent_health_check
    app.add_api_route("/health", profile_health, methods=["GET"], name="health_check")
    app.add_api_route("/api/info", api_info, methods=["GET"])

    from api.errors import APIError

    app.add_exception_handler(APIError, custom_api_error_handler)
    app.add_exception_handler(RequestValidationError, request_validation_error_handler)
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(Exception, general_exception_handler)


def create_application(profile: ApplicationProfile | str) -> FastAPI:
    resolved = coerce_profile(profile)
    title_suffix = "" if resolved is ApplicationProfile.COMBINED else f" ({resolved.value})"
    app = FastAPI(
        title=f"Finetune Platform API{title_suffix}",
        description="Finetune Platform API - LoRA/QLoRA fine-tuning and Agent workspace",
        version="2.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=create_lifespan(resolved),
        default_response_class=UnicodeJSONResponse,
    )
    app.state.profile = resolved.value
    register_profile_routers(app, resolved)
    _register_common_behavior(app, resolved)
    return app


__all__ = [
    "UnicodeJSONResponse",
    "api_info",
    "check_rate_limit",
    "create_application",
    "health_check",
    "logger",
    "root",
    "settings",
]
