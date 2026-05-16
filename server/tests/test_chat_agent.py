from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from agent_session.repository import AgentSessionRepository
from agent_session.service import AgentSessionService
from agent_runtime.repository import WorkflowRuntimeRepository
from agent_runtime.service import AgentRuntimeService
from api.agent_sessions import get_agent_session_service
from api.workflows import get_agent_runtime_service
from main import app


async def chat_agent_model_call(_messages):
    return '{"tool":"finalize","arguments":{"summary":"完成 Agent 会话"}}'


def make_client(tmp_path: Path) -> TestClient:
    db_path = str(tmp_path / "chat_agent.db")
    runtime_repository = WorkflowRuntimeRepository(db_path)
    runtime_service = AgentRuntimeService(repository=runtime_repository)
    session_repository = AgentSessionRepository(db_path)
    session_service = AgentSessionService(repository=session_repository, model_call=chat_agent_model_call)
    app.dependency_overrides[get_agent_runtime_service] = lambda: runtime_service
    app.dependency_overrides[get_agent_session_service] = lambda: session_service
    return TestClient(app)


def test_plain_question_stays_chat_mode(tmp_path):
    client = make_client(tmp_path)
    response = client.post(
        "/chat-agent/runs",
        json={"chat_session_id": "chat_1", "message_id": "msg_1", "content": "什么是 LoRA？"},
    )
    app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.headers["X-Agent-Entrypoint"] == "agent-session"
    data = response.json()
    assert data["mode"] == "chat"
    assert not data["workflow_id"]
    assert not data["agent_session_id"]


def test_agent_intent_creates_agent_session_and_run(tmp_path):
    client = make_client(tmp_path)
    response = client.post(
        "/chat-agent/runs",
        json={
            "chat_session_id": "chat_1",
            "message_id": "msg_1",
            "content": "给当前项目新增一个 smoke patch 并跑 typecheck",
            "agent_id": "build",
            "project_path": str(Path.cwd()),
        },
    )
    app.dependency_overrides.clear()

    assert response.status_code == 200
    data = response.json()
    assert data["mode"] == "agent"
    assert data["agent_session_id"]
    assert not data["workflow_id"]
    assert data["active_agent_id"] == "build"
    assert data["agent_session"]["title"].startswith("给当前项目")
    assert data["details_url"] == f"/chat?agentSession={data['agent_session_id']}"


def test_intent_endpoint_keeps_plain_help_request_in_chat_mode(tmp_path):
    client = make_client(tmp_path)
    response = client.post(
        "/chat-agent/intent",
        json={
            "content": "帮我解释一下 LoRA 和 QLoRA 的区别",
            "agent_id": "build",
            "template_id": "software_delivery",
            "routing_mode": "auto",
        },
    )
    app.dependency_overrides.clear()

    assert response.status_code == 200
    data = response.json()
    assert data["mode"] == "chat"


def test_intent_endpoint_supports_workflow_mode_response(tmp_path):
    client = make_client(tmp_path)
    response = client.post(
        "/chat-agent/intent",
        json={
            "content": "请给我设计一个多阶段 workflow，包含 stage、node 和审批流",
            "agent_id": "build",
            "template_id": "software_delivery",
            "routing_mode": "auto",
        },
    )
    app.dependency_overrides.clear()

    assert response.status_code == 200
    data = response.json()
    assert data["mode"] == "workflow"


def test_run_streams_agent_session_events_from_chat_agent(tmp_path):
    client = make_client(tmp_path)
    run = client.post(
        "/chat-agent/runs",
        json={"content": "给当前项目生成一个最终总结", "project_path": str(Path.cwd())},
    ).json()

    run_response = client.post(f"/chat-agent/runs/{run['id']}/run").json()
    assert "完成 Agent 会话" in run_response["summary"]
    assert run_response["agent_session_id"] == run["agent_session_id"]
    assert run_response["agent_parts"]
    with client.stream("GET", f"/chat-agent/runs/{run['id']}/events/stream") as response:
        body = next(response.iter_text())
    app.dependency_overrides.clear()

    assert response.status_code == 200
    assert "chat_agent_event" in body
    assert "summary_completed" in body
