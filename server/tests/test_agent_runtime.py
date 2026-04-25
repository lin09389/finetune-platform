from __future__ import annotations

from pathlib import Path

from agent_runtime.adapters import step_from_task, workflow_from_project
from agent_runtime.definitions import RuntimeExecutionContext
from agent_runtime.engine import AgentRuntimeEngine
from agent_runtime.runner import AgentRuntimeRunner
from agent_runtime.templates import SOFTWARE_DELIVERY_TEMPLATE, get_workflow_definition
from digital_team.models import AgentOutput
from digital_team.repository import DigitalTeamRepository


class DummyRuntimeRunner:
    async def execute(self, agent_id, context, step_input):
        if agent_id == "planner":
            return AgentOutput(
                summary="CEO 已拆解任务",
                tasks=[{"title": "实现数字团队页面"}],
                risks=["需要人工审批"],
                artifacts=[{"type": "acceptance", "items": ["可查看时间线"]}],
                next_action="请审批 CEO 计划",
                requires_approval=True,
            )
        if agent_id == "implementer":
            return AgentOutput(
                summary="程序员已生成实现建议",
                tasks=[{"title": "新增 API 和页面"}],
                risks=["需要测试"],
                artifacts=[{"type": "implementation_plan", "content": "新增 digital-team 业务层"}],
                next_action="交给质检审查",
                requires_approval=False,
            )
        return AgentOutput(
            summary="不通过：需要补充测试",
            risks=["测试不足"],
            artifacts=[{"acceptance_result": {"approved": False}}],
            next_action="人工确认后重试",
            requires_approval=False,
        )


class FakeProvider:
    def __init__(self):
        self.last_model = None

    def get_default_model(self):
        return "fallback-model"

    async def chat(self, messages, model, api_key, temperature, max_tokens):
        self.last_model = model
        return {"content": '{"summary":"ok","tasks":[],"risks":[],"artifacts":[],"next_action":"done","requires_approval":false}'}


def test_template_definition_contains_expected_steps():
    workflow = get_workflow_definition("software_dev_team")

    assert workflow is not None
    assert [step.key for step in workflow.steps] == ["plan", "implement", "review"]
    assert workflow.step_by_role("ceo").agent_id == "planner"


def test_adapter_maps_legacy_project_and_task_shapes():
    project = {
        "id": "dtp_test",
        "title": "数字团队",
        "goal": "做一个多 agent 流程",
        "template_id": "software_dev_team",
        "status": "draft",
        "current_stage": "draft",
        "provider": "minimax",
        "model": "MiniMax-M2.5",
        "project_path": str(Path.cwd()),
        "metadata": {},
        "tasks": [
            {
                "id": "dtt_test",
                "project_id": "dtp_test",
                "role": "ceo",
                "title": "需求拆解与验收标准",
                "description": "拆任务",
                "status": "awaiting_approval",
                "requires_approval": True,
                "input": {"goal": "x"},
                "output": {"summary": "ok"},
                "error": None,
            }
        ],
    }

    workflow_view = workflow_from_project(project, SOFTWARE_DELIVERY_TEMPLATE)
    step_view = step_from_task(project["tasks"][0], SOFTWARE_DELIVERY_TEMPLATE)

    assert workflow_view.template_id == "software_delivery"
    assert workflow_view.steps[0].step_key == "plan"
    assert step_view.agent_id == "planner"


def test_runtime_engine_advances_from_plan_to_implement_and_review(tmp_path):
    repository = DigitalTeamRepository(str(tmp_path / "agent_runtime.db"))
    engine = AgentRuntimeEngine(repository, DummyRuntimeRunner())
    team = repository.create_team("software_dev_team", "AI 软件开发团队", "desc")
    project = repository.create_project(
        {
            "title": "数字团队 MVP",
            "goal": "新增 AI 软件开发团队",
            "template_id": "software_dev_team",
            "project_path": str(Path.cwd()),
            "provider": "minimax",
            "model": None,
            "approval_mode": "manual",
        },
        team,
    )

    planned = __import__("asyncio").run(engine.start(project, "context"))
    plan_task = next(task for task in planned["tasks"] if task["role"] == "ceo")
    completed = __import__("asyncio").run(engine.approve(planned, plan_task, "context"))

    assert {task["role"] for task in completed["tasks"]} == {"ceo", "developer", "reviewer"}
    assert completed["status"] == "awaiting_approval"
    review_task = next(task for task in completed["tasks"] if task["role"] == "reviewer")
    assert review_task["status"] == "awaiting_approval"


def test_runtime_runner_prefers_saved_default_model(monkeypatch):
    provider = FakeProvider()
    monkeypatch.setattr("agent_runtime.runner.secure_storage.get", lambda key: {
        "api_key": "secret-key",
        "default_model": "saved-model",
        "group_id": "",
        "base_url": "",
    })
    monkeypatch.setattr("agent_runtime.runner.resolve_saved_provider", lambda provider_name, key_data: provider)

    runner = AgentRuntimeRunner()
    context = RuntimeExecutionContext(
        workflow_id="wf_1",
        goal="测试",
        provider="custom-provider",
        model=None,
    )

    __import__("asyncio").run(runner.execute("planner", context, {}))

    assert provider.last_model == "saved-model"
