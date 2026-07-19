from agent_session.execution_context import AgentDefinition
from agent_session.permission import (
    CONFIRM_ALL_REQUIRE_APPROVAL_EFFECTS,
    DEFAULT_DEEPAGENTS_INTERRUPT_ON,
    READ_ONLY_DENY_EFFECTS,
    SAFE_AUTO_REQUIRE_APPROVAL_EFFECTS,
    build_filesystem_permissions,
    default_deepagents_permission_metadata,
    filesystem_permission_profile_for_agent,
    grant_session_tool_trust,
    permission_policy_for_agent,
    policy_facts_for_session,
    resolve_deepagents_interrupt_on,
    validate_hitl_decisions,
)
from deepagents.middleware.filesystem import _check_fs_permission
from pydantic import BaseModel, ConfigDict
from tool_platform.definition import ToolDefinition
from tool_platform.models import CanonicalToolMeta
from tool_platform.policy import evaluate_tool_policy
from tool_platform.taxonomy import SideEffect, ToolKind, ToolRisk, defaults_for_kind


def test_build_profile_allows_workspace_read_and_write():
    rules = build_filesystem_permissions("build")

    assert _check_fs_permission(rules, "read", "/workspace") == "allow"
    assert _check_fs_permission(rules, "read", "/workspace/src/app.py") == "allow"
    assert _check_fs_permission(rules, "write", "/workspace") == "allow"
    assert _check_fs_permission(rules, "write", "/workspace/src/app.py") == "allow"


def test_build_profile_denies_sensitive_env_before_workspace_allow():
    rules = build_filesystem_permissions("build")

    assert rules[0].mode == "deny"
    assert _check_fs_permission(rules, "read", "/workspace/.env") == "deny"
    assert _check_fs_permission(rules, "write", "/workspace/packages/api/.env.local") == "deny"


def test_readonly_profile_allows_read_but_denies_write():
    rules = build_filesystem_permissions("readonly")

    assert _check_fs_permission(rules, "read", "/workspace") == "allow"
    assert _check_fs_permission(rules, "read", "/workspace/src/app.py") == "allow"
    assert _check_fs_permission(rules, "write", "/workspace") == "deny"
    assert _check_fs_permission(rules, "write", "/workspace/src/app.py") == "deny"


def test_readable_virtual_mount_roots_are_not_caught_by_fallback_deny():
    rules = build_filesystem_permissions("build")

    for path in ("/context", "/large_tool_results", "/conversation_history", "/memories", "/agent-memory", "/policies"):
        assert _check_fs_permission(rules, "read", path) == "allow"


def test_fallback_denies_unknown_paths():
    rules = build_filesystem_permissions("build")

    assert _check_fs_permission(rules, "read", "/tmp/outside.txt") == "deny"
    assert _check_fs_permission(rules, "write", "/context/generated.txt") == "deny"


def test_agent_profile_mapping():
    assert filesystem_permission_profile_for_agent("build") == "build"
    assert filesystem_permission_profile_for_agent("explore") == "readonly"
    assert filesystem_permission_profile_for_agent("review") == "readonly"
    assert filesystem_permission_profile_for_agent("unknown") == "deny_all"


def test_permission_policy_centralizes_runtime_access_rules():
    agent = AgentDefinition(id="limited", name="Limited", tools=["read_file", "grep"])
    # confirm_all still stores legacy deepagents_interrupt_on=True → full HITL map
    policy = permission_policy_for_agent(agent, "limited", default_deepagents_permission_metadata("confirm_all"))
    named_tools = [
        type("Tool", (), {"name": "read_file"})(),
        type("Tool", (), {"name": "execute"})(),
    ]

    assert policy.allowed_tools() == {"read_file", "grep"}
    assert [tool.name for tool in policy.filter_named_tools(named_tools)] == ["read_file"]
    assert policy.interrupt_on() == {"write_file": True, "edit_file": True, "execute": True}
    assert _check_fs_permission(policy.filesystem_permissions(), "read", "/workspace/src/app.py") == "deny"


def test_default_permission_metadata_safe_auto_is_weaker_than_confirm_all():
    safe = default_deepagents_permission_metadata("safe_auto")
    confirm = default_deepagents_permission_metadata("confirm_all")
    assert safe["autonomy_mode"] == "safe_auto"
    assert safe["deepagents_interrupt_on"] is False
    assert confirm["autonomy_mode"] == "confirm_all"
    assert confirm["deepagents_interrupt_on"] is True
    assert permission_policy_for_agent(None, "build", safe).interrupt_on() is None
    assert permission_policy_for_agent(None, "build", confirm).interrupt_on() == {
        "write_file": True,
        "edit_file": True,
        "execute": True,
    }


def test_permission_policy_defaults_to_agent_filesystem_profile_without_tool_limit():
    policy = permission_policy_for_agent(None, "project_chat", {})

    assert policy.allowed_tools() is None
    assert policy.interrupt_on() is None
    assert _check_fs_permission(policy.filesystem_permissions(), "read", "/workspace/src/app.py") == "allow"
    assert _check_fs_permission(policy.filesystem_permissions(), "write", "/workspace/src/app.py") == "deny"


def test_validate_hitl_decisions_normalizes_edit_action():
    part = {
        "type": "permission",
        "status": "pending",
        "payload": {
            "actions": [
                {
                    "name": "edit_file",
                    "args": {"file_path": "/workspace/a.py"},
                    "allowed_decisions": ["approve", "edit", "reject"],
                }
            ]
        },
    }

    decisions = validate_hitl_decisions(
        part,
        [{"type": "edit", "editedAction": {"name": "edit_file", "args": {"file_path": "/workspace/b.py"}}}],
    )

    assert decisions == [{"type": "edit", "edited_action": {"name": "edit_file", "args": {"file_path": "/workspace/b.py"}}}]


# --- deterministic tool policy facts adapter (Task 6) ---------------------------


class _StrictInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    path: str


class _StrictOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    content: str


async def _stub_handler(request: _StrictInput) -> _StrictOutput:  # pragma: no cover - policy never invokes handlers
    return _StrictOutput(content=request.path)


def _definition(name: str, kind: ToolKind, aliases: tuple[str, ...] = ()) -> ToolDefinition:
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
        input_model=_StrictInput,
        output_model=_StrictOutput,
        handler=_stub_handler,
        aliases=aliases,
    )


def test_policy_facts_for_session_read_only_denies_every_side_effect():
    facts = policy_facts_for_session(default_deepagents_permission_metadata("read_only"))

    assert facts.deny_for == READ_ONLY_DENY_EFFECTS
    assert facts.require_approval_for == frozenset()
    for effect in (
        SideEffect.WORKSPACE_WRITE,
        SideEffect.PROCESS,
        SideEffect.NETWORK,
        SideEffect.EXTERNAL_WRITE,
        SideEffect.CREDENTIAL,
        SideEffect.DESTRUCTIVE,
    ):
        assert effect in facts.deny_for


def test_policy_facts_for_session_confirm_all_asks_every_side_effect():
    facts = policy_facts_for_session(default_deepagents_permission_metadata("confirm_all"))

    assert facts.require_approval_for == CONFIRM_ALL_REQUIRE_APPROVAL_EFFECTS
    assert facts.deny_for == frozenset()
    # confirm_all gates workspace writes too (unlike safe_auto).
    assert SideEffect.WORKSPACE_WRITE in facts.require_approval_for


def test_policy_facts_for_session_safe_auto_allows_workspace_write_but_gates_sensitive_effects():
    facts = policy_facts_for_session(default_deepagents_permission_metadata("safe_auto"))

    assert facts.require_approval_for == SAFE_AUTO_REQUIRE_APPROVAL_EFFECTS
    assert facts.deny_for == frozenset()
    assert SideEffect.WORKSPACE_WRITE not in facts.require_approval_for
    for effect in (
        SideEffect.PROCESS,
        SideEffect.NETWORK,
        SideEffect.EXTERNAL_WRITE,
        SideEffect.CREDENTIAL,
        SideEffect.DESTRUCTIVE,
    ):
        assert effect in facts.require_approval_for


def test_policy_facts_for_session_defaults_to_safe_auto_for_missing_metadata():
    facts = policy_facts_for_session(None)

    assert facts.require_approval_for == SAFE_AUTO_REQUIRE_APPROVAL_EFFECTS
    assert facts.enforcement_status == "legacy_runtime"
    assert facts.trusted_names == frozenset()


def test_policy_facts_for_session_trusted_names_come_from_session_tool_trust():
    meta = grant_session_tool_trust(
        default_deepagents_permission_metadata("confirm_all"),
        ["edit_file", "execute"],
    )

    facts = policy_facts_for_session(meta)

    assert facts.trusted_names == frozenset({"edit_file", "execute"})


def test_policy_facts_for_session_read_only_never_gains_trust():
    meta = grant_session_tool_trust(
        {"autonomy_mode": "read_only", "deepagents_interrupt_on": False},
        ["write_file", "execute"],
    )

    facts = policy_facts_for_session(meta)

    assert facts.trusted_names == frozenset()
    assert facts.deny_for == READ_ONLY_DENY_EFFECTS


def test_policy_facts_for_session_forwards_projection_selectors_and_facts():
    facts = policy_facts_for_session(
        {"autonomy_mode": "safe_auto"},
        enforcement_status="shadow",
        allowed_names=frozenset({"read_file"}),
        denied_names=frozenset({"execute"}),
        risk_ceiling=ToolRisk.MEDIUM,
        runtime_kind="agent_session",
        enabled_capabilities=frozenset({"shell"}),
        provider_facts={"tool_calling": True},
        model_facts={"family": "gpt"},
        platform_facts={"sandbox": "local"},
    )

    assert facts.enforcement_status == "shadow"
    assert facts.allowed_names == frozenset({"read_file"})
    assert facts.denied_names == frozenset({"execute"})
    assert facts.risk_ceiling == ToolRisk.MEDIUM
    assert facts.runtime_kind == "agent_session"
    assert facts.enabled_capabilities == frozenset({"shell"})
    assert facts.provider_facts == {"tool_calling": True}
    assert facts.model_facts == {"family": "gpt"}
    assert facts.platform_facts == {"sandbox": "local"}


def test_policy_facts_for_session_redacts_sensitive_provider_facts():
    facts = policy_facts_for_session(
        {"autonomy_mode": "safe_auto"},
        provider_facts={"x-api-key": "secret-value"},
    )

    assert facts.provider_facts == {"x-api-key": "[REDACTED]"}
    assert "secret-value" not in facts.model_dump_json()


def test_policy_facts_for_session_does_not_mutate_metadata_or_interrupt_resolution():
    meta = default_deepagents_permission_metadata("confirm_all")
    snapshot = dict(meta)

    policy_facts_for_session(meta)

    assert meta == snapshot
    # Legacy DeepAgents HITL resolution is untouched by the policy facts adapter.
    assert resolve_deepagents_interrupt_on(meta) == DEFAULT_DEEPAGENTS_INTERRUPT_ON
    assert resolve_deepagents_interrupt_on(default_deepagents_permission_metadata("safe_auto")) is None


def test_policy_facts_end_to_end_confirm_all_write_asks_then_trust_allows():
    definition = _definition("test.write", ToolKind.WRITE, aliases=("write_file",))
    meta = default_deepagents_permission_metadata("confirm_all")

    untrusted = policy_facts_for_session(meta)
    assert evaluate_tool_policy(definition, untrusted).decision == "ask"

    trusted = policy_facts_for_session(grant_session_tool_trust(meta, ["write_file"]))
    decision = evaluate_tool_policy(definition, trusted)
    assert decision.decision == "allow"
    assert decision.reason_code == "trusted"


def test_policy_facts_end_to_end_read_only_denies_execute():
    definition = _definition("test.execute", ToolKind.EXECUTE, aliases=("execute",))
    facts = policy_facts_for_session(default_deepagents_permission_metadata("read_only"))

    decision = evaluate_tool_policy(definition, facts)
    assert decision.decision == "deny"
    assert decision.reason_code == "denied_side_effect"
