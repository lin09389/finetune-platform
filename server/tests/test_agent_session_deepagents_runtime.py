from __future__ import annotations

import asyncio
import json
import shutil
import uuid
from pathlib import Path

import pytest

from agent_session.models import AgentPromptRequest, AgentSessionCreate
from agent_session.async_subagents import AsyncSubagentService
from agent_session.repository import AgentSessionRepository
from agent_session.service import AgentSessionService
from agent_session.deepagents_runtime import DeepAgentsSessionRunner
from agent_session.runtime import (
    EPHEMERAL_BACKEND_ROUTES,
    FALLBACK_STATE_BACKEND_ROUTE,
    WORKSPACE_BACKEND_ROUTE,
    build_deepagents_backend,
    resolve_interrupt_on,
)


def test_agent_session_deepagents_reads_file_and_completes(tmp_path: Path):
    workspace = Path.cwd() / "tmp" / f"deepagents-runtime-{uuid.uuid4().hex[:8]}"
    workspace.mkdir()
    try:
        target = workspace / "hello.txt"
        target.write_text("hello from deepagents\n", encoding="utf-8")
        service = AgentSessionService(AgentSessionRepository(str(tmp_path / "agents.db")))
        session = service.create_session(AgentSessionCreate(title="deepagents prompt", project_path=str(workspace)))
        responses = iter(
            [
                json.dumps({"tool": "read_file", "arguments": {"file_path": "/workspace/hello.txt"}}, ensure_ascii=False),
                json.dumps({"type": "final", "content": "DeepAgents 已读取 hello.txt。"}, ensure_ascii=False),
            ]
        )

        async def model_call(_messages):
            return next(responses)

        service.model_call = model_call

        result = asyncio.run(service.prompt(session.id, AgentPromptRequest(content="读取 hello.txt 并总结")))
        events = service.list_events(session.id)

        assert result.status == "completed"
        assert result.metadata["runtime"] == "deepagents"
        assert any(part.type == "summary" and "DeepAgents" in (part.content or "") for part in result.parts)
        assert any(event["event_type"] == "session_started" for event in events)
        assert any(event["event_type"] == "tool_call_completed" for event in events)
    finally:
        shutil.rmtree(workspace, ignore_errors=True)


def test_agent_session_deepagents_edit_file_uses_official_hitl(tmp_path: Path):
    workspace = Path.cwd() / "tmp" / f"deepagents-action-{uuid.uuid4().hex[:8]}"
    workspace.mkdir()
    try:
        target = workspace / "hello.txt"
        target.write_text("hello\n", encoding="utf-8")
        service = AgentSessionService(AgentSessionRepository(str(tmp_path / "agents.db")))
        session = service.create_session(AgentSessionCreate(title="deepagents action", project_path=str(workspace)))
        responses = iter(
            [
                json.dumps(
                    {
                        "tool": "edit_file",
                        "arguments": {
                            "file_path": "/workspace/hello.txt",
                            "old_string": "hello\n",
                            "new_string": "hi\n",
                        },
                    },
                    ensure_ascii=False,
                ),
                json.dumps({"type": "final", "content": "已写入 hello.txt。"}, ensure_ascii=False),
            ]
        )

        async def model_call(_messages):
            return next(responses)

        service.model_call = model_call

        result = asyncio.run(service.prompt(session.id, AgentPromptRequest(content="把 hello 改成 hi")))

        assert result.status == "waiting_approval"
        assert target.read_text(encoding="utf-8") == "hello\n"
        assert any(part.type == "permission" and part.status == "pending" for part in result.parts)
    finally:
        shutil.rmtree(workspace, ignore_errors=True)


def test_agent_session_deepagents_execute_uses_official_hitl_without_whitelist(tmp_path: Path):
    workspace = Path.cwd() / "tmp" / f"deepagents-exec-{uuid.uuid4().hex[:8]}"
    workspace.mkdir()
    try:
        target = workspace / "cmd.txt"
        service = AgentSessionService(AgentSessionRepository(str(tmp_path / "agents.db")))
        session = service.create_session(AgentSessionCreate(title="deepagents execute", project_path=str(workspace)))
        responses = iter(
            [
                json.dumps(
                    {
                        "tool": "execute",
                        "arguments": {
                            "command": "python -c \"from pathlib import Path; Path('cmd.txt').write_text('ok', encoding='utf-8')\"",
                        },
                    },
                    ensure_ascii=False,
                ),
                json.dumps({"type": "final", "content": "命令已执行。"}, ensure_ascii=False),
            ]
        )

        async def model_call(_messages):
            return next(responses)

        service.model_call = model_call
        result = asyncio.run(service.prompt(session.id, AgentPromptRequest(content="运行一个命令写入 cmd.txt")))

        assert result.status == "waiting_approval"
        assert not target.exists()
        assert any(part.type == "permission" and part.status == "pending" for part in result.parts)
        assert not any(part.type == "command" for part in result.parts)
    finally:
        shutil.rmtree(workspace, ignore_errors=True)


def test_deepagents_runtime_registers_local_async_tools(monkeypatch, tmp_path: Path):
    captured: dict[str, object] = {}

    def fake_build_runtime(config):
        captured["tools"] = config.tools
        captured["subagents"] = config.subagents
        captured["interrupt_on"] = config.interrupt_on
        captured["project_path"] = config.project_path
        captured["permissions"] = config.permissions
        captured["skills"] = config.skills
        return object()

    monkeypatch.setattr("agent_session.deepagents_runtime.build_deep_agent_runtime", fake_build_runtime)
    monkeypatch.setattr("agent_session.deepagents_runtime._load_create_deep_agent", lambda: object())

    async def model_call(_messages):
        return json.dumps({"type": "final", "content": "ok"}, ensure_ascii=False)

    runner = DeepAgentsSessionRunner(repository=object(), notify_event=lambda *_args: None, model_call=model_call)
    graph = asyncio.run(
        runner._build_graph(
            {
                "id": "session",
                "project_path": str(tmp_path),
                "provider": "",
                "model": None,
                "metadata": {},
            },
            "测试官方内置工具链",
        )
    )

    assert graph is not None
    assert [tool.name for tool in captured["tools"]] == [
        "start_async_task",
        "check_async_task",
        "list_async_tasks",
        "update_async_task",
        "cancel_async_task",
    ]
    subagents = captured["subagents"]
    assert [item["name"] for item in subagents] == ["explore", "review"]
    assert all(item["model"] is not None for item in subagents)
    assert all(item["permissions"] for item in subagents)
    assert all("tools" not in item for item in subagents)
    assert captured["interrupt_on"] is None
    assert captured["project_path"] == str(tmp_path)
    assert captured["permissions"]
    assert "/skills/builtin/" in captured["skills"]


def test_agent_session_repository_persists_async_subtasks(tmp_path: Path):
    repository = AgentSessionRepository(str(tmp_path / "agents.db"))
    parent = repository.create_session({"agent_id": "build", "title": "parent"})
    child = repository.create_session({"agent_id": "explore", "title": "child"})

    task = repository.create_subtask(
        {
            "parent_session_id": parent["id"],
            "child_session_id": child["id"],
            "agent_name": "explore",
            "status": "running",
            "input_json": {"description": "inspect code"},
        }
    )
    updated = repository.update_subtask(task["id"], status="completed", result_json={"summary": "done"})
    event = repository.add_subtask_event(
        task["id"],
        parent["id"],
        "completed",
        "done",
        child_session_id=child["id"],
        status="completed",
        payload={"summary": "done"},
    )

    assert updated["input_json"]["description"] == "inspect code"
    assert updated["result_json"]["summary"] == "done"
    assert repository.get_subtask(task["id"])["status"] == "completed"
    assert [item["id"] for item in repository.list_subtasks(parent["id"])] == [task["id"]]
    assert repository.list_subtasks(parent["id"], "running") == []
    assert repository.list_subtask_events(task["id"])[0]["payload"]["summary"] == "done"
    assert repository.list_parent_subtask_events(parent["id"])[0]["id"] == event["id"]
    assert repository.summarize_subtask_metrics(parent["id"])["event_count"] == 1


def test_local_async_subtask_start_check_and_list(monkeypatch, tmp_path: Path):
    repository = AgentSessionRepository(str(tmp_path / "agents.db"))
    parent = repository.create_session({"agent_id": "build", "title": "parent", "project_path": str(tmp_path)})
    runner = DeepAgentsSessionRunner(
        repository=repository,
        notify_event=lambda *_args: None,
        model_call=lambda _messages: "ok",
    )
    scheduled = []

    def fake_create_task(coro):
        scheduled.append(coro)
        coro.close()
        return object()

    monkeypatch.setattr("agent_session.deepagents_runtime.asyncio.create_task", fake_create_task)

    result = asyncio.run(runner.start_async_subtask(parent["id"], "Explore", "inspect code"))
    task = repository.get_subtask(result["task_id"])
    child = repository.get_session(result["child_session_id"])
    listed = runner.list_async_subtasks(parent["id"])

    assert result["status"] == "running"
    assert result["health_status"] == "waiting"
    assert result["diagnostics"]["last_event_type"] == "scheduled"
    assert task["agent_name"] == "explore"
    assert child["agent_id"] == "explore"
    assert scheduled
    assert listed["tasks"][0]["task_id"] == result["task_id"]
    assert runner.check_async_subtask(parent["id"], result["task_id"])["status"] == "running"
    assert runner.list_async_subtask_events(parent["id"], result["task_id"])[-1]["event_type"] == "scheduled"
    assert runner.get_async_subtask_metrics(parent["id"])["total"] == 1
    assert any(part["payload"].get("agent_role") == "async_subagent" for part in repository.list_parts(parent["id"]))


def test_local_async_subtask_rejects_non_subagent_target(tmp_path: Path):
    repository = AgentSessionRepository(str(tmp_path / "agents.db"))
    parent = repository.create_session({"agent_id": "build", "title": "parent", "project_path": str(tmp_path)})
    runner = DeepAgentsSessionRunner(
        repository=repository,
        notify_event=lambda *_args: None,
        model_call=lambda _messages: "ok",
    )

    with pytest.raises(ValueError, match="Unknown async subagent type"):
        asyncio.run(runner.start_async_subtask(parent["id"], "build", "bad target"))

    with pytest.raises(ValueError, match="description is required"):
        asyncio.run(runner.start_async_subtask(parent["id"], "explore", " "))


def test_local_async_subtask_refresh_keeps_waiting_permission_running(tmp_path: Path):
    repository = AgentSessionRepository(str(tmp_path / "agents.db"))
    parent = repository.create_session({"agent_id": "build", "title": "parent", "project_path": str(tmp_path)})
    child = repository.create_session(
        {
            "agent_id": "explore",
            "title": "child",
            "project_path": str(tmp_path),
            "status": "waiting_permission",
            "metadata": {"ui_state": {"pending_permission": {"part_id": "part_permission", "actions": []}}},
        }
    )
    task = repository.create_subtask(
        {
            "parent_session_id": parent["id"],
            "child_session_id": child["id"],
            "agent_name": "explore",
            "status": "running",
            "input_json": {"description": "inspect code"},
        }
    )
    runner = DeepAgentsSessionRunner(
        repository=repository,
        notify_event=lambda *_args: None,
        model_call=lambda _messages: "ok",
    )

    result = runner.check_async_subtask(parent["id"], task["id"])

    assert result["status"] == "running"
    assert result["result"]["child_status"] == "waiting_permission"
    parent_event = repository.list_events(parent["id"])[-1]
    assert parent_event["event_type"] == "async_subtask_waiting_permission"
    assert parent_event["payload"]["child_status"] == "waiting_permission"
    assert parent_event["payload"]["has_pending_permission"] is True
    assert parent_event["payload"]["pending_permission_part_id"] == "part_permission"


def test_local_async_subtask_completion_writes_parent_summary(monkeypatch, tmp_path: Path):
    repository = AgentSessionRepository(str(tmp_path / "agents.db"))
    parent = repository.create_session({"agent_id": "build", "title": "parent", "project_path": str(tmp_path)})
    child = repository.create_session(
        {"agent_id": "explore", "title": "child", "project_path": str(tmp_path), "status": "running"}
    )
    task = repository.create_subtask(
        {
            "parent_session_id": parent["id"],
            "child_session_id": child["id"],
            "agent_name": "explore",
            "status": "running",
            "input_json": {"description": "inspect code"},
        }
    )

    async def fake_run_prompt(self, session_id, prompt, *, context_files=None):
        self.repository.add_part(session_id, "summary", status="completed", title="Final", content="探索完成", payload={})
        return self.repository.update_session(session_id, status="completed", metadata={})

    monkeypatch.setattr(DeepAgentsSessionRunner, "run_prompt", fake_run_prompt)
    emitted = []
    service = AsyncSubagentService(
        repository,
        notify_event=lambda _session_id, event: emitted.append(event),
        model_call=lambda _messages: "ok",
    )

    asyncio.run(service._run_task(task["id"], child["id"], "inspect code"))
    updated = repository.get_subtask(task["id"])
    parent_parts = repository.list_parts(parent["id"])

    assert updated["status"] == "completed"
    assert updated["result_json"]["summary"] == "探索完成"
    assert service.task_events(parent["id"], task["id"])[-1]["event_type"] == "completed"
    assert parent_parts[-1]["payload"]["agent_role"] == "async_subagent"
    assert parent_parts[-1]["payload"]["async_status"] == "completed"
    assert parent_parts[-1]["payload"]["child_status"] == "completed"
    assert parent_parts[-1]["payload"]["has_pending_permission"] is False
    assert emitted[-1]["event_type"] == "async_subtask_completed"


def test_async_subagent_service_cancel_prevents_stale_child_completion(monkeypatch, tmp_path: Path):
    repository = AgentSessionRepository(str(tmp_path / "agents.db"))
    parent = repository.create_session({"agent_id": "build", "title": "parent", "project_path": str(tmp_path)})
    service = AsyncSubagentService(repository, notify_event=lambda *_args: None, model_call=lambda _messages: "ok")

    def fake_create_task(coro):
        coro.close()
        return object()

    monkeypatch.setattr("agent_session.async_subagents.asyncio.create_task", fake_create_task)
    result = asyncio.run(service.start_task(parent["id"], "explore", "inspect code"))
    task_id = result["task_id"]
    child_id = result["child_session_id"]

    cancelled = asyncio.run(service.cancel_task(parent["id"], task_id, "stop it"))
    asyncio.run(service._run_task(task_id, child_id, "inspect code"))
    updated = repository.get_subtask(task_id)

    assert cancelled["status"] == "cancelled"
    assert updated["status"] == "cancelled"
    assert service.task_events(parent["id"], task_id)[-1]["event_type"] == "stale_child_ignored"
    assert repository.get_session(child_id)["status"] == "interrupted"


def test_async_subagent_service_update_restarts_same_task(monkeypatch, tmp_path: Path):
    repository = AgentSessionRepository(str(tmp_path / "agents.db"))
    parent = repository.create_session({"agent_id": "build", "title": "parent", "project_path": str(tmp_path)})
    service = AsyncSubagentService(repository, notify_event=lambda *_args: None, model_call=lambda _messages: "ok")

    def fake_create_task(coro):
        coro.close()
        return object()

    monkeypatch.setattr("agent_session.async_subagents.asyncio.create_task", fake_create_task)
    started = asyncio.run(service.start_task(parent["id"], "explore", "inspect code"))
    restarted = asyncio.run(service.update_task(parent["id"], started["task_id"], "inspect again"))

    assert restarted["task_id"] == started["task_id"]
    assert restarted["child_session_id"] != started["child_session_id"]
    assert restarted["restart_count"] == 1
    assert restarted["previous_child_session_ids"] == [started["child_session_id"]]
    assert restarted["input"]["description"] == "inspect again"
    assert repository.get_session(started["child_session_id"])["status"] == "interrupted"


def test_async_subagent_service_recovers_running_tasks(monkeypatch, tmp_path: Path):
    repository = AgentSessionRepository(str(tmp_path / "agents.db"))
    parent = repository.create_session({"agent_id": "build", "title": "parent", "project_path": str(tmp_path)})
    child = repository.create_session({"agent_id": "explore", "title": "child", "project_path": str(tmp_path), "status": "running"})
    task = repository.create_subtask(
        {
            "parent_session_id": parent["id"],
            "child_session_id": child["id"],
            "agent_name": "explore",
            "status": "running",
            "input_json": {"description": "inspect code", "subagent_type": "explore", "revision": 1},
        }
    )
    scheduled = []

    def fake_create_task(coro):
        scheduled.append(coro)
        coro.close()
        return object()

    monkeypatch.setattr("agent_session.async_subagents.asyncio.create_task", fake_create_task)
    service = AsyncSubagentService(repository, notify_event=lambda *_args: None, model_call=lambda _messages: "ok")
    result = asyncio.run(service.recover_running_tasks())

    assert result["scheduled"] == 1
    assert scheduled
    assert repository.get_subtask(task["id"])["status"] == "running"


def test_deepagents_backend_routes_internal_files_to_state_backend(tmp_path: Path):
    from deepagents.backends import CompositeBackend, LocalShellBackend, StateBackend

    backend = build_deepagents_backend(str(tmp_path))

    assert isinstance(backend, CompositeBackend)
    assert isinstance(backend.default, LocalShellBackend)
    assert isinstance(backend.routes[WORKSPACE_BACKEND_ROUTE], LocalShellBackend)
    for route in EPHEMERAL_BACKEND_ROUTES:
        assert isinstance(backend.routes[route], StateBackend)
    assert isinstance(backend.routes[FALLBACK_STATE_BACKEND_ROUTE], StateBackend)


def test_deepagents_runtime_resolves_optional_interrupt_config():
    assert resolve_interrupt_on({}) is None
    assert resolve_interrupt_on({"deepagents_interrupt_on": True}) == {"write_file": True, "edit_file": True, "execute": True}
    custom = {"write_file": False, "edit_file": True}
    assert resolve_interrupt_on({"deepagents_interrupt_on": custom}) == custom


def test_agent_session_deepagents_interrupt_creates_permission_card(tmp_path: Path):
    workspace = Path.cwd() / "tmp" / f"deepagents-hitl-{uuid.uuid4().hex[:8]}"
    workspace.mkdir()
    try:
        target = workspace / "hello.txt"
        target.write_text("hello\n", encoding="utf-8")
        service = AgentSessionService(AgentSessionRepository(str(tmp_path / "agents.db")))
        session = service.create_session(AgentSessionCreate(title="deepagents hitl", project_path=str(workspace)))
        responses = iter(
            [
                json.dumps(
                    {
                        "tool": "edit_file",
                        "arguments": {
                            "file_path": "/workspace/hello.txt",
                            "old_string": "hello\n",
                            "new_string": "hi\n",
                        },
                    },
                    ensure_ascii=False,
                ),
                json.dumps({"type": "final", "content": "已完成。"}, ensure_ascii=False),
            ]
        )

        async def model_call(_messages):
            return next(responses)

        service.model_call = model_call
        result = asyncio.run(service.prompt(session.id, AgentPromptRequest(content="把 hello 改成 hi")))

        assert result.status == "waiting_approval"
        permission = next(part for part in result.parts if part.type == "permission")
        assert permission.status == "pending"
        assert permission.payload["official_hitl"] is True
        assert permission.payload["tool"] == "edit_file"
        assert target.read_text(encoding="utf-8") == "hello\n"

        approved = asyncio.run(service.approve_permission_async(permission.id, True))

        assert approved.status == "completed"
        assert target.read_text(encoding="utf-8") == "hi\n"
    finally:
        shutil.rmtree(workspace, ignore_errors=True)


def test_agent_session_hitl_decision_validation_accepts_edit_and_respond(tmp_path: Path):
    service = AgentSessionService(AgentSessionRepository(str(tmp_path / "agents.db")))
    session = service.create_session(AgentSessionCreate(title="hitl decisions", project_path=str(Path.cwd())))
    service.repository.update_session(session.id, provider=None, model=None, metadata={"runtime": "deepagents"})
    part = service.repository.add_part(
        session.id,
        "permission",
        status="pending",
        title="Confirm tools",
        content="Confirm tools",
        payload={
            "official_hitl": True,
            "action_requests": [
                {"name": "edit_file", "args": {"file_path": "/a.py"}},
                {"name": "ask_user", "args": {"question": "Color?"}},
            ],
            "actions": [
                {"name": "edit_file", "args": {"file_path": "/a.py"}, "allowed_decisions": ["approve", "edit", "reject"]},
                {"name": "ask_user", "args": {"question": "Color?"}, "allowed_decisions": ["respond", "reject"]},
            ],
        },
    )

    result = asyncio.run(
        service.decide_permission_async(
            part["id"],
            [
                {"type": "edit", "edited_action": {"name": "edit_file", "args": {"file_path": "/b.py"}}},
                {"type": "respond", "message": "Blue."},
            ],
        )
    )

    updated = next(item for item in result.parts if item.id == part["id"])
    assert updated.status == "approved"
    assert updated.payload["decisions"][0]["edited_action"]["args"]["file_path"] == "/b.py"
    assert updated.payload["decisions"][1]["message"] == "Blue."


def test_agent_session_hitl_decision_validation_rejects_bad_batches(tmp_path: Path):
    service = AgentSessionService(AgentSessionRepository(str(tmp_path / "agents.db")))
    session = service.create_session(AgentSessionCreate(title="hitl decisions", project_path=str(Path.cwd())))
    service.repository.update_session(session.id, provider=None, model=None, metadata={"runtime": "deepagents"})
    part = service.repository.add_part(
        session.id,
        "permission",
        status="pending",
        title="Confirm tools",
        content="Confirm tools",
        payload={
            "official_hitl": True,
            "action_requests": [{"name": "ask_user", "args": {}}],
            "actions": [{"name": "ask_user", "args": {}, "allowed_decisions": ["respond"]}],
        },
    )

    with pytest.raises(ValueError, match="require a message"):
        asyncio.run(service.decide_permission_async(part["id"], [{"type": "respond"}]))

    with pytest.raises(ValueError, match="Expected 1 HITL decision"):
        asyncio.run(service.decide_permission_async(part["id"], [{"type": "respond", "message": "A"}, {"type": "respond", "message": "B"}]))


def test_agent_session_response_includes_deepagents_ui_state(tmp_path: Path):
    service = AgentSessionService(AgentSessionRepository(str(tmp_path / "agents.db")))
    session = service.create_session(AgentSessionCreate(title="ui state", project_path=str(Path.cwd())))
    service.repository.add_part(
        session.id,
        "tool_call",
        status="completed",
        title="read_file",
        content="Reading file",
        payload={"tool": "read_file", "args": {"file_path": "/workspace/a.py"}},
    )
    service.repository.add_part(
        session.id,
        "tool_result",
        status="completed",
        title="read_file result",
        content="File content",
        payload={"tool": "read_file"},
    )
    permission = service.repository.add_part(
        session.id,
        "permission",
        status="pending",
        title="Confirm edit",
        content="Confirm edit",
        payload={
            "official_hitl": True,
            "actions": [
                {
                    "name": "edit_file",
                    "args": {"file_path": "/workspace/a.py"},
                    "allowed_decisions": ["approve", "edit", "reject"],
                }
            ],
        },
    )
    service.repository.add_part(
        session.id,
        "summary",
        status="completed",
        title="Final",
        content="Done",
        payload={},
    )
    service.repository.update_session(session.id, status="waiting_approval", metadata={"runtime": "deepagents"})

    result = service.get_session(session.id)
    ui_state = result.metadata["ui_state"]

    assert [item["type"] for item in ui_state["timeline"]] == ["tool_call", "tool_result", "permission", "summary"]
    assert ui_state["pending_permission"]["part_id"] == permission["id"]
    assert ui_state["pending_permission"]["actions"][0]["name"] == "edit_file"
    assert ui_state["latest"]["permission"]["id"] == permission["id"]
    assert result.metadata["diagnostics"]["latest_action"]["id"] == permission["id"]


def test_agent_session_ui_state_marks_legacy_actions_read_only(tmp_path: Path):
    service = AgentSessionService(AgentSessionRepository(str(tmp_path / "agents.db")))
    session = service.create_session(AgentSessionCreate(title="legacy ui", project_path=str(Path.cwd())))
    diff = service.repository.add_part(
        session.id,
        "diff",
        status="pending",
        title="Old patch",
        content="legacy patch",
        payload={"changed_files": ["a.py"]},
    )
    command = service.repository.add_part(
        session.id,
        "command",
        status="approved",
        title="Old command",
        content="legacy command",
        payload={"command": ["pytest"]},
    )

    result = service.get_session(session.id)
    ui_state = result.metadata["ui_state"]
    items = {item["id"]: item for item in ui_state["timeline"]}

    assert items[diff["id"]]["legacy"] is True
    assert items[command["id"]]["legacy"] is True
    assert ui_state["pending_permission"] is None
    assert result.metadata["diagnostics"]["latest_action"] is None
