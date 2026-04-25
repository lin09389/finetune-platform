from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from api.digital_team import get_digital_team_service
from digital_team.models import AgentOutput
from digital_team.repository import DigitalTeamRepository
from digital_team.service import DigitalTeamService
from main import app


class DummyRunner:
    async def run_ceo(self, **kwargs):
        return AgentOutput(
            summary="CEO 已拆解任务",
            tasks=[{"title": "实现数字团队页面"}],
            risks=["需要人工审批"],
            artifacts=[{"type": "acceptance", "items": ["可查看时间线"]}],
            next_action="请审批 CEO 计划",
            requires_approval=True,
        )

    async def run_developer(self, **kwargs):
        return AgentOutput(
            summary="程序员已生成实现建议",
            tasks=[{"title": "新增 API 和页面"}],
            risks=["需要测试"],
            artifacts=[
                {"type": "implementation_plan", "content": "新增 digital-team 业务层"},
                {"type": "test_commands", "commands": ["pytest server/tests/test_digital_team.py"]},
            ],
            next_action="交给质检审查",
            requires_approval=False,
        )

    async def run_reviewer(self, **kwargs):
        return AgentOutput(
            summary="通过：方案具备可交付性",
            risks=[],
            artifacts=[{"acceptance_result": {"approved": True}}],
            next_action="可以交付",
            requires_approval=False,
        )


class FailingRunner(DummyRunner):
    async def run_ceo(self, **kwargs):
        raise RuntimeError("cloud unavailable")


def make_client(tmp_path: Path, runner=None) -> TestClient:
    repository = DigitalTeamRepository(str(tmp_path / "digital_team.db"))
    service = DigitalTeamService(repository=repository, agent_runner=runner or DummyRunner())
    service._project_context = lambda project_path, goal: "context"
    app.dependency_overrides[get_digital_team_service] = lambda: service
    return TestClient(app)


def test_create_project_success(tmp_path):
    client = make_client(tmp_path)
    response = client.post(
        "/digital-team/projects",
        json={
            "title": "数字团队 MVP",
            "goal": "新增 AI 软件开发团队",
            "template_id": "software_dev_team",
            "project_path": str(Path.cwd()),
            "provider": "minimax",
            "approval_mode": "manual",
        },
    )
    app.dependency_overrides.clear()

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "draft"
    assert data["template_id"] == "software_dev_team"


def test_unknown_template_returns_400(tmp_path):
    client = make_client(tmp_path)
    response = client.post(
        "/digital-team/projects",
        json={"title": "bad", "goal": "bad", "template_id": "unknown"},
    )
    app.dependency_overrides.clear()

    assert response.status_code == 400


def test_run_and_approve_full_flow(tmp_path):
    client = make_client(tmp_path)
    created = client.post(
        "/digital-team/projects",
        json={"title": "数字团队 MVP", "goal": "新增 AI 软件开发团队"},
    ).json()

    planned = client.post(f"/digital-team/projects/{created['id']}/run")
    assert planned.status_code == 200
    project = planned.json()
    assert project["status"] == "awaiting_approval"
    ceo_task = next(task for task in project["tasks"] if task["role"] == "ceo")
    assert ceo_task["status"] == "awaiting_approval"

    approved = client.post(f"/digital-team/tasks/{ceo_task['id']}/approve", json={"approved": True})
    assert approved.status_code == 200
    completed = approved.json()
    assert completed["status"] == "completed"
    assert {task["role"] for task in completed["tasks"]} == {"ceo", "developer", "reviewer"}

    timeline = client.get(f"/digital-team/projects/{created['id']}/timeline").json()
    artifacts = client.get(f"/digital-team/projects/{created['id']}/artifacts").json()
    app.dependency_overrides.clear()

    assert len(timeline["events"]) >= 3
    assert len(artifacts["artifacts"]) >= 3


def test_cloud_failure_marks_project_failed(tmp_path):
    client = make_client(tmp_path, runner=FailingRunner())
    created = client.post(
        "/digital-team/projects",
        json={"title": "数字团队 MVP", "goal": "新增 AI 软件开发团队"},
    ).json()

    response = client.post(f"/digital-team/projects/{created['id']}/run")
    app.dependency_overrides.clear()

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "failed"
    assert data["tasks"][0]["error"] == "cloud unavailable"

