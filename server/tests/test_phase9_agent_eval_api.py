from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from security.jwt_auth import Role, TokenPayload


def _client() -> TestClient:
    from api.agent_eval import router
    from api.agent_sessions import get_agent_session_user

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_agent_session_user] = lambda: TokenPayload(
        user_id="phase9-test-user",
        username="phase9",
        role=Role.USER,
        permissions=["agent_sessions:local"],
    )
    return TestClient(app)


def test_overview_exposes_publishable_baseline_without_private_data(monkeypatch):
    monkeypatch.delenv("ENABLE_REAL_MODEL_EVALUATION", raising=False)
    response = _client().get("/agent-eval/overview")

    assert response.status_code == 200
    body = response.json()
    assert body["schema_version"] == 1
    assert body["catalog"]["scenario_count"] >= 30
    assert set(body["catalog"]["by_mode"]) == {"coding", "training", "hybrid"}
    assert body["live_model"] == {
        "enabled": False,
        "default_dry_run": True,
        "requires_explicit_opt_in": True,
    }
    serialized = response.text.lower()
    assert "authorization" not in serialized
    assert "project_path" not in serialized
    assert "prompt" not in serialized


def test_real_model_run_defaults_to_plan_and_never_constructs_agent_service(monkeypatch):
    import api.agent_eval as endpoint

    monkeypatch.delenv("ENABLE_REAL_MODEL_EVALUATION", raising=False)
    monkeypatch.setattr(
        endpoint,
        "get_agent_session_service",
        lambda: (_ for _ in ()).throw(AssertionError("dry-run touched AgentSessionService")),
    )

    response = _client().post(
        "/agent-eval/real-model/run",
        json={"model_id": "local-test-model"},
    )

    assert response.status_code == 200
    assert response.json()["dry_run"] is True
    assert response.json()["would_execute"] is False


def test_live_run_requires_both_request_and_server_gates(monkeypatch):
    monkeypatch.delenv("ENABLE_REAL_MODEL_EVALUATION", raising=False)
    client = _client()

    missing_request_gate = client.post(
        "/agent-eval/real-model/run",
        json={"model_id": "local-test-model", "dry_run": False},
    )
    assert missing_request_gate.status_code == 403

    missing_server_gate = client.post(
        "/agent-eval/real-model/run",
        json={
            "model_id": "local-test-model",
            "dry_run": False,
            "explicit_opt_in": True,
        },
    )
    assert missing_server_gate.status_code == 403


def test_agent_eval_is_a_beta_agent_capability():
    from apps.capability_registry import build_info_capability_payload, capability_ids_by_tier

    assert "agent_eval" in capability_ids_by_tier()["beta"]
    assert build_info_capability_payload()["endpoints"]["agent_eval"] == "/agent-eval"
