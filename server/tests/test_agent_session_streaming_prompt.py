from __future__ import annotations

import asyncio
import json
import shutil
import uuid
from pathlib import Path

from fastapi import BackgroundTasks

from agent_session.models import AgentPromptRequest, AgentSessionCreate
from agent_session.terminal_manager import TerminalSession
from agent_session.repository import AgentSessionRepository
from agent_session.service import AgentSessionService
from agent_session.state import ensure_session_state


def _service(tmp_path: Path) -> AgentSessionService:
    return AgentSessionService(AgentSessionRepository(str(tmp_path / f"agent-streaming-{uuid.uuid4().hex}.db")))


def test_waiting_statuses_are_active_not_terminal():
    assert "waiting_approval" in AgentSessionService.ACTIVE_STATUSES
    assert "waiting_permission" in AgentSessionService.ACTIVE_STATUSES
    assert "waiting_approval" not in AgentSessionService.TERMINAL_STATUSES
    assert "waiting_permission" not in AgentSessionService.TERMINAL_STATUSES


def test_prompt_starts_background_run_without_waiting_for_processor(tmp_path: Path):
    service = _service(tmp_path)
    session = service.create_session(AgentSessionCreate(title="streaming", project_path=str(Path.cwd())))
    background = BackgroundTasks()
    calls = {"count": 0}

    async def model_call(_messages):
        calls["count"] += 1
        return json.dumps({"tool": "finalize", "arguments": {"summary": "后台完成。"}}, ensure_ascii=False)

    service.model_call = model_call

    started = service.start_prompt_background(
        session.id,
        AgentPromptRequest(content="后台执行"),
        background,
    )

    assert started.status == "running"
    assert started.metadata["background_run"] is True
    assert started.metadata["active_prompt_id"]
    assert calls["count"] == 0

    asyncio.run(background())
    finished = service.get_session(session.id)

    assert calls["count"] == 1
    assert finished.status == "completed"
    assert finished.parts[-1].type == "summary"
    assert finished.parts[-1].content == "后台完成。"


def test_duplicate_prompt_while_running_does_not_start_second_background_task(tmp_path: Path):
    service = _service(tmp_path)
    session = service.create_session(AgentSessionCreate(title="dedupe", project_path=str(Path.cwd())))
    first = BackgroundTasks()
    second = BackgroundTasks()

    service.start_prompt_background(session.id, AgentPromptRequest(content="第一次"), first)
    duplicate = service.start_prompt_background(session.id, AgentPromptRequest(content="第二次"), second)
    events = service.list_events(session.id)

    assert duplicate.status == "running"
    assert len(first.tasks) == 1
    assert len(second.tasks) == 0
    assert any(event["event_type"] == "prompt_already_running" for event in events)


def test_interrupt_background_prompt_prevents_later_model_call(tmp_path: Path):
    service = _service(tmp_path)
    session = service.create_session(AgentSessionCreate(title="interrupt", project_path=str(Path.cwd())))
    background = BackgroundTasks()
    calls = {"count": 0}

    async def model_call(_messages):
        calls["count"] += 1
        return json.dumps({"tool": "finalize", "arguments": {"summary": "不应执行"}}, ensure_ascii=False)

    service.model_call = model_call
    service.start_prompt_background(session.id, AgentPromptRequest(content="准备执行"), background)
    interrupted = service.interrupt_session(session.id)
    asyncio.run(background())
    result = service.get_session(session.id)
    events = service.list_events(session.id)

    assert interrupted.status == "interrupted"
    assert result.status == "interrupted"
    assert calls["count"] == 0
    assert any(part.type == "summary" and "中断" in (part.title or "") for part in result.parts)
    assert any(event["event_type"] == "session_interrupted" for event in events)


def test_background_run_records_incremental_part_events(tmp_path: Path):
    workspace = Path.cwd()
    run_dir = workspace / "tmp" / f"agent-streaming-{uuid.uuid4().hex[:8]}"
    run_dir.mkdir(parents=True, exist_ok=True)
    target = run_dir / "hello.txt"
    target.write_text("hello", encoding="utf-8")
    rel = target.relative_to(workspace).as_posix()
    service = _service(tmp_path)
    session = service.create_session(AgentSessionCreate(title="events", project_path=str(workspace)))
    background = BackgroundTasks()
    responses = iter(
        [
            "我先读取文件。\n" + json.dumps({"tool": "read", "arguments": {"path": rel}}, ensure_ascii=False),
            json.dumps({"tool": "finalize", "arguments": {"summary": "读取完成。"}}, ensure_ascii=False),
        ]
    )

    async def model_call(_messages):
        return next(responses)

    service.model_call = model_call
    service.processor.max_iterations = 4
    try:
        service.start_prompt_background(session.id, AgentPromptRequest(content="读取文件"), background)
        asyncio.run(background())
        result = service.get_session(session.id)
        events = service.list_events(session.id)

        assert result.status == "completed"
        assert [part.type for part in result.parts] == ["text", "text", "tool_call", "tool_result", "tool_call", "summary"]
        assert any(event["event_type"] == "part_created" and event["payload"].get("part_type") == "text" for event in events)
        assert any(event["event_type"] == "tool_call_started" and event["payload"].get("part_type") == "tool_call" for event in events)
        assert any(event["event_type"] == "tool_call_completed" and event["payload"].get("part_type") == "tool_result" for event in events)
        assert any(event["event_type"] == "summary_completed" and event["payload"].get("part_type") == "summary" for event in events)
    finally:
        shutil.rmtree(run_dir, ignore_errors=True)


def test_list_events_since_event_id_skips_previous_events(tmp_path: Path):
    service = _service(tmp_path)
    session = service.create_session(AgentSessionCreate(title="since", project_path=str(Path.cwd())))
    first = service.repository.add_event(session.id, "first", "第一条", {})
    second = service.repository.add_event(session.id, "second", "第二条", {})

    events = service.list_events(session.id, first["id"])

    assert [event["id"] for event in events] == [second["id"]]


def test_background_exception_writes_error_summary(tmp_path: Path):
    service = _service(tmp_path)
    session = service.create_session(AgentSessionCreate(title="failure", project_path=str(Path.cwd())))
    background = BackgroundTasks()

    async def model_call(_messages):
        raise RuntimeError("boom")

    service.model_call = model_call
    service.start_prompt_background(session.id, AgentPromptRequest(content="会失败"), background)
    asyncio.run(background())
    result = service.get_session(session.id)

    assert result.status == "needs_manual_review"
    assert result.parts[-1].type == "summary"
    assert "模型调用失败" in (result.parts[-1].content or "")


def test_approve_action_async_marks_part_approved_in_langgraph_mode(tmp_path: Path):
    service = _service(tmp_path)
    session = service.create_session(AgentSessionCreate(title="approval", project_path=str(Path.cwd())))
    service.repository.update_session(
        session.id,
        status="waiting_approval",
        metadata={**ensure_session_state(dict(session.metadata or {})), "runtime": "langgraph"},
    )
    command = service.repository.add_part(
        session.id,
        "command",
        status="pending",
        title="启动开发服务器",
        content="等待审批",
        payload={
            "tool": "run_dev_server",
            "command": ["npm", "run", "dev"],
            "server_url": "http://localhost:5173",
        },
    )

    calls = {"resume": 0}

    class DummyRunner:
        async def resume(self, *args, **kwargs):
            calls["resume"] += 1

    async def fake_get_graph_runner():
        return DummyRunner()

    service._get_graph_runner = fake_get_graph_runner  # type: ignore[method-assign]
    resumed = asyncio.run(service.approve_action_async(command["id"], True))
    approved_command = next(part for part in resumed.parts if part.id == command["id"])

    assert approved_command.status == "approved"
    assert calls["resume"] == 0


def test_execute_command_action_starts_terminal_and_returns_running(tmp_path: Path, monkeypatch):
    service = _service(tmp_path)
    session = service.create_session(AgentSessionCreate(title="terminal", project_path=str(Path.cwd())))
    command = service.repository.add_part(
        session.id,
        "command",
        status="approved",
        title="验证命令",
        content="等待执行",
        payload={"command": ["npm", "run", "typecheck"]},
    )

    class FakeTerminalManager:
        def start(self, *, part_id, session_id, command, cwd, timeout_seconds=120, on_output=None, on_exit=None):
            return TerminalSession(
                id="agt_fake",
                part_id=part_id,
                session_id=session_id,
                command=command,
                cwd=str(cwd),
                interactive=True,
            )

    monkeypatch.setattr("agent_session.processor.terminal_manager", FakeTerminalManager())

    executed = asyncio.run(service.execute_action_async(command["id"]))
    updated = next(part for part in executed.parts if part.id == command["id"])

    assert updated.status == "running"
    assert updated.payload["terminal_id"] == "agt_fake"
    assert updated.payload["interactive"] is True
    assert updated.payload["command"] == ["npm", "run", "typecheck"]


def test_terminal_exit_callback_updates_command_part(tmp_path: Path, monkeypatch):
    service = _service(tmp_path)
    session = service.create_session(AgentSessionCreate(title="terminal exit", project_path=str(Path.cwd())))
    command = service.repository.add_part(
        session.id,
        "command",
        status="approved",
        title="验证命令",
        content="等待执行",
        payload={"command": ["npm", "run", "typecheck"]},
    )
    captured: dict[str, TerminalSession] = {}

    class FakeTerminalManager:
        def start(self, *, part_id, session_id, command, cwd, timeout_seconds=120, on_output=None, on_exit=None):
            terminal = TerminalSession(
                id="agt_done",
                part_id=part_id,
                session_id=session_id,
                command=command,
                cwd=str(cwd),
                interactive=False,
            )
            terminal.stdout = "ok\n"
            terminal.exit_code = 0
            captured["terminal"] = terminal
            if on_exit:
                on_exit(terminal)
            return terminal

    monkeypatch.setattr("agent_session.processor.terminal_manager", FakeTerminalManager())

    executed = asyncio.run(service.execute_action_async(command["id"]))
    updated = next(part for part in executed.parts if part.id == command["id"])

    assert updated.status == "executed"
    assert updated.payload["terminal_id"] == "agt_done"
    assert updated.payload["stdout"] == "ok\n"
    assert updated.payload["exit_code"] == 0
