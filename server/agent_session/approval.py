from __future__ import annotations

from typing import Any


def permission_decisions(part_id: str, decisions: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "interrupt_kind": "permission_request",
        "part_id": part_id,
        "approved": all(decision.get("type") != "reject" for decision in decisions),
        "decisions": decisions,
    }
