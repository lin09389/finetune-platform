"""Central Phase-0 security / local-dev policy helpers.

All production vs local trade-offs should consult this module so middleware,
JWT init, agent session auth, inference internal keys, and GPU coordination
share one definition of "production-hard-closed + explicit local opt-in".
"""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_INFERENCE_INTERNAL_API_KEY = "finetune-local-inference-dev-key"

# Agent middleware + synthetic desktop user only when explicitly opted in.
ALLOW_LOCAL_AGENT_AUTH_ENV = "ALLOW_LOCAL_AGENT_AUTH"
GPU_COORDINATION_ENV = "GPU_COORDINATION"


def _env_flag(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _settings_obj(settings: Any | None = None) -> Any:
    if settings is not None:
        return settings
    from core.config import get_settings

    return get_settings()


def is_production_environment(settings: Any | None = None) -> bool:
    """True for production and staging (prod-equivalent hardening)."""
    env = str(getattr(_settings_obj(settings), "environment", "development") or "development")
    return env.lower() in {"production", "staging"}


def is_development_environment(settings: Any | None = None) -> bool:
    env = str(getattr(_settings_obj(settings), "environment", "development") or "development")
    return env.lower() == "development"


def allow_local_agent_auth(settings: Any | None = None) -> bool:
    """Whether anonymous/synthetic local agent auth is permitted.

    Production/staging: always False (flag cannot reopen).
    Non-production: requires explicit ALLOW_LOCAL_AGENT_AUTH=true
    (settings field or env).
    """
    cfg = _settings_obj(settings)
    if is_production_environment(cfg):
        return False
    if bool(getattr(cfg, "allow_local_agent_auth", False)):
        return True
    return _env_flag(ALLOW_LOCAL_AGENT_AUTH_ENV, default=False)


def require_configured_jwt_secret(
    secret: str | None,
    *,
    settings: Any | None = None,
    source: str = "JWTAuth",
) -> str:
    """Resolve JWT secret with fail-closed policy.

    Never auto-generates a random secret. Missing secret raises RuntimeError so
    multi-worker deployments cannot silently mint incompatible keys.
    """
    value = (secret or os.environ.get("JWT_SECRET_KEY") or "").strip()
    if value:
        return value

    env = getattr(_settings_obj(settings), "environment", "development")
    enable_auth = bool(getattr(_settings_obj(settings), "enable_auth", True))
    raise RuntimeError(
        f"{source}: JWT secret is required (set JWT_SECRET_KEY). "
        f"environment={env!r} enable_auth={enable_auth}. "
        "Copy server/.env.example and set a stable local secret for development/tests."
    )


def assert_inference_internal_key_safe(settings: Any | None = None) -> None:
    """Reject the hard-coded dev inference key outside development."""
    cfg = _settings_obj(settings)
    key = str(getattr(cfg, "inference_internal_api_key", "") or "")
    if is_production_environment(cfg) and key == DEFAULT_INFERENCE_INTERNAL_API_KEY:
        raise RuntimeError(
            "Production/staging requires a non-default INFERENCE_INTERNAL_API_KEY "
            f"(refusing {DEFAULT_INFERENCE_INTERNAL_API_KEY!r})"
        )
    if (
        not is_production_environment(cfg)
        and key == DEFAULT_INFERENCE_INTERNAL_API_KEY
    ):
        logger.warning(
            "Using default development inference internal API key; "
            "set INFERENCE_INTERNAL_API_KEY before production deployment."
        )


def gpu_coordination_enabled(settings: Any | None = None) -> bool:
    """GPU train/infer lease coordination.

    Default on. Disable only via GPU_COORDINATION=off outside production/staging
    so tests and single-workload local runs can opt out.
    """
    cfg = _settings_obj(settings)
    if is_production_environment(cfg):
        # Production always coordinates when the helper is consulted.
        return True
    raw = os.environ.get(GPU_COORDINATION_ENV)
    if raw is not None:
        return raw.strip().lower() not in {"0", "false", "no", "off"}
    return bool(getattr(cfg, "gpu_coordination", True))
