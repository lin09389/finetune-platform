"""Compile a session tool-platform projection for shadow binding.

This module is the agent-side seam that owns the DeepAgents dependency
direction.  It converts the Task-5 :mod:`tool_platform.adapters.deepagents`
builtin tool bindings into a :class:`~tool_platform.registry.ToolRegistry`
and an enforcement lookup (canonical name -> capability), then calls the
pure :func:`tool_platform.projection.compile_tool_projection` to produce an
immutable snapshot.

No availability probes run here, no handlers execute, and the legacy
DeepAgents runtime is never altered.  The snapshot is bound read-only so the
``shadow`` orchestration mode can later diff it against the legacy HITL
behaviour offline.
"""

from __future__ import annotations

from typing import Any

from tool_platform.adapters.deepagents import (
    builtin_tool_bindings,
)
from tool_platform.projection import ToolProjectionSnapshot, compile_tool_projection
from tool_platform.registry import ToolRegistry

from .agent_registry import AgentRegistry
from .permission import policy_facts_for_session


def _builtin_registry() -> ToolRegistry:
    """Build an in-process registry from the installed DeepAgents tool surface.

    No availability probes are configured: builtin tools are treated as
    available by default (cached state ``available=True`` after registration).
    """
    registry = ToolRegistry()
    for binding in builtin_tool_bindings():
        registry.register(binding.definition)
    registry.freeze()
    return registry


_BUILTIN_REGISTRY = _builtin_registry()
_BUILTIN_NAMES = frozenset(_BUILTIN_REGISTRY._definitions) | frozenset(_BUILTIN_REGISTRY._aliases)

_ENFORCEMENT_LOOKUP: dict[str, str] = {
    binding.definition.meta.canonical_name: binding.enforcement.value
    for binding in builtin_tool_bindings()
}


def _resolve_manifest_tool_policy(agent_registry: AgentRegistry, agent_id: str) -> dict[str, Any]:
    agent = agent_registry.get(agent_id)
    return dict(agent.tool_policy) if agent else {}


def compile_session_tool_projection(
    *,
    agent_registry: AgentRegistry,
    agent_id: str,
    metadata: dict[str, Any] | None,
    provider_facts: dict[str, Any] | None = None,
    model_facts: dict[str, Any] | None = None,
    platform_facts: dict[str, Any] | None = None,
    orchestration_mode: str = "legacy",
) -> ToolProjectionSnapshot | None:
    """Return a shadow snapshot when ``orchestration_mode`` is shadow/controlled.

    ``legacy`` returns ``None`` (nothing to bind).  ``shadow`` and
    ``controlled`` both compile a read-only snapshot (controlled additionally
    substitutes managed tools at runtime).  The snapshot is computed only
    from manifest selectors + autonomy metadata + the builtin registry; no
    probes run and no session state mutates.
    """
    if orchestration_mode not in {"shadow", "controlled"}:
        return None

    policy = _resolve_manifest_tool_policy(agent_registry, agent_id)
    # Restrict manifest selectors to names the builtin registry knows; manifest
    # may list tools (e.g. async-subagent helpers) that are intentionally not
    # part of the canonical builtin surface yet.
    raw_allowed = policy.get("allowed") if policy.get("allowed_explicit") else None
    allowed_names = (
        frozenset(name for name in raw_allowed if name in _BUILTIN_NAMES) if raw_allowed is not None else None
    )
    denied_names = frozenset(name for name in policy.get("denied") if name in _BUILTIN_NAMES)
    risk_ceiling = policy.get("risk_ceiling")
    allowed_kinds = frozenset(policy.get("kinds")) if policy.get("kinds") else None

    from tool_platform.taxonomy import ToolRisk

    policy_facts = policy_facts_for_session(
        metadata,
        enforcement_status=orchestration_mode,  # type: ignore[arg-type]
        allowed_names=allowed_names,
        denied_names=denied_names,
        risk_ceiling=ToolRisk(risk_ceiling) if risk_ceiling else None,
        runtime_kind="agent_session",
        enabled_capabilities=frozenset({"deepagents"}),
        provider_facts=provider_facts,
        model_facts=model_facts,
        platform_facts=platform_facts,
    )

    constraints: dict[str, Any] = {
        "runtime_kind": "agent_session",
        "allowed_kinds": [kind.value for kind in allowed_kinds] if allowed_kinds else None,
        "binding_mode": "binding_only",
        "coverage": "deepagents_builtins",
        "custom_tools_included": False,
        "runtime_enforcement": "legacy_runtime",
    }
    return compile_tool_projection(
        agent_id=agent_id,
        policy_facts=policy_facts,
        registry=_BUILTIN_REGISTRY,
        enforcement_lookup=_ENFORCEMENT_LOOKUP,
        orchestration_mode=orchestration_mode,  # type: ignore[arg-type]
        constraints=constraints,
    )


__all__ = ["compile_session_tool_projection"]
