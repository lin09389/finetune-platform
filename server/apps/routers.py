"""Lazy router registration for each deployable application profile."""

from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module
from typing import Iterable

from fastapi import FastAPI

from .profiles import ApplicationProfile


@dataclass(frozen=True)
class RouterSpec:
    module: str
    attribute: str = "router"
    prefix: str = ""
    tags: tuple[str, ...] = ()

    def register(self, app: FastAPI) -> None:
        router = getattr(import_module(self.module), self.attribute)
        kwargs: dict[str, object] = {}
        if self.prefix:
            kwargs["prefix"] = self.prefix
        if self.tags:
            kwargs["tags"] = list(self.tags)
        app.include_router(router, **kwargs)


SHARED_ROUTERS = (
    RouterSpec("api.auth"),
)

FINETUNE_ROUTERS = (
    RouterSpec("api.device", prefix="/device", tags=("Device",)),
    RouterSpec("api.models", prefix="/models", tags=("Models",)),
    RouterSpec("api.datasets", prefix="/datasets", tags=("Datasets",)),
    RouterSpec("api.training", prefix="/training", tags=("Training",)),
    RouterSpec("api.evaluation", prefix="/evaluation", tags=("Evaluation",)),
    RouterSpec("api.deployment", prefix="/deployment", tags=("Deployment",)),
    RouterSpec("api.inference", prefix="/inference", tags=("Inference",)),
    RouterSpec("api.inference.openai_routes"),
)

AGENT_ROUTERS = (
    RouterSpec("api.chat.routes", tags=("Chat",)),
    RouterSpec("api.agents"),
    RouterSpec("api.knowledge", prefix="/knowledge", tags=("Knowledge",)),
    RouterSpec("api.knowledge", prefix="/v2/knowledge", tags=("Knowledge v2",)),
    RouterSpec("api.workspace", prefix="/workspace", tags=("Workspace",)),
    RouterSpec("api.chat_agent"),
    RouterSpec("api.agent_sessions"),
    RouterSpec("api.agent_sessions", attribute="permission_router"),
    RouterSpec("api.agent_terminals"),
)

# These management endpoints still bridge both domains. They remain assigned to
# the profile that owns their underlying local runtime and will be replaced by
# an HTTP boundary in the next phase.
FINETUNE_MANAGEMENT_ROUTERS = (
    RouterSpec("api.model_center", prefix="/model-center", tags=("Model Center",)),
    RouterSpec("api.model_runtime", prefix="/model-runtime", tags=("Model Runtime",)),
)

AGENT_AUXILIARY_ROUTERS = (
    RouterSpec("api.memory", tags=("Memory",)),
    RouterSpec("api.compat", tags=("Compatibility",)),
    RouterSpec("api.context", prefix="/context", tags=("Context",)),
    RouterSpec("workspace.file_api", prefix="/files", tags=("Files",)),
    RouterSpec("workspace.task_api", prefix="/tasks", tags=("Tasks",)),
    RouterSpec("api.cloud_chat", prefix="/cloud", tags=("Cloud",)),
    RouterSpec("api.cua", tags=("CUA",)),
    RouterSpec("api.mcp", tags=("MCP",)),
    RouterSpec("api.gateway_api.routes", tags=("Gateway",)),
    RouterSpec("api.heartbeat", tags=("Heartbeat",)),
    RouterSpec("api.code_executor", prefix="/code", tags=("Code",)),
    RouterSpec("api.file_parser", tags=("File Parser",)),
    RouterSpec("api.chat_branch", tags=("Chat Branch",)),
    RouterSpec("api.chat_share", tags=("Chat Share",)),
    RouterSpec("api.entity", tags=("Entity",)),
    RouterSpec("api.ocr", tags=("OCR",)),
)

FINETUNE_ENGINE_ROUTERS = (
    RouterSpec("api.inference_engine", tags=("Inference Engine",)),
)

INTEGRATION_ROUTERS = (
    RouterSpec("api.runtime", prefix="/runtime", tags=("Runtime",)),
)


def _register_many(app: FastAPI, specs: Iterable[RouterSpec]) -> None:
    for spec in specs:
        spec.register(app)


def register_profile_routers(app: FastAPI, profile: ApplicationProfile) -> None:
    """Register routers in the same order as the legacy combined app."""
    _register_many(app, SHARED_ROUTERS)
    if profile.includes_finetune:
        _register_many(app, FINETUNE_ROUTERS)
    if profile.includes_agent:
        _register_many(app, AGENT_ROUTERS)
    if profile.includes_finetune:
        _register_many(app, FINETUNE_MANAGEMENT_ROUTERS)
    if profile.includes_agent:
        _register_many(app, AGENT_AUXILIARY_ROUTERS)
    if profile.includes_finetune:
        _register_many(app, FINETUNE_ENGINE_ROUTERS)
    if profile is ApplicationProfile.COMBINED:
        _register_many(app, INTEGRATION_ROUTERS)


__all__ = ["RouterSpec", "register_profile_routers"]
