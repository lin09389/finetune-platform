from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from agent_runtime.service import AgentRuntimeService
from api.workflows import get_agent_runtime_service
from digital_team.models import AgentOutput
from digital_team.repository import DigitalTeamRepository
from main import app


class DummyRuntimeRunner:
    async def execute(self, agent_id, context, step_input):
        if agent_id == "planner":
            return AgentOutput(
                summary="Planner 已拆解任务",
                tasks=[{"title": "新增工作流页面"}],
                risks=["需要人工审批"],
                artifacts=[{"type": "acceptance", "items": ["可查看时间线"]}],
                next_action="请审批计划",
                requires_approval=True,
            )
        if agent_id == "implementer":
            return AgentOutput(
                summary="Implementer 已生成实现建议",
                tasks=[{"title": "新增 /workflows API 和页面"}],
                risks=["需要回归 digital-team"],
                artifacts=[{"type": "implementation_plan", "content": "复用 agent_runtime"}],
                next_action="交给 Reviewer",
                requires_approval=False,
            )
        return AgentOutput(
            summary="通过：工作流可交付",
            risks=[],
            artifacts=[{"acceptance_result": {"approved": True}}],
            next_action="可以交付",
            requires_approval=False,
        )


def make_client(tmp_path: Path) -> TestClient:
    repository = DigitalTeamRepository(str(tmp_path / "workflows.db"))
    service = AgentRuntimeService(repository=repository, runner=DummyRuntimeRunner())
    service._project_context = lambda project_path, goal: "context"
    app.dependency_overrides[get_agent_runtime_service] = lambda: service
    return TestClient(app)


def test_workflow_templates_expose_software_delivery(tmp_path):
    client = make_client(tmp_path)
    response = client.get("/workflows/templates")
    app.dependency_overrides.clear()

    assert response.status_code == 200
    data = response.json()
    assert data[0]["id"] == "software_delivery"
    assert [step["key"] for step in data[0]["steps"]] == ["plan", "implement", "review"]


def test_create_workflow_success(tmp_path):
    client = make_client(tmp_path)
    response = client.post(
        "/workflows",
        json={
            "title": "工作流入口",
            "goal": "新增通用多 Agent 工作流页面",
            "template_id": "software_delivery",
            "provider": "minimax",
            "approval_mode": "manual",
        },
    )
    app.dependency_overrides.clear()

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "draft"
    assert data["template_id"] == "software_delivery"
    assert data["legacy_template_id"] == "software_dev_team"
    assert data["workflow_id"] == data["id"]


def test_run_and_approve_workflow_full_flow(tmp_path):
    client = make_client(tmp_path)
    created = client.post(
        "/workflows",
        json={"title": "工作流入口", "goal": "新增通用多 Agent 工作流页面"},
    ).json()

    planned = client.post(f"/workflows/{created['workflow_id']}/run")
    assert planned.status_code == 200
    workflow = planned.json()
    assert workflow["status"] == "awaiting_approval"
    plan_step = next(step for step in workflow["steps"] if step["step_key"] == "plan")
    assert plan_step["agent_id"] == "planner"
    assert plan_step["legacy_role"] == "ceo"

    approved = client.post(f"/workflow-steps/{plan_step['step_id']}/approve", json={"approved": True})
    assert approved.status_code == 200
    completed = approved.json()
    assert completed["status"] == "completed"
    assert {step["step_key"] for step in completed["steps"]} == {"plan", "implement", "review"}

    timeline = client.get(f"/workflows/{created['workflow_id']}/timeline").json()
    artifacts = client.get(f"/workflows/{created['workflow_id']}/artifacts").json()
    app.dependency_overrides.clear()

    assert len(timeline["events"]) >= 3
    assert len(artifacts["artifacts"]) >= 3
