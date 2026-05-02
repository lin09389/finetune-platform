from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from agent_runtime.repository import WorkflowRuntimeRepository
from agent_runtime.service import AgentRuntimeService
from api.workflows import get_agent_runtime_service
from digital_team.models import AgentOutput
from main import app


class RecoveryRunner:
    async def execute(self, agent_id, context, step_input):
        return AgentOutput(
            summary="最终恢复摘要",
            tasks=[],
            risks=[],
            artifacts=[
                {
                    "type": "patch",
                    "title": "写入恢复 smoke 文件",
                    "payload": {"files": [{"path": "tmp/chat-agent-recovery-smoke.txt", "content": "recovered"}]},
                }
            ],
            next_action="已完成，可刷新恢复状态。",
            requires_approval=False,
        )


def make_client(tmp_path: Path):
    repository = WorkflowRuntimeRepository(str(tmp_path / "chat_agent_recovery.db"))
    service = AgentRuntimeService(repository=repository, runner=RecoveryRunner())
    app.dependency_overrides[get_agent_runtime_service] = lambda: service
    return TestClient(app), repository


def test_get_run_recovers_observability_actions_and_final_summary(tmp_path):
    target = Path.cwd() / "tmp" / "chat-agent-recovery-smoke.txt"
    if target.exists():
        target.unlink()
    target.parent.mkdir(exist_ok=True)
    client, repository = make_client(tmp_path)
    run = client.post(
        "/chat-agent/runs",
        json={"content": "给当前项目新增一个恢复 smoke 文件", "project_path": str(Path.cwd()), "force_agent": True},
    ).json()

    started = client.post(f"/chat-agent/runs/{run['id']}/run").json()
    workflow_id = started["workflow_id"]
    repository.add_tool_call(
        workflow_id,
        None,
        "build",
        "inspect_project",
        arguments={"path": str(Path.cwd())},
        status="completed",
        result_summary="已检查项目",
    )
    recovered = client.get(f"/chat-agent/runs/{run['id']}").json()
    action = recovered["observability"]["actions"][0]
    execution_count = len(action["executions"])
    executed_again = client.post(f"/chat-agent/actions/{action['id']}/execute").json()
    recovered_again = client.get(f"/chat-agent/runs/{run['id']}").json()
    app.dependency_overrides.clear()

    try:
        assert recovered["status"] == "awaiting_approval"
        assert recovered["final_summary"] == "最终恢复摘要"
        assert recovered["observability"]["tool_calls"][0]["tool_name"] == "inspect_project"
        assert action["status"] == "executed"
        assert action["execution_mode"] == "auto"
        assert action["auto_executed_at"]
        assert target.read_text(encoding="utf-8") == "recovered"
        assert executed_again["status"] == "executed"
        assert len(recovered_again["observability"]["actions"][0]["executions"]) == execution_count
    finally:
        if target.exists():
            target.unlink()


def test_get_run_surfaces_manual_review_reason(tmp_path):
    client, repository = make_client(tmp_path)
    run = client.post(
        "/chat-agent/runs",
        json={"content": "给当前项目做一个需要人工处理的任务", "project_path": str(Path.cwd()), "force_agent": True},
    ).json()
    workflow_id = run["workflow_id"]
    repository.update_project(
        workflow_id,
        status="needs_manual_review",
        metadata={
            "execution_state": "needs_manual_review",
            "blocked_state": {"reason": "检测到重复工具调用"},
        },
    )

    recovered = client.get(f"/chat-agent/runs/{run['id']}").json()
    app.dependency_overrides.clear()

    assert recovered["status"] == "needs_manual_review"
    assert recovered["recoverable"] is True
    assert recovered["execution_state"] == "needs_manual_review"
    assert "检测到重复工具调用" in recovered["execution_state_message"]
    assert recovered["blocked_state"]["reason"] == "检测到重复工具调用"
