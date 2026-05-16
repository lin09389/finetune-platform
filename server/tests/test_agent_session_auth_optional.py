from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from agent_session.repository import AgentSessionRepository
from agent_session.service import AgentSessionService
from api.agent_sessions import get_agent_session_service
from core.config import settings
from main import app
from workspace import local_paths as workspace_local_paths


def _client_with_service(tmp_path: Path) -> tuple[TestClient, AgentSessionService]:
    service = AgentSessionService(AgentSessionRepository(str(tmp_path / "agent_session_optional_auth.db")))
    app.dependency_overrides[get_agent_session_service] = lambda: service
    return TestClient(app), service


def _workspace_root() -> Path:
    cwd = Path.cwd().resolve()
    return cwd.parent if cwd.name == "server" else cwd


def test_agent_sessions_allow_desktop_optional_auth_without_token(tmp_path: Path):
    client, _ = _client_with_service(tmp_path)
    workspace = _workspace_root()
    try:
        response = client.post(
            "/agent-sessions",
            json={"title": "desktop smoke", "agent_id": "build", "project_path": str(workspace)},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["title"] == "desktop smoke"
        assert Path(body["project_path"]).name == workspace.name

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
            json={"title": "prod", "agent_id": "build", "project_path": str(_workspace_root())},
        )
        assert response.status_code == 401
    finally:
        monkeypatch.setattr(settings, "environment", original_environment)
        app.dependency_overrides.clear()


def test_agent_sessions_allow_registered_local_workspace_path(tmp_path: Path, monkeypatch):
    external_root = tmp_path / "external-workspace"
    external_root.mkdir(parents=True, exist_ok=True)
    metadata_file = tmp_path / "workspace-metadata.json"
    metadata_file.write_text(
        '{"ws_local":{"id":"ws_local","name":"Local","local_path":%s}}' % json.dumps(str(external_root)),
        encoding="utf-8",
    )
    monkeypatch.setattr(workspace_local_paths, "WORKSPACE_METADATA_FILE", metadata_file)
    client, _ = _client_with_service(tmp_path)
    try:
        response = client.post(
            "/agent-sessions",
            json={"title": "external", "agent_id": "build", "project_path": str(external_root)},
        )
        assert response.status_code == 200
        body = response.json()
        assert Path(body["project_path"]) == external_root.resolve()
    finally:
        app.dependency_overrides.clear()


def test_agent_sessions_reject_unregistered_external_project_path(tmp_path: Path, monkeypatch):
    external_root = tmp_path / "unregistered-workspace"
    external_root.mkdir(parents=True, exist_ok=True)
    metadata_file = tmp_path / "workspace-metadata-empty.json"
    metadata_file.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(workspace_local_paths, "WORKSPACE_METADATA_FILE", metadata_file)
    client, _ = _client_with_service(tmp_path)
    try:
        response = client.post(
            "/agent-sessions",
            json={"title": "blocked", "agent_id": "build", "project_path": str(external_root)},
        )
        assert response.status_code == 400
        assert "project_path must be inside the workspace" in str(response.json())
    finally:
        app.dependency_overrides.clear()
