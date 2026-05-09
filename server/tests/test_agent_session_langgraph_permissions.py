from __future__ import annotations

import asyncio
import json
import uuid
from pathlib import Path

from agent_session.models import AgentPromptRequest, AgentSessionCreate
from agent_session.repository import AgentSessionRepository
from agent_session.service import AgentSessionService
from core.config import settings


def test_agent_session_langgraph_permission_resume_and_reject(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(settings, "agent_session_langgraph_enabled", True)
    db_path = tmp_path / "agent_session_langgraph_permission.db"
    service = AgentSessionService(AgentSessionRepository(str(db_path)))
    session = service.create_session(AgentSessionCreate(title="langgraph permission", project_path=str(Path.cwd())))
    responses = iter(
        [
            json.dumps({"tool": "magic_tool", "arguments": {"foo": "bar"}}, ensure_ascii=False),
            json.dumps({"tool": "finalize", "arguments": {"summary": "权限确认后已完成。"}}, ensure_ascii=False),
        ]
    )

    async def model_call(_messages):
        return next(responses)

    service.model_call = model_call
    first = asyncio.run(service.prompt(session.id, AgentPromptRequest(content="使用未知工具后继续")))
    permission = next(part for part in first.parts if part.type == "permission")
    assert first.status == "waiting_permission"
    assert permission.status == "pending"

    approve_service = AgentSessionService(AgentSessionRepository(str(db_path)))
    approve_service.model_call = model_call
    approved = asyncio.run(approve_service.approve_permission_async(permission.id, True))
    assert approved.status == "completed"
    assert approved.parts[-1].type == "summary"
    assert approved.parts[-1].content == "权限确认后已完成。"
    assert approved.metadata["last_resume_decision"]["approved"] is True

    reject_db_path = tmp_path / f"agent_session_langgraph_permission_reject_{uuid.uuid4().hex}.db"
    reject_service = AgentSessionService(AgentSessionRepository(str(reject_db_path)))
    reject_session = reject_service.create_session(AgentSessionCreate(title="langgraph permission reject", project_path=str(Path.cwd())))

    async def reject_model_call(_messages):
        return json.dumps({"tool": "magic_tool", "arguments": {"foo": "bar"}}, ensure_ascii=False)

    reject_service.model_call = reject_model_call
    blocked = asyncio.run(reject_service.prompt(reject_session.id, AgentPromptRequest(content="使用未知工具后拒绝")))
    blocked_permission = next(part for part in blocked.parts if part.type == "permission")
    reject_resume_service = AgentSessionService(AgentSessionRepository(str(reject_db_path)))
    rejected = asyncio.run(reject_resume_service.approve_permission_async(blocked_permission.id, False))
    assert rejected.status == "failed"
