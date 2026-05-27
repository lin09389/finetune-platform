from deepagents.middleware.filesystem import _check_fs_permission

from agent_session.permission import (
    build_filesystem_permissions,
    filesystem_permission_profile_for_agent,
)


def test_build_profile_allows_workspace_read_and_write():
    rules = build_filesystem_permissions("build")

    assert _check_fs_permission(rules, "read", "/workspace/src/app.py") == "allow"
    assert _check_fs_permission(rules, "write", "/workspace/src/app.py") == "allow"


def test_build_profile_denies_sensitive_env_before_workspace_allow():
    rules = build_filesystem_permissions("build")

    assert rules[0].mode == "deny"
    assert _check_fs_permission(rules, "read", "/workspace/.env") == "deny"
    assert _check_fs_permission(rules, "write", "/workspace/packages/api/.env.local") == "deny"


def test_readonly_profile_allows_read_but_denies_write():
    rules = build_filesystem_permissions("readonly")

    assert _check_fs_permission(rules, "read", "/workspace/src/app.py") == "allow"
    assert _check_fs_permission(rules, "write", "/workspace/src/app.py") == "deny"


def test_fallback_denies_unknown_paths():
    rules = build_filesystem_permissions("build")

    assert _check_fs_permission(rules, "read", "/tmp/outside.txt") == "deny"
    assert _check_fs_permission(rules, "write", "/context/generated.txt") == "deny"


def test_agent_profile_mapping():
    assert filesystem_permission_profile_for_agent("build") == "build"
    assert filesystem_permission_profile_for_agent("explore") == "readonly"
    assert filesystem_permission_profile_for_agent("review") == "readonly"
    assert filesystem_permission_profile_for_agent("unknown") == "deny_all"
