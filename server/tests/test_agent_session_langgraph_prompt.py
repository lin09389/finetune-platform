from __future__ import annotations

import asyncio
import json
import shutil
import uuid
from pathlib import Path

from agent_session.models import AgentPromptRequest, AgentSessionCreate
from agent_session.repository import AgentSessionRepository
from agent_session.service import AgentSessionService
from core.config import settings


def test_agent_session_langgraph_prompt_runs_tool_loop_and_finalizes(tmp_path: Path, monkeypatch):
    workspace = Path.cwd()
    run_dir = workspace / "tmp" / f"agent-session-langgraph-{uuid.uuid4().hex[:8]}"
    run_dir.mkdir(parents=True, exist_ok=True)
    target = run_dir / "hello.txt"
    target.write_text("hello from langgraph", encoding="utf-8")
    monkeypatch.setattr(settings, "agent_session_langgraph_enabled", True)
    service = AgentSessionService(AgentSessionRepository(str(tmp_path / "agent_session_langgraph_prompt.db")))
    session = service.create_session(AgentSessionCreate(title="langgraph prompt", project_path=str(workspace)))
    rel = target.relative_to(workspace).as_posix()
    responses = iter(
        [
            "我先读取目标文件。\n" + json.dumps({"tool": "read", "arguments": {"path": rel}}, ensure_ascii=False),
            json.dumps({"tool": "finalize", "arguments": {"summary": "LangGraph 已读取并完成总结。"}}, ensure_ascii=False),
        ]
    )

    async def model_call(_messages):
        return next(responses)

    service.model_call = model_call
    try:
        result = asyncio.run(service.prompt(session.id, AgentPromptRequest(content="读取 hello.txt 并总结")))
        events = service.list_events(session.id)

        assert result.status == "completed"
        assert [part.type for part in result.parts] == ["text", "text", "tool_call", "tool_result", "tool_call", "summary"]
        assert result.parts[-1].content == "LangGraph 已读取并完成总结。"
        assert any(event["event_type"] == "session_started" for event in events)
        assert any(event["event_type"] == "phase_change" for event in events)
        assert any(event["event_type"] == "tool_call_completed" for event in events)
        assert any(event["event_type"] == "summary_completed" for event in events)
    finally:
        shutil.rmtree(run_dir, ignore_errors=True)
