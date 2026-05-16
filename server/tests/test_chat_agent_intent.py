from pathlib import Path

from fastapi.testclient import TestClient

from agent_runtime_legacy.repository import WorkflowRuntimeRepository
from agent_runtime_legacy.service import AgentRuntimeService
from api.workflows import get_agent_runtime_service
from chat_agent.intent import ChatAgentIntentClassifier
from digital_team.models import AgentOutput
from main import app


class IntentRunner:
    async def execute(self, agent_id, context, step_input):
        return AgentOutput(summary="ok", next_action="done")


def make_client(tmp_path: Path) -> TestClient:
    repository = WorkflowRuntimeRepository(str(tmp_path / "chat_agent_intent.db"))
    service = AgentRuntimeService(repository=repository, runner=IntentRunner())
    app.dependency_overrides[get_agent_runtime_service] = lambda: service
    return TestClient(app)


def test_intent_plain_question_uses_local_rule(tmp_path, monkeypatch):
    async def fail_cloud(*args, **kwargs):
        raise AssertionError("cloud should not be called")

    monkeypatch.setattr(ChatAgentIntentClassifier, "_cloud_route", fail_cloud)
    client = make_client(tmp_path)
    response = client.post("/chat-agent/intent", json={"content": "什么是 LoRA？"})
    app.dependency_overrides.clear()

    assert response.status_code == 200
    data = response.json()
    assert data["mode"] == "chat"
    assert data["source"] == "local_rule"


def test_intent_agent_goal_uses_local_rule(tmp_path, monkeypatch):
    async def fail_cloud(*args, **kwargs):
        raise AssertionError("cloud should not be called")

    monkeypatch.setattr(ChatAgentIntentClassifier, "_cloud_route", fail_cloud)
    client = make_client(tmp_path)
    response = client.post("/chat-agent/intent", json={"content": "给当前项目新增 smoke 文件并跑 typecheck"})
    app.dependency_overrides.clear()

    assert response.status_code == 200
    data = response.json()
    assert data["mode"] == "agent"
    assert data["source"] == "local_rule"
    assert data["suggested_agent_id"] == "build"


def test_intent_ambiguous_message_uses_cloud(tmp_path, monkeypatch):
    async def fake_cloud(self, content, *, provider, model, agent_id, template_id):
        return self._decision("agent", 0.82, "需要检查项目并给出改动。", "cloud", agent_id, template_id)

    monkeypatch.setattr(ChatAgentIntentClassifier, "_cloud_route", fake_cloud)
    client = make_client(tmp_path)
    response = client.post(
        "/chat-agent/intent",
        json={"content": "把这个体验做顺一点", "provider": "mock", "model": "mock-model"},
    )
    app.dependency_overrides.clear()

    assert response.status_code == 200
    data = response.json()
    assert data["mode"] == "agent"
    assert data["source"] == "cloud"
    assert data["confidence"] == 0.82


def test_intent_cloud_failure_falls_back(tmp_path, monkeypatch):
    async def broken_cloud(*args, **kwargs):
        raise ValueError("bad json")

    monkeypatch.setattr(ChatAgentIntentClassifier, "_cloud_route", broken_cloud)
    client = make_client(tmp_path)
    response = client.post("/chat-agent/intent", json={"content": "把这个体验做顺一点"})
    app.dependency_overrides.clear()

    assert response.status_code == 200
    data = response.json()
    assert data["mode"] == "chat"
    assert data["source"] == "fallback"
    assert "云端意图判断失败" in data["reason"]


def test_intent_manual_modes(tmp_path):
    client = make_client(tmp_path)
    chat = client.post(
        "/chat-agent/intent",
        json={"content": "给当前项目新增 smoke 文件", "routing_mode": "chat"},
    ).json()
    agent = client.post(
        "/chat-agent/intent",
        json={"content": "什么是 LoRA？", "routing_mode": "agent"},
    ).json()
    app.dependency_overrides.clear()

    assert chat["mode"] == "chat"
    assert chat["source"] == "manual"
    assert agent["mode"] == "agent"
    assert agent["source"] == "manual"


def test_chat_agent_run_routes_are_removed(tmp_path):
    client = make_client(tmp_path)
    response = client.post("/chat-agent/runs", json={"content": "legacy"})
    app.dependency_overrides.clear()

    assert response.status_code == 404

