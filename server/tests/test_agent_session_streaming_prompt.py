from __future__ import annotations

import asyncio
import json
import shutil
import uuid
from pathlib import Path

from fastapi import BackgroundTasks

from agent_session.models import AgentPromptRequest, AgentSessionCreate
from agent_session.repository import AgentSessionRepository
from agent_session.service import AgentSessionService


def _service(tmp_path: Path) -> AgentSessionService:
    return AgentSessionService(AgentSessionRepository(str(tmp_path / f"agent-streaming-{uuid.uuid4().hex}.db")))


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
