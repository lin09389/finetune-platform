from __future__ import annotations

import asyncio
import json
from pathlib import Path

from agent_session.models import AgentPromptRequest, AgentSessionCreate
from agent_session.repository import AgentSessionRepository
from agent_session.service import AgentSessionService
from core.config import settings


def test_agent_session_langgraph_keeps_streaming_path_on_old_processor(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(settings, "agent_session_langgraph_enabled", True)
    service = AgentSessionService(AgentSessionRepository(str(tmp_path / "agent_session_langgraph_stream.db")))
    session = service.create_session(AgentSessionCreate(title="stream fallback", project_path=str(Path.cwd()), provider="mock", model="mock-model"))

    async def model_call(_messages):
        return "最终结果：流式路径完成。"

    async def stream_model_call(_messages):
        yield {"content": "最终结果：流式路径完成。"}

    monkeypatch.setattr(service, "_cloud_model_call", lambda _session: model_call)
    monkeypatch.setattr(service, "_cloud_stream_model_call", lambda _session: stream_model_call)

    result = asyncio.run(service.prompt(session.id, AgentPromptRequest(content="使用流式路径")))
    events = service.list_events(session.id)

    assert result.status == "completed"
    assert result.metadata["runtime"] == "langgraph"
    assert any(event["event_type"] == "model_stream_started" for event in events)
    assert any(event["event_type"] == "model_stream_completed" for event in events)
    assert result.metadata["streaming_diagnostics"]["mode"] == "chat_stream"
