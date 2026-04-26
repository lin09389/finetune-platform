from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from agent_runtime.repository import WorkflowRuntimeRepository
from agent_runtime.service import AgentRuntimeService
from api.workflows import get_agent_runtime_service
from digital_team.models import AgentOutput
from main import app


class SequencedRunner:
    def __init__(self, raw: bool = False):
        self.calls: list[str] = []
        self.raw = raw

    async def execute(self, agent_id, context, step_input):
        self.calls.append(agent_id)
        if self.raw:
            return AgentOutput(
                summary="模型输出不是可解析的结构化 JSON，需要人工审查。",
                raw_output="not-json",
                needs_manual_review=True,
                requires_approval=True,
                next_action="请人工审查",
            )
        return AgentOutput(
            summary=f"{agent_id} done",
            tasks=[],
            risks=[],
            artifacts=[{"agent": agent_id}],
            next_action="next",
            requires_approval=True,
        )


def make_client(tmp_path: Path, runner: SequencedRunner | None = None) -> TestClient:
    repository = WorkflowRuntimeRepository(str(tmp_path / "workflow_templates.db"))
    service = AgentRuntimeService(repository=repository, runner=runner or SequencedRunner())
    service._project_context = lambda project_path, goal: "context"
    app.dependency_overrides[get_agent_runtime_service] = lambda: service
    return TestClient(app)


def custom_template_payload(template_id: str = "content_ops"):
    return {
        "id": template_id,
        "name": "内容运营团队",
        "description": "选题、写作、审查",
        "default_provider": "minimax",
        "default_model": "MiniMax-M2.5",
        "agents": [
            {
                "agent_id": "planner",
                "name": "选题策划",
                "description": "拆解内容目标",
                "system_prompt": "你负责把用户目标拆成内容任务。",
            },
            {
                "agent_id": "writer",
                "name": "内容写作",
                "description": "写出内容草稿",
                "system_prompt": "你负责生成内容草稿。",
            },
        ],
        "steps": [
            {
                "step_key": "plan",
                "agent_id": "planner",
                "title": "内容计划",
                "description": "输出选题和结构",
                "artifact_type": "content_plan",
                "requires_approval": True,
                "sort_order": 0,
            },
            {
                "step_key": "write",
                "agent_id": "writer",
                "title": "内容草稿",
                "description": "输出正文草稿",
                "artifact_type": "content_draft",
                "requires_approval": False,
                "sort_order": 1,
            },
        ],
    }


def test_create_custom_template_and_list_it(tmp_path):
    client = make_client(tmp_path)
    response = client.post("/workflows/templates", json=custom_template_payload())
    listed = client.get("/workflows/templates")
    app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["id"] == "content_ops"
    assert "content_ops" in {item["id"] for item in listed.json()}


def test_invalid_template_id_returns_422(tmp_path):
    client = make_client(tmp_path)
    payload = custom_template_payload("Bad ID")
    response = client.post("/workflows/templates", json=payload)
    app.dependency_overrides.clear()

    assert response.status_code == 422


def test_step_referencing_missing_agent_returns_422(tmp_path):
    client = make_client(tmp_path)
    payload = custom_template_payload()
    payload["steps"][0]["agent_id"] = "missing"
    response = client.post("/workflows/templates", json=payload)
    app.dependency_overrides.clear()

    assert response.status_code == 422


def test_builtin_template_cannot_be_deleted(tmp_path):
    client = make_client(tmp_path)
    response = client.delete("/workflows/templates/software_delivery")
    app.dependency_overrides.clear()

    assert response.status_code == 400


def test_custom_template_workflow_runs_in_step_order(tmp_path):
    runner = SequencedRunner()
    client = make_client(tmp_path, runner)
    client.post("/workflows/templates", json=custom_template_payload())
    created = client.post(
        "/workflows",
        json={"title": "内容计划", "goal": "写一篇产品更新", "template_id": "content_ops"},
    ).json()

    planned = client.post(f"/workflows/{created['workflow_id']}/run").json()
    assert planned["status"] == "awaiting_approval"
    plan_step = next(step for step in planned["steps"] if step["step_key"] == "plan")

    completed = client.post(f"/workflow-steps/{plan_step['step_id']}/approve", json={"approved": True}).json()
    app.dependency_overrides.clear()

    assert completed["status"] == "completed"
    assert runner.calls == ["planner", "writer"]
    assert [step["step_key"] for step in completed["steps"]] == ["plan", "write"]


def test_manual_review_output_is_preserved(tmp_path):
    runner = SequencedRunner(raw=True)
    client = make_client(tmp_path, runner)
    created = client.post(
        "/workflows",
        json={"title": "raw", "goal": "触发 raw output", "template_id": "software_delivery"},
    ).json()

    planned = client.post(f"/workflows/{created['workflow_id']}/run").json()
    app.dependency_overrides.clear()

    step = planned["steps"][0]
    assert step["status"] == "needs_manual_review"
    assert step["output"]["raw_output"] == "not-json"
