from __future__ import annotations

from datetime import datetime
from typing import Any

from .execution_plan import sync_execution_plan_status
from .state import clear_runtime_latches, ensure_session_state, set_phase
from .status import TERMINAL_SESSION_STATUSES

TERMINAL_STATUSES = TERMINAL_SESSION_STATUSES


class AgentSessionStateMachine:
    """Centralizes AgentSession status, phase, metadata, and latch transitions."""

    def __init__(self, repository: Any):
        self.repository = repository

    def update_metadata(self, session_id: str, mutator: Any) -> dict[str, Any]:
        session = self._require_session(session_id)
        metadata = ensure_session_state(dict(session.get("metadata") or {}))
        metadata = mutator(metadata) or metadata
        return self.repository.update_session(session_id, metadata=metadata)

    def mark_running(self, session_id: str, *, metadata: dict[str, Any] | None = None, **updates: Any) -> dict[str, Any]:
        session = self._require_session(session_id)
        next_metadata = ensure_session_state(dict(metadata if metadata is not None else session.get("metadata") or {}))
        next_metadata = set_phase(next_metadata, "running")
        # 重新开始执行时清除中断标志，否则 prompt() 会因 interrupt_requested=True 静默返回。
        next_metadata["interrupt_requested"] = False
        next_metadata["interrupt_recorded"] = False
        next_metadata = sync_execution_plan_status(next_metadata, "running")
        return self.repository.update_session(session_id, status="running", metadata=next_metadata, **updates)

    def mark_waiting_approval(
        self,
        session_id: str,
        *,
        metadata: dict[str, Any] | None = None,
        pending_interrupt: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        session = self._require_session(session_id)
        next_metadata = ensure_session_state(dict(metadata if metadata is not None else session.get("metadata") or {}))
        next_metadata = set_phase(next_metadata, "waiting_approval")
        if pending_interrupt is not None:
            next_metadata["pending_deepagents_interrupt"] = pending_interrupt
        next_metadata = sync_execution_plan_status(next_metadata, "waiting_approval")
        return self.repository.update_session(session_id, status="waiting_approval", metadata=next_metadata)

    def mark_completed(self, session_id: str, *, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        session = self._require_session(session_id)
        next_metadata = ensure_session_state(dict(metadata if metadata is not None else session.get("metadata") or {}))
        next_metadata = set_phase(next_metadata, "completed")
        next_metadata = clear_runtime_latches(next_metadata)
        next_metadata["last_prompt_completed_at"] = datetime.now().isoformat()
        next_metadata = sync_execution_plan_status(next_metadata, "completed")
        return self.repository.update_session(session_id, status="completed", metadata=next_metadata)

    def mark_failed(
        self,
        session_id: str,
        *,
        metadata: dict[str, Any] | None = None,
        status: str = "failed",
        error: str | None = None,
        clear_latches: bool = False,
    ) -> dict[str, Any]:
        if status not in {"failed", "needs_manual_review"}:
            raise ValueError(f"Unsupported failure status: {status}")
        session = self._require_session(session_id)
        next_metadata = ensure_session_state(dict(metadata if metadata is not None else session.get("metadata") or {}))
        next_metadata = set_phase(next_metadata, status)
        if clear_latches:
            next_metadata = clear_runtime_latches(next_metadata)
        if error:
            state = dict(next_metadata.get("state") or {})
            state["latest_error"] = error
            next_metadata["latest_error"] = error
            next_metadata["state"] = state
        next_metadata = sync_execution_plan_status(next_metadata, status, error=error)
        return self.repository.update_session(session_id, status=status, metadata=next_metadata)

    def mark_interrupted(
        self,
        session_id: str,
        *,
        metadata: dict[str, Any] | None = None,
        reason: str | None = None,
    ) -> dict[str, Any]:
        session = self._require_session(session_id)
        next_metadata = ensure_session_state(dict(metadata if metadata is not None else session.get("metadata") or {}))
        next_metadata = set_phase(next_metadata, "interrupted")
        next_metadata["interrupt_requested"] = True
        next_metadata["interrupt_recorded"] = True
        next_metadata["interrupted_at"] = datetime.now().isoformat()
        next_metadata = clear_runtime_latches(next_metadata)
        if reason:
            state = dict(next_metadata.get("state") or {})
            state["latest_error"] = reason
            next_metadata["latest_error"] = reason
            next_metadata["state"] = state
        next_metadata = sync_execution_plan_status(next_metadata, "interrupted", error=reason)
        return self.repository.update_session(session_id, status="interrupted", metadata=next_metadata)

    def clear_active_prompt(self, session_id: str, prompt_id: str) -> dict[str, Any] | None:
        session = self.repository.get_session(session_id)
        if not session:
            return None
        metadata = ensure_session_state(dict(session.get("metadata") or {}))
        if metadata.get("active_prompt_id") != prompt_id:
            return session
        metadata["last_prompt_completed_at"] = datetime.now().isoformat()
        metadata["active_prompt_id"] = None
        return self.repository.update_session(session_id, metadata=metadata)

    def _require_session(self, session_id: str) -> dict[str, Any]:
        session = self.repository.get_session(session_id)
        if not session:
            raise ValueError("Agent session not found")
        return session


__all__ = ["AgentSessionStateMachine", "TERMINAL_STATUSES"]
