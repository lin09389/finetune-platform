from __future__ import annotations

import asyncio
from pathlib import Path

from agent_runtime.repository import WorkflowRuntimeRepository
from agent_runtime.service import AgentRuntimeService


def test_approve_permission_request_appends_override_and_emits_event(tmp_path):
    repository = WorkflowRuntimeRepository(str(tmp_path / "permission_replay.db"))
    service = AgentRuntimeService(repository=repository)

    workflow = service.repository.create_project(
        {
            "title": "permission replay",
            "goal": "test",
            "template_id": "software_delivery",
            "project_path": str(Path.cwd()),
            "provider": "minimax",
            "model": None,
            "approval_mode": "manual",
        }
    )
    step = service.repository.create_task(
        workflow["id"],
        "implementer",
        "实现",
        "实现任务",
        "awaiting_approval",
        step_key="implement",
    )
    action = service.repository.add_action_proposal(
        workflow["id"],
        step["id"],
        "permission_request",
        "权限请求",
        payload={
            "permission": "tool.propose_patch",
            "pattern": str(Path.cwd()),
            "tool_name": "propose_patch",
            "tool_arguments": {"title": "x"},
            "agent_id": "implementer",
            "replay_of_call_id": "wftc_x",
        },
    )

    async def fake_retry(project, task, _project_context):
        return project

    service.engine.retry = fake_retry  # type: ignore[assignment]
    approved = asyncio.run(service.approve_action(action["id"]))

    assert approved.action_type == "permission_request"
    updated = service.repository.get_project(workflow["id"]) or {}
    overrides = (updated.get("metadata") or {}).get("permission_overrides") or []
    assert len(overrides) == 1
    assert overrides[0]["tool_name"] == "propose_patch"
    events = service.repository.list_events(workflow["id"])
    assert any(item["event_type"] == "permission_approved" for item in events)
