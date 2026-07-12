"""Phase 3: truthful tool-end events + FileData virtual files (shared cloud/local)."""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest
from agent_session.deepagents_events import DeepAgentsEventMapper
from agent_session.permission import build_filesystem_permissions
from agent_session.runtime import normalize_deepagents_files, prepare_deepagents_files
from agent_session.trajectory import (
    content_indicates_tool_failure,
    is_successful_tool_result,
    normalize_workspace_path,
)
from context.deepagents import build_deepagents_context_pack
from deepagents.middleware.filesystem import _check_fs_permission
from langchain_core.messages import ToolMessage


class FakeRepository:
    def __init__(self):
        self.parts = []
        self.events = []
        self.session = {"id": "session-phase3", "metadata": {}}

    def add_part(self, session_id, part_type, *, status, title, content, payload):
        part = {
            "id": f"part-{len(self.parts) + 1}",
            "session_id": session_id,
            "type": part_type,
            "status": status,
            "title": title,
            "content": content,
            "payload": payload,
        }
        self.parts.append(part)
        return part

    def add_event(self, session_id, event_type, message, payload):
        event = {
            "id": f"event-{len(self.events) + 1}",
            "session_id": session_id,
            "event_type": event_type,
            "type": event_type,
            "message": message,
            "payload": payload,
        }
        self.events.append(event)
        return event

    def update_part(self, part_id, **updates):
        part = next(part for part in self.parts if part["id"] == part_id)
        part.update(updates)
        return part

    def get_session(self, _session_id):
        return self.session

    def update_session(self, _session_id, **updates):
        self.session.update(updates)
        return self.session


@pytest.mark.parametrize(
    ("content", "tool", "expected_fail"),
    [
        ("Error: permission denied for read on /workspace", "ls", True),
        ("error: something broke", "read_file", True),
        ("permission denied for read on /", "glob", True),
        ("failed: boom", "execute", True),
        ("listed files successfully", "ls", False),
        ("This report mentions error handling best practices", "read_file", False),
        # Prefix-looking prose must stay successful (no bare "Error" without colon).
        ("Error handling best practices for APIs", "read_file", False),
        ("Error-prone modules should be reviewed carefully", "read_file", False),
        # Documentation that mentions permission denied early must not fail.
        ("permission denied errors are returned by the OS when access is blocked", "read_file", False),
        ("See section: permission denied handling in the security guide", "read_file", False),
        ("", "ls", False),
    ],
)
def test_content_indicates_tool_failure_markers(content, tool, expected_fail):
    assert content_indicates_tool_failure(content, tool=tool) is expected_fail
    # Trajectory success check stays consistent with the shared classifier.
    msg = ToolMessage(content=content, tool_call_id="t1", name=tool)
    assert is_successful_tool_result(msg, tool=tool) is (not expected_fail)


def test_event_mapper_keeps_benign_error_prefix_prose_completed():
    """Mapper must not treat 'Error handling…' / early permission docs as tool failure."""
    repo = FakeRepository()
    emitted = []
    mapper = DeepAgentsEventMapper(repo, lambda _sid, event: emitted.append(event), "session-phase3")

    mapper.handle({"event": "on_tool_start", "name": "read_file", "run_id": "run-benign", "data": {"input": {}}})
    mapper.handle(
        {
            "event": "on_tool_end",
            "name": "read_file",
            "run_id": "run-benign",
            "data": {"output": "Error handling best practices for APIs\npermission denied is discussed below."},
        }
    )

    assert repo.parts[0]["status"] == "completed"
    assert repo.events[-1]["event_type"] == "tool_call_completed"
    assert emitted[-1]["event_type"] == "tool_call_completed"


def test_event_mapper_marks_error_string_tool_end_as_failed():
    repo = FakeRepository()
    emitted = []
    mapper = DeepAgentsEventMapper(repo, lambda _sid, event: emitted.append(event), "session-phase3")

    mapper.handle(
        {
            "event": "on_tool_start",
            "name": "ls",
            "run_id": "run-err",
            "data": {"input": {"path": "/workspace"}},
        }
    )
    mapper.handle(
        {
            "event": "on_tool_end",
            "name": "ls",
            "run_id": "run-err",
            "data": {"output": "Error: permission denied for read on /workspace"},
        }
    )

    assert repo.parts[0]["status"] == "failed"
    assert repo.parts[0]["content"].startswith("Error:")
    assert repo.events[-1]["event_type"] == "tool_call_failed"
    assert emitted[-1]["event_type"] == "tool_call_failed"
    assert emitted[-1]["payload"]["status"] == "failed"
    assert emitted[-1]["payload"]["tool"] == "ls"


def test_event_mapper_keeps_successful_tool_end_completed():
    repo = FakeRepository()
    emitted = []
    mapper = DeepAgentsEventMapper(repo, lambda _sid, event: emitted.append(event), "session-phase3")

    mapper.handle({"event": "on_tool_start", "name": "ls", "run_id": "run-ok", "data": {"input": {}}})
    mapper.handle(
        {
            "event": "on_tool_end",
            "name": "ls",
            "run_id": "run-ok",
            "data": {"output": "a.py\nb.py\n"},
        }
    )

    assert repo.parts[0]["status"] == "completed"
    assert repo.events[-1]["event_type"] == "tool_call_completed"
    assert emitted[-1]["event_type"] == "tool_call_completed"


def test_event_mapper_respects_toolmessage_error_status():
    repo = FakeRepository()
    emitted = []
    mapper = DeepAgentsEventMapper(repo, lambda _sid, event: emitted.append(event), "session-phase3")
    output = ToolMessage(content="not found", tool_call_id="c1", name="read_file", status="error")

    mapper.handle({"event": "on_tool_start", "name": "read_file", "run_id": "run-status", "data": {"input": {}}})
    mapper.handle({"event": "on_tool_end", "name": "read_file", "run_id": "run-status", "data": {"output": output}})

    assert repo.parts[0]["status"] == "failed"
    assert repo.events[-1]["event_type"] == "tool_call_failed"


def test_normalize_and_prepare_filedata_shapes():
    plain = normalize_deepagents_files({"/context/task.md": "hello"})
    assert plain["/context/task.md"] == {"content": "hello", "encoding": "utf-8"}

    typed = normalize_deepagents_files({"/context/a.md": {"content": "x", "encoding": "utf-8"}})
    assert typed["/context/a.md"]["content"] == "x"

    class Snapshot:
        values = {
            "files": {
                "/context/legacy.md": "LEGACY",
                "/context/typed.md": {"content": "TYPED", "encoding": "utf-8"},
            }
        }

    class Graph:
        checkpointer = object()

        async def aget_state(self, _config):
            return Snapshot()

    files = asyncio.run(
        prepare_deepagents_files(
            Graph(),
            {"configurable": {"thread_id": "phase3"}},
            {"/context/task.md": "CURRENT"},
        )
    )
    for path, value in files.items():
        assert isinstance(value, dict), path
        assert isinstance(value.get("content"), str), path
        assert value.get("encoding") == "utf-8"
    assert files["/context/legacy.md"]["content"] == "LEGACY"
    assert files["/context/task.md"]["content"] == "CURRENT"
    assert not any(isinstance(v, str) for v in files.values())


@pytest.mark.asyncio
async def test_context_pack_emits_filedata_not_bare_strings():
    pack = await build_deepagents_context_pack(
        goal="inspect project",
        active_context={"file_path": "server/example.py", "selection": {"text": "print(1)"}},
        explicit_context=None,
        project_path=None,
    )
    assert pack.has_files
    for path, value in pack.files.items():
        assert isinstance(value, dict), path
        assert isinstance(value["content"], str), path
        assert value.get("encoding") == "utf-8"
    assert "/context/task.md" in pack.files


def test_build_workspace_paths_allow_and_escape_denied():
    rules = build_filesystem_permissions("build")
    assert _check_fs_permission(rules, "read", "/workspace") == "allow"
    assert _check_fs_permission(rules, "read", "/workspace/src/app.py") == "allow"
    assert _check_fs_permission(rules, "read", "/tmp/outside.txt") == "deny"
    assert _check_fs_permission(rules, "read", "/etc/passwd") == "deny"

    # Trajectory path normalization rejects escape via ..
    assert normalize_workspace_path("/workspace/../outside") == ""
    assert normalize_workspace_path("/workspace/src/../src/app.py") == "/workspace/src/app.py"
    assert normalize_workspace_path("/workspace") == "/workspace"
    assert normalize_workspace_path("src/app.py") == "/workspace/src/app.py"
