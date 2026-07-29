from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

RuntimeKind = Literal["agent_session"]
CanonicalRunStatus = Literal[
    "idle",
    "running",
    "blocked",
    "completed",
    "failed",
    "interrupted",
]


class AgentRunStateSnapshot(BaseModel):
    runtime_kind: RuntimeKind
    status: CanonicalRunStatus
    phase: str
    current_stage: str | None = None
    current_node: str | None = None
    active_agent_id: str | None = None
    blocked_state: dict[str, Any] | None = None
    recoverable: bool = False
    terminal: bool = False
    latest_error: str | None = None
    raw_status: str | None = None
    raw_phase: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


def agent_session_state_snapshot(session: dict[str, Any]) -> AgentRunStateSnapshot:
    metadata = dict(session.get("metadata") or {})
    nested_state = dict(metadata.get("state") or {})
    raw_status = str(session.get("status") or "idle")
    raw_phase = str(nested_state.get("current_phase") or metadata.get("current_phase") or raw_status)
    blocked_state = metadata.get("blocked_state") if isinstance(metadata.get("blocked_state"), dict) else None
    status = _canonical_session_status(raw_status, raw_phase)
    return AgentRunStateSnapshot(
        runtime_kind="agent_session",
        status=status,
        phase=raw_phase,
        current_stage=str(nested_state.get("stage") or metadata.get("stage") or "") or None,
        current_node=str(nested_state.get("node") or metadata.get("node") or "") or None,
        active_agent_id=session.get("agent_id"),
        blocked_state=blocked_state,
        recoverable=status in {"running", "blocked"},
        terminal=status in {"completed", "failed", "interrupted"},
        latest_error=_latest_error({**metadata, **nested_state}, blocked_state),
        raw_status=raw_status,
        raw_phase=raw_phase,
        metadata=metadata,
    )


def _canonical_session_status(raw_status: str, raw_phase: str) -> CanonicalRunStatus:
    if raw_status == "completed":
        return "completed"
    if raw_status == "failed":
        return "failed"
    if raw_status == "interrupted":
        return "interrupted"
    if raw_status in {"waiting_approval", "waiting_permission", "needs_manual_review"} or raw_phase in {"waiting_approval", "waiting_permission", "needs_manual_review"}:
        return "blocked"
    if raw_status == "idle":
        return "idle"
    return "running"


def _latest_error(metadata: dict[str, Any], blocked_state: dict[str, Any] | None) -> str | None:
    if blocked_state:
        reason = str(blocked_state.get("message") or blocked_state.get("reason") or "").strip()
        if reason:
            return reason
    state_message = str(metadata.get("execution_state_message") or metadata.get("latest_error") or "").strip()
    return state_message or None
