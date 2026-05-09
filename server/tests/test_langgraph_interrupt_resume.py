from __future__ import annotations

from copy import deepcopy
from pathlib import Path

from fastapi.testclient import TestClient
from langgraph.types import Command

from agent_runtime.langgraph.nodes import LangGraphWorkflowRuntime
from agent_runtime.repository import WorkflowRuntimeRepository
from agent_runtime.service import AgentRuntimeService
from api.workflows import get_agent_runtime_service
from main import app


class MinimalRuntimeRepository:
    def __init__(self):
        self.project = {
            "id": "wf_1",
            "goal": "finish work",
            "template_id": "tpl_1",
            "provider": "glm",
            "model": "glm-4",
            "status": "awaiting_approval",
            "current_stage": "work_approval",
            "metadata": {},
            "tasks": [],
        }
        self.task = {
            "id": "task_1",
            "workflow_id": "wf_1",
            "step_key": "work",
            "title": "Do work",
            "description": "Work step",
            "status": "awaiting_approval",
            "sort_order": 0,
            "output": None,
        }
        self.project["tasks"] = [self.task]
        self.actions: dict[str, dict] = {}
        self.events: list[dict] = []
        self.artifacts: list[dict] = []

    def get_project(self, workflow_id):
        assert workflow_id == "wf_1"
        return self.project

    def get_task(self, task_id):
        if task_id == self.task["id"]:
            return self.task
        return None

    def update_task(self, task_id, **fields):
        assert task_id == self.task["id"]
        self.task.update(fields)

    def update_project(self, workflow_id, **fields):
        assert workflow_id == "wf_1"
        self.project.update(fields)

    def add_artifact(self, workflow_id, step_id, artifact_type, title, content):
        self.artifacts.append(
            {
                "workflow_id": workflow_id,
                "step_id": step_id,
                "artifact_type": artifact_type,
                "title": title,
                "content": content,
            }
        )

    def add_event(self, workflow_id, step_id, event_type, actor, message, payload=None):
        self.events.append(
            {
                "workflow_id": workflow_id,
                "step_id": step_id,
                "event_type": event_type,
                "actor": actor,
                "message": message,
                "payload": payload or {},
            }
        )

    def get_action_proposal(self, action_id):
        return self.actions.get(action_id)

    def add_action_proposal(self, workflow_id, step_id, action_type, title, description="", payload=None, created_by="agent"):
        action = {
            "id": "action_1",
            "workflow_id": workflow_id,
            "step_id": step_id,
            "action_type": action_type,
            "title": title,
            "description": description,
            "payload": payload or {},
            "status": "pending_approval",
        }
        self.actions[action["id"]] = action
        return action


class ApprovingActionService:
    def __init__(self, repository: MinimalRuntimeRepository):
        self.repository = repository
        self.executed_ids: list[str] = []

    def execute(self, action_id: str):
        self.executed_ids.append(action_id)
        action = self.repository.actions[action_id]
        action["status"] = "executed"
        return action


def test_action_gate_executes_approved_action_after_interrupt_resume(monkeypatch):
    repository = MinimalRuntimeRepository()
    action = repository.add_action_proposal("wf_1", "task_1", "patch", "Patch file", payload={"files": [{"path": "tmp.txt", "content": "ok"}]})
    action_service = ApprovingActionService(repository)
    runtime = LangGraphWorkflowRuntime(repository=repository, runner=object(), context_builder=None, memory_curator=None, action_service=action_service)

    def fake_interrupt(payload):
        repository.actions[payload["action_id"]]["status"] = "approved"
        return {"decision": "approved"}

    monkeypatch.setattr("agent_runtime.langgraph.nodes.interrupt", fake_interrupt)

    state = {
        "workflow_id": "wf_1",
        "current_task_id": "task_1",
        "pending_actions": [deepcopy(action)],
        "metadata": {
            "workflow_steps": [
                {
                    "step_key": "work",
                    "agent_id": "worker",
                    "title": "Do work",
                    "description": "Work step",
                    "requires_approval": False,
                    "sort_order": 0,
                }
            ]
        },
    }

    update = __import__("asyncio").run(runtime.action_gate_node(state))

    assert update["pending_actions"] == []
    assert action_service.executed_ids == ["action_1"]
    event_types = [event["event_type"] for event in repository.events]
    assert "approval_needed" in event_types
    assert "approval_granted" in event_types
    assert "action_executed" in event_types


def test_review_gate_completes_step_after_interrupt_resume(monkeypatch):
    repository = MinimalRuntimeRepository()
    runtime = LangGraphWorkflowRuntime(repository=repository, runner=object(), context_builder=None, memory_curator=None, action_service=object())
    monkeypatch.setattr("agent_runtime.langgraph.nodes.interrupt", lambda payload: {"approved": True, "comment": "ship it"})

    state = {
        "workflow_id": "wf_1",
        "current_task_id": "task_1",
        "step_index": 0,
        "final_output": {
            "summary": "done",
            "tasks": [],
            "risks": [],
            "artifacts": [],
            "next_action": "",
            "requires_approval": True,
        },
        "metadata": {
            "workflow_steps": [
                {
                    "step_key": "work",
                    "agent_id": "worker",
                    "title": "Do work",
                    "description": "Work step",
                    "artifact_type": "result",
                    "artifact_title": "Work output",
                    "requires_approval": True,
                    "sort_order": 0,
                }
            ]
        },
    }

    update = __import__("asyncio").run(runtime.review_gate_node(state))

    assert update["execution_state"] == "completed"
    assert repository.task["status"] == "completed"
    assert repository.project["status"] == "completed"
    assert repository.artifacts[0]["artifact_type"] == "result"


class CapturingGraph:
    def __init__(self, repository: WorkflowRuntimeRepository, update_callback):
        self.repository = repository
        self.update_callback = update_callback
        self.calls: list[Command] = []

    async def ainvoke(self, value, config=None):
        self.calls.append(value)
        assert isinstance(value, Command)
        self.update_callback(value, config)
        return {"ok": True}


def _make_service_client(tmp_path: Path, graph: CapturingGraph | None = None) -> tuple[TestClient, AgentRuntimeService]:
    repository = WorkflowRuntimeRepository(str(tmp_path / "langgraph_interrupt_resume.db"))
    service = AgentRuntimeService(repository=repository)
    if graph is not None:
        service._langgraph = graph
    app.dependency_overrides[get_agent_runtime_service] = lambda: service
    return TestClient(app), service


def _template_payload(*, requires_approval: bool) -> dict:
    return {
        "id": "resume_tpl",
        "name": "Resume Flow",
        "description": "resume",
        "default_provider": "minimax",
        "agents": [
            {
                "agent_id": "worker",
                "name": "Worker",
                "description": "does work",
                "system_prompt": "输出 JSON。",
            }
        ],
        "steps": [
            {
                "step_key": "work",
                "agent_id": "worker",
                "title": "执行",
                "description": "执行工作",
                "artifact_type": "result",
                "requires_approval": requires_approval,
                "sort_order": 0,
            }
        ],
    }


def test_step_approve_endpoint_uses_command_resume(tmp_path):
    holder: dict[str, Command] = {}
    client, service = _make_service_client(tmp_path)

    def update_callback(value, config):
        holder["command"] = value
        task = service.repository.get_task(holder["task_id"])
        service.repository.update_task(task["id"], status="completed", completed_at="now")
        service.repository.update_project(holder["workflow_id"], status="completed", current_stage="completed")

    graph = CapturingGraph(service.repository, update_callback)
    service._langgraph = graph
    client.post("/workflows/templates", json=_template_payload(requires_approval=True))
    workflow = client.post(
        "/workflows",
        json={"title": "resume", "goal": "resume", "template_id": "resume_tpl", "project_path": str(Path.cwd())},
    ).json()
    task = service.repository.create_task(
        project_id=workflow["workflow_id"],
        role="worker",
        title="执行",
        description="执行工作",
        status="awaiting_approval",
        input_data={"goal": "resume"},
        requires_approval=True,
        step_key="work",
        sort_order=0,
    )
    service.repository.update_project(workflow["workflow_id"], status="awaiting_approval", current_stage="work_approval")
    holder["workflow_id"] = workflow["workflow_id"]
    holder["task_id"] = task["id"]

    response = client.post(f"/workflow-steps/{task['id']}/approve", json={"approved": True, "comment": "looks good"})
    app.dependency_overrides.clear()

    assert response.status_code == 200
    assert graph.calls
    assert holder["command"].resume == {"interrupt_kind": "step_approval", "approved": True, "comment": "looks good"}
    body = response.json()
    assert body["workflow_id"] == workflow["workflow_id"]
    assert isinstance(body["steps"], list)


def test_action_approve_endpoint_uses_command_resume(tmp_path):
    holder: dict[str, Command] = {}
    client, service = _make_service_client(tmp_path)

    def update_callback(value, config):
        holder["command"] = value

    graph = CapturingGraph(service.repository, update_callback)
    service._langgraph = graph
    client.post("/workflows/templates", json=_template_payload(requires_approval=False))
    workflow = client.post(
        "/workflows",
        json={"title": "actions", "goal": "approve action", "template_id": "resume_tpl", "project_path": str(Path.cwd())},
    ).json()
    task = service.repository.create_task(
        project_id=workflow["workflow_id"],
        role="worker",
        title="执行",
        description="执行工作",
        status="running",
        input_data={"goal": "approve action"},
        requires_approval=False,
        step_key="work",
        sort_order=0,
    )
    action = service.repository.add_action_proposal(
        workflow["workflow_id"],
        task["id"],
        "patch",
        "Patch file",
        payload={"files": [{"path": "tmp.txt", "content": "ok"}]},
    )

    response = client.post(f"/workflow-actions/{action['id']}/approve")
    app.dependency_overrides.clear()

    assert response.status_code == 200
    assert graph.calls
    assert holder["command"].resume == {
        "interrupt_kind": "action_approval",
        "action_id": action["id"],
        "decision": "approved",
    }
    body = response.json()
    assert body["id"] == action["id"]
    assert body["status"] == "approved"
