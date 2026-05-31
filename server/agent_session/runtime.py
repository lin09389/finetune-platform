from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .deepagents_compat import patch_torch_pytree_for_transformers
from skills import resolve_skill_source_specs, resolve_skill_sources


EPHEMERAL_BACKEND_ROUTES = ("/context/", "/large_tool_results/", "/conversation_history/")
WORKSPACE_BACKEND_ROUTE = "/workspace/"
FALLBACK_STATE_BACKEND_ROUTE = "/"


@dataclass(frozen=True)
class DeepAgentRuntimeConfig:
    model: Any
    project_path: str
    system_prompt: str
    memory: list[str]
    checkpointer: Any
    user_id: str = "default"
    agent_id: str = "build"
    org_id: str = "default-org"
    interrupt_on: dict[str, Any] | None = None
    permissions: list[Any] | None = None
    tools: list[Any] | None = None
    skills: list[str] | None = None
    subagents: list[dict[str, Any]] | None = None


def build_deep_agent_runtime(config: DeepAgentRuntimeConfig) -> Any:
    """Build the official DeepAgents runtime for an AgentSession."""

    patch_torch_pytree_for_transformers()
    from deepagents import create_deep_agent

    return create_deep_agent(
        model=config.model,
        tools=config.tools or [],
        system_prompt=config.system_prompt,
        backend=build_deepagents_backend(
            config.project_path,
            user_id=config.user_id,
            agent_id=config.agent_id,
            org_id=config.org_id,
        ),
        memory=config.memory,
        skills=config.skills or [],
        subagents=config.subagents or [],
        permissions=config.permissions,
        interrupt_on=config.interrupt_on,
        checkpointer=config.checkpointer,
    )


def build_deepagents_backend(
    project_path: str,
    *,
    user_id: str = "default",
    agent_id: str = "build",
    org_id: str = "default-org",
) -> Any:
    """Build a CompositeBackend that separates project files from agent state.

    The default backend must support execute, because CompositeBackend delegates
    execute to its default backend. Internal DeepAgents paths are routed to
    StateBackend so offloaded results and conversation history do not pollute
    the user's project directory.
    """

    from deepagents.backends import CompositeBackend, LocalShellBackend, StateBackend
    from memory.memory_service import get_memory_service

    env = {
        key: value
        for key, value in os.environ.items()
        if key.upper() in {"PATH", "PATHEXT", "SYSTEMROOT", "WINDIR", "SYSTEMDRIVE", "COMSPEC", "TEMP", "TMP"}
    }
    project_backend = LocalShellBackend(
        root_dir=str(Path(project_path).resolve()),
        virtual_mode=True,
        timeout=120,
        max_output_bytes=100_000,
        env=env,
        inherit_env=False,
    )
    memory_service = get_memory_service()
    memory_service.store.ensure_namespace("user", user_id)
    memory_service.store.ensure_namespace("agent", agent_id)
    memory_service.store.ensure_namespace("org", org_id)
    user_memory_backend = LocalShellBackend(
        root_dir=str(memory_service.store.resolver.files_dir_for("user", user_id).resolve()),
        virtual_mode=True,
        timeout=120,
        max_output_bytes=100_000,
        env=env,
        inherit_env=False,
    )
    agent_memory_backend = LocalShellBackend(
        root_dir=str(memory_service.store.resolver.files_dir_for("agent", agent_id).resolve()),
        virtual_mode=True,
        timeout=120,
        max_output_bytes=100_000,
        env=env,
        inherit_env=False,
    )
    org_policy_backend = LocalShellBackend(
        root_dir=str(memory_service.store.resolver.files_dir_for("org", org_id).resolve()),
        virtual_mode=True,
        timeout=120,
        max_output_bytes=100_000,
        env=env,
        inherit_env=False,
    )
    skill_routes = {
        source.virtual_path: LocalShellBackend(
            root_dir=str(source.path.resolve()),
            virtual_mode=True,
            timeout=120,
            max_output_bytes=100_000,
            env=env,
            inherit_env=False,
        )
        for source in resolve_skill_source_specs(project_path, agent_id=agent_id)
    }
    return CompositeBackend(
        default=project_backend,
        routes={
            WORKSPACE_BACKEND_ROUTE: project_backend,
            "/memories/": user_memory_backend,
            "/agent-memory/": agent_memory_backend,
            "/policies/": org_policy_backend,
            **skill_routes,
            **{route: StateBackend() for route in EPHEMERAL_BACKEND_ROUTES},
            FALLBACK_STATE_BACKEND_ROUTE: StateBackend(),
        },
    )


def resolve_interrupt_on(metadata: dict[str, Any] | None) -> dict[str, Any] | None:
    """Read optional DeepAgents HITL interrupt configuration from session metadata."""

    raw = dict(metadata or {}).get("deepagents_interrupt_on")
    if raw is True:
        return {"write_file": True, "edit_file": True, "execute": True}
    if isinstance(raw, dict):
        return raw
    return None


def memory_files_for_project(
    project_path: str,
    *,
    user_id: str = "default",
    agent_id: str = "build",
    org_id: str = "default-org",
) -> list[str]:
    from memory.memory_service import get_memory_service

    memory_service = get_memory_service()
    user_files = [file["path"] for file in memory_service.list_files("user", user_id)]
    agent_files = [file["path"] for file in memory_service.list_files("agent", agent_id)]
    policy_files = [file["path"] for file in memory_service.list_files("org", org_id)]
    memory = [*user_files, *agent_files, *policy_files]
    agents_file = Path(project_path) / "AGENTS.md"
    if agents_file.exists() and agents_file.is_file():
        memory.append("/workspace/AGENTS.md")
    return memory


__all__ = [
    "DeepAgentRuntimeConfig",
    "EPHEMERAL_BACKEND_ROUTES",
    "FALLBACK_STATE_BACKEND_ROUTE",
    "WORKSPACE_BACKEND_ROUTE",
    "build_deep_agent_runtime",
    "build_deepagents_backend",
    "memory_files_for_project",
    "resolve_skill_sources",
    "resolve_interrupt_on",
]

