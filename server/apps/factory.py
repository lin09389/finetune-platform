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
from fastapi.responses import JSONResponse, Response

from core.config import settings
from core.logging import log_request_completed, setup_logging
from core.telemetry import (
    PROMETHEUS_CONTENT_TYPE,
    configure_telemetry,
    get_telemetry_registry,
)
from core.tracing import correlation_id_var, trace_id_var, user_id_var
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


def resolve_log_dir() -> Path:
    """Resolve a writable log directory for server and desktop deployments.

    Source checkouts keep the historical repository-level ``logs`` default.
    A packaged desktop supervisor must set ``FINETUNE_LOG_DIR`` to its user-data
    tree so application resources remain immutable and upgrade-safe.
    """

    configured = os.getenv("FINETUNE_LOG_DIR", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    return Path(__file__).resolve().parents[2] / "logs"


LOG_DIR = resolve_log_dir()
LOG_DIR.mkdir(parents=True, exist_ok=True)
logger = setup_logging(
    log_dir=LOG_DIR,
    log_level=settings.log_level,
    enable_json=settings.log_format == "json",
    max_bytes=settings.log_max_bytes,
    backup_count=settings.log_backup_count,
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
    "/experimental/status",
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
    """Skip bearer auth for agent routes only under explicit local opt-in.

    Production/staging never allow this (even if ALLOW_LOCAL_AGENT_AUTH is set).
    Non-production requires ALLOW_LOCAL_AGENT_AUTH=true — bare development alone
    is not enough when ENABLE_AUTH=true.
    """
    from security.runtime_policy import allow_local_agent_auth

    if not allow_local_agent_auth(settings):
        return False
    return path.startswith(_LOCAL_AGENT_AUTH_FALLBACK_PREFIXES)


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
    # Local-first scrapers may read process metrics without a token. Production
    # and staging keep the endpoint behind the same JWT gate as other APIs.
    if path == "/metrics":
        from security.runtime_policy import is_production_environment

        if not is_production_environment(settings):
            return await call_next(request)
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
    supplied = request.headers.get("X-Correlation-Id") or request.headers.get("X-Trace-Id")
    correlation_id = supplied if supplied and re.fullmatch(r"[A-Za-z0-9._-]{1,128}", supplied) else str(uuid.uuid4())
    correlation_token = correlation_id_var.set(correlation_id)
    trace_token = trace_id_var.set(correlation_id)
    user_token = user_id_var.set(request.headers.get("X-User-Id", "anonymous"))
    try:
        response = await call_next(request)
        # Legacy clients can keep consuming X-Trace-Id.  Both names identify
        # the same request so new integrations have one correlation primitive.
        response.headers["X-Trace-Id"] = correlation_id
        response.headers["X-Correlation-Id"] = correlation_id
        return response
    finally:
        correlation_id_var.reset(correlation_token)
        trace_id_var.reset(trace_token)
        user_id_var.reset(user_token)


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
                    **_cors_response_headers_for_request(request),
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
    start_time = time.perf_counter()
    app = request.scope.get("app")
    profile = str(getattr(getattr(app, "state", None), "profile", "other"))
    try:
        response = await call_next(request)
    except Exception:
        duration_seconds = time.perf_counter() - start_time
        log_request_completed(
            logger,
            method=request.method,
            status_code=500,
            duration_ms=duration_seconds * 1000,
            profile=profile,
        )
        get_telemetry_registry().record_http_request(
            method=request.method,
            status_code=500,
            duration_seconds=duration_seconds,
            profile=profile,
        )
        raise
    duration_seconds = time.perf_counter() - start_time
    response.headers["X-Process-Time"] = f"{duration_seconds:.4f}"
    log_request_completed(
        logger,
        method=request.method,
        status_code=response.status_code,
        duration_ms=duration_seconds * 1000,
        profile=profile,
    )
    get_telemetry_registry().record_http_request(
        method=request.method,
        status_code=response.status_code,
        duration_seconds=duration_seconds,
        profile=profile,
    )
    return response


async def metrics_endpoint() -> Response:
    """Expose bounded process-local aggregates in Prometheus 0.0.4 text."""

    return Response(
        content=get_telemetry_registry().render_prometheus(),
        headers={"Content-Type": PROMETHEUS_CONTENT_TYPE},
    )


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
    try:
        import torch
    except ImportError:
        # Torch-free installs (control-plane-only profiles) still serve a healthy
        # payload; accelerator info is simply unavailable.
        return health

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


def _agent_runtime_env_for_info() -> dict:
    """Non-secret Agent process environment probe for operators (Phase 4)."""
    try:
        from core.runtime_env import probe_agent_runtime_environment

        payload = probe_agent_runtime_environment()
        # Keep /api/info compact: drop executable path noise if desired, but path helps ops.
        return {
            "in_virtualenv": payload.get("in_virtualenv"),
            "packages": payload.get("packages"),
            "warnings": payload.get("warnings") or [],
            "recommended_command": payload.get("recommended_command"),
            "app_db_path": payload.get("app_db_path"),
            "langgraph_checkpoint_db_path": payload.get("langgraph_checkpoint_db_path"),
        }
    except Exception as exc:
        return {"warnings": [f"agent_runtime_env probe failed: {exc}"]}


def _agent_ready_payload() -> dict:
    """Agent control-plane readiness for Workbench / ops (not model catalog readiness)."""
    try:
        from apps.lifespan import get_agent_readiness

        return get_agent_readiness()
    except Exception as exc:
        return {
            "ready": False,
            "session_service": False,
            "context_service": False,
            "memory_service": False,
            "issues": [f"agent_ready probe failed: {exc}"],
        }


def _storage_info_for_api() -> dict:
    try:
        from core.storage import APP_DB_PATH, get_langgraph_checkpoint_db_path

        return {
            "app_db_path": APP_DB_PATH,
            "langgraph_checkpoint_db_path": get_langgraph_checkpoint_db_path(),
            "path_is_absolute": True,
        }
    except Exception as exc:
        return {"error": str(exc)}


async def api_info():
    """Capability tiers and mounts are registry-driven (apps.capability_registry)."""
    from apps.capability_registry import build_info_capability_payload

    tier_payload = build_info_capability_payload(settings)
    from agent_session.model_capabilities import (
        build_agent_model_runtime_payload,
        saved_cloud_agent_model_configured,
    )
    from security.encryption import secure_storage
    from cloud_models import CloudProviderRepository

    cloud_model_configured = saved_cloud_agent_model_configured(CloudProviderRepository(secure_storage))

    # OCR backend availability (experimental capability; safe to probe even if deps missing)
    try:
        from api.ocr import RAPIDOCR_AVAILABLE, TESSERACT_AVAILABLE
        ocr_backends = {
            "tesseract": {"available": TESSERACT_AVAILABLE},
            "rapidocr": {"available": RAPIDOCR_AVAILABLE},
        }
    except Exception:
        ocr_backends = {
            "tesseract": {"available": False},
            "rapidocr": {"available": False},
        }

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
        "capability_tiers": tier_payload["capability_tiers"],
        "experimental_enabled": tier_payload["experimental_enabled"],
        "experimental_capabilities": tier_payload["experimental_capabilities"],
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
        "agent_model_runtime": build_agent_model_runtime_payload(
            settings,
            cloud_model_configured=cloud_model_configured,
        ),
        "agent_runtime_env": _agent_runtime_env_for_info(),
        "agent_ready": _agent_ready_payload(),
        "storage": _storage_info_for_api(),
        "ocr_backends": ocr_backends,
        "endpoints": tier_payload["endpoints"],
    }


async def experimental_status():
    """Experimental readiness — independent of core /health."""
    from apps.capability_registry import experimental_status_payload

    return experimental_status_payload(settings)


async def experimental_isolation_middleware(request: Request, call_next):
    """Contain experimental-path failures so they do not surface as unhandled GA crashes.

    Only wraps ``/experimental/*`` (and logs tier context). Legacy experimental
    aliases still run through normal handlers + existing auth.
    """
    path = request.url.path.rstrip("/") or "/"
    if not path.startswith("/experimental"):
        return await call_next(request)
    try:
        return await call_next(request)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Experimental route failure path=%s: %s", path, exc)
        return JSONResponse(
            status_code=503,
            content={
                "error": "experimental_unavailable",
                "tier": "experimental",
                "detail": "Experimental capability failed; core GA endpoints are unaffected.",
                "path": path,
            },
            headers={"X-Capability-Tier": "experimental"},
        )


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
        expose_headers=["X-Correlation-Id", "X-Process-Time", "X-Trace-Id"],
        allow_headers=[
            "Authorization",
            "Content-Type",
            "X-Backend",
            "X-Requested-With",
            "X-Trace-Id",
            "X-Correlation-Id",
        ],
    )
    app.middleware("http")(authentication_middleware)
    app.middleware("http")(experimental_isolation_middleware)
    app.middleware("http")(security_middleware)
    app.middleware("http")(logging_middleware)
    app.middleware("http")(security_headers_middleware)
    # Register last so correlation context exists for every custom middleware.
    app.middleware("http")(trace_middleware)

    app.add_api_route("/", root, methods=["GET"])
    profile_health = health_check
    if profile is ApplicationProfile.AGENT:
        async def agent_health_check():
            return await _health_payload(include_accelerator=False)

        profile_health = agent_health_check
    app.add_api_route("/health", profile_health, methods=["GET"], name="health_check")
    app.add_api_route("/metrics", metrics_endpoint, methods=["GET"], include_in_schema=False)
    app.add_api_route("/api/info", api_info, methods=["GET"])
    app.add_api_route(
        "/experimental/status",
        experimental_status,
        methods=["GET"],
        tags=["Experimental"],
    )

    from api.errors import APIError

    app.add_exception_handler(APIError, custom_api_error_handler)
    app.add_exception_handler(RequestValidationError, request_validation_error_handler)
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(Exception, general_exception_handler)


def create_application(profile: ApplicationProfile | str) -> FastAPI:
    resolved = coerce_profile(profile)
    configure_telemetry(settings.observability_max_series)
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
    "resolve_log_dir",
    "root",
    "settings",
]
