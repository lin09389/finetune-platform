from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from agent_runtime.repository import WorkflowRuntimeRepository
from agent_runtime.service import AgentRuntimeService
from api.workflows import get_agent_runtime_service
from digital_team.models import AgentOutput
from main import app


class ChatAgentRunner:
    async def execute(self, agent_id, context, step_input):
        return AgentOutput(
            summary="完成 Agent 步骤",
            tasks=[],
            risks=[],
            artifacts=[
                {
                    "type": "patch",
                    "title": "写入 smoke 文件",
                    "payload": {"files": [{"path": "tmp_chat_agent_smoke.txt", "content": "chat agent worked"}]},
                }
            ],
            next_action="等待用户审批动作",
            requires_approval=False,
        )


def make_client(tmp_path: Path) -> TestClient:
    repository = WorkflowRuntimeRepository(str(tmp_path / "chat_agent.db"))
    service = AgentRuntimeService(repository=repository, runner=ChatAgentRunner())
    app.dependency_overrides[get_agent_runtime_service] = lambda: service
    return TestClient(app)


def test_plain_question_stays_chat_mode(tmp_path):
    client = make_client(tmp_path)
    response = client.post(
        "/chat-agent/runs",
        json={"chat_session_id": "chat_1", "message_id": "msg_1", "content": "什么是 LoRA？"},
    )
    app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.headers["X-Agent-Compat-Mode"] == "legacy-workflow"
    data = response.json()
    assert data["mode"] == "chat"
    assert not data["workflow_id"]


def test_agent_intent_creates_workflow_and_run(tmp_path):
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
    assert data["workflow_id"]
    assert data["active_agent_id"] == "build"
    assert data["workflow"]["goal"].startswith("给当前项目")
    assert data["details_url"] == f"/workflows?workflow={data['workflow_id']}"


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


def test_run_streams_events_and_action_can_execute_from_chat_agent(tmp_path):
    target = Path.cwd() / "tmp_chat_agent_smoke.txt"
    if target.exists():
        target.unlink()
    client = make_client(tmp_path)
    run = client.post(
        "/chat-agent/runs",
        json={"content": "给当前项目新增一个 smoke patch", "project_path": str(Path.cwd())},
    ).json()

    run_response = client.post(f"/chat-agent/runs/{run['id']}/run").json()
    assert "完成 Agent 步骤" in run_response["summary"]
    actions = run_response["observability"]["actions"]
    patch_action = actions[0]
    blocked = client.post(f"/chat-agent/actions/{patch_action['id']}/execute")
    client.post(f"/chat-agent/actions/{patch_action['id']}/approve")
    executed = client.post(f"/chat-agent/actions/{patch_action['id']}/execute").json()
    with client.stream("GET", f"/chat-agent/runs/{run['id']}/events/stream") as response:
        body = next(response.iter_text())
    app.dependency_overrides.clear()

    try:
        assert blocked.status_code == 400
        assert executed["status"] == "executed"
        assert target.read_text(encoding="utf-8") == "chat agent worked"
        assert response.status_code == 200
        assert "chat_agent_event" in body
        assert "action_proposed" in body
    finally:
        if target.exists():
            target.unlink()
