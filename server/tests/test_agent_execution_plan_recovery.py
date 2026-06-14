from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from fastapi import BackgroundTasks

from agent_session.execution_plan_events import apply_execution_event
from agent_session.models import AgentExecutionPlanRecoverRequest, AgentPromptRequest, AgentSessionCreate
from agent_session.repository import AgentSessionRepository
from agent_session.service import AgentSessionService


def _service(tmp_path: Path) -> AgentSessionService:
    return AgentSessionService(AgentSessionRepository(str(tmp_path / "agents.db")))


def _session_with_plan(service: AgentSessionService, tmp_path: Path) -> str:
    session = service.create_session(AgentSessionCreate(title="recover", project_path=str(Path.cwd())))
    service.start_prompt_background(session.id, AgentPromptRequest(content="ship it"), BackgroundTasks())
    return session.id


def _mark_tool_failed(service: AgentSessionService, session_id: str) -> str:
    session = service.repository.get_session(session_id)
    assert session
    metadata = dict(session.get("metadata") or {})
    metadata = apply_execution_event(
        metadata,
        {
            "id": "event_tool_start",
            "event_type": "tool_call_started",
            "message": "tool",
            "payload": {"part_id": "part_tool", "tool": "execute"},
            "created_at": "2026-01-01T00:00:00+00:00",
        },
    )
    metadata = apply_execution_event(
        metadata,
        {
            "id": "event_failed",
            "event_type": "session_failed",
            "message": "boom",
            "payload": {"error": "boom"},
            "created_at": "2026-01-01T00:00:01+00:00",
        },
    )
    service.repository.update_session(session_id, status="needs_manual_review", metadata=metadata)
    return str(metadata["execution_plan"]["current_node_id"])


def test_recover_missing_node_is_rejected(tmp_path: Path):
    service = _service(tmp_path)
    session_id = _session_with_plan(service, tmp_path)

    with pytest.raises(ValueError, match="node not found"):
        asyncio.run(
            service.recover_execution_node(
                session_id,
                "missing",
                AgentExecutionPlanRecoverRequest(action="retry_node"),
                BackgroundTasks(),
            )
        )


def test_recover_completed_node_is_rejected(tmp_path: Path):
    service = _service(tmp_path)
    session_id = _session_with_plan(service, tmp_path)

    with pytest.raises(ValueError, match="not recoverable"):
        asyncio.run(
            service.recover_execution_node(
                session_id,
                "understand_task",
                AgentExecutionPlanRecoverRequest(action="retry_node"),
                BackgroundTasks(),
            )
        )


def test_retry_node_queues_recovery_prompt_and_keeps_current_node(tmp_path: Path):
    service = _service(tmp_path)
    session_id = _session_with_plan(service, tmp_path)
    node_id = _mark_tool_failed(service, session_id)
    background_tasks = BackgroundTasks()

    response = asyncio.run(
        service.recover_execution_node(
            session_id,
            node_id,
            AgentExecutionPlanRecoverRequest(action="retry_node", instruction="continue carefully"),
            background_tasks,
        )
    )

    assert len(background_tasks.tasks) == 1
    assert response.node_id == node_id
    assert response.action == "retry_node"
    assert response.execution_plan
    assert response.execution_plan.current_node_id == node_id
    node = next(item for item in response.execution_plan.nodes if item["id"] == node_id)
    assert node["status"] == "running"
    assert node["recoverable"] is False
    assert node["recovery_attempts"] == 1
    assert node["output"]["recovery_history"]


def test_recover_with_existing_latch_does_not_queue_duplicate_prompt(tmp_path: Path):
    service = _service(tmp_path)
    session_id = _session_with_plan(service, tmp_path)
    node_id = _mark_tool_failed(service, session_id)
    service._set_recovery_latch(session_id, node_id, "rec_existing", "retry_node")
    background_tasks = BackgroundTasks()

    response = asyncio.run(
        service.recover_execution_node(
            session_id,
            node_id,
            AgentExecutionPlanRecoverRequest(action="retry_node"),
            background_tasks,
        )
    )

    assert len(background_tasks.tasks) == 0
    assert response.node_id == node_id
    assert response.action == "retry_node"


def test_recover_rejects_when_background_task_is_running(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    service = _service(tmp_path)
    session_id = _session_with_plan(service, tmp_path)
    node_id = _mark_tool_failed(service, session_id)
    monkeypatch.setattr(service, "_has_running_prompt_task", lambda _session_id: True)

    with pytest.raises(ValueError, match="running background task"):
        asyncio.run(
            service.recover_execution_node(
                session_id,
                node_id,
                AgentExecutionPlanRecoverRequest(action="retry_node"),
                BackgroundTasks(),
            )
        )


def test_recovery_start_failure_records_manual_review(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    service = _service(tmp_path)
    session_id = _session_with_plan(service, tmp_path)
    node_id = _mark_tool_failed(service, session_id)

    def fail_start(*_args, **_kwargs):
        raise RuntimeError("cannot queue")

    monkeypatch.setattr(service, "_start_recovery_prompt_background", fail_start)

    with pytest.raises(RuntimeError, match="cannot queue"):
        asyncio.run(
            service.recover_execution_node(
                session_id,
                node_id,
                AgentExecutionPlanRecoverRequest(action="retry_node"),
                BackgroundTasks(),
            )
        )

    session = service.repository.get_session(session_id)
    assert session
    assert session["status"] == "needs_manual_review"
    node = next(item for item in session["metadata"]["execution_plan"]["nodes"] if item["id"] == node_id)
    assert node["recovery_error"] == "cannot queue"


def test_workspace_repairs_plan_and_exposes_recovery_timeline(tmp_path: Path):
    service = _service(tmp_path)
    session_id = _session_with_plan(service, tmp_path)
    node_id = _mark_tool_failed(service, session_id)
    session = service.repository.get_session(session_id)
    assert session
    service._event(
        session_id,
        "node_recovery_requested",
        "recover requested",
        {"node_id": node_id, "recovery_id": "rec_workspace", "action": "retry_node", "summary": "recover requested"},
    )
    session = service.repository.get_session(session_id)
    assert session
    metadata = dict(session.get("metadata") or {})
    plan = dict(metadata["execution_plan"])
    plan["current_node_id"] = "missing"
    plan["edges"] = [{"from": "missing", "to": "also_missing", "type": "depends_on"}]
    metadata["execution_plan"] = plan
    service.repository.update_session(session_id, metadata=metadata)

    workspace = service.get_workspace(session_id)

    assert workspace.execution_plan.current_node_id != "missing"
    assert workspace.diagnostics["execution_plan_warnings"]
    assert any(item.type == "recovery" for item in workspace.execution_timeline)


def test_restart_subagent_creates_new_task_linkage(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    service = _service(tmp_path)
    session_id = _session_with_plan(service, tmp_path)
    session = service.repository.get_session(session_id)
    assert session
    metadata = apply_execution_event(
        dict(session.get("metadata") or {}),
        {
            "id": "event_sub_failed",
            "event_type": "async_subtask_failed",
            "message": "child failed",
            "payload": {"task_id": "agt_old", "agent_name": "explore", "summary": "child failed"},
            "created_at": "2026-01-01T00:00:00+00:00",
        },
    )
    service.repository.create_subtask(
        {
            "id": "agt_old",
            "parent_session_id": session_id,
            "agent_name": "explore",
            "status": "failed",
            "input_json": {"description": "inspect repo", "subagent_type": "explore"},
            "result_json": {},
        }
    )
    service.repository.update_session(session_id, status="needs_manual_review", metadata=metadata)
    node_id = str(metadata["execution_plan"]["current_node_id"])
    captured: dict[str, str] = {}

    async def fake_start_task(parent_session_id: str, subagent_type: str, description: str):
        captured.update({"parent": parent_session_id, "agent": subagent_type, "description": description})
        return {"task_id": "agt_new"}

    monkeypatch.setattr(service.async_subagent_service, "start_task", fake_start_task)

    response = asyncio.run(
        service.recover_execution_node(
            session_id,
            node_id,
            AgentExecutionPlanRecoverRequest(action="restart_subagent", instruction="retry with logs"),
            BackgroundTasks(),
        )
    )

    assert response.started_task_id == "agt_new"
    assert captured["agent"] == "explore"
    assert "inspect repo" in captured["description"]
    node = next(item for item in response.execution_plan.nodes if item["id"] == node_id)
    assert node["output"]["previous_task_id"] == "agt_old"
    assert node["output"]["recovery_task_id"] == "agt_new"
    assert node["output"]["recovery_history"][-1]["new_task_id"] == "agt_new"
