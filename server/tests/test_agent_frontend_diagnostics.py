from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from agent_session.diagnostics import AgentFrontendDiagnosticsRepository
from agent_session.repository import AgentSessionRepository
from agent_session.service import AgentSessionService
from agent_session.models import AgentSessionCreate
from api.agent_sessions import (
    get_agent_frontend_diagnostics_repository,
    get_agent_session_service,
    get_agent_session_user,
)
from main import app
from security.jwt_auth import Role, TokenPayload


def test_agent_frontend_diagnostics_upserts_monotonic_session_aggregates(tmp_path: Path):
    repository = AgentFrontendDiagnosticsRepository(str(tmp_path / "diagnostics.db"))
    report = {
        "sessionId": "ags_private",
        "protocolVersion": "agent.session.v1",
        "unknownEvents": 2,
        "parseFailures": 1,
        "reconnects": 3,
        "recoveryRequested": 2,
        "recoverySucceeded": 1,
        "recoveryFailed": 1,
        "attentionByKind": {"permission": 1},
        "updatedAt": "2026-06-20T00:00:00Z",
    }
    repository.upsert(report, "alice")
    repository.upsert({**report, "unknownEvents": 1, "recoverySucceeded": 2}, "alice")

    summary = repository.summary()
    assert summary["sessions"] == 1
    assert summary["unknown_events"] == 2
    assert summary["parse_failures"] == 1
    assert summary["reconnects"] == 3
    assert summary["recovery_requested"] == 2
    assert summary["recovery_succeeded"] == 2
    assert summary["recovery_success_rate"] == 1.0


def test_agent_frontend_diagnostics_hashes_session_identity(tmp_path: Path):
    repository = AgentFrontendDiagnosticsRepository(str(tmp_path / "diagnostics.db"))
    first = repository.session_hash("ags_private", "alice")
    second = repository.session_hash("ags_private", "bob")
    assert first != second
    assert "ags_private" not in first


def test_agent_session_history_is_authoritative_and_owner_scoped(tmp_path: Path):
    service = AgentSessionService(AgentSessionRepository(str(tmp_path / "sessions.db")))
    first = service.create_session(AgentSessionCreate(title="Alice task"), "alice")
    service.create_session(AgentSessionCreate(title="Bob task"), "bob")

    listed = service.list_sessions("alice")
    assert [session.id for session in listed] == [first.id]
    assert listed[0].parts == []
    assert listed[0].preferences.display_title is None
    assert listed[0].preferences.pinned is False
    assert listed[0].preferences.archived is False


def test_agent_session_preferences_are_authoritative_and_owner_scoped(tmp_path: Path):
    service = AgentSessionService(AgentSessionRepository(str(tmp_path / "sessions-prefs.db")))
    app.dependency_overrides[get_agent_session_service] = lambda: service
    app.dependency_overrides[get_agent_session_user] = lambda: TokenPayload(
        user_id="alice",
        username="alice",
        role=Role.USER,
        permissions=["agent_sessions:test"],
    )
    client = TestClient(app)
    try:
        created = client.post("/agent-sessions", json={"title": "Original task"}).json()
        response = client.patch(
            f"/agent-sessions/{created['id']}/preferences",
            json={"display_title": "Polished name", "pinned": True, "archived": True},
        )
        assert response.status_code == 200
        preferences = response.json()["preferences"]
        assert preferences["display_title"] == "Polished name"
        assert preferences["pinned"] is True
        assert preferences["archived"] is True
        assert preferences["updated_at"]

        fetched = client.get(f"/agent-sessions/{created['id']}").json()
        listed = client.get("/agent-sessions").json()
        assert fetched["preferences"] == preferences
        assert listed[0]["preferences"] == preferences
        assert fetched["title"] == "Original task"

        app.dependency_overrides[get_agent_session_user] = lambda: TokenPayload(
            user_id="bob",
            username="bob",
            role=Role.USER,
            permissions=["agent_sessions:test"],
        )
        denied = client.patch(
            f"/agent-sessions/{created['id']}/preferences",
            json={"display_title": "Bob rename"},
        )
        assert denied.status_code == 403
    finally:
        app.dependency_overrides.clear()


def test_agent_frontend_diagnostics_http_contract_and_admin_summary(tmp_path: Path):
    repository = AgentFrontendDiagnosticsRepository(str(tmp_path / "diagnostics-api.db"))
    app.dependency_overrides[get_agent_frontend_diagnostics_repository] = lambda: repository
    app.dependency_overrides[get_agent_session_user] = lambda: TokenPayload(
        user_id="alice",
        username="alice",
        role=Role.USER,
        permissions=["agent_sessions:test"],
    )
    client = TestClient(app)
    try:
        response = client.post(
            "/agent-sessions/diagnostics/batch",
            json={
                "reports": [{
                    "sessionId": "ags_http",
                    "protocolVersion": "agent.session.v1",
                    "unknownEvents": 1,
                    "parseFailures": 2,
                    "reconnects": 3,
                    "recoveryRequested": 1,
                    "recoverySucceeded": 1,
                    "recoveryFailed": 0,
                    "attentionByKind": {"permission": 1},
                    "updatedAt": "2026-06-20T00:00:00Z",
                }]
            },
        )
        assert response.status_code == 200
        assert response.json() == {"accepted": 1}
        assert client.get("/agent-sessions/diagnostics/summary").status_code == 403

        app.dependency_overrides[get_agent_session_user] = lambda: TokenPayload(
            user_id="admin",
            username="admin",
            role=Role.ADMIN,
            permissions=["agent_sessions:test"],
        )
        summary = client.get("/agent-sessions/diagnostics/summary")
        assert summary.status_code == 200
        assert summary.json()["sessions"] == 1
        assert summary.json()["parse_failures"] == 2
    finally:
        app.dependency_overrides.clear()
