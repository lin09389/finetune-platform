from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from agent_session.goal_plan import goal_planning_enabled_for_session
from agent_session.goal_planner import (
    GOAL_PLAN_STATUS_ATTACHED,
    GOAL_PLAN_STATUS_FAILED,
    GOAL_PLAN_STATUS_SKIPPED,
)

PHASE_STATE_SCHEMA_VERSION = "agent.execution.phase.v1"

PhaseId = Literal["inspect", "plan", "implement", "verify", "review", "deliver"]
PhaseRoutingMode = Literal[
    "legacy",
    "goal_plan",
    "execution_plan_fallback",
    "shadow",
    "controlled",
]
PhaseLifecycleStatus = Literal[
    "active",
    "waiting_approval",
    "waiting_permission",
    "needs_manual_review",
    "completed",
    "failed",
]

PHASE_ORDER: tuple[PhaseId, ...] = ("inspect", "plan", "implement", "verify", "review", "deliver")
DEFAULT_VERIFY_RETRY_BUDGET = 2

NEXT_PHASE: dict[PhaseId, PhaseId | None] = {
    "inspect": "plan",
    "plan": "implement",
    "implement": "verify",
    "verify": "review",
    "review": "deliver",
    "deliver": None,
}


class PhaseEvidenceRef(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    ref_type: Literal[
        "execution_plan",
        "goal_plan",
        "session_event",
        "verification",
        "user_action",
        "system",
    ]
    ref_id: str = Field(min_length=1)
    summary: str = Field(min_length=1)


class PhaseState(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    schema_version: Literal["agent.execution.phase.v1"]
    current_phase: PhaseId
    routing_mode: PhaseRoutingMode
    lifecycle_status: PhaseLifecycleStatus = "active"
    transition_reason: str = Field(min_length=1)
    evidence_refs: list[PhaseEvidenceRef]
    retry_counters: dict[str, int] = Field(default_factory=dict)
    pending_steering: list[str] = Field(default_factory=list)
    next_visible_action: str = Field(min_length=1)
    revision: int = Field(ge=0, default=0)
    terminal: bool = False
    fail_closed: bool = False
    fail_closed_reasons: list[str] = Field(default_factory=list)

    @field_validator("retry_counters")
    @classmethod
    def _non_negative_retries(cls, value: dict[str, int]) -> dict[str, int]:
        cleaned: dict[str, int] = {}
        for key, count in value.items():
            if int(count) < 0:
                raise ValueError(f"retry counter {key} cannot be negative")
            cleaned[str(key)] = int(count)
        return cleaned


class PhaseTransitionError(ValueError):
    """Raised when a phase transition violates deterministic rules."""


def _goal_plan_routing_mode(metadata: dict[str, Any]) -> PhaseRoutingMode:
    goal_status = str(metadata.get("goal_plan_status") or "")
    if goal_status == GOAL_PLAN_STATUS_ATTACHED:
        return "goal_plan"
    if goal_status in {GOAL_PLAN_STATUS_FAILED, GOAL_PLAN_STATUS_SKIPPED}:
        return "execution_plan_fallback"
    execution_plan = metadata.get("execution_plan")
    if isinstance(execution_plan, dict) and isinstance(execution_plan.get("goal_plan"), dict):
        return "goal_plan"
    return "execution_plan_fallback"


def resolve_phase_routing_mode(metadata: dict[str, Any]) -> PhaseRoutingMode:
    orchestration = str(metadata.get("orchestration_mode") or "").strip().lower()
    if orchestration == "controlled":
        return "controlled"
    if orchestration == "shadow":
        return "shadow"
    if str(metadata.get("phase_routing_mode") or "").strip().lower() == "controlled":
        return "controlled"
    base = _goal_plan_routing_mode(metadata)
    if base == "execution_plan_fallback":
        return base
    return base


def phase_routing_enabled_for_session(session: dict[str, Any]) -> bool:
    return goal_planning_enabled_for_session(session)


def initial_build_phase_state(
    *,
    metadata: dict[str, Any],
    session: dict[str, Any],
    reason: str = "build_prompt_started",
) -> PhaseState:
    if not phase_routing_enabled_for_session(session):
        return PhaseState(
            schema_version=PHASE_STATE_SCHEMA_VERSION,
            current_phase="inspect",
            routing_mode="legacy",
            transition_reason="phase routing disabled for non-build session",
            evidence_refs=[
                PhaseEvidenceRef(ref_type="system", ref_id="phase_routing", summary="Train/Hybrid keeps legacy runtime")
            ],
            next_visible_action="Continue with existing runtime behavior.",
            revision=0,
        )

    routing_mode = resolve_phase_routing_mode(metadata)
    evidence = [
        PhaseEvidenceRef(
            ref_type="execution_plan",
            ref_id=str((metadata.get("execution_plan") or {}).get("plan_id") or "execution_plan"),
            summary="Execution plan is the durable orchestration fact source.",
        )
    ]
    goal_plan = (metadata.get("execution_plan") or {}).get("goal_plan")
    if isinstance(goal_plan, dict):
        evidence.append(
            PhaseEvidenceRef(
                ref_type="goal_plan",
                ref_id=str(goal_plan.get("schema_version") or "goal_plan"),
                summary="Goal plan informs phase diagnostics only.",
            )
        )
    elif str(metadata.get("goal_plan_status") or "") == GOAL_PLAN_STATUS_FAILED:
        evidence.append(
            PhaseEvidenceRef(
                ref_type="system",
                ref_id="goal_plan_failed",
                summary="Goal plan unavailable; execution-plan fallback remains active.",
            )
        )

    return PhaseState(
        schema_version=PHASE_STATE_SCHEMA_VERSION,
        current_phase="inspect",
        routing_mode=routing_mode,
        transition_reason=reason,
        evidence_refs=evidence,
        retry_counters={"verify": 0},
        next_visible_action="Inspect the workspace and constraints before planning changes.",
        revision=0,
    )


def serialize_phase_state(state: PhaseState) -> dict[str, Any]:
    return state.model_dump(mode="json")


def parse_phase_state(raw: Any) -> PhaseState | None:
    if not isinstance(raw, dict):
        return None
    if raw.get("schema_version") != PHASE_STATE_SCHEMA_VERSION:
        return None
    try:
        return PhaseState.model_validate(raw)
    except Exception:
        return None


def restore_build_phase_state(metadata: dict[str, Any], *, session: dict[str, Any]) -> PhaseState:
    restored = parse_phase_state(metadata.get("phase_state"))
    if restored is not None:
        return restored
    return initial_build_phase_state(metadata=metadata, session=session)


def persist_phase_state(metadata: dict[str, Any], state: PhaseState) -> dict[str, Any]:
    updated = dict(metadata)
    updated["phase_state"] = serialize_phase_state(state)
    return updated


def _bump(state: PhaseState, **changes: Any) -> PhaseState:
    payload = state.model_dump()
    payload.update(changes)
    payload["revision"] = int(state.revision) + 1
    return PhaseState.model_validate(payload)


def apply_session_status_gate(state: PhaseState, session_status: str) -> PhaseState:
    if state.terminal:
        return state
    status = str(session_status or "")
    if status == "waiting_approval":
        return _bump(
            state,
            lifecycle_status="waiting_approval",
            transition_reason="approval_pending",
            next_visible_action="Wait for approval before advancing phases.",
        )
    if status == "waiting_permission":
        return _bump(
            state,
            lifecycle_status="waiting_permission",
            transition_reason="permission_pending",
            next_visible_action="Wait for permission before advancing phases.",
        )
    if status in {"running", "verifying", "repairing"} and state.lifecycle_status in {
        "waiting_approval",
        "waiting_permission",
    }:
        return _bump(
            state,
            lifecycle_status="active",
            transition_reason="approval_resumed",
            next_visible_action=f"Continue phase {state.current_phase}.",
        )
    return state


def queue_steering_message(state: PhaseState, message: str) -> PhaseState:
    if state.terminal:
        return state
    cleaned = str(message or "").strip()
    if not cleaned:
        return state
    pending = list(state.pending_steering)
    pending.append(cleaned)
    return _bump(
        state,
        pending_steering=pending,
        transition_reason="steering_queued",
        next_visible_action="Steering queued; it will apply at the next safe phase boundary.",
    )


def consume_steering_at_boundary(state: PhaseState) -> PhaseState:
    if not state.pending_steering:
        return state
    return _bump(
        state,
        pending_steering=[],
        transition_reason="steering_applied_at_boundary",
        next_visible_action=f"Continue phase {state.current_phase} with queued steering applied.",
    )


def advance_phase(
    state: PhaseState,
    *,
    reason: str,
    evidence: PhaseEvidenceRef,
    event_revision: int | None = None,
) -> PhaseState:
    if state.terminal:
        return state
    if state.lifecycle_status in {"waiting_approval", "waiting_permission"}:
        raise PhaseTransitionError("cannot advance phase while approval or permission is pending")
    if event_revision is not None and event_revision < state.revision:
        return state
    next_phase = NEXT_PHASE[state.current_phase]
    if next_phase is None:
        return mark_terminal(state, status="completed", reason="deliver_complete", evidence=evidence)
    refs = list(state.evidence_refs)
    refs.append(evidence)
    updated = consume_steering_at_boundary(state)
    return _bump(
        updated,
        current_phase=next_phase,
        transition_reason=reason,
        evidence_refs=refs,
        next_visible_action=f"Enter {next_phase} phase.",
        lifecycle_status="active",
    )


def apply_verification_outcome(
    state: PhaseState,
    *,
    success: bool,
    evidence: PhaseEvidenceRef,
    retry_budget: int = DEFAULT_VERIFY_RETRY_BUDGET,
) -> PhaseState:
    if state.terminal or state.current_phase != "verify":
        return state
    if state.lifecycle_status in {"waiting_approval", "waiting_permission"}:
        return state
    if success:
        return advance_phase(state, reason="verification_passed", evidence=evidence)
    counters = dict(state.retry_counters)
    attempt = int(counters.get("verify", 0)) + 1
    counters["verify"] = attempt
    refs = list(state.evidence_refs)
    refs.append(evidence)
    if attempt >= retry_budget:
        return _bump(
            state,
            retry_counters=counters,
            lifecycle_status="needs_manual_review",
            transition_reason="verification_retry_exhausted",
            evidence_refs=refs,
            next_visible_action="Verification retries exhausted; manual review required.",
        )
    return _bump(
        state,
        current_phase="implement",
        retry_counters=counters,
        lifecycle_status="active",
        transition_reason="verification_failed",
        evidence_refs=refs,
        next_visible_action="Return to implement and address verification failures.",
    )


def mark_terminal(
    state: PhaseState,
    *,
    status: PhaseLifecycleStatus,
    reason: str,
    evidence: PhaseEvidenceRef,
) -> PhaseState:
    refs = list(state.evidence_refs)
    refs.append(evidence)
    return _bump(
        state,
        terminal=True,
        lifecycle_status=status,
        transition_reason=reason,
        evidence_refs=refs,
        next_visible_action="Session phase routing reached a terminal state.",
    )


def apply_phase_control_event(state: PhaseState, event: dict[str, Any]) -> PhaseState:
    event_type = str(event.get("event_type") or "")
    event_id = str(event.get("id") or "")
    payload = dict(event.get("payload") or {})
    revision_hint = payload.get("phase_revision")
    event_revision = int(revision_hint) if isinstance(revision_hint, int) else None

    evidence = PhaseEvidenceRef(
        ref_type="session_event",
        ref_id=event_id or event_type or "event",
        summary=str(event.get("message") or event_type or "phase event"),
    )

    if event_type == "steering_queued":
        message = str(payload.get("message") or payload.get("content") or "")
        return queue_steering_message(state, message)

    if event_type in {"waiting_approval", "session_waiting_approval"}:
        return apply_session_status_gate(state, "waiting_approval")
    if event_type in {"waiting_permission", "session_waiting_permission"}:
        return apply_session_status_gate(state, "waiting_permission")
    if event_type in {"session_running", "prompt_resumed"}:
        return apply_session_status_gate(state, "running")

    if state.terminal:
        return state

    if event_type in {"verification_failed", "phase_verification_failed"}:
        return apply_verification_outcome(state, success=False, evidence=evidence)
    if event_type in {"verification_passed", "phase_verification_passed"}:
        return apply_verification_outcome(state, success=True, evidence=evidence)
    if event_type == "phase_boundary_complete":
        return advance_phase(state, reason="phase_boundary_complete", evidence=evidence, event_revision=event_revision)
    if event_type in {"session_completed", "build_delivered"}:
        return mark_terminal(state, status="completed", reason=event_type, evidence=evidence)
    if event_type in {"session_failed", "build_failed"}:
        return mark_terminal(state, status="failed", reason=event_type, evidence=evidence)
    return state


def controlled_phase_routing_requires_fail_closed(metadata: dict[str, Any], *, session: dict[str, Any]) -> tuple[bool, list[str]]:
    if resolve_phase_routing_mode(metadata) != "controlled":
        return False, []
    if not phase_routing_enabled_for_session(session):
        return False, []
    reasons: list[str] = []
    if not str(session.get("provider") or metadata.get("provider") or "").strip():
        reasons.append("missing_provider")
    if not str(session.get("model") or metadata.get("model") or "").strip():
        reasons.append("missing_model")
    if not str(dict(metadata).get("autonomy_mode") or "").strip():
        reasons.append("missing_autonomy_mode")
    if not str(session.get("project_path") or "").strip():
        reasons.append("missing_runtime_workspace")
    return bool(reasons), reasons


__all__ = [
    "DEFAULT_VERIFY_RETRY_BUDGET",
    "PHASE_ORDER",
    "PHASE_STATE_SCHEMA_VERSION",
    "PhaseEvidenceRef",
    "PhaseState",
    "PhaseTransitionError",
    "apply_phase_control_event",
    "apply_session_status_gate",
    "apply_verification_outcome",
    "advance_phase",
    "controlled_phase_routing_requires_fail_closed",
    "initial_build_phase_state",
    "parse_phase_state",
    "persist_phase_state",
    "phase_routing_enabled_for_session",
    "queue_steering_message",
    "resolve_phase_routing_mode",
    "restore_build_phase_state",
    "serialize_phase_state",
]
