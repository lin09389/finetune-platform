"""Compile a session's tool projection into an immutable shadow snapshot.

The projection turns Agent Manifest selectors + runtime/capability/autonomy
facts into a deterministic, JSON-safe snapshot of which canonical tools are
visible, how they are enforced, and what the deterministic policy facts are.
It is a **pure compile step**: no availability probes are run, no handlers
execute, nothing is persisted.  The legacy DeepAgents runtime stays the
authoritative execution path; this snapshot is bound so that future
``legacy`` vs ``shadow`` comparison can be computed offline from the same
facts without re-running anything.

Construction of the source registry and the enforcement lookup is supplied by
the caller (see :func:`agent_session.runtime_contract.for_agent_session`),
keeping :mod:`tool_platform.projection` free of any DeepAgents/adapter
import and therefore inside the tool-platform dependency floor.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_serializer

from .models import FrozenJsonObject, freeze_json_object, redact_json, thaw_json_object
from .policy import ToolPolicyFacts
from .registry import ToolProjectionContext, ToolRegistry
from .taxonomy import SideEffect, ToolKind, ToolRisk

OrchestrationMode = Literal["legacy", "shadow", "controlled"]
ProjectionEnforcementStatus = Literal["legacy_runtime", "shadow", "controlled"]


class _ProjectionModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True, validate_default=True)


class ResolvedToolSummary(_ProjectionModel):
    """JSON-safe summary of one tool visible in the projection."""

    canonical_name: str = Field(min_length=1, max_length=200)
    kind: ToolKind
    risk: ToolRisk
    side_effects: frozenset[SideEffect]
    enforcement_capability: Literal["hidden_and_enforced", "visible_but_enforced", "unsupported"]
    source: str = ""

    @field_serializer("side_effects")
    def serialize_side_effects(self, value: frozenset[SideEffect]) -> JsonValue:
        return sorted(item.value for item in value)


class ToolProjectionSnapshot(_ProjectionModel):
    """Immutable, wire-safe snapshot of a session's compiled tool projection."""

    schema_version: Literal[1] = 1
    orchestration_mode: OrchestrationMode
    enforcement_status: ProjectionEnforcementStatus
    agent_id: str = Field(min_length=1, max_length=200)
    runtime_kind: str | None = None
    resolved_tools: tuple[ResolvedToolSummary, ...] = ()
    denied: tuple[str, ...] = ()
    enforcement_blockers: tuple[str, ...] = ()
    policy_facts: ToolPolicyFacts
    facts: FrozenJsonObject = Field(default_factory=dict)

    @field_serializer("facts")
    def serialize_facts(self, value: FrozenJsonObject) -> JsonValue:
        return thaw_json_object(value)

    def diagnostic_dump(self) -> dict[str, JsonValue]:
        return redact_json(self.model_dump(mode="json"))  # type: ignore[return-value]


def compile_tool_projection(
    *,
    agent_id: str,
    policy_facts: ToolPolicyFacts,
    registry: ToolRegistry | None,
    enforcement_lookup: Mapping[str, str] | None = None,
    orchestration_mode: OrchestrationMode = "legacy",
    constraints: Mapping[str, Any] | None = None,
) -> ToolProjectionSnapshot:
    """Compile manifest selectors + policy facts into an immutable snapshot.

    ``registry`` may be ``None`` (e.g. legacy mode with nothing to bind); the
    snapshot is then empty and marked ``legacy_runtime``.  ``enforcement_lookup`` maps
    canonical tool names to a DeepAgents enforcement capability value; tools not
    present are treated as ``unsupported`` (fail closed).  Availability probes
    are never run here: only the cached registry availability is consulted.
    """

    constraints = constraints or {}
    enforcement_status: ProjectionEnforcementStatus = (
        "legacy_runtime"
        if orchestration_mode == "legacy"
        else orchestration_mode  # type: ignore[assignment]
    )

    if registry is None:
        return ToolProjectionSnapshot(
            orchestration_mode=orchestration_mode,
            enforcement_status=enforcement_status,
            agent_id=agent_id,
            runtime_kind=constraints.get("runtime_kind"),
            policy_facts=policy_facts,
            facts=freeze_json_object(dict(constraints)),
        )

    context = ToolProjectionContext(
        agent_id=agent_id,
        allowed_names=policy_facts.allowed_names,
        denied_names=policy_facts.denied_names,
        allowed_kinds=_kinds(constraints.get("allowed_kinds")),
        risk_ceiling=policy_facts.risk_ceiling,
        runtime_kind=policy_facts.runtime_kind,
        enabled_capabilities=policy_facts.enabled_capabilities,
        provider_facts=policy_facts.provider_facts,
        model_facts=policy_facts.model_facts,
        platform_facts=policy_facts.platform_facts,
    )
    visible = registry.project(context)
    lookup = enforcement_lookup or {}

    resolved: list[ResolvedToolSummary] = []
    blockers: set[str] = set()
    denied_canonical: set[str] = set()

    denied_set = set(policy_facts.denied_names or frozenset())

    for definition in visible:
        capability = str(lookup.get(definition.meta.canonical_name, "unsupported"))
        if capability not in {"hidden_and_enforced", "visible_but_enforced", "unsupported"}:
            capability = "unsupported"
        resolved.append(
            ResolvedToolSummary(
                canonical_name=definition.meta.canonical_name,
                kind=definition.meta.kind,
                risk=definition.meta.risk,
                side_effects=frozenset(definition.meta.side_effects),
                enforcement_capability=capability,  # type: ignore[arg-type]
                source="",
            )
        )
        if capability == "unsupported":
            blockers.add(definition.meta.canonical_name)

    for name in denied_set:
        if registry.resolve(name) is not None:
            denied_canonical.add(name)

    return ToolProjectionSnapshot(
        orchestration_mode=orchestration_mode,
        enforcement_status=enforcement_status,
        agent_id=agent_id,
        runtime_kind=constraints.get("runtime_kind"),
        resolved_tools=tuple(resolved),
        denied=tuple(sorted(denied_canonical)),
        enforcement_blockers=tuple(sorted(blockers)),
        policy_facts=policy_facts,
        facts=freeze_json_object(dict(constraints)),
    )


def _kinds(value: Any) -> frozenset[ToolKind] | None:
    if value is None:
        return None
    if isinstance(value, frozenset):
        return value
    return frozenset(ToolKind(item) for item in value)


__all__ = [
    "OrchestrationMode",
    "ProjectionEnforcementStatus",
    "ResolvedToolSummary",
    "ToolProjectionSnapshot",
    "compile_tool_projection",
]
