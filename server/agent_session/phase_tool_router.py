from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field
from tool_platform.taxonomy import ToolKind

from agent_session.agent_registry import AgentRegistry
from agent_session.phase_controller import (
    PhaseId,
    PhaseRoutingMode,
    PhaseState,
    controlled_phase_routing_requires_fail_closed,
)
from agent_session.tool_projection import compile_session_tool_projection

PHASE_PROJECTION_SCHEMA_VERSION = "agent.execution.phase_projection.v1"

PhaseProjectionApplication = Literal["none", "shadow", "next_runtime_contract", "blocked"]

_BUILTIN_KIND_BY_NAME: dict[str, ToolKind] = {
    "ls": ToolKind.LIST_DIR,
    "read_file": ToolKind.READ,
    "glob": ToolKind.SEARCH,
    "grep": ToolKind.SEARCH,
    "write_file": ToolKind.WRITE,
    "edit_file": ToolKind.EDIT,
    "execute": ToolKind.EXECUTE,
    "task": ToolKind.TASK,
    "write_todos": ToolKind.TODO,
}

PHASE_CANDIDATE_KINDS: dict[PhaseId, frozenset[ToolKind]] = {
    "inspect": frozenset({ToolKind.LIST_DIR, ToolKind.READ, ToolKind.SEARCH}),
    "plan": frozenset({ToolKind.READ, ToolKind.SEARCH, ToolKind.TODO, ToolKind.PLAN_MODE}),
    "implement": frozenset({ToolKind.READ, ToolKind.WRITE, ToolKind.EDIT, ToolKind.SEARCH, ToolKind.LIST_DIR}),
    "verify": frozenset({ToolKind.EXECUTE, ToolKind.READ, ToolKind.SEARCH, ToolKind.LIST_DIR}),
    "review": frozenset({ToolKind.READ, ToolKind.SEARCH, ToolKind.LIST_DIR}),
    "deliver": frozenset({ToolKind.READ, ToolKind.LIST_DIR}),
}


class PhaseToolProjection(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    schema_version: Literal["agent.execution.phase_projection.v1"]
    phase: PhaseId
    routing_mode: PhaseRoutingMode
    application: PhaseProjectionApplication
    allowed_tools: list[str]
    denied_tools: list[str]
    blocked_reasons: list[str]
    goal_plan_scope_hints: list[str] = Field(default_factory=list)
    tightening_proof: dict[str, Any] = Field(default_factory=dict)
    runtime_bound: bool = False


def _manifest_allowed_names(agent_registry: AgentRegistry, agent_id: str) -> frozenset[str] | None:
    agent = agent_registry.get(agent_id)
    if agent is None:
        return None
    policy = dict(agent.tool_policy or {})
    if not policy.get("allowed_explicit"):
        return None
    allowed = policy.get("allowed")
    if not isinstance(allowed, list):
        return frozenset()
    return frozenset(str(name) for name in allowed)


def _goal_plan_scope_hints(metadata: dict[str, Any]) -> list[str]:
    execution_plan = metadata.get("execution_plan")
    if not isinstance(execution_plan, dict):
        return []
    goal_plan = execution_plan.get("goal_plan")
    if not isinstance(goal_plan, dict):
        return []
    scopes = goal_plan.get("file_scopes") or []
    hints: list[str] = []
    for item in scopes:
        if isinstance(item, dict) and str(item.get("path") or "").strip():
            hints.append(str(item["path"]))
    return hints


def compile_phase_tool_projection(
    *,
    agent_registry: AgentRegistry,
    agent_id: str,
    metadata: dict[str, Any],
    session: dict[str, Any],
    phase_state: PhaseState,
    orchestration_mode: str,
    provider: str | None = None,
    model: str | None = None,
) -> PhaseToolProjection:
    phase = phase_state.current_phase
    routing_mode = phase_state.routing_mode
    hints = _goal_plan_scope_hints(metadata)

    if routing_mode == "legacy":
        return PhaseToolProjection(
            schema_version=PHASE_PROJECTION_SCHEMA_VERSION,
            phase=phase,
            routing_mode=routing_mode,
            application="none",
            allowed_tools=[],
            denied_tools=[],
            blocked_reasons=[],
            goal_plan_scope_hints=hints,
            tightening_proof={"reason": "legacy_runtime"},
            runtime_bound=False,
        )

    fail_closed, fail_reasons = controlled_phase_routing_requires_fail_closed(metadata, session=session)
    if fail_closed:
        return PhaseToolProjection(
            schema_version=PHASE_PROJECTION_SCHEMA_VERSION,
            phase=phase,
            routing_mode="controlled",
            application="blocked",
            allowed_tools=[],
            denied_tools=[],
            blocked_reasons=fail_reasons,
            goal_plan_scope_hints=hints,
            tightening_proof={"fail_closed": True, "missing_facts": fail_reasons},
            runtime_bound=False,
        )

    snapshot = compile_session_tool_projection(
        agent_registry=agent_registry,
        agent_id=agent_id,
        metadata=metadata,
        orchestration_mode=orchestration_mode if orchestration_mode in {"shadow", "controlled"} else "shadow",
        provider_facts={"provider": provider} if provider else None,
        model_facts={"model": model} if model else None,
    )
    manifest_allowed = _manifest_allowed_names(agent_registry, agent_id)
    phase_kinds = PHASE_CANDIDATE_KINDS[phase]

    allowed: list[str] = []
    denied: list[str] = []
    blocked = list(snapshot.enforcement_blockers if snapshot else ())

    if snapshot:
        for tool in snapshot.resolved_tools:
            name = tool.canonical_name
            kind = _BUILTIN_KIND_BY_NAME.get(name, tool.kind)
            if kind not in phase_kinds:
                denied.append(name)
                continue
            if manifest_allowed is not None and name not in manifest_allowed:
                denied.append(name)
                continue
            allowed.append(name)

    allowed_set = set(allowed)
    for name in blocked:
        if name in allowed_set:
            allowed_set.remove(name)
            denied.append(name)

    application: PhaseProjectionApplication
    if orchestration_mode == "controlled":
        application = "next_runtime_contract"
    elif orchestration_mode == "shadow" or routing_mode in {"goal_plan", "execution_plan_fallback", "shadow"}:
        application = "shadow"
    else:
        application = "none"

    return PhaseToolProjection(
        schema_version=PHASE_PROJECTION_SCHEMA_VERSION,
        phase=phase,
        routing_mode=routing_mode,
        application=application,
        allowed_tools=sorted(allowed_set),
        denied_tools=sorted(set(denied)),
        blocked_reasons=sorted(set(blocked)),
        goal_plan_scope_hints=hints,
        tightening_proof={
            "intersection": "phase_candidates∩manifest∩policy_snapshot",
            "goal_plan_authority": "diagnostic_only",
            "phase_kinds": sorted(kind.value for kind in phase_kinds),
        },
        runtime_bound=application == "next_runtime_contract",
    )


def serialize_phase_tool_projection(projection: PhaseToolProjection) -> dict[str, Any]:
    return projection.model_dump(mode="json")


def parse_phase_tool_projection(raw: Any) -> PhaseToolProjection | None:
    if not isinstance(raw, dict):
        return None
    try:
        return PhaseToolProjection.model_validate(raw)
    except Exception:
        return None


def persist_phase_tool_projection(metadata: dict[str, Any], projection: PhaseToolProjection) -> dict[str, Any]:
    updated = dict(metadata)
    updated["phase_tool_projection"] = serialize_phase_tool_projection(projection)
    return updated


def bootstrap_build_phase_routing(
    *,
    metadata: dict[str, Any],
    session: dict[str, Any],
    agent_registry: AgentRegistry,
    orchestration_mode: str,
    provider: str | None,
    model: str | None,
) -> dict[str, Any]:
    from agent_session.phase_controller import initial_build_phase_state, persist_phase_state

    if str(session.get("agent_id") or "build") != "build":
        return metadata
    from agent_session.phase_controller import phase_routing_enabled_for_session

    if not phase_routing_enabled_for_session(session):
        return metadata

    state = initial_build_phase_state(metadata=metadata, session=session)
    fail_closed, reasons = controlled_phase_routing_requires_fail_closed(metadata, session=session)
    if fail_closed:
        state = state.model_copy(
            update={
                "fail_closed": True,
                "fail_closed_reasons": reasons,
                "next_visible_action": "Controlled phase routing blocked until runtime facts are complete.",
            }
        )
    metadata = persist_phase_state(metadata, state)
    projection = compile_phase_tool_projection(
        agent_registry=agent_registry,
        agent_id=str(session.get("agent_id") or "build"),
        metadata=metadata,
        session=session,
        phase_state=state,
        orchestration_mode=orchestration_mode,
        provider=provider,
        model=model,
    )
    return persist_phase_tool_projection(metadata, projection)


__all__ = [
    "PHASE_CANDIDATE_KINDS",
    "PHASE_PROJECTION_SCHEMA_VERSION",
    "PhaseProjectionApplication",
    "PhaseToolProjection",
    "compile_phase_tool_projection",
    "parse_phase_tool_projection",
    "persist_phase_tool_projection",
    "serialize_phase_tool_projection",
]
