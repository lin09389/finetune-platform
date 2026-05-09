from __future__ import annotations

import asyncio
from pathlib import Path

from fastapi.testclient import TestClient

from agent_session.models import AgentPartResponse, AgentSessionResponse
from agent_session.repository import AgentSessionRepository
from agent_session.service import AgentSessionService
from api.agent_sessions import get_agent_session_service
from main import app
from security.auth_middleware import get_current_user


def test_agent_session_action_route_uses_async_service_method(tmp_path: Path, monkeypatch):
    repository = AgentSessionRepository(str(tmp_path / "agent_session_langgraph_api.db"))
    service = AgentSessionService(repository)
    session = repository.create_session(
        {
            "agent_id": "build",
            "status": "waiting_approval",
            "title": "api async",
            "project_path": str(Path.cwd()),
            "metadata": {"runtime": "langgraph"},
        }
    )
    part = repository.add_part(session["id"], "diff", status="pending", title="补丁", content="pending", payload={})
    session["parts"] = repository.list_parts(session["id"])
    payload_session = AgentSessionResponse(**service.get_session(session["id"]).model_dump())

    def should_not_be_called(*args, **kwargs):
        raise AssertionError("sync approve_action path should not be used")

    async def async_approve_action(part_id: str, approved: bool):
        assert part_id == part["id"]
        assert approved is True
        return payload_session

    monkeypatch.setattr(service, "approve_action", should_not_be_called)
    monkeypatch.setattr(service, "approve_action_async", async_approve_action)
    app.dependency_overrides[get_agent_session_service] = lambda: service
    app.dependency_overrides[get_current_user] = lambda: object()
    try:
        client = TestClient(app)
        response = client.post(f"/agent-actions/{part['id']}/approve")
        assert response.status_code == 200
        body = response.json()
        assert body["part"]["id"] == part["id"]
        assert body["session"]["id"] == session["id"]
    finally:
        app.dependency_overrides.clear()
