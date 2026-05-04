from __future__ import annotations

import json
import asyncio
import shutil
import uuid
from pathlib import Path

from agent_session.models import AgentPromptRequest, AgentSessionCreate
from agent_session.repository import AgentSessionRepository
from agent_session.service import AgentSessionService


def test_agent_session_events_are_persisted_in_order(tmp_path: Path):
    workspace = Path.cwd()
    run_dir = workspace / "tmp" / f"agent-events-{uuid.uuid4().hex[:8]}"
    run_dir.mkdir(parents=True, exist_ok=True)
    target = run_dir / "hello.txt"
    target.write_text("hello", encoding="utf-8")
    repository = AgentSessionRepository(str(tmp_path / "events.db"))
    service = AgentSessionService(repository)
    session = service.create_session(AgentSessionCreate(title="events", project_path=str(workspace)))
    rel = target.relative_to(workspace).as_posix()
    responses = iter(
        [
            {"tool": "read", "arguments": {"path": rel}},
            {"tool": "finalize", "arguments": {"summary": "完成。"}},
        ]
    )

    async def model_call(_messages):
        return json.dumps(next(responses), ensure_ascii=False)

    service.processor.max_iterations = 4
    service.model_call = model_call
    try:
        asyncio.run(service.prompt(session.id, AgentPromptRequest(content="读取文件")))
        events = service.list_events(session.id)

        assert [event["event_type"] for event in events][:2] == ["session_started", "tool_call_started"]
        assert events[-1]["event_type"] == "summary_completed"
        restored = service.get_session(session.id)
        assert restored.status == "completed"
        assert restored.parts[-1].type == "summary"
    finally:
        shutil.rmtree(run_dir, ignore_errors=True)


def test_agent_session_failed_state_has_error_part(tmp_path: Path):
    repository = AgentSessionRepository(str(tmp_path / "failed_events.db"))
    service = AgentSessionService(repository)
    session = service.create_session(AgentSessionCreate(title="failed", project_path=str(Path.cwd())))

    async def model_call(_messages):
        return "not json and not useful"

    service.processor.max_iterations = 1
    service.model_call = model_call
    result = asyncio.run(service.prompt(session.id, AgentPromptRequest(content="无法完成")))

    assert result.status == "needs_manual_review"
    assert result.parts[-1].type == "summary"
    assert result.parts[-1].content
