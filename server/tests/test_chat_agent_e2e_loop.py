from __future__ import annotations

import asyncio
from pathlib import Path

from fastapi.testclient import TestClient

from agent_runtime.actions import WorkflowActionService
from agent_runtime.definitions import RuntimeExecutionContext
from agent_runtime.models import WorkflowCreate
from agent_runtime.repository import WorkflowRuntimeRepository
from agent_runtime.service import AgentRuntimeService
from agent_runtime.tool_loop import AgentToolLoop
from agent_runtime.tools import AgentToolExecutor
from api.workflows import get_agent_runtime_service
from main import app


def _workspace_root() -> Path:
    cwd = Path.cwd().resolve()
    return cwd.parent if cwd.name == "server" else cwd


class E2EToolLoopRunner:
    def __init__(self):
        self.responses = {
            "planner": [
                '{"thought":"完成规划","tool":"finalize","arguments":{"summary":"已完成计划，等待执行。","tasks":["理解目标"],"risks":[],"next_action":"请批准进入实现"}}',
            ],
            "implementer": [
                '{"thought":"先检查项目","tool":"inspect_project","arguments":{}}',
                '{"thought":"识别验证命令","tool":"detect_project_commands","arguments":{}}',
                '{"thought":"读取项目说明","tool":"read_file","arguments":{"path":"AGENTS.md"}}',
                '{"thought":"生成 smoke 补丁","tool":"propose_patch","arguments":{"title":"写入 smoke 文件","payload":{"files":[{"path":"tmp/chat_agent_e2e_smoke.txt","content":"chat agent e2e worked"}]}}}',
                '{"thought":"建议运行语法检查","tool":"propose_command","arguments":{"title":"py compile","payload":{"command":["python","-m","py_compile","server/agent_runtime/tool_loop.py"],"timeout_seconds":120}}}',
                '{"thought":"读取执行结果","tool":"read_execution_result","arguments":{}}',
                '{"thought":"完成实现","tool":"finalize","arguments":{"summary":"已生成并执行 smoke 补丁，验证命令已通过。","tasks":["检查项目","写入 smoke 文件","运行验证"],"changed_files":["tmp/chat_agent_e2e_smoke.txt"],"commands":[["python","-m","py_compile","server/agent_runtime/tool_loop.py"]],"verification":"通过","risks":[],"next_action":"等待审查"}}',
            ],
            "reviewer": [
                '{"thought":"审查通过","tool":"finalize","arguments":{"summary":"审查通过：smoke 补丁和验证结果可交付。","tasks":["审查执行结果"],"risks":[],"next_action":"已完成"}}',
            ],
        }

    async def execute_tool_loop(self, agent_id, context, step_input, *, project, task, repository, action_service, trace_id=None):
        responses = iter(self.responses[agent_id])

        async def model_call(_messages):
            return next(responses)

        loop = AgentToolLoop(repository, AgentToolExecutor(repository, action_service), max_iterations=8)
        response = await loop.run(
            agent_id=agent_id,
            context=context,
            step_input=step_input,
            project=project,
            task=task,
            model_call=model_call,
            trace_id=trace_id,
        )
        return response.output


def make_client(tmp_path: Path) -> tuple[TestClient, AgentRuntimeService]:
    repository = WorkflowRuntimeRepository(str(tmp_path / "chat_agent_e2e.db"))
    service = AgentRuntimeService(repository=repository, runner=E2EToolLoopRunner())
    app.dependency_overrides[get_agent_runtime_service] = lambda: service
    return TestClient(app), service


def create_legacy_run(service: AgentRuntimeService, content: str):
    from chat_agent.repository import ChatAgentRepository

    workflow = service.create_workflow(
        WorkflowCreate(
            title=content[:30],
            goal=content,
            project_path=str(_workspace_root()),
            provider="mock",
            agent_id="build",
        )
    )
    return ChatAgentRepository(service.repository.db_path).create_run(
        chat_session_id=None,
        trigger_message_id=None,
        workflow_id=workflow.workflow_id,
        intent_type="agent_work",
        summary=f"已创建 Agent 工作流：{workflow.title}",
        metadata={"compat_mode": "legacy_workflow"},
    )


def test_chat_agent_e2e_loop_recovers_and_returns_final_summary(tmp_path: Path):
    target = _workspace_root() / "tmp" / "chat_agent_e2e_smoke.txt"
    if target.exists():
        target.unlink()
    client, _service = make_client(tmp_path)
    try:
        created = create_legacy_run(_service, "新增一个 tmp smoke 文件并运行 py_compile")
        planned = client.post(f"/chat-agent/runs/{created['id']}/run").json()
        plan_step = next(step for step in planned["workflow"]["steps"] if step["step_key"] == "plan")

        completed = client.post(f"/chat-agent/steps/{plan_step['step_id']}/approve", json={"approved": True}).json()
        recovered = client.get(f"/chat-agent/runs/{created['id']}").json()

        actions = completed["observability"]["actions"]
        patch_action = next(action for action in actions if action["action_type"] == "patch")
        command_action = next(action for action in actions if action["action_type"] == "command")

        assert completed["status"] == "completed"
        assert "审查通过" in completed["final_summary"]
        assert recovered["final_summary"] == completed["final_summary"]
        assert target.read_text(encoding="utf-8") == "chat agent e2e worked"
        assert patch_action["status"] == "executed"
        assert patch_action["changed_files"] == ["tmp/chat_agent_e2e_smoke.txt"]
        assert command_action["status"] == "executed"
        assert command_action["executions"][-1]["exit_code"] == 0
        assert completed["observability"]["tool_calls"]
        assert all(call.get("trace_id") for call in completed["observability"]["tool_calls"])
    finally:
        app.dependency_overrides.clear()
        if target.exists():
            target.unlink()


def test_tool_loop_plain_final_text_requires_manual_review(tmp_path: Path):
    repository = WorkflowRuntimeRepository(str(tmp_path / "plain_final.db"))
    action_service = WorkflowActionService(repository)
    project = repository.create_project(
        {
            "title": "plain final",
            "goal": "总结结果",
            "template_id": "software_delivery",
            "project_path": str(Path.cwd()),
            "provider": "mock",
            "model": None,
            "approval_mode": "manual",
        }
    )
    task = repository.create_task(project["id"], "implementer", "实现", "实现任务", "running", step_key="implement")

    async def model_call(_messages):
        return "最终结果：已经完成检查，没有需要执行的补丁。"

    response = asyncio.run(
        AgentToolLoop(repository, AgentToolExecutor(repository, action_service), max_iterations=2).run(
            agent_id="implementer",
            context=RuntimeExecutionContext(workflow_id=project["id"], goal=project["goal"], project_path=str(Path.cwd()), provider="mock"),
            step_input={"agent": {"system_prompt": "实现"}, "step": {"step_key": "implement"}},
            project=project,
            task=task,
            model_call=model_call,
        )
    )

    assert response.needs_manual_review is True
    assert "不是可解析的工具 JSON" in response.output.summary
    assert repository.get_project(project["id"])["metadata"]["execution_state"] == "needs_manual_review"
