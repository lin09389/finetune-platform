"""Lazy router registration for each deployable application profile.

Experimental capabilities are gated by ``settings.enable_experimental_capabilities``
and mounted under ``/experimental/*`` with legacy path aliases when enabled.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from dataclasses import dataclass
from importlib import import_module

from fastapi import FastAPI

from core.config import settings

from .capability_registry import (
    EXPERIMENTAL_MOUNT_PREFIX,
    EXPERIMENTAL_ROUTER_SPECS,
    experimental_enabled,
)
from .profiles import ApplicationProfile

logger = logging.getLogger(__name__)


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
    RouterSpec("api.model_center", prefix="/model-center", tags=("Model Center",)),
    RouterSpec("api.model_runtime", prefix="/model-runtime", tags=("Model Runtime",)),
)

INFERENCE_ROUTERS = (
    RouterSpec("api.inference.facade", prefix="/inference", tags=("Inference",)),
    RouterSpec("api.inference.facade", attribute="openai_router"),
)

AGENT_ROUTERS = (
    RouterSpec("api.chat.routes", tags=("Chat",)),
    RouterSpec("api.agents"),
    RouterSpec("api.knowledge", prefix="/knowledge", tags=("Knowledge",)),
    RouterSpec("api.knowledge", prefix="/v2/knowledge", tags=("Knowledge v2",)),
    RouterSpec("api.workspace", prefix="/workspace", tags=("Workspace",)),
    RouterSpec("api.workspace_portability", prefix="/workspace", tags=("Workspace Portability",)),
    RouterSpec("api.chat_agent"),
    RouterSpec("api.agent_sessions"),
    RouterSpec("api.agent_sessions", attribute="permission_router"),
    RouterSpec("api.agent_terminals"),
)

# Non-experimental auxiliary (beta / support) — always registered with agent profile.
AGENT_AUXILIARY_ROUTERS = (
    RouterSpec("api.memory", tags=("Memory",)),
    RouterSpec("api.compat", tags=("Compatibility",)),
    RouterSpec("api.context", prefix="/context", tags=("Context",)),
    RouterSpec("workspace.file_api", prefix="/files", tags=("Files",)),
    RouterSpec("workspace.task_api", prefix="/tasks", tags=("Tasks",)),
    RouterSpec("api.cloud_chat", prefix="/cloud", tags=("Cloud",)),
    RouterSpec("api.agent_eval"),
    RouterSpec("api.code_executor", prefix="/code", tags=("Code",)),
    RouterSpec("api.file_parser", tags=("File Parser",)),
    RouterSpec("api.chat_branch", tags=("Chat Branch",)),
    RouterSpec("api.chat_share", tags=("Chat Share",)),
    RouterSpec("api.entity", tags=("Entity",)),
)

INTEGRATION_ROUTERS = (
    RouterSpec("api.runtime", prefix="/runtime", tags=("Runtime",)),
)


def _register_many(app: FastAPI, specs: Iterable[RouterSpec]) -> None:
    for spec in specs:
        spec.register(app)


def _register_experimental_routers(app: FastAPI) -> None:
    """Mount experimental routers under /experimental/* + legacy aliases."""
    if not experimental_enabled(settings):
        logger.info(
            "Experimental capabilities disabled "
            "(enable_experimental_capabilities=false); skipping CUA/MCP/Gateway/Heartbeat/OCR"
        )
        app.state.experimental_enabled = False
        return

    app.state.experimental_enabled = True
    for module, attribute, tag in EXPERIMENTAL_ROUTER_SPECS:
        try:
            router = getattr(import_module(module), attribute)
        except Exception as exc:
            # Isolation: a broken experimental module must not abort app boot.
            logger.warning(
                "Skipping experimental router %s.%s (%s): %s",
                module,
                attribute,
                tag,
                exc,
            )
            continue
        # Canonical isolation mount: /experimental + router.prefix (e.g. /cua)
        app.include_router(
            router,
            prefix=EXPERIMENTAL_MOUNT_PREFIX,
            tags=(f"Experimental/{tag}",),
        )
        # Legacy alias for existing clients/tests (same router object, dual mount)
        app.include_router(router, tags=(tag,))
        logger.info(
            "Registered experimental %s under %s/* and legacy paths",
            tag,
            EXPERIMENTAL_MOUNT_PREFIX,
        )


def register_profile_routers(app: FastAPI, profile: ApplicationProfile) -> None:
    """Register routers in the same order as the legacy combined app."""
    _register_many(app, SHARED_ROUTERS)
    if profile.includes_finetune:
        _register_many(app, FINETUNE_ROUTERS)
        _register_many(app, INFERENCE_ROUTERS)
    if profile.includes_agent:
        _register_many(app, AGENT_ROUTERS)
        _register_many(app, AGENT_AUXILIARY_ROUTERS)
        _register_experimental_routers(app)
    if profile is ApplicationProfile.COMBINED:
        _register_many(app, INTEGRATION_ROUTERS)


__all__ = ["RouterSpec", "register_profile_routers"]
