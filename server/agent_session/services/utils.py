from __future__ import annotations

from typing import Any

from agent_session.state import clear_runtime_latches, ensure_session_state, record_fallback_summary


def ensure_failed_metadata(
    session: dict[str, Any],
    message: str,
    *,
    failure_kind: str = "runtime_error",
    next_action: str = "manual_review",
    recoverable: bool = True,
) -> dict[str, Any]:
    metadata = ensure_session_state(dict(session.get("metadata") or {}))
    metadata = record_fallback_summary(metadata)
    metadata = clear_runtime_latches(metadata)
    metadata["latest_error"] = message
    metadata["model_protocol_status"] = "needs_manual_review"
    metadata["failure_kind"] = failure_kind
    metadata["next_action"] = next_action
    metadata["recoverable"] = recoverable
    state = dict(metadata.get("state") or {})
    state["latest_error"] = message
    state["failure_kind"] = failure_kind
    state["next_action"] = next_action
    metadata["state"] = state
    return metadata
