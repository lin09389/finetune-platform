from __future__ import annotations

from typing import Any

from agent_session.state import clear_runtime_latches, ensure_session_state, record_fallback_summary


def ensure_failed_metadata(session: dict[str, Any], message: str) -> dict[str, Any]:
    metadata = ensure_session_state(dict(session.get("metadata") or {}))
    metadata = record_fallback_summary(metadata)
    metadata = clear_runtime_latches(metadata)
    metadata["latest_error"] = message
    metadata["model_protocol_status"] = "needs_manual_review"
    state = dict(metadata.get("state") or {})
    state["latest_error"] = message
    metadata["state"] = state
    return metadata
