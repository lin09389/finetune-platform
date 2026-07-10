"""Tests for shared workspace path policy and related HTTP handlers."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from workspace import path_policy
from workspace.path_policy import (
    require_valid_project_path,
    resolve_default_project_path,
    validate_agent_project_path,
)


def _settings(base_dir: Path, agent_default: str | None = None) -> SimpleNamespace:
    return SimpleNamespace(base_dir=base_dir, agent_default_project_path=agent_default)


def test_resolve_default_uses_server_parent_as_repo_root(tmp_path: Path):
    server_dir = tmp_path / "server"
    server_dir.mkdir()
    settings = _settings(server_dir)
    assert resolve_default_project_path(settings) == str(tmp_path.resolve())


def test_validate_null_path_returns_default(tmp_path: Path):
    server_dir = tmp_path / "server"
    server_dir.mkdir()
    settings = _settings(server_dir)
    result = validate_agent_project_path(None, settings)
    assert result.ok is True
    assert result.allowed is True
    assert result.resolved_path == str(tmp_path.resolve())
    assert result.needs_register is False


def test_validate_subdirectory_under_default_root(tmp_path: Path):
    server_dir = tmp_path / "server"
    server_dir.mkdir()
    child = tmp_path / "packages" / "app"
    child.mkdir(parents=True)
    settings = _settings(server_dir)
    result = validate_agent_project_path(str(child), settings)
    assert result.ok is True
    assert result.allowed is True
    assert result.resolved_path == str(child.resolve())


def test_validate_missing_path(tmp_path: Path):
    server_dir = tmp_path / "server"
    server_dir.mkdir()
    settings = _settings(server_dir)
    missing = tmp_path / "does-not-exist"
    result = validate_agent_project_path(str(missing), settings)
    assert result.ok is False
    assert result.exists is False
    assert result.error_code == "path_missing"
    assert result.needs_register is False


def test_validate_file_path_rejected(tmp_path: Path):
    server_dir = tmp_path / "server"
    server_dir.mkdir()
    file_path = tmp_path / "readme.txt"
    file_path.write_text("x", encoding="utf-8")
    settings = _settings(server_dir)
    result = validate_agent_project_path(str(file_path), settings)
    assert result.ok is False
    assert result.exists is True
    assert result.is_dir is False
    assert result.error_code == "path_not_dir"


def test_validate_out_of_allowlist_needs_register(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    server_dir = tmp_path / "server"
    server_dir.mkdir()
    outside = tmp_path / "outside_project"
    outside.mkdir()
    # Isolate registered roots: empty metadata
    meta = tmp_path / "empty-meta.json"
    meta.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(path_policy, "load_workspace_metadata", lambda: {})
    monkeypatch.setattr(
        "workspace.local_paths.load_workspace_metadata",
        lambda: {},
    )
    settings = _settings(server_dir)
    # Place outside completely outside default root by using a sibling under a different tree
    alien = tmp_path.parent / f"alien-ws-{tmp_path.name}"
    alien.mkdir(exist_ok=True)
    try:
        result = validate_agent_project_path(str(alien), settings)
        assert result.ok is False
        assert result.exists is True
        assert result.is_dir is True
        assert result.allowed is False
        assert result.needs_register is True
        assert result.error_code == "path_not_allowed"
    finally:
        try:
            alien.rmdir()
        except OSError:
            pass


def test_validate_allowed_after_workspace_registration(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    server_dir = tmp_path / "server"
    server_dir.mkdir()
    alien = tmp_path.parent / f"registered-ws-{tmp_path.name}"
    alien.mkdir(exist_ok=True)
    registered = {
        "ws_test": {
            "id": "ws_test",
            "name": "Registered",
            "local_path": str(alien.resolve()),
        }
    }
    monkeypatch.setattr(path_policy, "load_workspace_metadata", lambda: registered)
    monkeypatch.setattr("workspace.local_paths.load_workspace_metadata", lambda: registered)
    # get_allowed_workspace_roots imports load_workspace_metadata from local_paths
    settings = _settings(server_dir)
    try:
        before = validate_agent_project_path(str(alien), _settings(server_dir))
        # With empty registration first
        monkeypatch.setattr(path_policy, "load_workspace_metadata", lambda: {})
        monkeypatch.setattr("workspace.local_paths.load_workspace_metadata", lambda: {})
        blocked = validate_agent_project_path(str(alien), settings)
        assert blocked.needs_register is True

        monkeypatch.setattr(path_policy, "load_workspace_metadata", lambda: registered)
        monkeypatch.setattr("workspace.local_paths.load_workspace_metadata", lambda: registered)
        after = validate_agent_project_path(str(alien), settings)
        assert after.ok is True
        assert after.allowed is True
        assert after.resolved_path == str(alien.resolve())
        assert require_valid_project_path(str(alien), settings) == str(alien.resolve())
    finally:
        try:
            alien.rmdir()
        except OSError:
            pass


def test_require_valid_project_path_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    server_dir = tmp_path / "server"
    server_dir.mkdir()
    monkeypatch.setattr("workspace.local_paths.load_workspace_metadata", lambda: {})
    settings = _settings(server_dir)
    with pytest.raises(ValueError, match="不存在"):
        require_valid_project_path(str(tmp_path / "missing"), settings)


def test_session_lifecycle_delegates_to_path_policy(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from agent_session.repository import AgentSessionRepository
    from agent_session.service import AgentSessionService

    server_dir = tmp_path / "server"
    server_dir.mkdir()
    child = tmp_path / "nested"
    child.mkdir()

    monkeypatch.setattr("agent_session.services.session_lifecycle.settings.base_dir", server_dir)
    monkeypatch.setattr("agent_session.services.session_lifecycle.settings.agent_default_project_path", None)
    monkeypatch.setattr("workspace.local_paths.load_workspace_metadata", lambda: {})
    monkeypatch.setattr("workspace.path_policy.load_workspace_metadata", lambda: {})

    service = AgentSessionService(AgentSessionRepository(str(tmp_path / "agents.db")))
    resolved = service.validate_project_path(str(child))
    assert resolved == str(child.resolve())
    assert service.validate_project_path(None) == str(tmp_path.resolve())


def test_allowed_roots_and_validate_path_http_endpoints(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    import importlib

    workspace_api = importlib.import_module("api.workspace")

    server_dir = tmp_path / "server"
    server_dir.mkdir()
    child = tmp_path / "sub"
    child.mkdir()
    alien = tmp_path.parent / f"http-alien-{tmp_path.name}"
    alien.mkdir(exist_ok=True)

    monkeypatch.setattr(workspace_api.settings, "base_dir", server_dir)
    monkeypatch.setattr(workspace_api.settings, "agent_default_project_path", None)
    monkeypatch.setattr("workspace.local_paths.load_workspace_metadata", lambda: {})
    monkeypatch.setattr("workspace.path_policy.load_workspace_metadata", lambda: {})

    app = FastAPI()
    app.include_router(workspace_api.router, prefix="/workspace")
    client = TestClient(app)

    roots = client.get("/workspace/allowed-roots")
    assert roots.status_code == 200
    body = roots.json()
    assert body["default_project_path"] == str(tmp_path.resolve())
    assert any(item["path"] == str(tmp_path.resolve()) for item in body["roots"])

    ok = client.post("/workspace/validate-path", json={"path": str(child)})
    assert ok.status_code == 200
    ok_body = ok.json()
    assert ok_body["ok"] is True
    assert ok_body["allowed"] is True

    missing = client.post("/workspace/validate-path", json={"path": str(tmp_path / "nope")})
    assert missing.status_code == 200
    assert missing.json()["error_code"] == "path_missing"

    blocked = client.post("/workspace/validate-path", json={"path": str(alien)})
    assert blocked.status_code == 200
    blocked_body = blocked.json()
    assert blocked_body["ok"] is False
    assert blocked_body["needs_register"] is True
    assert blocked_body["error_code"] == "path_not_allowed"

    # After registration metadata is visible, path validates
    registered = {
        "ws_http": {"id": "ws_http", "name": "HTTP", "local_path": str(alien.resolve())}
    }
    monkeypatch.setattr("workspace.local_paths.load_workspace_metadata", lambda: registered)
    monkeypatch.setattr("workspace.path_policy.load_workspace_metadata", lambda: registered)
    allowed = client.post("/workspace/validate-path", json={"path": str(alien)})
    assert allowed.status_code == 200
    assert allowed.json()["ok"] is True
    assert allowed.json()["allowed"] is True

    try:
        alien.rmdir()
    except OSError:
        pass


def test_default_path_validate_http(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    import importlib

    workspace_api = importlib.import_module("api.workspace")

    server_dir = tmp_path / "server"
    server_dir.mkdir()
    monkeypatch.setattr(workspace_api.settings, "base_dir", server_dir)
    monkeypatch.setattr(workspace_api.settings, "agent_default_project_path", None)

    app = FastAPI()
    app.include_router(workspace_api.router, prefix="/workspace")
    client = TestClient(app)
    resp = client.post("/workspace/validate-path", json={"path": None})
    assert resp.status_code == 200
    assert resp.json()["ok"] is True
    assert resp.json()["resolved_path"] == str(tmp_path.resolve())
