from __future__ import annotations

from agent_session.policy import evaluate_agent_action_policy


def _session(mode: str = "safe_auto") -> dict:
    return {"metadata": {"autonomy_mode": mode}}


def _files(count: int, lines: int = 1) -> list[dict[str, str]]:
    content = "\n".join(f"line_{index}" for index in range(lines)) + "\n"
    return [{"path": f"client/src/feature_{index}.tsx", "content": content} for index in range(count)]


def test_safe_auto_allows_up_to_six_touched_source_files():
    files = _files(6, lines=20)
    touched = {item["path"] for item in files}

    policy = evaluate_agent_action_policy(_session(), "diff", {"files": files}, touched)

    assert policy["execution_mode"] == "auto"


def test_safe_auto_requires_approval_above_source_file_threshold():
    files = _files(7, lines=20)
    touched = {item["path"] for item in files}

    policy = evaluate_agent_action_policy(_session(), "diff", {"files": files}, touched)

    assert policy["execution_mode"] == "approval_required"


def test_safe_auto_requires_approval_above_total_line_threshold():
    files = _files(4, lines=151)
    touched = {item["path"] for item in files}

    policy = evaluate_agent_action_policy(_session(), "diff", {"files": files}, touched)

    assert policy["execution_mode"] == "approval_required"


def test_safe_auto_blocks_sensitive_and_delete_patches():
    sensitive = evaluate_agent_action_policy(
        _session(),
        "diff",
        {"files": [{"path": ".env", "content": "SECRET=1\n"}]},
        {".env"},
    )
    deleted = evaluate_agent_action_policy(
        _session(),
        "diff",
        {"files": [{"path": "client/src/feature.tsx", "content": "", "delete": True}]},
        {"client/src/feature.tsx"},
    )

    assert sensitive["execution_mode"] == "blocked"
    assert deleted["execution_mode"] == "blocked"


def test_safe_auto_blocks_non_allowlisted_commands_but_auto_starts_dev_server():
    blocked = evaluate_agent_action_policy(_session(), "command", {"command": ["node", "script.js"]}, set())
    dev_server = evaluate_agent_action_policy(
        _session(),
        "command",
        {"tool": "run_dev_server", "command": ["npm", "run", "dev"], "long_running": True},
        set(),
    )

    assert blocked["execution_mode"] == "blocked"
    assert dev_server["execution_mode"] == "auto"
