"""Offline, deterministic acceptance coverage for the Coding Agent engineering loop.

The runner deliberately uses AgentSessionService, its DeepAgents runtime adapter,
SQLite repository, emitted events, and a fresh service reload.  Only model
decisions are simulated.  This is an engineering-contract test, not a model
quality benchmark.
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
from collections import deque
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import pytest
from agent_session.models import AgentPromptRequest, AgentSessionCreate
from agent_session.repository import AgentSessionRepository
from agent_session.service import AgentSessionService

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "coding_agent_runtime_scenarios.json"
REQUIRED_KINDS = {
    "python",
    "react_typescript",
    "cross_stack",
    "failure_recovery",
    "refresh_reload",
    "path_isolation",
}
CODING_DIFF_CONTRACT_AVAILABLE = importlib.util.find_spec("agent_session.coding_diff") is not None


def _fixture() -> dict[str, Any]:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def _write_project(workspace: Path, files: dict[str, str]) -> None:
    for relative_path, content in files.items():
        path = workspace / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


def _tool(name: str, arguments: dict[str, Any]) -> str:
    return json.dumps({"tool": name, "arguments": arguments}, ensure_ascii=False)


def _final() -> str:
    return json.dumps({"type": "final", "content": "Offline scripted Coding Agent completed."})


def _fake_model(responses: Iterable[str]):
    scripted = deque(responses)

    async def model_call(_messages: list[dict[str, str]]) -> str:
        if not scripted:
            raise AssertionError("The scripted fake model exhausted its tool-call sequence")
        return scripted.popleft()

    return model_call


def _edit(path: str, old: str, new: str) -> str:
    return _tool("edit_file", {"file_path": f"/workspace/{path}", "old_string": old, "new_string": new})


def _read(path: str) -> str:
    return _tool("read_file", {"file_path": f"/workspace/{path}"})


def _execute(command: str) -> str:
    return _tool("execute", {"command": command})


def _script_for(scenario_id: str) -> list[str]:
    if scenario_id == "python-single-file-fix":
        return [
            _read("app.py"),
            _read("test_app.py"),
            _edit("app.py", "return min(value, 10)", "return max(0, min(value, 10))"),
            _execute("python -m py_compile app.py"),
            _final(),
        ]
    if scenario_id == "react-typescript-change":
        return [
            _read("client/src/StatusCard.tsx"),
            _read("client/src/StatusCard.test.tsx"),
            _edit("client/src/StatusCard.tsx", "<span>idle</span>", '<span role="status">ready</span>'),
            _execute("node -e \"const fs=require('fs'); if (!fs.readFileSync('client/src/StatusCard.tsx','utf8').includes('role=\\\"status\\\"')) process.exit(1)\""),
            _final(),
        ]
    if scenario_id == "cross-stack-multi-file":
        return [
            *[_read(path) for path in ("server/tasks.py", "server/test_tasks.py", "client/src/tasks.ts", "client/src/TaskList.tsx")],
            _edit("server/tasks.py", "{'name': 'demo'}", "{'name': 'demo', 'status': 'ready'}"),
            _edit("client/src/tasks.ts", "{ name: string }", "{ name: string; status: 'ready' }"),
            _edit("client/src/TaskList.tsx", "() => null", "() => <span>ready</span>"),
            _execute("python -m py_compile server/tasks.py"),
            _execute("node -e \"const fs=require('fs'); if (!fs.readFileSync('client/src/TaskList.tsx','utf8').includes('ready')) process.exit(1)\""),
            _final(),
        ]
    if scenario_id == "failed-tool-reread-repair":
        return [
            _read("parser.py"),
            _read("test_parser.py"),
            _edit("parser.py", "return value.strip()", "return value.strip().upper()"),
            _execute("python -c \"import sys; sys.exit(1)\""),
            _read("parser.py"),
            _edit("parser.py", "return value.strip().upper()", "return value.strip().lower()"),
            _execute("python -m py_compile parser.py"),
            _final(),
        ]
    if scenario_id == "refresh-reload-review":
        return [_read("src/main.py"), _edit("src/main.py", "'before'", "'after'"), _execute("python -m py_compile src/main.py"), _final()]
    if scenario_id == "workspace-escape-rejected":
        return [_read("safe.py"), _edit("../outside.py", "", "OUTSIDE = True"), _final()]
    raise AssertionError(f"No tool script for scenario {scenario_id}")


def _part_payload(part: Any) -> dict[str, Any]:
    payload = getattr(part, "payload", None)
    return dict(payload or {})


def _diff_parts(parts: Iterable[Any]) -> list[Any]:
    return [part for part in parts if getattr(part, "type", None) == "diff"]


def _event_part_ids(events: Iterable[dict[str, Any]]) -> set[str]:
    return {
        str(event.get("payload", {}).get("part_id"))
        for event in events
        if isinstance(event.get("payload"), dict) and event["payload"].get("part_id")
    }


def test_runtime_scenario_fixture_is_complete_and_declares_only_offline_execution():
    fixture = _fixture()

    assert fixture["contract_version"] == 1
    assert fixture["runtime"] == {
        "model": "scripted-tool-calling-fake",
        "network": False,
        "cuda": False,
        "execution_loop": "deepagents",
    }
    assert {scenario["kind"] for scenario in fixture["scenarios"]} == REQUIRED_KINDS
    for scenario in fixture["scenarios"]:
        assert {"id", "files", "operations", "expected_files", "expected_diff_paths", "verification_after_last_write"} <= scenario.keys()
        assert scenario["operations"]
        assert all(not Path(path).is_absolute() and ".." not in Path(path).parts for path in scenario["expected_files"])


@pytest.mark.skipif(
    not CODING_DIFF_CONTRACT_AVAILABLE,
    reason="Track A coding-diff persistence contract is not present in this checkout yet",
)
@pytest.mark.parametrize("scenario", _fixture()["scenarios"], ids=lambda item: item["id"])
def test_coding_agent_engineering_loop_runs_through_real_session_boundaries(tmp_path: Path, scenario: dict[str, Any]):
    workspace = tmp_path / "project"
    workspace.mkdir()
    _write_project(workspace, scenario["files"])
    repository = AgentSessionRepository(str(tmp_path / "agent-sessions.db"))
    service = AgentSessionService(repository, model_call=_fake_model(_script_for(scenario["id"])))
    session = service.create_session(AgentSessionCreate(title=scenario["id"], project_path=str(workspace)))
    repository.update_session(
        session.id,
        metadata={**session.metadata, "deepagents_interrupt_on": False},
    )

    result = asyncio.run(service.prompt(session.id, AgentPromptRequest(content=f"Run {scenario['id']}")))
    parts = result.parts
    events = service.list_events(session.id)

    for relative_path, expected_content in scenario["expected_files"].items():
        assert (workspace / relative_path).read_text(encoding="utf-8") == expected_content

    if scenario["kind"] == "path_isolation":
        assert not (tmp_path / "outside.py").exists()
        assert any(event["event_type"] == "trajectory_guard_blocked" for event in events)
        assert not _diff_parts(parts)
        return

    diffs = _diff_parts(parts)
    assert result.status == "completed"
    assert len(diffs) == len(scenario["expected_diff_paths"])
    assert [payload["path"] for payload in map(_part_payload, diffs)] == scenario["expected_diff_paths"]
    assert [payload["write_sequence"] for payload in map(_part_payload, diffs)] == sorted(
        payload["write_sequence"] for payload in map(_part_payload, diffs)
    )
    assert all(payload["contract_version"] == 1 and payload["review_status"] == "ready" for payload in map(_part_payload, diffs))
    assert all(not Path(payload["path"]).is_absolute() and ".." not in Path(payload["path"]).parts for payload in map(_part_payload, diffs))
    assert {part.id for part in diffs} <= _event_part_ids(events)

    trajectory = result.metadata["trajectory_guard"]
    steps = trajectory["steps"]
    last_write = max(step["sequence"] for step in steps if step["kind"] == "write" and step["success"])
    assert scenario["verification_after_last_write"] is True
    assert any(step["kind"] == "verification" and step["success"] and step["sequence"] > last_write for step in steps)
    if scenario["kind"] == "failure_recovery":
        failed_verification = next(step for step in steps if step["kind"] == "verification" and not step["success"])
        repair_read = next(step for step in steps if step["kind"] == "read" and step["sequence"] > failed_verification["sequence"])
        assert repair_read["path"] == "/workspace/parser.py"

    reloaded = AgentSessionService(AgentSessionRepository(str(tmp_path / "agent-sessions.db")))
    restored = reloaded.get_session(session.id)
    restored_diffs = _diff_parts(restored.parts)
    assert [(part.id, _part_payload(part)) for part in restored_diffs] == [(part.id, _part_payload(part)) for part in diffs]
    assert restored.status == "completed"
