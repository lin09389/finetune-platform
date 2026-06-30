"""API package with backward-compatible lazy router exports.

Importing a focused module such as ``api.agent_sessions`` must not eagerly load
the training and inference stacks (and vice versa). Legacy ``from api import
training`` style imports continue to resolve their router on first access.
"""

from __future__ import annotations

from importlib import import_module
from typing import Any


_ROUTER_EXPORTS: dict[str, tuple[str, str]] = {
    "agent_session_permissions": ("api.agent_sessions", "permission_router"),
    "agent_sessions": ("api.agent_sessions", "router"),
    "agents": ("api.agents", "router"),
    "chat": ("api.chat.routes", "router"),
    "chat_agent": ("api.chat_agent", "router"),
    "cloud_chat": ("api.cloud_chat", "router"),
    "context": ("api.context", "router"),
    "cua": ("api.cua", "router"),
    "datasets": ("api.datasets", "router"),
    "deployment_router": ("api.deployment", "router"),
    "device": ("api.device", "router"),
    "evaluation_router": ("api.evaluation", "router"),
    "gateway": ("api.gateway_api.routes", "router"),
    "heartbeat": ("api.heartbeat", "router"),
    "inference": ("api.inference", "router"),
    "knowledge": ("api.knowledge", "router"),
    "mcp": ("api.mcp", "router"),
    "memory": ("api.memory", "router"),
    "model_center": ("api.model_center", "router"),
    "model_runtime": ("api.model_runtime", "router"),
    "models": ("api.models", "router"),
    "training": ("api.training", "router"),
    "workspace": ("api.workspace", "router"),
}
_MODULE_EXPORTS = {
    "deployment": "api.deployment",
    "evaluation": "api.evaluation",
}

__all__ = [*_ROUTER_EXPORTS, *_MODULE_EXPORTS]


def __getattr__(name: str) -> Any:
    if name in _MODULE_EXPORTS:
        value = import_module(_MODULE_EXPORTS[name])
    elif name in _ROUTER_EXPORTS:
        module_name, attribute = _ROUTER_EXPORTS[name]
        value = getattr(import_module(module_name), attribute)
    else:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted({*globals(), *__all__})
