from pathlib import Path

from fastapi.testclient import TestClient

from agent_runtime_legacy.models import WorkflowCreate
from agent_runtime_legacy.repository import WorkflowRuntimeRepository
from agent_runtime_legacy.service import AgentRuntimeService
from api.workflows import get_agent_runtime_service
from main import app


client = TestClient(app)


def test_workflow_mutations_are_retired():
    create = client.post(
        "/workflows",
        json={"title": "old", "goal": "old path", "template_id": "software_delivery"},
    )
    run = client.post("/workflows/legacy-id/run")
    approve = client.post("/workflow-steps/legacy-step/approve", json={"approved": True})

    assert create.status_code == 404
    assert run.status_code == 404
    assert approve.status_code == 404


def test_workflow_reads_move_to_agent_session_history(tmp_path: Path):
    repository = WorkflowRuntimeRepository(str(tmp_path / "legacy_history.db"))
    service = AgentRuntimeService(repository=repository)
    workflow = service.create_workflow(WorkflowCreate(title="Legacy", goal="Keep history"))
    app.dependency_overrides[get_agent_runtime_service] = lambda: service
    scoped_client = TestClient(app)

    workflow_read = scoped_client.get(f"/workflows/{workflow.workflow_id}")
    history_read = scoped_client.get(f"/agent-sessions/legacy-workflows/{workflow.workflow_id}")
    app.dependency_overrides.clear()

    assert workflow_read.status_code == 404
    assert history_read.status_code == 200
    data = history_read.json()
    assert data["id"] == workflow.workflow_id
    assert data["source_runtime"] == "workflow_legacy"
    assert data["state"]["runtime_kind"] == "workflow_legacy"

