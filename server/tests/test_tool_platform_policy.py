"""Table-driven contract tests for the deterministic tool policy evaluator."""

from __future__ import annotations

import pytest
from pydantic import BaseModel, ConfigDict, ValidationError
from tool_platform.definition import ToolDefinition
from tool_platform.models import CanonicalToolMeta, ToolAvailability
from tool_platform.policy import ToolPolicyDecision, ToolPolicyFacts, evaluate_tool_policy
from tool_platform.taxonomy import SideEffect, ToolKind, ToolRisk, defaults_for_kind


class StrictInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    path: str


class StrictOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    content: str


async def _handler(request: StrictInput) -> StrictOutput:
    return StrictOutput(content=request.path)


def make_definition(
    name: str = "test.tool",
    *,
    aliases: tuple[str, ...] = (),
    kind: ToolKind = ToolKind.READ,
    runtime_kinds: frozenset[str] = frozenset(),
    required_capabilities: frozenset[str] = frozenset(),
    agent_ids: frozenset[str] = frozenset(),
    required_provider_facts: dict[str, object] | None = None,
    required_model_facts: dict[str, object] | None = None,
    required_platform_facts: dict[str, object] | None = None,
) -> ToolDefinition[StrictInput, StrictOutput]:
    defaults = defaults_for_kind(kind)
    return ToolDefinition(
        meta=CanonicalToolMeta(
            canonical_name=name,
            kind=kind,
            side_effects=defaults.side_effects,
            risk=defaults.risk,
            execution_location=defaults.execution_location,
            display_name=name,
            description="A test tool.",
        ),
        input_model=StrictInput,
        output_model=StrictOutput,
        handler=_handler,
        aliases=aliases,
        runtime_kinds=runtime_kinds,
        required_capabilities=required_capabilities,
        agent_ids=agent_ids,
        required_provider_facts=required_provider_facts or {},
        required_model_facts=required_model_facts or {},
        required_platform_facts=required_platform_facts or {},
    )


# Side-effect gates mirror what agent_session.permission.policy_facts_for_session
# derives from each autonomy mode.
_SAFE_AUTO_ASK = frozenset(
    {SideEffect.PROCESS, SideEffect.NETWORK, SideEffect.EXTERNAL_WRITE, SideEffect.CREDENTIAL, SideEffect.DESTRUCTIVE}
)
_CONFIRM_ALL_ASK = frozenset(
    {
        SideEffect.WORKSPACE_WRITE,
        SideEffect.PROCESS,
        SideEffect.NETWORK,
        SideEffect.EXTERNAL_WRITE,
        SideEffect.CREDENTIAL,
        SideEffect.DESTRUCTIVE,
    }
)
_READ_ONLY_DENY = _CONFIRM_ALL_ASK

SAFE_AUTO_FACTS = ToolPolicyFacts(require_approval_for=_SAFE_AUTO_ASK)
CONFIRM_ALL_FACTS = ToolPolicyFacts(require_approval_for=_CONFIRM_ALL_ASK)
READ_ONLY_FACTS = ToolPolicyFacts(deny_for=_READ_ONLY_DENY)


@pytest.mark.parametrize(
    ("kind", "facts", "expected_decision", "expected_reason"),
    [
        # safe_auto: read-only tools allowed; workspace writes allowed (no HITL);
        # process / network / credential / destructive ask.
        (ToolKind.READ, SAFE_AUTO_FACTS, "allow", "default_allow"),
        (ToolKind.LIST_DIR, SAFE_AUTO_FACTS, "allow", "default_allow"),
        (ToolKind.SEARCH, SAFE_AUTO_FACTS, "allow", "default_allow"),
        (ToolKind.WRITE, SAFE_AUTO_FACTS, "allow", "default_allow"),
        (ToolKind.EDIT, SAFE_AUTO_FACTS, "allow", "default_allow"),
        (ToolKind.EXECUTE, SAFE_AUTO_FACTS, "ask", "requires_approval"),
        (ToolKind.WEB_SEARCH, SAFE_AUTO_FACTS, "ask", "requires_approval"),
        (ToolKind.WEB_FETCH, SAFE_AUTO_FACTS, "ask", "requires_approval"),
        (ToolKind.MCP_EXTENSION, SAFE_AUTO_FACTS, "ask", "requires_approval"),
        (ToolKind.TRAINING, SAFE_AUTO_FACTS, "ask", "requires_approval"),
        # confirm_all: every non-NONE side effect asks; pure reads still allow.
        (ToolKind.READ, CONFIRM_ALL_FACTS, "allow", "default_allow"),
        (ToolKind.WRITE, CONFIRM_ALL_FACTS, "ask", "requires_approval"),
        (ToolKind.EDIT, CONFIRM_ALL_FACTS, "ask", "requires_approval"),
        (ToolKind.EXECUTE, CONFIRM_ALL_FACTS, "ask", "requires_approval"),
        # read_only: any side effect beyond NONE is hard-denied (fail-closed).
        (ToolKind.READ, READ_ONLY_FACTS, "allow", "default_allow"),
        (ToolKind.LIST_DIR, READ_ONLY_FACTS, "allow", "default_allow"),
        (ToolKind.WRITE, READ_ONLY_FACTS, "deny", "denied_side_effect"),
        (ToolKind.EDIT, READ_ONLY_FACTS, "deny", "denied_side_effect"),
        (ToolKind.EXECUTE, READ_ONLY_FACTS, "deny", "denied_side_effect"),
        (ToolKind.WEB_SEARCH, READ_ONLY_FACTS, "deny", "denied_side_effect"),
        (ToolKind.MCP_EXTENSION, READ_ONLY_FACTS, "deny", "denied_side_effect"),
    ],
)
def test_autonomy_matrix(kind, facts, expected_decision, expected_reason):
    definition = make_definition(name=f"test.{kind.value}", kind=kind)

    decision = evaluate_tool_policy(definition, facts)

    assert decision.decision == expected_decision
    assert decision.reason_code == expected_reason
    assert decision.canonical_name == definition.meta.canonical_name
    assert decision.risk == definition.meta.risk


def test_read_only_defaults_allow_without_any_gates():
    definition = make_definition(kind=ToolKind.READ)
    decision = evaluate_tool_policy(definition, ToolPolicyFacts())
    assert decision.decision == "allow"
    assert decision.reason_code == "default_allow"
    assert decision.matched_rules == ()


def test_workspace_write_trusted_downgrades_ask_to_allow():
    definition = make_definition(name="test.write", aliases=("write_file",), kind=ToolKind.WRITE)
    facts = ToolPolicyFacts(
        require_approval_for=frozenset({SideEffect.WORKSPACE_WRITE}),
        trusted_names=frozenset({"write_file"}),
    )

    decision = evaluate_tool_policy(definition, facts)

    assert decision.decision == "allow"
    assert decision.reason_code == "trusted"
    assert decision.matched_rules == ("requires_approval", "trusted")


def test_trust_matches_canonical_name_or_alias():
    definition = make_definition(name="test.execute", aliases=("run",), kind=ToolKind.EXECUTE)
    facts = ToolPolicyFacts(
        require_approval_for=frozenset({SideEffect.PROCESS}),
        trusted_names=frozenset({"run"}),
    )
    assert evaluate_tool_policy(definition, facts).reason_code == "trusted"

    facts_canonical = ToolPolicyFacts(
        require_approval_for=frozenset({SideEffect.PROCESS}),
        trusted_names=frozenset({"test.execute"}),
    )
    assert evaluate_tool_policy(definition, facts_canonical).reason_code == "trusted"


def test_trust_does_not_override_explicit_deny():
    definition = make_definition(name="test.write", aliases=("write_file",), kind=ToolKind.WRITE)
    facts = ToolPolicyFacts(
        denied_names=frozenset({"write_file"}),
        trusted_names=frozenset({"write_file"}),
        require_approval_for=frozenset({SideEffect.WORKSPACE_WRITE}),
    )
    assert evaluate_tool_policy(definition, facts).reason_code == "explicit_deny"


def test_trust_does_not_override_risk_ceiling():
    definition = make_definition(name="test.execute", kind=ToolKind.EXECUTE)
    facts = ToolPolicyFacts(
        risk_ceiling=ToolRisk.MEDIUM,
        trusted_names=frozenset({"test.execute"}),
    )
    decision = evaluate_tool_policy(definition, facts)
    assert decision.reason_code == "risk_above_ceiling"
    assert decision.decision == "deny"


def test_explicit_deny_matches_canonical_name_or_alias():
    definition = make_definition(name="test.write", aliases=("write_file",), kind=ToolKind.WRITE)

    by_canonical = ToolPolicyFacts(denied_names=frozenset({"test.write"}))
    assert evaluate_tool_policy(definition, by_canonical).reason_code == "explicit_deny"

    by_alias = ToolPolicyFacts(denied_names=frozenset({"write_file"}))
    assert evaluate_tool_policy(definition, by_alias).reason_code == "explicit_deny"


def test_explicit_deny_takes_precedence_over_denied_side_effect():
    definition = make_definition(name="test.execute", kind=ToolKind.EXECUTE)
    facts = ToolPolicyFacts(
        denied_names=frozenset({"test.execute"}),
        deny_for=frozenset({SideEffect.PROCESS, SideEffect.DESTRUCTIVE}),
    )
    decision = evaluate_tool_policy(definition, facts)
    assert decision.reason_code == "explicit_deny"


def test_empty_allowed_names_denies_everything():
    definition = make_definition(kind=ToolKind.READ)
    facts = ToolPolicyFacts(allowed_names=frozenset())
    decision = evaluate_tool_policy(definition, facts)
    assert decision.decision == "deny"
    assert decision.reason_code == "not_in_allowed_names"


def test_non_empty_allowed_names_excludes_unlisted_tools():
    allowed = make_definition(name="test.allowed", kind=ToolKind.READ)
    blocked = make_definition(name="test.blocked", kind=ToolKind.READ)
    facts = ToolPolicyFacts(allowed_names=frozenset({"test.allowed"}))

    assert evaluate_tool_policy(allowed, facts).decision == "allow"
    assert evaluate_tool_policy(blocked, facts).reason_code == "not_in_allowed_names"


def test_risk_ceiling_denies_above_and_allows_at_ceiling():
    definition = make_definition(name="test.execute", kind=ToolKind.EXECUTE)  # risk HIGH

    above = evaluate_tool_policy(definition, ToolPolicyFacts(risk_ceiling=ToolRisk.MEDIUM))
    assert above.decision == "deny"
    assert above.reason_code == "risk_above_ceiling"

    at_ceiling = evaluate_tool_policy(definition, ToolPolicyFacts(risk_ceiling=ToolRisk.HIGH))
    assert at_ceiling.decision == "allow"


@pytest.mark.parametrize(
    ("field", "kwargs", "facts_kwargs"),
    [
        ("required_capabilities", {"required_capabilities": frozenset({"shell"})}, {"enabled_capabilities": frozenset()}),
        ("runtime_kinds", {"runtime_kinds": frozenset({"agent_session"})}, {"runtime_kind": "worker"}),
        ("agent_ids", {"agent_ids": frozenset({"build"})}, {"agent_id": "review"}),
        ("required_provider_facts", {"required_provider_facts": {"tool_calling": True}}, {"provider_facts": {"tool_calling": False}}),
        ("required_model_facts", {"required_model_facts": {"family": "gpt"}}, {"model_facts": {"family": "llama"}}),
        ("required_platform_facts", {"required_platform_facts": {"sandbox": "local"}}, {"platform_facts": {}}),
    ],
)
def test_missing_required_facts_fail_closed(field, kwargs, facts_kwargs):
    definition = make_definition(name="test.execute", kind=ToolKind.EXECUTE, **kwargs)
    facts = ToolPolicyFacts(**facts_kwargs)

    decision = evaluate_tool_policy(definition, facts)

    assert decision.decision == "deny"
    assert decision.reason_code == "missing_required_facts"
    assert decision.matched_rules == ("missing_required_facts",)


def test_satisfied_required_facts_proceed_to_decision():
    definition = make_definition(
        name="test.execute",
        kind=ToolKind.EXECUTE,
        agent_ids=frozenset({"build"}),
        runtime_kinds=frozenset({"agent_session"}),
        required_capabilities=frozenset({"shell"}),
        required_provider_facts={"tool_calling": True},
        required_model_facts={"family": "gpt"},
        required_platform_facts={"sandbox": "local"},
    )
    facts = ToolPolicyFacts(
        agent_id="build",
        runtime_kind="agent_session",
        enabled_capabilities=frozenset({"shell", "other"}),
        provider_facts={"tool_calling": True},
        model_facts={"family": "gpt"},
        platform_facts={"sandbox": "local"},
        require_approval_for=frozenset({SideEffect.PROCESS}),
    )
    decision = evaluate_tool_policy(definition, facts)
    assert decision.decision == "ask"
    assert decision.reason_code == "requires_approval"


def test_unknown_tool_denies_fail_closed():
    decision = evaluate_tool_policy(None, ToolPolicyFacts(), requested_name="missing.tool")

    assert decision.decision == "deny"
    assert decision.reason_code == "unknown_tool"
    assert decision.canonical_name == "missing.tool"
    assert decision.risk == ToolRisk.CRITICAL
    assert decision.matched_rules == ("unknown_tool",)


def test_unavailable_denies_when_explicitly_unavailable():
    definition = make_definition(kind=ToolKind.READ)
    availability = ToolAvailability(
        canonical_name="test.tool", available=False, reason_code="dependency_missing"
    )
    decision = evaluate_tool_policy(definition, ToolPolicyFacts(), availability=availability)
    assert decision.decision == "deny"
    assert decision.reason_code == "unavailable"


def test_availability_none_does_not_deny():
    definition = make_definition(kind=ToolKind.READ)
    decision = evaluate_tool_policy(definition, ToolPolicyFacts(), availability=None)
    assert decision.decision == "allow"


def test_enforcement_status_does_not_change_decision_logic():
    definition = make_definition(kind=ToolKind.EXECUTE)
    for status in ("legacy_runtime", "shadow", "controlled"):
        facts = ToolPolicyFacts(
            enforcement_status=status,  # type: ignore[arg-type]
            require_approval_for=frozenset({SideEffect.PROCESS}),
        )
        decision = evaluate_tool_policy(definition, facts)
        assert decision.decision == "ask"
        assert decision.reason_code == "requires_approval"


def test_policy_facts_are_frozen_strict_and_redact_secrets():
    facts = ToolPolicyFacts(provider_facts={"x-api-key": "catalog-secret", "tool_calling": True})

    assert facts.provider_facts == {"x-api-key": "[REDACTED]", "tool_calling": True}
    dumped = facts.model_dump_json()
    assert "catalog-secret" not in dumped
    assert facts.model_config.get("frozen") is True
    with pytest.raises(ValidationError):
        ToolPolicyFacts(unknown_field=True)  # type: ignore[call-arg]
    # Round-trip preserves the (already redacted) facts and frozenset gates.
    assert ToolPolicyFacts.model_validate_json(dumped) == facts


def test_policy_facts_round_trip_preserves_side_effect_gates():
    facts = ToolPolicyFacts(
        require_approval_for=frozenset({SideEffect.PROCESS, SideEffect.NETWORK}),
        deny_for=frozenset({SideEffect.DESTRUCTIVE}),
        trusted_names=frozenset({"write_file"}),
        risk_ceiling=ToolRisk.HIGH,
    )
    assert ToolPolicyFacts.model_validate_json(facts.model_dump_json()) == facts


def test_policy_decision_is_frozen_and_strict():
    decision = evaluate_tool_policy(make_definition(kind=ToolKind.READ), ToolPolicyFacts())
    assert decision.model_config.get("frozen") is True
    with pytest.raises(ValidationError):
        ToolPolicyDecision(
            decision="allow",
            reason_code="default_allow",
            canonical_name="test.tool",
            risk=ToolRisk.LOW,
            unknown=True,  # type: ignore[call-arg]
        )
