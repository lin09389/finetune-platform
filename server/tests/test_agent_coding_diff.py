from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest
from agent_session.coding_diff import (
    MAX_DIFF_SOURCE_BYTES,
    MAX_INLINE_DIFF_BYTES,
    MAX_INLINE_DIFF_LINES,
    build_coding_diff_payload,
)
from agent_session.repository import AgentSessionRepository
from agent_session.trajectory import TrajectoryGuardMiddleware, TrajectoryStateStore
from langchain_core.messages import ToolMessage
from langgraph.prebuilt.tool_node import ToolCallRequest

POLICY = {
    "enabled": True,
    "require_read_before_write": True,
    "require_context_before_create": True,
    "validate_after_write": True,
    "rollback_on_validation_failure": True,
    "require_verification_after_write": True,
    "max_auto_corrections": 2,
}


def _request(name: str, args: dict[str, Any], call_id: str) -> ToolCallRequest:
    return ToolCallRequest(
        tool_call={"name": name, "args": args, "id": call_id, "type": "tool_call"},
        tool=None,
        state={"messages": []},
        runtime=None,  # type: ignore[arg-type]
    )


async def _ok(request: ToolCallRequest) -> ToolMessage:
    return ToolMessage(content="ok", tool_call_id=str(request.tool_call["id"]))


def _middleware(tmp_path: Path, workspace: Path):
    repository = AgentSessionRepository(str(tmp_path / "agents.db"))
    session = repository.create_session(
        {"agent_id": "build", "title": "coding diff", "project_path": str(workspace), "metadata": {}}
    )
    events: list[dict[str, Any]] = []
    middleware = TrajectoryGuardMiddleware(
        repository=repository,
        notify_event=lambda _session_id, event: events.append(event),
        session_id=session["id"],
        project_path=str(workspace),
        policy=POLICY,
    )
    TrajectoryStateStore(repository, lambda *_args: None, session["id"]).begin_run()
    return repository, session["id"], events, middleware


def test_payload_is_versioned_relative_and_handles_added_modified_deleted_unicode():
    added = build_coding_diff_payload(
        path="/workspace/src/你好.py",
        before_existed=False,
        before_content=b"",
        after_existed=True,
        after_content="print('你好')\n".encode(),
        write_sequence=7,
    )
    deleted = build_coding_diff_payload(
        path="src/old.py",
        before_existed=True,
        before_content=b"old\n",
        after_existed=False,
        after_content=b"",
        write_sequence=8,
    )
    modified = build_coding_diff_payload(
        path="src/app.py",
        before_existed=True,
        before_content=b"before\n",
        after_existed=True,
        after_content=b"after\n",
        write_sequence=9,
    )

    assert added["contract_version"] == 1
    assert added["path"] == "src/你好.py"
    assert added["changed_files"] == ["src/你好.py"]
    assert added["change_type"] == "added"
    assert added["review_status"] == "ready"
    assert "你好" in added["diff"]
    assert deleted["change_type"] == "deleted"
    assert modified["change_type"] == "modified"
    assert modified["additions"] == modified["deletions"] == 1
    assert "C:" not in modified["diff"]


def test_payload_rejects_absolute_or_traversal_path_leaks():
    kwargs = {
        "before_existed": False,
        "before_content": b"",
        "after_existed": True,
        "after_content": b"new\n",
        "write_sequence": 1,
    }
    for path in ("C:\\Users\\private\\secret.py", "/tmp/secret.py", "../secret.py", "src/../secret.py"):
        with pytest.raises(ValueError):
            build_coding_diff_payload(path=path, **kwargs)


def test_binary_and_oversized_payloads_are_metadata_only_and_bounded():
    binary = build_coding_diff_payload(
        path="asset.bin",
        before_existed=True,
        before_content=b"\x00old",
        after_existed=True,
        after_content=b"\x00new",
        write_sequence=1,
    )
    oversized = build_coding_diff_payload(
        path="generated.txt",
        before_existed=True,
        before_content=b"a" * (MAX_DIFF_SOURCE_BYTES + 1),
        after_existed=True,
        after_content=b"b" * (MAX_DIFF_SOURCE_BYTES + 1),
        write_sequence=2,
    )
    line_truncated = build_coding_diff_payload(
        path="many-lines.txt",
        before_existed=True,
        before_content=b"old\n" * (MAX_INLINE_DIFF_LINES + 20),
        after_existed=True,
        after_content=b"new\n" * (MAX_INLINE_DIFF_LINES + 20),
        write_sequence=3,
    )

    assert binary["binary"] is True and binary["diff"] == ""
    assert oversized["binary"] is False and oversized["truncated"] is True and oversized["diff"] == ""
    assert line_truncated["truncated"] is True
    assert len(line_truncated["diff"].encode("utf-8")) <= MAX_INLINE_DIFF_BYTES
    assert len(line_truncated["diff"].splitlines()) <= MAX_INLINE_DIFF_LINES


def test_successful_repeated_writes_persist_chronological_diff_parts_and_cover_completion(tmp_path: Path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    target = workspace / "app.py"
    target.write_text("value = 'old'\n", encoding="utf-8")
    repository, session_id, events, middleware = _middleware(tmp_path, workspace)

    asyncio.run(middleware.awrap_tool_call(_request("read_file", {"file_path": "/workspace/app.py"}, "read"), _ok))

    async def write_first(request: ToolCallRequest) -> ToolMessage:
        target.write_text("value = 'first'\n", encoding="utf-8")
        return await _ok(request)

    async def write_second(request: ToolCallRequest) -> ToolMessage:
        target.write_text("value = 'second'\n", encoding="utf-8")
        return await _ok(request)

    asyncio.run(middleware.awrap_tool_call(_request("edit_file", {"file_path": "/workspace/app.py"}, "write-1"), write_first))
    asyncio.run(middleware.awrap_tool_call(_request("edit_file", {"file_path": "/workspace/app.py"}, "write-2"), write_second))
    asyncio.run(middleware.awrap_tool_call(_request("execute", {"command": "python -m pytest -q"}, "verify"), _ok))

    diffs = [part for part in repository.list_parts(session_id) if part["type"] == "diff"]
    sequences = [part["payload"]["write_sequence"] for part in diffs]
    restored = AgentSessionRepository(str(tmp_path / "agents.db"))
    restored_diffs = [part for part in restored.list_parts(session_id) if part["type"] == "diff"]
    store = TrajectoryStateStore(repository, lambda *_args: None, session_id)

    assert len(diffs) == 2
    assert sequences == sorted(sequences)
    assert all(part["payload"]["path"] == "app.py" for part in diffs)
    assert all(part["payload"]["review_status"] == "ready" for part in diffs)
    assert len(restored_diffs) == 2
    assert store.completion_issues(POLICY) == []
    assert sum(event["event_type"] == "coding_diff_ready" for event in events) == 2


def test_rollbacks_and_failed_writes_never_persist_diff_parts(tmp_path: Path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    target = workspace / "app.py"
    original = "def value():\n    return 1\n"
    target.write_text(original, encoding="utf-8")
    repository, session_id, _, middleware = _middleware(tmp_path, workspace)

    blocked = asyncio.run(
        middleware.awrap_tool_call(
            _request("edit_file", {"file_path": "/workspace/app.py"}, "blocked"),
            _ok,
        )
    )
    assert blocked.status == "error"
    assert not [part for part in repository.list_parts(session_id) if part["type"] == "diff"]

    asyncio.run(middleware.awrap_tool_call(_request("read_file", {"file_path": "/workspace/app.py"}, "read"), _ok))

    async def failed_write(request: ToolCallRequest) -> ToolMessage:
        return ToolMessage(content="write failed", tool_call_id=str(request.tool_call["id"]), status="error")

    failed = asyncio.run(
        middleware.awrap_tool_call(
            _request("edit_file", {"file_path": "/workspace/app.py"}, "failed"),
            failed_write,
        )
    )
    assert failed.status == "error"
    assert not [part for part in repository.list_parts(session_id) if part["type"] == "diff"]

    async def invalid_write(request: ToolCallRequest) -> ToolMessage:
        target.write_text("def value():\nreturn broken\n", encoding="utf-8")
        return await _ok(request)

    result = asyncio.run(
        middleware.awrap_tool_call(_request("edit_file", {"file_path": "/workspace/app.py"}, "write"), invalid_write)
    )

    assert result.status == "error"
    assert target.read_text(encoding="utf-8") == original
    assert not [part for part in repository.list_parts(session_id) if part["type"] == "diff"]


def test_completion_gate_requires_persisted_diff_for_each_successful_write(tmp_path: Path):
    repository = AgentSessionRepository(str(tmp_path / "agents.db"))
    session = repository.create_session({"agent_id": "build", "project_path": str(tmp_path), "metadata": {}})
    store = TrajectoryStateStore(repository, lambda *_args: None, session["id"])
    store.begin_run()
    store.record_step("read", tool="read_file", path="/workspace/app.py")
    store.record_step("write", tool="edit_file", path="/workspace/app.py")
    store.record_step("verification", tool="execute", command="python -m pytest -q")

    issues = store.completion_issues(POLICY)

    assert [issue["reason_code"] for issue in issues] == ["diff_coverage_required"]
