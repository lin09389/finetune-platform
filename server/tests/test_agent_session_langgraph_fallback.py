from __future__ import annotations

import asyncio
import json
from pathlib import Path

from agent_session.models import AgentPromptRequest, AgentSessionCreate
from agent_session.repository import AgentSessionRepository
from agent_session.service import AgentSessionService
from core.config import settings


def test_agent_session_langgraph_init_failure_stops_without_processor_fallback(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(settings, "agent_session_langgraph_enabled", True)
    service = AgentSessionService(AgentSessionRepository(str(tmp_path / "agent_session_langgraph_init_fallback.db")))
    session = service.create_session(AgentSessionCreate(title="graph fallback", project_path=str(Path.cwd())))

    async def model_call(_messages):
        return json.dumps({"tool": "finalize", "arguments": {"summary": "已回退到旧 processor。"}}, ensure_ascii=False)

    async def broken_get_graph(self):
        raise RuntimeError("langgraph init exploded")

    monkeypatch.setattr(service, "model_call", model_call)
    monkeypatch.setattr("agent_session.service.AgentSessionGraphRunner.get_graph", broken_get_graph)

    result = asyncio.run(service.prompt(session.id, AgentPromptRequest(content="触发 LangGraph 初始化失败")))

    assert result.status == "needs_manual_review"
    assert result.parts[-1].type == "summary"
    assert "LangGraph 初始化失败" in result.parts[-1].content
    assert result.metadata["last_graph_error"]
    assert result.metadata["execution_trace"]["failure_code"] == "langgraph_init_failed"
    assert result.metadata["execution_trace"]["fallback_used"] is False
