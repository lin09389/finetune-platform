from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from skills import resolve_skill_source_specs, resolve_skill_sources, scan_skill_manifests

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
    middleware: list[Any] | None = None
    tools: list[Any] | None = None
    skills: list[str] | None = None
    enabled_skill_sources: list[str] | None = None
    subagents: list[dict[str, Any]] | None = None


def build_deep_agent_runtime(config: DeepAgentRuntimeConfig) -> Any:
    """Compatibility wrapper for the unified DeepAgents runtime factory."""

    from .runtime_contract import AgentRuntimeContract
    from .runtime_factory import build_deep_agent_from_contract

    return build_deep_agent_from_contract(
        AgentRuntimeContract(
            runtime_kind="agent_session",
            session_id="compat",
            project_path=config.project_path,
            user_id=config.user_id,
            agent_id=config.agent_id,
            org_id=config.org_id,
            model=config.model,
            tools=config.tools or [],
            system_prompt=config.system_prompt,
            memory=config.memory,
            skills=config.skills or [],
            enabled_skill_sources=config.enabled_skill_sources,
            permissions=config.permissions,
            middleware=config.middleware,
            subagents=config.subagents,
            interrupt_on=config.interrupt_on,
            checkpointer=config.checkpointer,
            backend_mode="workspace",
        )
    )


def build_deepagents_backend(
    project_path: str,
    *,
    user_id: str = "default",
    agent_id: str = "build",
    org_id: str = "default-org",
    enabled_skill_sources: list[str] | None = None,
) -> Any:
    """Build a CompositeBackend that separates project files from agent state.

    The default backend must support execute, because CompositeBackend delegates
    execute to its default backend. Internal DeepAgents paths are routed to
    StateBackend so offloaded results and conversation history do not pollute
    the user's project directory.
    """

    from deepagents.backends import CompositeBackend, LocalShellBackend, StateBackend

    from memory.memory_service import get_memory_service

    from .runtime_factory import deepagents_shell_env

    env = deepagents_shell_env()
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
        for source in resolve_enabled_skill_source_specs(project_path, agent_id=agent_id, enabled_skill_sources=enabled_skill_sources)
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


def describe_deepagents_mounts(
    project_path: str,
    *,
    agent_id: str = "build",
    enabled_skill_sources: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Return a reader-facing summary of the virtual filesystem routes."""

    skill_mounts = [
        {
            "path": source.virtual_path,
            "kind": "skills",
            "label": f"Skills: {source.name}",
            "writable": False,
            "description": "DeepAgents skill source mounted read-only for progressive disclosure.",
        }
        for source in resolve_enabled_skill_source_specs(project_path, agent_id=agent_id, enabled_skill_sources=enabled_skill_sources)
    ]
    return [
        {
            "path": "/workspace/",
            "kind": "workspace",
            "label": "Project workspace",
            "writable": True,
            "description": "Current project files mounted through the DeepAgents filesystem backend.",
        },
        {
            "path": "/memories/",
            "kind": "memory",
            "label": "User memory",
            "writable": True,
            "description": "Long-lived user memory files available to the agent.",
        },
        {
            "path": "/agent-memory/",
            "kind": "memory",
            "label": "Agent memory",
            "writable": True,
            "description": "Agent-scoped memory files.",
        },
        {
            "path": "/policies/",
            "kind": "policy",
            "label": "Policies",
            "writable": False,
            "description": "Organization or workspace policy files.",
        },
        {
            "path": "/context/",
            "kind": "context",
            "label": "Task context",
            "writable": False,
            "description": "Ephemeral task context files assembled for the current prompt.",
        },
        {
            "path": "/large_tool_results/",
            "kind": "ephemeral",
            "label": "Large tool results",
            "writable": False,
            "description": "Offloaded large tool outputs from DeepAgents.",
        },
        {
            "path": "/conversation_history/",
            "kind": "ephemeral",
            "label": "Conversation history",
            "writable": False,
            "description": "DeepAgents conversation history summaries.",
        },
        *skill_mounts,
    ]


def describe_skill_sources(
    project_path: str,
    *,
    agent_id: str = "build",
    enabled_skill_sources: list[str] | None = None,
) -> list[dict[str, Any]]:
    enabled = _enabled_skill_source_set(enabled_skill_sources)
    return [
        {
            "name": source.name,
            "virtual_path": source.virtual_path,
            "priority": source.priority,
            "available": source.path.exists() and source.path.is_dir(),
            "enabled": enabled is None or source.virtual_path in enabled or source.name in enabled,
        }
        for source in resolve_skill_source_specs(project_path, agent_id=agent_id)
    ]


def describe_skill_registry(project_path: str, *, agent_id: str = "build") -> dict[str, Any]:
    sources = resolve_skill_source_specs(project_path, agent_id=agent_id)
    manifests = scan_skill_manifests(sources)
    by_source: dict[str, list[dict[str, Any]]] = {source.virtual_path: [] for source in sources}
    for manifest in manifests:
        source_path = manifest.source.virtual_path if manifest.source else ""
        by_source.setdefault(source_path, []).append(
            {
                "name": manifest.name,
                "description": manifest.description,
                "virtual_skill_file": manifest.virtual_skill_file,
                "allowed_tools": manifest.allowed_tools,
                "source": source_path,
            }
        )
    return {
        "sources": [
            {
                "name": source.name,
                "virtual_path": source.virtual_path,
                "priority": source.priority,
                "available": source.path.exists() and source.path.is_dir(),
                "enabled_by_default": True,
                "skills": by_source.get(source.virtual_path, []),
            }
            for source in sources
        ]
    }


def resolve_enabled_skill_source_specs(
    project_path: str,
    *,
    agent_id: str = "build",
    enabled_skill_sources: list[str] | None = None,
) -> list[Any]:
    sources = resolve_skill_source_specs(project_path, agent_id=agent_id)
    enabled = _enabled_skill_source_set(enabled_skill_sources)
    if enabled is None:
        return sources
    return [source for source in sources if source.virtual_path in enabled or source.name in enabled]


def resolve_enabled_skill_sources(
    project_path: str,
    *,
    user_id: str = "default",
    agent_id: str = "build",
    org_id: str = "default-org",
    enabled_skill_sources: list[str] | None = None,
) -> list[str]:
    _ = user_id, org_id
    return [
        source.virtual_path
        for source in resolve_enabled_skill_source_specs(
            project_path,
            agent_id=agent_id,
            enabled_skill_sources=enabled_skill_sources,
        )
    ]


def validate_skill_tool_compatibility(
    project_path: str,
    *,
    agent_id: str = "build",
    enabled_skill_sources: list[str] | None = None,
    allowed_tools: set[str] | None = None,
) -> list[dict[str, Any]]:
    """Ensure enabled DeepAgents skills do not require tools denied to the agent.

    `allowed-tools` is optional in SKILL.md. When present, it is treated as a
    capability declaration that must fit within the agent's runtime tool policy.
    """

    if allowed_tools is None:
        return []
    sources = resolve_enabled_skill_source_specs(
        project_path,
        agent_id=agent_id,
        enabled_skill_sources=enabled_skill_sources,
    )
    violations: list[dict[str, Any]] = []
    for manifest in scan_skill_manifests(sources):
        missing = sorted(set(manifest.allowed_tools) - allowed_tools)
        if missing:
            violations.append(
                {
                    "skill": manifest.name,
                    "virtual_skill_file": manifest.virtual_skill_file,
                    "missing_tools": missing,
                    "allowed_tools": sorted(allowed_tools),
                }
            )
    if violations:
        details = "; ".join(
            f"{item['skill']} requires {', '.join(item['missing_tools'])}"
            for item in violations
        )
        raise ValueError(f"Enabled skills require tools denied by agent '{agent_id}': {details}")
    return []


def _enabled_skill_source_set(enabled_skill_sources: list[str] | None) -> set[str] | None:
    if enabled_skill_sources is None:
        return None
    return {str(item).strip() for item in enabled_skill_sources if str(item).strip()}


def resolve_interrupt_on(metadata: dict[str, Any] | None) -> dict[str, Any] | None:
    from .permission import resolve_deepagents_interrupt_on

    return resolve_deepagents_interrupt_on(metadata)


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
    "describe_deepagents_mounts",
    "describe_skill_registry",
    "describe_skill_sources",
    "memory_files_for_project",
    "resolve_enabled_skill_sources",
    "resolve_enabled_skill_source_specs",
    "resolve_skill_sources",
    "resolve_interrupt_on",
    "validate_skill_tool_compatibility",
]

