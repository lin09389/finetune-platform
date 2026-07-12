from agent_session.execution_context import AgentDefinition
from agent_session.permission import (
    build_filesystem_permissions,
    default_deepagents_permission_metadata,
    filesystem_permission_profile_for_agent,
    permission_policy_for_agent,
    validate_hitl_decisions,
)
from deepagents.middleware.filesystem import _check_fs_permission


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
