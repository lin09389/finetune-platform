from agent_runtime_legacy.permission import PermissionAction, PermissionRule, evaluate


def test_permission_last_rule_wins():
    rules = [
        PermissionRule(permission="tool.read_file", pattern="*", action=PermissionAction.DENY),
        PermissionRule(permission="tool.read_file", pattern="src/*", action=PermissionAction.ALLOW),
    ]
    assert evaluate("tool.read_file", "src/app.py", rules) == PermissionAction.ALLOW


def test_permission_wildcard_match():
    rules = [PermissionRule(permission="tool.*", pattern="**/*.tsx", action=PermissionAction.ALLOW)]
    assert evaluate("tool.search_code", "client/src/pages/ChatNew.tsx", rules) == PermissionAction.ALLOW


def test_permission_default_is_ask():
    assert evaluate("tool.propose_patch", "tmp/file.txt", []) == PermissionAction.ASK

