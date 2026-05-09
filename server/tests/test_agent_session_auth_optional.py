from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from agent_session.repository import AgentSessionRepository
from agent_session.service import AgentSessionService
from api.agent_sessions import get_agent_session_service
from core.config import settings
from main import app


def _client_with_service(tmp_path: Path) -> tuple[TestClient, AgentSessionService]:
    service = AgentSessionService(AgentSessionRepository(str(tmp_path / "agent_session_optional_auth.db")))
    app.dependency_overrides[get_agent_session_service] = lambda: service
    return TestClient(app), service


def test_agent_sessions_allow_desktop_optional_auth_without_token(tmp_path: Path):
    client, _ = _client_with_service(tmp_path)
    try:
        response = client.post(
            "/agent-sessions",
            json={"title": "desktop smoke", "agent_id": "build", "project_path": str(Path.cwd())},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["title"] == "desktop smoke"
        assert Path(body["project_path"]).name == "finetune-platform"

        prompt = client.post(
            f"/agent-sessions/{body['id']}/prompt",
            json={"content": "只读检查一下项目。"},
        )
        assert prompt.status_code == 200

        events = client.get(f"/agent-sessions/{body['id']}/events")
        assert events.status_code == 200

        with client.stream("GET", f"/agent-sessions/{body['id']}/events/stream") as stream:
            assert stream.status_code == 200
    finally:
        app.dependency_overrides.clear()


def test_agent_sessions_require_token_in_production_without_fallback(tmp_path: Path, monkeypatch):
    original_environment = settings.environment
    monkeypatch.setattr(settings, "environment", "production")
    client, _ = _client_with_service(tmp_path)
    try:
        response = client.post(
            "/agent-sessions",
            json={"title": "prod", "agent_id": "build", "project_path": str(Path.cwd())},
        )
        assert response.status_code == 401
    finally:
        monkeypatch.setattr(settings, "environment", original_environment)
        app.dependency_overrides.clear()
