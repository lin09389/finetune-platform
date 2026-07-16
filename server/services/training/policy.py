"""Training control-plane policy helpers (skip checks, RBAC, WS auth)."""

from __future__ import annotations

from typing import Any

from fastapi import Depends, HTTPException, WebSocket
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from core.config import Settings, get_settings
from security.auth_middleware import get_current_user_optional
from security.jwt_auth import Role, TokenPayload, get_jwt_auth
from security.runtime_policy import is_production_environment

_security = HTTPBearer(auto_error=False)


def allow_skip_resource_check(cfg: Settings | None = None) -> bool:
    """Clients may skip resource checks only outside production/staging."""
    return not is_production_environment(cfg or get_settings())


def history_authority(cfg: Settings | None = None) -> str:
    """Where history/list_training_records reads from for the active mode."""
    mode = getattr(cfg or get_settings(), "training_execution_mode", "worker")
    return "sqlite_jobs" if mode == "worker" else "json_history"


async def require_training_operator(
    current_user: TokenPayload | None = Depends(get_current_user_optional),
) -> TokenPayload | None:
    """Gate mutating training control when auth is enabled.

    - ENABLE_AUTH=false (local/tests): allow through.
    - ENABLE_AUTH=true: require ADMIN or SUPER_ADMIN.
    """
    settings = get_settings()
    if not settings.enable_auth:
        return current_user
    if current_user is None:
        raise HTTPException(
            status_code=401,
            detail={"error": "missing_authorization", "message": "Training control requires authentication"},
            headers={"WWW-Authenticate": "Bearer"},
        )
    auth = get_jwt_auth()
    if not auth.has_role(current_user, Role.ADMIN):
        raise HTTPException(
            status_code=403,
            detail={"error": "insufficient_role", "message": "Training control requires administrator role"},
        )
    return current_user


def authenticate_training_websocket(websocket: WebSocket) -> TokenPayload | None:
    """Validate JWT for training WS when auth is enabled.

    Accepts ``Authorization: Bearer <token>`` header or ``?token=`` query param
    (browsers cannot set WS Authorization easily).
    """
    settings = get_settings()
    if not settings.enable_auth:
        return None

    token: str | None = None
    auth_header = websocket.headers.get("authorization") or websocket.headers.get("Authorization")
    if auth_header and auth_header.lower().startswith("bearer "):
        token = auth_header[7:].strip()
    if not token:
        token = (websocket.query_params.get("token") or "").strip() or None
    if not token:
        raise HTTPException(status_code=401, detail="Missing bearer token for training WebSocket")

    try:
        return get_jwt_auth().verify_token(token)
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Invalid or expired token") from exc


def map_progress_status(raw: str | None, *, job_status: str | None = None) -> str:
    """Normalize job/event status into TrainingProgress vocabulary."""
    value = (raw or job_status or "idle").strip().lower()
    if value in {"leased", "queued"}:
        return "loading"
    if value == "running":
        return "training"
    if value == "cancellation_requested":
        return "stopping"
    return value


__all__ = [
    "allow_skip_resource_check",
    "authenticate_training_websocket",
    "history_authority",
    "map_progress_status",
    "require_training_operator",
]
