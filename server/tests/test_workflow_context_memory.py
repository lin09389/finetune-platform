from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from agent_runtime.repository import WorkflowRuntimeRepository
from agent_runtime.service import AgentRuntimeService
from api.workflows import get_agent_runtime_service
from digital_team.models import AgentOutput
from main import app


class RecordingRunner:
    def __init__(self):
        self.context_packs = []

    async def execute(self, agent_id, context, step_input):
        self.context_packs.append(step_input.get("context_pack", {}))
        return AgentOutput(
            summary=f"{agent_id} 已完成",
            tasks=[],
            risks=[],
            artifacts=[{"agent": agent_id}],
            next_action="done",
            requires_approval=False,
        )


def make_client(tmp_path: Path, runner: RecordingRunner | None = None) -> TestClient:
    repository = WorkflowRuntimeRepository(str(tmp_path / "workflow_context.db"))
    service = AgentRuntimeService(repository=repository, runner=runner or RecordingRunner())
    app.dependency_overrides[get_agent_runtime_service] = lambda: service
    return TestClient(app)


def single_step_template():
    return {
        "id": "quick_ops",
        "name": "快速流程",
        "description": "单步完成",
        "default_provider": "minimax",
        "agents": [
            {
                "agent_id": "worker",
                "name": "Worker",
                "description": "执行任务",
                "system_prompt": "你负责完成当前步骤，并严格输出 JSON。",
            }
        ],
        "steps": [
            {
                "step_key": "work",
                "agent_id": "worker",
                "title": "执行",
                "description": "完成任务",
                "artifact_type": "result",
                "requires_approval": False,
                "sort_order": 0,
            }
        ],
    }


def test_create_workflow_creates_default_context_profile(tmp_path):
    client = make_client(tmp_path)
    created = client.post(
        "/workflows",
        json={"title": "上下文", "goal": "我偏好中文回答", "project_path": str(Path.cwd())},
    ).json()

    profile = client.get(f"/workflows/{created['workflow_id']}/context")
    app.dependency_overrides.clear()

    assert profile.status_code == 200
    data = profile.json()
    assert data["include_project_context"] is True
    assert data["include_memory"] is True
    assert data["max_context_chars"] == 6000


def test_update_context_profile_and_snapshot_injected_chat_context(tmp_path):
    runner = RecordingRunner()
    client = make_client(tmp_path, runner)
    session = client.post("/chat/sessions", json={"title": "上下文来源"}).json()
    client.post(
        f"/chat/sessions/{session['id']}/messages",
        json={"role": "user", "content": "请把所有产物都写成中文。"},
    )
    client.post("/workflows/templates", json=single_step_template())
    created = client.post(
        "/workflows",
        json={
            "title": "聊天上下文",
            "goal": "生成方案",
            "template_id": "quick_ops",
            "chat_session_id": session["id"],
            "include_chat_context": True,
        },
    ).json()

    completed = client.post(f"/workflows/{created['workflow_id']}/run").json()
    snapshots = client.get(f"/workflows/{created['workflow_id']}/context/snapshots").json()
    app.dependency_overrides.clear()

    assert completed["status"] == "completed"
    assert "请把所有产物都写成中文" in runner.context_packs[0]["chat"]
    assert snapshots[0]["step_key"] == "work"
    assert "聊天上下文" in snapshots[0]["content"]


def test_completed_workflow_auto_writes_and_reverts_memory(tmp_path):
    client = make_client(tmp_path)
    client.post("/workflows/templates", json=single_step_template())
    created = client.post(
        "/workflows",
        json={"title": "记忆", "goal": "我偏好输出简洁一点", "template_id": "quick_ops"},
    ).json()

    client.post(f"/workflows/{created['workflow_id']}/run")
    memories = client.get(f"/workflows/{created['workflow_id']}/memory").json()
    active = next(item for item in memories if item["status"] == "active")
    reverted = client.post(f"/workflow-memory/{active['id']}/revert").json()
    app.dependency_overrides.clear()

    assert memories
    assert {item["memory_type"] for item in memories} >= {"workflow_retro"}
    assert reverted["status"] == "reverted"
