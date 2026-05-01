from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from agent_runtime.actions import WorkflowActionService
from agent_runtime.repository import WorkflowRuntimeRepository
from agent_runtime.service import AgentRuntimeService
from api.workflows import get_agent_runtime_service
from digital_team.models import AgentOutput
from main import app


class ActionRunner:
    async def execute(self, agent_id, context, step_input):
        return AgentOutput(
            summary="生成动作建议",
            tasks=[],
            risks=[],
            artifacts=[
                {
                    "type": "patch",
                    "title": "写入测试文件",
                    "payload": {"files": [{"path": "tmp_action_output.txt", "content": "hello action"}]},
                },
                {
                    "type": "command",
                    "title": "编译检查",
                    "payload": {"command": ["python", "-m", "py_compile", "server/agent_runtime/actions.py"]},
                },
            ],
            next_action="等待审批动作",
            requires_approval=False,
        )


class FailingRunner:
    async def execute(self, agent_id, context, step_input):
        raise RuntimeError("boom")


def make_client(tmp_path: Path, runner=None) -> TestClient:
    repository = WorkflowRuntimeRepository(str(tmp_path / "workflow_observability.db"))
    service = AgentRuntimeService(repository=repository, runner=runner or ActionRunner())
    app.dependency_overrides[get_agent_runtime_service] = lambda: service
    return TestClient(app)


def single_step_template():
    return {
        "id": "action_ops",
        "name": "动作流程",
        "description": "生成动作",
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
                "description": "生成动作建议",
                "artifact_type": "result",
                "requires_approval": False,
                "sort_order": 0,
            }
        ],
    }


def test_observability_empty_before_run(tmp_path):
    client = make_client(tmp_path)
    client.post("/workflows/templates", json=single_step_template())
    workflow = client.post(
        "/workflows",
        json={"title": "obs", "goal": "观察", "template_id": "action_ops", "project_path": str(Path.cwd())},
    ).json()

    response = client.get(f"/workflows/{workflow['workflow_id']}/observability")
    app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["step_logs"] == []
    assert response.json()["actions"] == []


def test_run_creates_step_logs_and_action_proposals(tmp_path):
    client = make_client(tmp_path)
    client.post("/workflows/templates", json=single_step_template())
    workflow = client.post(
        "/workflows",
        json={"title": "actions", "goal": "生成动作", "template_id": "action_ops", "project_path": str(Path.cwd())},
    ).json()

    client.post(f"/workflows/{workflow['workflow_id']}/run")
    logs = client.get(f"/workflows/{workflow['workflow_id']}/step-logs").json()
    actions = client.get(f"/workflows/{workflow['workflow_id']}/actions").json()
    app.dependency_overrides.clear()

    statuses = {action["action_type"]: action["status"] for action in actions}
    assert {log["status"] for log in logs} >= {"started", "completed"}
    assert {action["action_type"] for action in actions} == {"patch", "command"}
    assert statuses["patch"] == "pending_approval"
    assert statuses["command"] == "executed"


def test_unapproved_action_cannot_execute_and_approved_patch_can_write_inside_workspace(tmp_path):
    target = Path.cwd() / "tmp_action_output.txt"
    if target.exists():
        target.unlink()
    client = make_client(tmp_path)
    client.post("/workflows/templates", json=single_step_template())
    workflow = client.post(
        "/workflows",
        json={"title": "patch", "goal": "写文件", "template_id": "action_ops", "project_path": str(Path.cwd())},
    ).json()
    client.post(f"/workflows/{workflow['workflow_id']}/run")
    actions = client.get(f"/workflows/{workflow['workflow_id']}/actions").json()
    patch_action = next(action for action in actions if action["action_type"] == "patch")

    blocked = client.post(f"/workflow-actions/{patch_action['id']}/execute")
    client.post(f"/workflow-actions/{patch_action['id']}/approve")
    executed = client.post(f"/workflow-actions/{patch_action['id']}/execute").json()
    app.dependency_overrides.clear()

    try:
        assert blocked.status_code == 400
        assert executed["status"] == "executed"
        assert target.read_text(encoding="utf-8") == "hello action"
    finally:
        if target.exists():
            target.unlink()


def test_approved_command_runs_and_non_allowlisted_command_is_rejected(tmp_path):
    client = make_client(tmp_path)
    client.post("/workflows/templates", json=single_step_template())
    workflow = client.post(
        "/workflows",
        json={"title": "command", "goal": "跑检查", "template_id": "action_ops", "project_path": str(Path.cwd())},
    ).json()
    client.post(f"/workflows/{workflow['workflow_id']}/run")
    actions = client.get(f"/workflows/{workflow['workflow_id']}/actions").json()
    command_action = next(action for action in actions if action["action_type"] == "command")

    executed = client.get(f"/workflows/{workflow['workflow_id']}/actions").json()
    command_after_run = next(action for action in executed if action["action_type"] == "command")
    bad_action = client.app.dependency_overrides[get_agent_runtime_service]().repository.add_action_proposal(
        workflow["workflow_id"],
        None,
        "command",
        "bad",
        payload={"command": ["git", "status"]},
    )
    client.post(f"/workflow-actions/{bad_action['id']}/approve")
    rejected = client.post(f"/workflow-actions/{bad_action['id']}/execute")
    app.dependency_overrides.clear()

    assert command_after_run["status"] == "executed"
    assert command_after_run["executions"][-1]["exit_code"] == 0
    assert rejected.status_code == 400


def test_command_root_detects_client_for_npm_when_project_is_workspace_root(tmp_path):
    service = WorkflowActionService(repository=None)
    root = service._command_root({"project_path": str(Path.cwd())}, ["npm", "run", "typecheck"])

    assert root.name == "client"


def test_command_allowlist_accepts_windows_npm_cmd():
    service = WorkflowActionService(repository=None)

    assert service._command_allowed(["npm.cmd", "run", "typecheck"])


def test_observability_contains_actions_logs_and_recent_events_after_execution(tmp_path):
    target = Path.cwd() / "tmp_action_output.txt"
    if target.exists():
        target.unlink()
    client = make_client(tmp_path)
    client.post("/workflows/templates", json=single_step_template())
    workflow = client.post(
        "/workflows",
        json={"title": "e2e", "goal": "端到端打通", "template_id": "action_ops", "project_path": str(Path.cwd())},
    ).json()
    client.post(f"/workflows/{workflow['workflow_id']}/run")
    actions = client.get(f"/workflows/{workflow['workflow_id']}/actions").json()
    patch_action = next(action for action in actions if action["action_type"] == "patch")
    client.post(f"/workflow-actions/{patch_action['id']}/approve")
    client.post(f"/workflow-actions/{patch_action['id']}/execute")

    observability = client.get(f"/workflows/{workflow['workflow_id']}/observability").json()
    timeline = client.get(f"/workflows/{workflow['workflow_id']}/timeline").json()
    app.dependency_overrides.clear()

    try:
        assert observability["step_logs"]
        assert any(action["status"] == "executed" for action in observability["actions"])
        event_types = {event["event_type"] for event in timeline["events"]}
        assert {"action_proposed", "action_approved", "action_executed"} <= event_types
    finally:
        if target.exists():
            target.unlink()


def test_sse_stream_includes_action_events(tmp_path):
    client = make_client(tmp_path)
    client.post("/workflows/templates", json=single_step_template())
    workflow = client.post(
        "/workflows",
        json={"title": "sse", "goal": "事件流", "template_id": "action_ops", "project_path": str(Path.cwd())},
    ).json()
    client.post(f"/workflows/{workflow['workflow_id']}/run")

    with client.stream("GET", f"/workflows/{workflow['workflow_id']}/events/stream") as response:
      body = next(response.iter_text())
    app.dependency_overrides.clear()

    assert response.status_code == 200
    assert "workflow_event" in body
    assert "action_proposed" in body


def test_step_failure_writes_failed_log(tmp_path):
    client = make_client(tmp_path, FailingRunner())
    client.post("/workflows/templates", json=single_step_template())
    workflow = client.post(
        "/workflows",
        json={"title": "fail", "goal": "失败", "template_id": "action_ops", "project_path": str(Path.cwd())},
    ).json()

    client.post(f"/workflows/{workflow['workflow_id']}/run")
    logs = client.get(f"/workflows/{workflow['workflow_id']}/step-logs").json()
    app.dependency_overrides.clear()

    assert any(log["status"] == "failed" and "boom" in (log["error"] or "") for log in logs)
