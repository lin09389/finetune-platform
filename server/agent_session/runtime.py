from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


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
    interrupt_on: dict[str, Any] | None = None
    permissions: list[Any] | None = None
    tools: list[Any] | None = None


def build_deep_agent_runtime(config: DeepAgentRuntimeConfig) -> Any:
    """Build the official DeepAgents runtime for an AgentSession."""

    from deepagents import create_deep_agent

    return create_deep_agent(
        model=config.model,
        tools=config.tools or [],
        system_prompt=config.system_prompt,
        backend=build_deepagents_backend(config.project_path),
        memory=config.memory,
        permissions=config.permissions,
        interrupt_on=config.interrupt_on,
        checkpointer=config.checkpointer,
    )


def build_deepagents_backend(project_path: str) -> Any:
    """Build a CompositeBackend that separates project files from agent state.

    The default backend must support execute, because CompositeBackend delegates
    execute to its default backend. Internal DeepAgents paths are routed to
    StateBackend so offloaded results and conversation history do not pollute
    the user's project directory.
    """

    from deepagents.backends import CompositeBackend, LocalShellBackend, StateBackend

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
    return CompositeBackend(
        default=project_backend,
        routes={
            WORKSPACE_BACKEND_ROUTE: project_backend,
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


def memory_files_for_project(project_path: str) -> list[str]:
    agents_file = Path(project_path) / "AGENTS.md"
    if agents_file.exists() and agents_file.is_file():
        return ["/workspace/AGENTS.md"]
    return []


__all__ = [
    "DeepAgentRuntimeConfig",
    "EPHEMERAL_BACKEND_ROUTES",
    "FALLBACK_STATE_BACKEND_ROUTE",
    "WORKSPACE_BACKEND_ROUTE",
    "build_deep_agent_runtime",
    "build_deepagents_backend",
    "memory_files_for_project",
    "resolve_interrupt_on",
]

