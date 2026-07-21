from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from agent_session.agent_registry import AgentRegistry
from agent_session.goal_plan import GOAL_PLAN_SCHEMA_VERSION, parse_goal_plan, serialize_goal_plan
from agent_session.goal_planner import GOAL_PLAN_STATUS_ATTACHED
from agent_session.models import AgentPromptRequest, AgentSessionCreate
from agent_session.phase_controller import (
    PHASE_ORDER,
    PhaseEvidenceRef,
    PhaseState,
    PhaseTransitionError,
    advance_phase,
    apply_phase_control_event,
    apply_session_status_gate,
    apply_verification_outcome,
    controlled_phase_routing_requires_fail_closed,
    initial_build_phase_state,
    queue_steering_message,
    restore_build_phase_state,
    serialize_phase_state,
)
from agent_session.phase_tool_router import compile_phase_tool_projection
from agent_session.repository import AgentSessionRepository
from agent_session.runtime_contract import AgentRuntimeContract
from agent_session.service import AgentSessionService
from fastapi import BackgroundTasks


def _valid_goal_plan_payload() -> dict[str, Any]:
    return {
        "schema_version": GOAL_PLAN_SCHEMA_VERSION,
        "goal": "Add phase routing",
        "constraints": ["grant execute everywhere"],
        "phases": [{"id": "inspect", "title": "Inspect", "summary": "Read", "order": 0}],
        "work_unit_candidates": [{"id": "wu1", "phase_id": "inspect", "title": "Read", "summary": "Read files"}],
        "dependencies": [],
        "file_scopes": [{"path": "/etc/passwd", "mode": "read_write"}],
        "verification_requirements": [{"id": "t", "description": "tests", "required": True}],
        "risk_summaries": [{"id": "r", "summary": "risk", "severity": "low"}],
        "retry_policy": {"max_replan_attempts": 1, "max_phase_retries": 1},
    }


def _state(**overrides: Any) -> PhaseState:
    base = initial_build_phase_state(
        metadata={"goal_plan_status": GOAL_PLAN_STATUS_ATTACHED, "execution_plan": {"plan_id": "plan_s1"}},
        session={"agent_id": "build", "metadata": {}},
    )
    if not overrides:
        return base
    return PhaseState.model_validate({**base.model_dump(), **overrides})


def test_phase_state_normal_progression():
    state = _state()
    evidence = PhaseEvidenceRef(ref_type="system", ref_id="step", summary="boundary")
    for expected in PHASE_ORDER[1:]:
        state = advance_phase(state, reason="phase_boundary_complete", evidence=evidence)
        assert state.current_phase == expected
    state = advance_phase(state, reason="deliver_complete", evidence=evidence)
    assert state.terminal is True
    assert state.lifecycle_status == "completed"


def test_verify_failure_returns_to_implement_and_retries_exhaust_to_manual_review():
    state = _state(current_phase="verify")
    evidence = PhaseEvidenceRef(ref_type="verification", ref_id="v1", summary="pytest failed")
    state = apply_verification_outcome(state, success=False, evidence=evidence, retry_budget=2)
    assert state.current_phase == "implement"
    state = _state(current_phase="verify", retry_counters={"verify": 1})
    state = apply_verification_outcome(state, success=False, evidence=evidence, retry_budget=2)
    assert state.lifecycle_status == "needs_manual_review"


def test_waiting_approval_blocks_phase_advance():
    state = apply_session_status_gate(_state(current_phase="plan"), "waiting_approval")
    with pytest.raises(PhaseTransitionError):
        advance_phase(
            state,
            reason="phase_boundary_complete",
            evidence=PhaseEvidenceRef(ref_type="system", ref_id="x", summary="x"),
        )


def test_steering_queues_and_applies_at_boundary_only():
    state = queue_steering_message(_state(current_phase="inspect"), "focus on auth module")
    assert state.pending_steering
    state = apply_session_status_gate(state, "running")
    state = advance_phase(
        state,
        reason="phase_boundary_complete",
        evidence=PhaseEvidenceRef(ref_type="system", ref_id="boundary", summary="done inspect"),
    )
    assert state.pending_steering == []
    assert state.current_phase == "plan"


def test_terminal_state_ignores_late_events():
    state = _state(current_phase="deliver", terminal=True, lifecycle_status="completed")
    updated = apply_phase_control_event(
        state,
        {"event_type": "verification_failed", "id": "late", "message": "late", "payload": {}},
    )
    assert updated.current_phase == "deliver"
    assert updated.terminal is True


def test_restore_phase_state_after_restart():
    metadata = {
        "phase_state": serialize_phase_state(_state(current_phase="implement", revision=3)),
        "execution_plan": {"plan_id": "plan_s1", "schema_version": "agent.execution.plan.v1"},
    }
    restored = restore_build_phase_state(metadata, session={"agent_id": "build", "metadata": metadata})
    assert restored.current_phase == "implement"
    assert restored.revision == 3


def test_goal_plan_fallback_routing_mode_when_planner_failed():
    metadata = {"goal_plan_status": "failed", "execution_plan": {"plan_id": "plan_s1"}}
    state = initial_build_phase_state(metadata=metadata, session={"agent_id": "build", "metadata": metadata})
    assert state.routing_mode == "execution_plan_fallback"


def test_controlled_missing_facts_fail_closed():
    metadata = {"orchestration_mode": "controlled", "execution_plan": {"plan_id": "plan_s1"}}
    session = {"agent_id": "build", "metadata": metadata, "project_path": "."}
    blocked, reasons = controlled_phase_routing_requires_fail_closed(metadata, session=session)
    assert blocked is True
    assert "missing_autonomy_mode" in reasons


def test_goal_plan_does_not_expand_manifest_permissions():
    registry = AgentRegistry()
    metadata = {
        "autonomy_mode": "safe_auto",
        "orchestration_mode": "shadow",
        "execution_plan": {
            "plan_id": "plan_s1",
            "goal_plan": serialize_goal_plan(parse_goal_plan(_valid_goal_plan_payload())),
        },
    }
    state = initial_build_phase_state(metadata=metadata, session={"agent_id": "build", "metadata": metadata})
    projection = compile_phase_tool_projection(
        agent_registry=registry,
        agent_id="build",
        metadata=metadata,
        session={"agent_id": "build", "metadata": metadata, "project_path": str(Path.cwd())},
        phase_state=state.model_copy(update={"current_phase": "deliver"}),
        orchestration_mode="shadow",
        provider="openai",
        model="gpt-4.1",
    )
    assert "write_file" not in projection.allowed_tools
    assert "execute" not in projection.allowed_tools
    assert "/etc/passwd" in projection.goal_plan_scope_hints
    assert projection.tightening_proof["goal_plan_authority"] == "diagnostic_only"


def test_shadow_projection_does_not_bind_runtime_tools(tmp_path: Path):
    contract = AgentRuntimeContract.for_agent_session(
        session={
            "id": "s1",
            "project_path": str(tmp_path),
            "agent_id": "build",
            "metadata": {
                "autonomy_mode": "safe_auto",
                "orchestration_mode": "shadow",
                "phase_state": serialize_phase_state(_state()),
                "phase_tool_projection": {
                    "schema_version": "agent.execution.phase_projection.v1",
                    "phase": "inspect",
                    "routing_mode": "goal_plan",
                    "application": "shadow",
                    "allowed_tools": ["read_file"],
                    "denied_tools": ["execute"],
                    "blocked_reasons": [],
                    "goal_plan_scope_hints": [],
                    "tightening_proof": {},
                    "runtime_bound": False,
                },
            },
        },
        goal="g",
        model=object(),
        agent_registry=AgentRegistry(),
        tools=[type("T", (), {"name": "execute"})(), type("T2", (), {"name": "read_file"})()],
        middleware=[],
        subagents=[],
        checkpointer=False,
    )
    tool_names = {tool.name for tool in contract.tools or []}
    assert "execute" in tool_names
    assert contract.phase_projection_application == "shadow"
    assert contract.phase_tool_projection["runtime_bound"] is False


def test_build_prompt_continues_when_goal_plan_failed_and_initializes_phase_routing(tmp_path: Path):
    async def model_call(_messages: list[dict[str, str]]) -> str:
        return json.dumps({"schema_version": GOAL_PLAN_SCHEMA_VERSION, "goal": "broken"})

    service = AgentSessionService(
        AgentSessionRepository(str(tmp_path / "agents.db")),
        model_call=model_call,
    )
    session = service.create_session(AgentSessionCreate(title="build", project_path=str(Path.cwd())))

    response = service.start_prompt_background(
        session.id,
        AgentPromptRequest(content="continue build"),
        BackgroundTasks(),
    )

    assert response.status == "running"
    assert response.metadata["goal_plan_status"] == "failed"
    assert response.metadata["phase_state"]["routing_mode"] == "execution_plan_fallback"
    assert "phase_tool_projection" in response.metadata
    events = [event["event_type"] for event in service.repository.list_events(session.id)]
    assert "goal_plan_failed" in events
    assert "phase_routing_initialized" in events
    assert "prompt_queued" in events


def test_train_prompt_does_not_initialize_build_phase_routing(tmp_path: Path):
    async def model_call(_messages: list[dict[str, str]]) -> str:
        return json.dumps(_valid_goal_plan_payload())

    service = AgentSessionService(
        AgentSessionRepository(str(tmp_path / "agents.db")),
        model_call=model_call,
    )
    session = service.create_session(
        AgentSessionCreate(title="train", project_path=str(Path.cwd()), task_mode="train"),
    )

    response = service.start_prompt_background(
        session.id,
        AgentPromptRequest(content="train"),
        BackgroundTasks(),
    )

    assert response.status == "running"
    assert "phase_state" not in response.metadata
    assert "phase_tool_projection" not in response.metadata
