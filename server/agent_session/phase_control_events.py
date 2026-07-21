from __future__ import annotations

import logging
from typing import Any

from agent_session.goal_plan import goal_planning_enabled_for_session
from agent_session.phase_controller import (
    apply_phase_control_event,
    apply_session_status_gate,
    parse_phase_state,
    persist_phase_state,
)
from agent_session.phase_tool_router import (
    compile_phase_tool_projection,
    persist_phase_tool_projection,
)
from agent_session.runtime_contract import resolve_orchestration_mode
from agent_session.state import ensure_session_state

logger = logging.getLogger(__name__)

PHASE_CONTROL_EVENT_TYPES = frozenset(
    {
        "permission_asked",
        "permission_decided",
        "phase_boundary_complete",
        "phase_verification_failed",
        "phase_verification_passed",
        "steering_queued",
        "session_completed",
        "session_failed",
        "summary_completed",
    }
)


def _event_key(event: dict[str, Any]) -> str:
    return str(event.get("id") or "")


def _map_runtime_event_to_phase_event(event: dict[str, Any]) -> dict[str, Any] | None:
    event_type = str(event.get("event_type") or "")
    payload = dict(event.get("payload") or {}) if isinstance(event.get("payload"), dict) else {}

    if event_type == "permission_asked":
        return {
            "event_type": "waiting_permission" if payload.get("permission_kind") == "permission" else "waiting_approval",
            "id": event.get("id"),
            "message": event.get("message"),
            "payload": payload,
        }
    if event_type == "permission_decided":
        status = str(payload.get("status") or "")
        if status == "approved":
            return {
                "event_type": "prompt_resumed",
                "id": event.get("id"),
                "message": event.get("message"),
                "payload": payload,
            }
        return None
    if event_type == "summary_completed":
        return {
            "event_type": "session_completed",
            "id": event.get("id"),
            "message": event.get("message"),
            "payload": payload,
        }
    if event_type in PHASE_CONTROL_EVENT_TYPES:
        return event
    return None


def _refresh_phase_tool_projection(
    *,
    metadata: dict[str, Any],
    session: dict[str, Any],
    agent_registry: Any,
) -> dict[str, Any]:
    state = parse_phase_state(metadata.get("phase_state"))
    if state is None:
        return metadata
    projection = compile_phase_tool_projection(
        agent_registry=agent_registry,
        agent_id=str(session.get("agent_id") or "build"),
        metadata=metadata,
        session=session,
        phase_state=state,
        orchestration_mode=resolve_orchestration_mode(metadata),
        provider=str(session.get("provider") or metadata.get("provider") or "") or None,
        model=session.get("model") or metadata.get("model"),
    )
    return persist_phase_tool_projection(metadata, projection)


def apply_phase_control_event_to_session(
    repository: Any,
    session_id: str,
    event: dict[str, Any],
    *,
    agent_registry: Any | None = None,
) -> None:
    try:
        session = repository.get_session(session_id)
        if not session:
            return
        session_payload = {**session, "metadata": dict(session.get("metadata") or {})}
        if not goal_planning_enabled_for_session(session_payload):
            return
        event_type = str(event.get("event_type") or "")
        if event_type not in PHASE_CONTROL_EVENT_TYPES and event_type not in {"permission_asked", "permission_decided"}:
            return

        metadata = ensure_session_state(dict(session.get("metadata") or {}))
        if "phase_state" not in metadata:
            return

        event_key = _event_key(event)
        applied = [str(item) for item in metadata.get("phase_applied_event_ids") or [] if str(item)]
        if event_key and event_key in set(applied):
            return

        mapped = _map_runtime_event_to_phase_event(event)
        if mapped is None:
            return

        prior = parse_phase_state(metadata.get("phase_state"))
        if prior is None:
            return
        if prior.terminal:
            if event_key:
                applied.append(event_key)
                metadata["phase_applied_event_ids"] = applied[-200:]
                repository.update_session(session_id, metadata=metadata)
            return

        if event_type == "permission_asked":
            next_state = apply_session_status_gate(
                prior,
                "waiting_permission" if str((event.get("payload") or {}).get("permission_kind")) == "permission" else "waiting_approval",
            )
        else:
            next_state = apply_phase_control_event(prior, mapped)

        if next_state.model_dump() == prior.model_dump():
            return

        metadata = persist_phase_state(metadata, next_state)
        registry = agent_registry
        if registry is not None and next_state.current_phase != prior.current_phase:
            metadata = _refresh_phase_tool_projection(
                metadata=metadata,
                session={**session_payload, "metadata": metadata},
                agent_registry=registry,
            )
        if event_key:
            applied.append(event_key)
            metadata["phase_applied_event_ids"] = applied[-200:]
        repository.update_session(session_id, metadata=metadata)
    except Exception:
        logger.exception("Failed to apply phase control event for session %s", session_id)


__all__ = [
    "PHASE_CONTROL_EVENT_TYPES",
    "apply_phase_control_event_to_session",
]
