from __future__ import annotations

from typing import Any


def is_langgraph_resume_enabled(settings_enabled: bool, metadata: dict[str, Any]) -> bool:
    return bool(settings_enabled and metadata.get("runtime") == "langgraph")


def permission_decision(part_id: str, approved: bool) -> dict[str, Any]:
    return {
        "interrupt_kind": "permission_request",
        "part_id": part_id,
        "approved": approved,
        "decisions": [{"type": "approve" if approved else "reject"}],
    }


def permission_decisions(part_id: str, decisions: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "interrupt_kind": "permission_request",
        "part_id": part_id,
        "approved": all(decision.get("type") != "reject" for decision in decisions),
        "decisions": decisions,
    }


def action_approval_decision(part_id: str, approved: bool) -> dict[str, Any]:
    return {
        "interrupt_kind": "action_approval",
        "part_id": part_id,
        "approved": approved,
        "decisions": [{"type": "approve" if approved else "reject"}],
    }


def action_execute_decision(part_id: str) -> dict[str, Any]:
    return {
        "interrupt_kind": "action_approval",
        "part_id": part_id,
        "decision": "executed",
        "decisions": [{"type": "approve"}],
    }
