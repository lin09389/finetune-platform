"""Deterministic, fail-closed tool policy decisions.

The policy layer turns explicit facts (risk, side effects, name selectors,
session trust, required runtime/capability/provider/model/platform facts,
availability) into a single ``allow`` / ``ask`` / ``deny`` decision.  It is a
pure function: it never persists approval state, runs no probes, and performs
no I/O.  Approval persistence stays owned by the existing DeepAgents/session
HITL integration; this evaluator only computes the target decision.

Unknown tools and missing required facts always fail closed (``deny``).
``trusted_names`` may downgrade an ``ask`` to ``allow`` but never overrides a
``deny``.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_serializer, field_validator

from .definition import ToolDefinition
from .models import FrozenJsonObject, ToolAvailability, freeze_json_object, redact_json
from .taxonomy import SideEffect, ToolRisk

_RISK_ORDER: dict[ToolRisk, int] = {
    ToolRisk.LOW: 0,
    ToolRisk.MEDIUM: 1,
    ToolRisk.HIGH: 2,
    ToolRisk.CRITICAL: 3,
}


class ToolPolicyDecision(BaseModel):
    """A single deterministic policy verdict for one tool invocation."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    decision: Literal["allow", "ask", "deny"]
    reason_code: str = Field(min_length=1, max_length=200)
    canonical_name: str = Field(min_length=1, max_length=200)
    risk: ToolRisk
    matched_rules: tuple[str, ...] = ()


class ToolPolicyFacts(BaseModel):
    """Non-secret session facts consumed by the policy evaluator.

    ``allowed_names=None`` imposes no name allow-list; an empty set explicitly
    permits no names (deny-all).  ``require_approval_for`` turns a matching
    side effect into ``ask``; ``deny_for`` turns it into a hard ``deny``.
    ``trusted_names`` downgrades ``ask`` to ``allow`` for tools approved in
    this session.  Required-fact fields mirror the registry projection so the
    evaluator can fail closed when a tool's runtime/capability/provider/model/
    platform requirements are unsatisfied.
    """

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True, validate_default=True)

    enforcement_status: Literal["legacy_runtime", "shadow", "controlled"] = "legacy_runtime"
    agent_id: str | None = None
    allowed_names: frozenset[str] | None = None
    denied_names: frozenset[str] = frozenset()
    risk_ceiling: ToolRisk | None = None
    trusted_names: frozenset[str] = frozenset()
    require_approval_for: frozenset[SideEffect] = frozenset()
    deny_for: frozenset[SideEffect] = frozenset()
    runtime_kind: str | None = None
    enabled_capabilities: frozenset[str] | None = None
    provider_facts: FrozenJsonObject = Field(default_factory=dict)
    model_facts: FrozenJsonObject = Field(default_factory=dict)
    platform_facts: FrozenJsonObject = Field(default_factory=dict)

    @field_validator("provider_facts", "model_facts", "platform_facts")
    @classmethod
    def _redact_facts(cls, value: FrozenJsonObject) -> FrozenJsonObject:
        return freeze_json_object(redact_json(value))  # type: ignore[return-value]

    @field_serializer("provider_facts", "model_facts", "platform_facts")
    def _serialize_facts(self, value: FrozenJsonObject) -> JsonValue:
        return _jsonable(value)


def _jsonable(value: object) -> JsonValue:
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (tuple, frozenset, set)):
        return [_jsonable(item) for item in value]
    return value  # type: ignore[return-value]


def _names_for(definition: ToolDefinition[Any, Any]) -> frozenset[str]:
    return frozenset({definition.meta.canonical_name, *definition.aliases})


def _facts_match(required: Mapping[str, object], actual: Mapping[str, object]) -> bool:
    return all(key in actual and actual[key] == expected for key, expected in required.items())


def _required_facts_satisfied(
    definition: ToolDefinition[Any, Any], facts: ToolPolicyFacts
) -> bool:
    if definition.agent_ids and facts.agent_id not in definition.agent_ids:
        return False
    if definition.runtime_kinds and facts.runtime_kind not in definition.runtime_kinds:
        return False
    if definition.required_capabilities and (
        facts.enabled_capabilities is None
        or not definition.required_capabilities.issubset(facts.enabled_capabilities)
    ):
        return False
    if not _facts_match(definition.required_provider_facts, facts.provider_facts):
        return False
    if not _facts_match(definition.required_model_facts, facts.model_facts):
        return False
    return _facts_match(definition.required_platform_facts, facts.platform_facts)


def evaluate_tool_policy(
    definition: ToolDefinition[Any, Any] | None,
    facts: ToolPolicyFacts,
    *,
    requested_name: str | None = None,
    availability: ToolAvailability | None = None,
) -> ToolPolicyDecision:
    """Evaluate a deterministic, fail-closed policy decision.

    ``definition=None`` (unknown / unresolved tool) always denies.  A ``None``
    ``availability`` is treated as "not checked" rather than unavailable; callers
    that want full fail-closed behavior should pass the registry's cached
    :class:`~tool_platform.models.ToolAvailability`.
    """

    if definition is None:
        return ToolPolicyDecision(
            decision="deny",
            reason_code="unknown_tool",
            canonical_name=requested_name or "unknown",
            risk=ToolRisk.CRITICAL,
            matched_rules=("unknown_tool",),
        )

    meta = definition.meta
    names = _names_for(definition)

    if names & facts.denied_names:
        return ToolPolicyDecision(
            decision="deny",
            reason_code="explicit_deny",
            canonical_name=meta.canonical_name,
            risk=meta.risk,
            matched_rules=("explicit_deny",),
        )

    if facts.allowed_names is not None and not (names & facts.allowed_names):
        return ToolPolicyDecision(
            decision="deny",
            reason_code="not_in_allowed_names",
            canonical_name=meta.canonical_name,
            risk=meta.risk,
            matched_rules=("not_in_allowed_names",),
        )

    if meta.side_effects & facts.deny_for:
        return ToolPolicyDecision(
            decision="deny",
            reason_code="denied_side_effect",
            canonical_name=meta.canonical_name,
            risk=meta.risk,
            matched_rules=("denied_side_effect",),
        )

    if facts.risk_ceiling is not None and _RISK_ORDER[meta.risk] > _RISK_ORDER[facts.risk_ceiling]:
        return ToolPolicyDecision(
            decision="deny",
            reason_code="risk_above_ceiling",
            canonical_name=meta.canonical_name,
            risk=meta.risk,
            matched_rules=("risk_above_ceiling",),
        )

    if not _required_facts_satisfied(definition, facts):
        return ToolPolicyDecision(
            decision="deny",
            reason_code="missing_required_facts",
            canonical_name=meta.canonical_name,
            risk=meta.risk,
            matched_rules=("missing_required_facts",),
        )

    if availability is not None and not availability.available:
        return ToolPolicyDecision(
            decision="deny",
            reason_code="unavailable",
            canonical_name=meta.canonical_name,
            risk=meta.risk,
            matched_rules=("unavailable",),
        )

    if meta.side_effects & facts.require_approval_for:
        if names & facts.trusted_names:
            return ToolPolicyDecision(
                decision="allow",
                reason_code="trusted",
                canonical_name=meta.canonical_name,
                risk=meta.risk,
                matched_rules=("requires_approval", "trusted"),
            )
        return ToolPolicyDecision(
            decision="ask",
            reason_code="requires_approval",
            canonical_name=meta.canonical_name,
            risk=meta.risk,
            matched_rules=("requires_approval",),
        )

    return ToolPolicyDecision(
        decision="allow",
        reason_code="default_allow",
        canonical_name=meta.canonical_name,
        risk=meta.risk,
        matched_rules=(),
    )


__all__ = [
    "ToolPolicyDecision",
    "ToolPolicyFacts",
    "evaluate_tool_policy",
]
