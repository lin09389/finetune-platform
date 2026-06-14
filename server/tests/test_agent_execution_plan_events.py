from __future__ import annotations

from server.agent_session.execution_context import AgentDefinition
from server.agent_session.execution_plan import build_initial_execution_plan
from server.agent_session.execution_plan_events import apply_execution_event
from server.agent_session.runtime_policy import build_agent_runtime_policy


def _metadata():
    agent = AgentDefinition(id="build", name="Build", mode="primary", tools=["read_file", "edit_file", "execute"])
    policy = build_agent_runtime_policy(
        agent=agent,
        agent_id="build",
        project_path=".",
        metadata={},
        runtime_kind="agent_session",
        thread_id="agent_session:s1:deepagents",
        checkpointer=True,
    )
    return {
        "execution_plan": build_initial_execution_plan(
            session={"id": "s1", "agent_id": "build", "status": "running"},
            policy=policy,
            goal="ship it",
            status="running",
        )
    }


def _event(event_type: str, **payload):
    return {
        "id": f"event_{event_type}_{payload.get('part_id') or payload.get('task_id') or '1'}",
        "event_type": event_type,
        "message": payload.get("summary") or event_type,
        "payload": payload,
        "created_at": "2026-01-01T00:00:00+00:00",
    }


def test_tool_start_creates_running_tool_node_idempotently():
    metadata = _metadata()
    event = _event("tool_call_started", part_id="part_tool", tool="read_file")

    updated = apply_execution_event(metadata, event)
    replayed = apply_execution_event(updated, event)

    nodes = replayed["execution_plan"]["nodes"]
    tool_nodes = [node for node in nodes if node.get("source_part_id") == "part_tool"]
    assert len(tool_nodes) == 1
    assert tool_nodes[0]["status"] == "running"
    assert tool_nodes[0]["tool"] == "read_file"
    assert replayed["execution_plan"]["current_node_id"] == tool_nodes[0]["id"]


def test_tool_completed_records_output_and_restores_primary_node():
    metadata = apply_execution_event(_metadata(), _event("tool_call_started", part_id="part_tool", tool="read_file"))

    updated = apply_execution_event(
        metadata,
        _event(
            "tool_call_completed",
            part_id="part_tool",
            tool="read_file",
            part={"id": "part_tool", "content": "ok"},
        ),
    )

    tool_node = next(node for node in updated["execution_plan"]["nodes"] if node.get("source_part_id") == "part_tool")
    assert tool_node["status"] == "completed"
    assert tool_node["output"]["part_id"] == "part_tool"
    assert updated["execution_plan"]["current_node_id"] == "execute_primary_agent"


def test_permission_block_and_resume_keeps_same_node():
    metadata = apply_execution_event(_metadata(), _event("tool_call_started", part_id="part_tool", tool="edit_file"))
    blocked = apply_execution_event(metadata, _event("permission_asked", part_id="part_perm", tool="edit_file", summary="needs approval"))
    blocked_node_id = blocked["execution_plan"]["current_node_id"]
    node = next(item for item in blocked["execution_plan"]["nodes"] if item["id"] == blocked_node_id)
    assert node["status"] == "blocked"
    assert node["blocked_reason"] == "needs approval"
    assert node["source_part_id"] == "part_tool"
    assert node["source_permission_part_id"] == "part_perm"

    resumed = apply_execution_event(blocked, _event("permission_decided", part_id="part_perm", status="approved"))

    assert resumed["execution_plan"]["current_node_id"] == blocked_node_id
    node = next(item for item in resumed["execution_plan"]["nodes"] if item["id"] == blocked_node_id)
    assert node["status"] == "running"
    assert node["blocked_reason"] is None


def test_summary_completed_finishes_primary_and_summary_nodes():
    updated = apply_execution_event(_metadata(), _event("summary_completed", part_id="part_summary", summary="done"))

    statuses = {node["id"]: node["status"] for node in updated["execution_plan"]["nodes"]}
    assert statuses["execute_primary_agent"] == "completed"
    assert statuses["summarize_result"] == "completed"
    assert updated["execution_plan"]["status"] == "completed"


def test_runtime_failure_lands_on_current_node():
    metadata = apply_execution_event(_metadata(), _event("tool_call_started", part_id="part_tool", tool="execute"))

    updated = apply_execution_event(metadata, _event("session_failed", error="boom"))

    node = next(item for item in updated["execution_plan"]["nodes"] if item["id"] == updated["execution_plan"]["current_node_id"])
    assert node["status"] == "failed"
    assert node["error"] == "boom"


def test_async_subtask_events_bind_and_update_subagent_node():
    metadata = _metadata()
    started = apply_execution_event(
        metadata,
        _event("async_subtask_started", task_id="agt_1", agent_name="explore", async_status="running", summary="started"),
    )
    node = next(item for item in started["execution_plan"]["nodes"] if item.get("source_task_id") == "agt_1")
    assert node["kind"] == "subagent"
    assert node["agent_id"] == "explore"
    assert node["status"] == "running"

    failed = apply_execution_event(
        started,
        _event("async_subtask_failed", task_id="agt_1", agent_name="explore", async_status="failed", summary="child failed"),
    )
    node = next(item for item in failed["execution_plan"]["nodes"] if item.get("source_task_id") == "agt_1")
    assert node["status"] == "failed"
    assert node["error"] == "child failed"
    assert node["retry_policy"]["retry_on"] == ["failed"]
