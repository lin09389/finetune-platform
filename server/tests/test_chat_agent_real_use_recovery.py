from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from agent_runtime.repository import WorkflowRuntimeRepository
from agent_runtime.models import WorkflowCreate
from agent_runtime.service import AgentRuntimeService
from api.workflows import get_agent_runtime_service
from digital_team.models import AgentOutput
from main import app


class RealUseRunner:
    async def execute(self, agent_id, context, step_input):
        return AgentOutput(
            summary="真实验收恢复摘要",
            tasks=[],
            risks=[],
            artifacts=[
                {
                    "type": "patch",
                    "title": "写入真实验收 smoke 文件",
                    "payload": {"files": [{"path": "tmp/chat-agent-real-use.txt", "content": "real-use"}]},
                }
            ],
            next_action="查看恢复状态。",
            requires_approval=False,
        )


def make_client(tmp_path: Path):
    repository = WorkflowRuntimeRepository(str(tmp_path / "chat_agent_real_use.db"))
    service = AgentRuntimeService(repository=repository, runner=RealUseRunner())
    app.dependency_overrides[get_agent_runtime_service] = lambda: service
    return TestClient(app), repository


def clear_overrides():
    app.dependency_overrides.clear()


def create_legacy_run(repository: WorkflowRuntimeRepository, service: AgentRuntimeService, content: str, autonomy_mode: str = "safe_auto"):
    workflow = service.create_workflow(
        WorkflowCreate(
            title=content[:30],
            goal=content,
            project_path=str(Path.cwd()),
            provider="mock",
            agent_id="build",
            autonomy_mode=autonomy_mode,
        )
    )
    from chat_agent.repository import ChatAgentRepository

    return ChatAgentRepository(repository.db_path).create_run(
        chat_session_id=None,
        trigger_message_id=None,
        workflow_id=workflow.workflow_id,
        intent_type="agent_work",
        summary=f"已创建 Agent 工作流：{workflow.title}",
        metadata={"compat_mode": "legacy_workflow"},
    )


def test_get_run_recovers_latest_event_tool_action_and_no_duplicate_auto_execution(tmp_path):
    target = Path.cwd() / "tmp" / "chat-agent-real-use.txt"
    if target.exists():
        target.unlink()
    target.parent.mkdir(exist_ok=True)
    client, repository = make_client(tmp_path)
    service = app.dependency_overrides[get_agent_runtime_service]()
    run = create_legacy_run(repository, service, "新增真实验收 smoke 文件")

    started = client.post(f"/chat-agent/runs/{run['id']}/run").json()
    workflow_id = started["workflow_id"]
    repository.add_tool_call(
        workflow_id,
        None,
        "build",
        "inspect_project",
        arguments={},
        status="completed",
        result_summary="已检查项目结构",
    )
    recovered = client.get(f"/chat-agent/runs/{run['id']}").json()
    action = recovered["latest_action"]
    execution_count = len(action["executions"])
    execute_again = client.post(f"/chat-agent/actions/{action['id']}/execute").json()
    recovered_again = client.get(f"/chat-agent/runs/{run['id']}").json()
    clear_overrides()

    try:
        assert recovered["latest_event"]["event_type"]
        assert recovered["latest_tool_call"]["tool_name"] == "inspect_project"
        assert recovered["latest_action"]["title"] == "写入真实验收 smoke 文件"
        assert recovered["final_summary"] == "真实验收恢复摘要"
        assert recovered["acceptance_report"]["summary"]
        assert target.read_text(encoding="utf-8") == "real-use"
        assert execute_again["status"] == "executed"
        assert len(recovered_again["latest_action"]["executions"]) == execution_count
    finally:
        if target.exists():
            target.unlink()


def test_get_run_explains_awaiting_approval_action(tmp_path):
    client, repository = make_client(tmp_path)
    service = app.dependency_overrides[get_agent_runtime_service]()
    run = create_legacy_run(repository, service, "新增需要确认的 smoke 文件", autonomy_mode="confirm_all")

    recovered = client.post(f"/chat-agent/runs/{run['id']}/run").json()
    clear_overrides()

    assert recovered["latest_action"]["status"] == "pending_approval"
    assert recovered["latest_action"]["title"] == "写入真实验收 smoke 文件"
    assert "写入真实验收 smoke 文件" in recovered["execution_state_message"]


def test_get_run_explains_failed_latest_action(tmp_path):
    client, repository = make_client(tmp_path)
    service = app.dependency_overrides[get_agent_runtime_service]()
    run = create_legacy_run(repository, service, "制造失败动作")
    workflow_id = run["workflow_id"]
    action = repository.add_action_proposal(
        workflow_id=workflow_id,
        step_id=None,
        action_type="command",
        title="失败验证命令",
        description="用于恢复说明测试",
        payload={"command": ["python", "-m", "py_compile", "tmp/not-found.py"], "_failure_summary": "文件不存在"},
    )
    repository.update_action_status(action["id"], "failed")
    repository.update_project(
        workflow_id,
        status="failed",
        metadata={"execution_state": "failed"},
    )

    recovered = client.get(f"/chat-agent/runs/{run['id']}").json()
    clear_overrides()

    assert recovered["latest_action"]["status"] == "failed"
    assert recovered["latest_action"]["failure_summary"] == "文件不存在"
    assert "失败验证命令" in recovered["execution_state_message"]
    assert "文件不存在" in recovered["execution_state_message"]
