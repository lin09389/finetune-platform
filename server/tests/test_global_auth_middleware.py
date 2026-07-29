import main
from fastapi.testclient import TestClient

import security.jwt_auth


class _FakeJwt:
    def verify_token(self, token: str):
        return {"sub": "student"} if token == "valid-token" else None


def test_global_auth_middleware_protects_business_routes(monkeypatch):
    monkeypatch.setattr(main.settings, "enable_auth", True)
    monkeypatch.setattr(security.jwt_auth, "get_jwt_auth", lambda: _FakeJwt())
    client = TestClient(main.app)

    missing = client.get("/training/history")
    invalid = client.get(
        "/training/history",
        headers={"Authorization": "Bearer invalid-token"},
    )
    valid = client.get(
        "/training/history",
        headers={"Authorization": "Bearer valid-token"},
    )
    public = client.get("/health")

    assert missing.status_code == 401
    assert invalid.status_code == 401
    assert valid.status_code == 200
    assert public.status_code == 200


def test_global_auth_middleware_allows_local_agent_fallback_only_in_development(monkeypatch):
    monkeypatch.setattr(main.settings, "enable_auth", True)
    monkeypatch.setattr(main.settings, "environment", "development")
    client = TestClient(main.app)

    local_agents = client.get("/agents", headers={"Origin": "http://127.0.0.1:5173"})

    assert local_agents.status_code == 200
    assert local_agents.headers["access-control-allow-origin"] in {"*", "http://127.0.0.1:5173"}

    monkeypatch.setattr(main.settings, "environment", "production")
    protected_agents = client.get("/agents", headers={"Origin": "http://127.0.0.1:5173"})

    assert protected_agents.status_code == 401
    assert "access-control-allow-origin" in protected_agents.headers
