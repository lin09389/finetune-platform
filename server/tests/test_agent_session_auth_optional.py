from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from agent_session.repository import AgentSessionRepository
from agent_session.service import AgentSessionService
from agent_session.terminal_manager import TerminalSession, terminal_manager
from api.agent_sessions import get_agent_session_service, get_agent_session_user
from core.config import settings
from main import app
from memory.memory_service import reset_memory_service
from security.jwt_auth import Role, TokenPayload
from workspace import local_paths as workspace_local_paths


def _client_with_service(tmp_path: Path) -> tuple[TestClient, AgentSessionService]:
    service = AgentSessionService(AgentSessionRepository(str(tmp_path / "agent_session_optional_auth.db")))
    app.dependency_overrides[get_agent_session_service] = lambda: service
    return TestClient(app), service


def _workspace_root() -> Path:
    cwd = Path.cwd().resolve()
    return cwd.parent if cwd.name == "server" else cwd


def _override_agent_user(user_id: str, role: Role = Role.USER) -> None:
    app.dependency_overrides[get_agent_session_user] = lambda: TokenPayload(
        user_id=user_id,
        username=user_id,
        role=role,
        permissions=["agent_sessions:test"],
    )


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
        assert body["metadata"]["user_id"] == "desktop-local-user"

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


def test_agent_session_endpoints_enforce_session_owner(tmp_path: Path):
    client, service = _client_with_service(tmp_path)
    workspace = _workspace_root()
    try:
        _override_agent_user("alice")
        created = client.post(
            "/agent-sessions",
            json={"title": "owned", "agent_id": "build", "project_path": str(workspace)},
        )
        assert created.status_code == 200
        session_id = created.json()["id"]
        permission = service.repository.add_part(
            session_id,
            "permission",
            status="pending",
            title="Permission",
            payload={"official_hitl": True, "actions": [{"name": "edit_file"}]},
        )

        _override_agent_user("bob")
        assert client.get(f"/agent-sessions/{session_id}").status_code == 403
        assert client.get(f"/agent-sessions/{session_id}/events").status_code == 403
        assert client.get(f"/agent-sessions/{session_id}/events/stream").status_code == 403
        assert client.post(f"/agent-sessions/{session_id}/prompt", json={"content": "hi"}).status_code == 403
        assert client.post(f"/agent-permissions/{permission['id']}/approve").status_code == 403
        assert service.repository.get_part(permission["id"])["status"] == "pending"

        _override_agent_user("admin", Role.ADMIN)
        assert client.get(f"/agent-sessions/{session_id}").status_code == 200
    finally:
        app.dependency_overrides.clear()


def test_agent_terminal_websocket_enforces_session_owner(tmp_path: Path):
    client, service = _client_with_service(tmp_path)
    terminal_id = "terminal-owner-test"
    try:
        session = service.repository.create_session(
            {
                "agent_id": "build",
                "title": "terminal",
                "project_path": str(tmp_path),
                "metadata": {"user_id": "alice"},
            }
        )
        terminal = TerminalSession(
            id=terminal_id,
            part_id="part-terminal",
            session_id=session["id"],
            command=["python", "--version"],
            cwd=str(tmp_path),
            interactive=False,
        )
        with terminal_manager._lock:
            terminal_manager._sessions[terminal_id] = terminal

        _override_agent_user("alice")
        with client.websocket_connect(f"/agent-terminals/{terminal_id}/ws") as websocket:
            ready = json.loads(websocket.receive_text())
            assert ready["type"] == "ready"
            assert ready["terminal_id"] == terminal_id

        _override_agent_user("bob")
        with client.websocket_connect(f"/agent-terminals/{terminal_id}/ws") as websocket:
            error = json.loads(websocket.receive_text())
            assert error == {"type": "error", "message": "Terminal access denied"}
            with pytest.raises(WebSocketDisconnect) as disconnect:
                websocket.receive_text()
            assert disconnect.value.code == 4403
    finally:
        with terminal_manager._lock:
            terminal_manager._sessions.pop(terminal_id, None)
        app.dependency_overrides.clear()


def test_agent_session_stream_returns_404_for_missing_session(tmp_path: Path):
    client, _ = _client_with_service(tmp_path)
    try:
        response = client.get("/agent-sessions/missing-session/events/stream")
        assert response.status_code == 404
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


def test_agent_sessions_async_task_rest_lifecycle(tmp_path: Path, monkeypatch):
    client, service = _client_with_service(tmp_path)
    workspace = _workspace_root()
    scheduled = []

    def fake_create_task(coro):
        scheduled.append(coro)
        coro.close()
        return object()

    monkeypatch.setattr("agent_session.async_subagents.asyncio.create_task", fake_create_task)
    try:
        session_response = client.post(
            "/agent-sessions",
            json={"title": "async tasks", "agent_id": "build", "project_path": str(workspace)},
        )
        session_id = session_response.json()["id"]

        started = client.post(
            f"/agent-sessions/{session_id}/async-tasks",
            json={"subagent_type": "explore", "description": "inspect code"},
        )
        assert started.status_code == 200
        task = started.json()
        assert task["status"] == "running"
        assert scheduled

        listed = client.get(f"/agent-sessions/{session_id}/async-tasks")
        assert listed.status_code == 200
        assert listed.json()["tasks"][0]["task_id"] == task["task_id"]

        fetched = client.get(f"/agent-sessions/{session_id}/async-tasks/{task['task_id']}")
        assert fetched.status_code == 200
        assert fetched.json()["task_id"] == task["task_id"]

        restarted = client.patch(
            f"/agent-sessions/{session_id}/async-tasks/{task['task_id']}",
            json={"description": "inspect again"},
        )
        assert restarted.status_code == 200
        assert restarted.json()["task_id"] == task["task_id"]
        assert restarted.json()["restart_count"] == 1

        cancelled = client.post(f"/agent-sessions/{session_id}/async-tasks/{task['task_id']}/cancel", json={})
        assert cancelled.status_code == 200
        assert cancelled.json()["status"] == "cancelled"

        other = service.repository.create_session({"agent_id": "build", "title": "other", "project_path": str(workspace)})
        missing = client.get(f"/agent-sessions/{other['id']}/async-tasks/{task['task_id']}")
        assert missing.status_code == 404
    finally:
        app.dependency_overrides.clear()


def test_agent_artifact_original_reads_matched_session_artifact(tmp_path: Path):
    client, service = _client_with_service(tmp_path)
    project = tmp_path / "project"
    target = project / "src" / "app.py"
    target.parent.mkdir(parents=True)
    target.write_text("print('hello')\n", encoding="utf-8")
    try:
        session = service.repository.create_session(
            {
                "agent_id": "build",
                "title": "artifact original",
                "project_path": str(project),
                "status": "completed",
                "metadata": {},
            }
        )
        service.repository.add_part(
            session["id"],
            "diff",
            status="completed",
            title="src/app.py",
            content="changed",
            payload={"changed_files": ["/workspace/src/app.py"], "diff": "--- old\n+++ new\n"},
        )
        artifact = service.get_overview(session["id"]).artifacts[0]

        response = client.get(f"/agent-sessions/{session['id']}/artifacts/{quote(artifact.id, safe='')}/original")

        assert response.status_code == 200
        assert response.json() == "print('hello')\n"

        missing = client.get(f"/agent-sessions/{session['id']}/artifacts/part_missing:src/app.py:1/original")
        assert missing.status_code == 404
    finally:
        app.dependency_overrides.clear()


def test_agent_artifact_original_blocks_workspace_path_escape(tmp_path: Path):
    client, service = _client_with_service(tmp_path)
    project = tmp_path / "project"
    project.mkdir()
    try:
        session = service.repository.create_session(
            {
                "agent_id": "build",
                "title": "artifact escape",
                "project_path": str(project),
                "status": "completed",
                "metadata": {},
            }
        )
        service.repository.add_part(
            session["id"],
            "diff",
            status="completed",
            title="escape",
            content="changed",
            payload={"changed_files": ["/workspace/../secret.txt"], "diff": "--- old\n+++ new\n"},
        )
        artifact = service.get_overview(session["id"]).artifacts[0]

        response = client.get(f"/agent-sessions/{session['id']}/artifacts/{quote(artifact.id, safe='')}/original")

        assert response.status_code == 403
    finally:
        app.dependency_overrides.clear()


def test_agent_session_workspace_read_model_returns_deepagents_view(tmp_path: Path):
    client, service = _client_with_service(tmp_path)
    workspace = _workspace_root()
    try:
        session_response = client.post(
            "/agent-sessions",
            json={"title": "workspace view", "agent_id": "build", "project_path": str(workspace)},
        )
        session_id = session_response.json()["id"]
        diff_part = service.repository.add_part(
            session_id,
            "diff",
            status="pending",
            title="修改文件",
            content="准备修改",
            payload={
                "changed_files": ["/workspace/app.py"],
                "file_changes": [
                    {
                        "path": "/workspace/app.py",
                        "status": "modified",
                        "summary": "更新入口",
                        "diff": "@@ patch",
                    }
                ],
            },
        )
        service.repository.add_part(
            session_id,
            "command",
            status="completed",
            title="验证命令",
            content="ok",
            payload={"command": ["npm", "run", "typecheck"], "exit_code": 0, "stdout": "x" * 1400},
        )
        service.repository.add_part(
            session_id,
            "tool_call",
            status="completed",
            title="read_file",
            content="读取文件",
            payload={"tool": "read_file", "args": {"file_path": "/workspace/app.py"}},
        )
        service.repository.add_part(
            session_id,
            "tool_result",
            status="completed",
            title="read_file result",
            content="文件内容",
            payload={"tool": "read_file", "stdout": "print('hello')"},
        )
        service.repository.add_part(
            session_id,
            "permission",
            status="approved",
            title="edit_file",
            content="已批准",
            payload={"action": {"name": "edit_file", "args": {"file_path": "/workspace/app.py"}}},
        )
        service.repository.add_part(
            session_id,
            "summary",
            status="completed",
            title="总结",
            content="执行完成",
            payload={},
        )
        service.repository.add_part(
            session_id,
            "error",
            status="failed",
            title="错误",
            content="工具失败",
            payload={"error": "boom"},
        )
        service.repository.add_event(session_id, "status", "running", {"part_id": diff_part["id"]})
        child = service.repository.create_session(
            {
                "agent_id": "explore",
                "title": "child",
                "project_path": str(workspace),
                "status": "waiting_permission",
                "metadata": {"ui_state": {"pending_permission": {"part_id": "part_permission", "actions": []}}},
            }
        )
        service.repository.create_subtask(
            {
                "parent_session_id": session_id,
                "child_session_id": child["id"],
                "agent_name": "explore",
                "status": "running",
                "input_json": {"description": "inspect code"},
                "result_json": {"summary": "关键发现：入口在 /workspace/app.py。结论：结构清晰。"},
            }
        )
        service.repository.create_subtask(
            {
                "parent_session_id": session_id,
                "child_session_id": child["id"],
                "agent_name": "review",
                "status": "completed",
                "input_json": {"description": "review code"},
                "result_json": {"summary": "有条件通过。风险列表：缺少回归测试。验证建议：运行 npm test。"},
            }
        )

        response = client.get(f"/agent-sessions/{session_id}/workspace")

        assert response.status_code == 200
        body = response.json()
        assert body["session"]["id"] == session_id
        assert body["timeline"]
        assert body["async_tasks"]["metrics"]["total"] == 2
        assert body["async_tasks"]["tasks"][0]["status"] == "running"
        assert body["async_tasks"]["tasks"][0]["child_status"] == "waiting_permission"
        assert body["async_tasks"]["tasks"][0]["has_pending_permission"] is True
        assert body["async_tasks"]["tasks"][0]["pending_permission_part_id"] == "part_permission"
        assert body["todos"] == []
        assert body["plan"]["todos"] == []
        assert any(mount["path"] == "/workspace/" for mount in body["vfs_mounts"])
        assert body["runtime"]["workspace_root"] == body["session"]["project_path"]
        assert isinstance(body["skill_sources"], list)
        artifact_types = {artifact["artifact_type"] for artifact in body["artifacts"]}
        assert {"file_change", "command_result", "test_result", "subtask_result", "finding", "risk"}.issubset(artifact_types)
        command_artifact = next(artifact for artifact in body["artifacts"] if artifact["artifact_type"] == "command_result")
        assert command_artifact["type"] == "command_result"
        assert command_artifact["source"]["kind"] == "part"
        assert len(command_artifact["payload"]["stdout"]) < 1300
        assert command_artifact["payload"]["stdout"].endswith("...")
        assert body["changed_files"][0]["path"] == "/workspace/app.py"
        action_types = {action["action_type"] for action in body["next_actions"]}
        assert {"resolve_permission", "review_risks", "inspect_file"}.issubset(action_types)
        assert "restart_failed_task" not in action_types
        assert body["next_actions"][0]["priority"] == "high"
        assert body["recent_events"][0]["event_type"] == "status"
        execution_types = {item["type"] for item in body["execution_timeline"]}
        assert {"command", "tool_call", "tool_result", "permission", "summary", "error"}.issubset(execution_types)
        tool_call = next(item for item in body["execution_timeline"] if item["type"] == "tool_call")
        assert tool_call["source_part_id"]
        assert tool_call["payload_excerpt"]["tool"] == "read_file"
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


def test_agent_session_workspace_normalizes_metadata_todos(tmp_path: Path):
    client, service = _client_with_service(tmp_path)
    try:
        session = service.repository.create_session(
            {
                "agent_id": "build",
                "title": "todo workspace",
                "project_path": str(tmp_path),
                "metadata": {
                    "todos": [
                        {"id": "todo_1", "title": "Read project", "status": "in_progress", "agent": "build"},
                        {"id": "todo_2", "title": "Summarize findings", "status": "done"},
                    ]
                },
            }
        )

        response = client.get(f"/agent-sessions/{session['id']}/workspace")

        assert response.status_code == 200
        body = response.json()
        assert body["plan"]["source"] == "metadata"
        assert [todo["status"] for todo in body["todos"]] == ["in_progress", "completed"]
        assert body["todos"][0]["owner_agent"] == "build"
    finally:
        app.dependency_overrides.clear()


def test_agent_session_skill_sources_can_be_disabled_for_session(tmp_path: Path):
    client, _ = _client_with_service(tmp_path)
    workspace = _workspace_root()
    try:
        registry = client.get("/agents/skills", params={"project_path": str(workspace), "agent_id": "build"})
        assert registry.status_code == 200
        assert any(source["virtual_path"] == "/skills/builtin/" for source in registry.json()["sources"])

        session_response = client.post(
            "/agent-sessions",
            json={
                "title": "skills disabled",
                "agent_id": "build",
                "project_path": str(workspace),
                "enabled_skill_sources": [],
            },
        )
        assert session_response.status_code == 200
        session_id = session_response.json()["id"]

        workspace_response = client.get(f"/agent-sessions/{session_id}/workspace")

        assert workspace_response.status_code == 200
        body = workspace_response.json()
        builtin = next(source for source in body["skill_sources"] if source["virtual_path"] == "/skills/builtin/")
        assert builtin["available"] is True
        assert builtin["enabled"] is False
        assert all(mount["kind"] != "skills" for mount in body["vfs_mounts"])
    finally:
        app.dependency_overrides.clear()


def test_agent_session_memory_files_are_listed_and_read_only_readable(tmp_path: Path):
    reset_memory_service(tmp_path / "memory")
    client, service = _client_with_service(tmp_path)
    try:
        session = service.repository.create_session(
            {
                "agent_id": "build",
                "title": "memory files",
                "project_path": str(tmp_path),
                "metadata": {"user_id": "alice"},
            }
        )
        _override_agent_user("alice")

        files_response = client.get(f"/agent-sessions/{session['id']}/memory-files")
        assert files_response.status_code == 200
        paths = {file["path"] for file in files_response.json()}
        assert "/memories/user.md" in paths
        assert "/memories/project.md" in paths
        assert "/agent-memory/agent.md" in paths

        file_response = client.get(
            f"/agent-sessions/{session['id']}/memory-file",
            params={"path": "/memories/user.md"},
        )

        assert file_response.status_code == 200
        body = file_response.json()
        assert body["path"] == "/memories/user.md"
        assert "# User Memory" in body["content"]

        escape_response = client.get(
            f"/agent-sessions/{session['id']}/memory-file",
            params={"path": "/memories/../agent.md"},
        )
        assert escape_response.status_code == 404

        non_markdown_response = client.get(
            f"/agent-sessions/{session['id']}/memory-file",
            params={"path": "/memories/user.txt"},
        )
        assert non_markdown_response.status_code == 404
    finally:
        app.dependency_overrides.clear()
        reset_memory_service()
