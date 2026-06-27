from __future__ import annotations

import logging
from copy import deepcopy
from datetime import UTC, datetime
from typing import Any

from .execution_plan import PLAN_SCHEMA_VERSION, repair_execution_plan
from .state import ensure_session_state

logger = logging.getLogger(__name__)


EVENT_TYPES = {
    "tool_call_started",
    "tool_call_completed",
    "tool_call_failed",
    "permission_asked",
    "permission_decided",
    "summary_completed",
    "session_failed",
    "session_interrupted",
    "async_subtask_started",
    "async_subtask_completed",
    "async_subtask_failed",
    "async_subtask_cancelled",
    "async_subtask_running",
    "async_subtask_updated",
    "async_subtask_restarted",
    "node_recovery_requested",
    "node_recovery_started",
    "node_recovery_completed",
    "node_recovery_failed",
    "node_recovery_rejected",
}


def apply_execution_event(metadata: dict[str, Any], event: dict[str, Any]) -> dict[str, Any]:
    metadata = ensure_session_state(dict(metadata or {}))
    plan = metadata.get("execution_plan")
    if not isinstance(plan, dict) or plan.get("schema_version") != PLAN_SCHEMA_VERSION:
        return metadata

    event_type = _event_type(event)
    if event_type not in EVENT_TYPES:
        return metadata

    payload = _payload(event)
    event_key = _event_key(event_type, event, payload)
    plan = deepcopy(plan)
    applied = [str(item) for item in plan.get("applied_event_ids") or [] if str(item)]
    if event_key and event_key in set(applied):
        plan, warnings = repair_execution_plan(plan, default_agent_id=_str(plan.get("agent_id") or "build") or "build")
        if warnings:
            plan["validation_warnings"] = warnings[-20:]
        metadata["execution_plan"] = plan
        return metadata

    nodes = [_normalize_node(item) for item in plan.get("nodes") or []]
    if event_type == "tool_call_started":
        _tool_started(plan, nodes, payload, event)
    elif event_type == "tool_call_completed":
        _tool_completed(plan, nodes, payload, event)
    elif event_type == "tool_call_failed":
        _tool_failed(plan, nodes, payload, event)
    elif event_type == "permission_asked":
        _permission_asked(plan, nodes, payload, event)
    elif event_type == "permission_decided":
        _permission_decided(plan, nodes, payload, event)
    elif event_type == "summary_completed":
        _summary_completed(plan, nodes, payload, event)
    elif event_type in {"session_failed", "session_interrupted"}:
        _runtime_stopped(plan, nodes, payload, event, event_type)
    elif event_type.startswith("async_subtask_"):
        _async_subtask_event(plan, nodes, payload, event, event_type)
    elif event_type.startswith("node_recovery_"):
        _node_recovery_event(plan, nodes, payload, event, event_type)

    plan["nodes"] = nodes
    plan["edges"] = _edges_from_nodes(nodes)
    plan["current_node_id"] = _current_node_id(nodes)
    plan["updated_at"] = _now()
    if event_key:
        applied.append(event_key)
        plan["applied_event_ids"] = applied[-200:]
    plan, warnings = repair_execution_plan(plan, default_agent_id=_str(plan.get("agent_id") or "build") or "build")
    if warnings:
        plan["validation_warnings"] = warnings[-20:]
    metadata["execution_plan"] = plan
    return metadata


def apply_execution_event_to_session(repository: Any, session_id: str, event: dict[str, Any]) -> None:
    try:
        if not hasattr(repository, "get_session") or not hasattr(repository, "update_session"):
            return
        session = repository.get_session(session_id)
        if not session:
            return
        metadata = ensure_session_state(dict(session.get("metadata") or {}))
        updated = apply_execution_event(metadata, event)
        if updated != metadata:
            repository.update_session(session_id, metadata=updated)
    except Exception:
        logger.exception("Failed to apply execution plan event for session %s", session_id)


def _tool_started(plan: dict[str, Any], nodes: list[dict[str, Any]], payload: dict[str, Any], event: dict[str, Any]) -> None:
    part_id = _str(payload.get("part_id"))
    tool = _str(payload.get("tool"))
    node = _find_by(nodes, "source_part_id", part_id) if part_id else None
    if node is None:
        parent = _primary_node(nodes)
        node = _append_node(
            nodes,
            {
                "id": f"tool:{part_id or _str(event.get('id')) or len(nodes) + 1}",
                "title": f"工具调用：{tool or 'tool'}",
                "description": "运行时工具调用节点。",
                "agent_id": _str(payload.get("agent_name")) or _str(parent.get("agent_id")) or _str(plan.get("agent_id")) or "build",
                "kind": "tool",
                "depends_on": [parent["id"]] if parent else [],
                "input_contract": {},
                "output_contract": {},
                "retry_policy": {"max_attempts": 0, "retry_on": []},
                "approval_policy": {"requires_approval": False, "tools": []},
                "output": {},
            },
        )
    node.update(
        {
            "status": "running",
            "source_part_id": part_id or node.get("source_part_id"),
            "source_event_id": _str(event.get("id")) or node.get("source_event_id"),
            "tool": tool or node.get("tool"),
            "started_at": node.get("started_at") or _event_time(event),
            "blocked_reason": None,
            "error": None,
        }
    )
    plan["status"] = "running"


def _tool_completed(plan: dict[str, Any], nodes: list[dict[str, Any]], payload: dict[str, Any], event: dict[str, Any]) -> None:
    part = payload.get("part") if isinstance(payload.get("part"), dict) else {}
    part_id = _str(payload.get("part_id") or part.get("id"))
    tool = _str(payload.get("tool") or part.get("title"))
    node = _find_by(nodes, "source_part_id", part_id) or _current_node(nodes)
    if not node:
        return
    node.update(
        {
            "status": "completed",
            "source_part_id": part_id or node.get("source_part_id"),
            "source_event_id": _str(event.get("id")) or node.get("source_event_id"),
            "tool": tool or node.get("tool"),
            "completed_at": node.get("completed_at") or _event_time(event),
            "output": _compact_output(part or payload),
            "error": None,
            "blocked_reason": None,
        }
    )
    primary = _primary_node(nodes)
    if primary and primary.get("status") not in {"completed", "failed", "interrupted", "blocked"}:
        primary["status"] = "running"
    plan["status"] = "running"


def _tool_failed(plan: dict[str, Any], nodes: list[dict[str, Any]], payload: dict[str, Any], event: dict[str, Any]) -> None:
    part = payload.get("part") if isinstance(payload.get("part"), dict) else {}
    part_id = _str(payload.get("part_id") or part.get("id"))
    tool = _str(payload.get("tool") or part.get("title"))
    error = _str(payload.get("error") or payload.get("summary") or part.get("content") or event.get("message"))
    node = _find_by(nodes, "source_part_id", part_id) or _current_node(nodes)
    if not node:
        parent = _primary_node(nodes)
        node = _append_node(
            nodes,
            {
                "id": f"tool:{part_id or _str(event.get('id')) or len(nodes) + 1}",
                "title": f"工具调用：{tool or 'tool'}",
                "description": "运行时工具调用节点。",
                "agent_id": _str(payload.get("agent_name")) or _str(parent.get("agent_id")) or _str(plan.get("agent_id")) or "build",
                "kind": "tool",
                "depends_on": [parent["id"]] if parent else [],
                "input_contract": {},
                "output_contract": {},
                "retry_policy": {"max_attempts": 1, "retry_on": ["failed"]},
                "approval_policy": {"requires_approval": False, "tools": []},
                "output": {},
            },
        )
    node.update(
        {
            "status": "failed",
            "source_part_id": part_id or node.get("source_part_id"),
            "source_event_id": _str(event.get("id")) or node.get("source_event_id"),
            "tool": tool or node.get("tool"),
            "completed_at": _event_time(event),
            "output": _compact_output(part or payload),
            "error": error,
            "blocked_reason": None,
            "retry_policy": {"max_attempts": 1, "retry_on": ["failed"]},
        }
    )
    _mark_recoverable(node, action="retry_node", reason=error or "Tool call failed.")
    plan["status"] = "failed"


def _permission_asked(plan: dict[str, Any], nodes: list[dict[str, Any]], payload: dict[str, Any], event: dict[str, Any]) -> None:
    node = _current_node(nodes) or _primary_node(nodes)
    if not node:
        return
    reason = _str(payload.get("summary") or payload.get("message") or event.get("message") or "等待审批")
    node.update(
        {
            "status": "blocked",
            "source_permission_part_id": _str(payload.get("part_id")) or node.get("source_permission_part_id"),
            "source_event_id": _str(event.get("id")) or node.get("source_event_id"),
            "tool": _str(payload.get("tool")) or node.get("tool"),
            "blocked_reason": reason,
        }
    )
    plan["status"] = "blocked"


def _permission_decided(plan: dict[str, Any], nodes: list[dict[str, Any]], payload: dict[str, Any], event: dict[str, Any]) -> None:
    part_id = _str(payload.get("part_id"))
    node = _find_by(nodes, "source_permission_part_id", part_id) or _find_by(nodes, "source_part_id", part_id) or _current_node(nodes)
    if not node:
        return
    decision_type = _decision_type(payload)
    if decision_type == "reject":
        node.update(
            {
                "status": "blocked",
                "source_event_id": _str(event.get("id")) or node.get("source_event_id"),
                "blocked_reason": _str(payload.get("summary") or event.get("message") or "审批已拒绝，需要人工恢复。"),
                "error": _str(payload.get("message") or payload.get("summary") or "permission rejected"),
            }
        )
        _mark_recoverable(node, action="manual_review", reason="Permission was rejected.")
        plan["status"] = "blocked"
    else:
        node.update(
            {
                "status": "running",
                "source_event_id": _str(event.get("id")) or node.get("source_event_id"),
                "blocked_reason": None,
                "error": None,
                "recovery_error": None,
            }
        )
        plan["status"] = "running"


def _summary_completed(plan: dict[str, Any], nodes: list[dict[str, Any]], payload: dict[str, Any], event: dict[str, Any]) -> None:
    primary = _find_by(nodes, "id", "execute_primary_agent")
    if primary and primary.get("status") not in {"failed", "interrupted"}:
        primary["status"] = "completed"
        primary.setdefault("completed_at", _event_time(event))
    node = _find_by(nodes, "id", "summarize_result")
    if not node:
        return
    node.update(
        {
            "status": "completed",
            "source_part_id": _str(payload.get("part_id")) or node.get("source_part_id"),
            "source_event_id": _str(event.get("id")) or node.get("source_event_id"),
            "completed_at": node.get("completed_at") or _event_time(event),
            "output": {"summary": _str(payload.get("summary") or event.get("message"))},
            "error": None,
        }
    )
    plan["status"] = "completed"


def _runtime_stopped(plan: dict[str, Any], nodes: list[dict[str, Any]], payload: dict[str, Any], event: dict[str, Any], event_type: str) -> None:
    node = _current_node(nodes) or _primary_node(nodes)
    if not node:
        return
    status = "interrupted" if event_type == "session_interrupted" else "failed"
    message = _str(payload.get("error") or payload.get("summary") or event.get("message"))
    node.update(
        {
            "status": status,
            "source_event_id": _str(event.get("id")) or node.get("source_event_id"),
            "error": message or node.get("error"),
            "completed_at": node.get("completed_at") or _event_time(event),
        }
    )
    _mark_recoverable(node, action=_recovery_action_for(node), reason=message or "Runtime stopped before the node completed.")
    plan["status"] = status


def _async_subtask_event(plan: dict[str, Any], nodes: list[dict[str, Any]], payload: dict[str, Any], event: dict[str, Any], event_type: str) -> None:
    task_id = _str(payload.get("task_id"))
    if not task_id:
        return
    node = _find_by(nodes, "source_task_id", task_id)
    status = _async_status(payload, event_type)
    if node is None:
        parent = _primary_node(nodes)
        node = _append_node(
            nodes,
            {
                "id": f"subagent:{task_id}",
                "title": f"子 Agent：{_str(payload.get('agent_name')) or 'subagent'}",
                "description": _str(payload.get("summary") or event.get("message") or "异步子任务"),
                "agent_id": _str(payload.get("agent_name")) or "subagent",
                "kind": "subagent",
                "depends_on": [parent["id"]] if parent else [],
                "input_contract": {"task_id": task_id},
                "output_contract": {},
                "retry_policy": {"max_attempts": 1 if status == "failed" else 0, "retry_on": ["failed"] if status == "failed" else []},
                "approval_policy": {"requires_approval": False, "tools": []},
                "output": {},
            },
        )
    node.update(
        {
            "status": status,
            "source_task_id": task_id,
            "source_event_id": _str(event.get("id")) or node.get("source_event_id"),
            "agent_id": _str(payload.get("agent_name")) or node.get("agent_id"),
            "started_at": node.get("started_at") or _event_time(event),
            "completed_at": _event_time(event) if status in {"completed", "failed", "interrupted"} else node.get("completed_at"),
            "blocked_reason": _str(payload.get("child_status")) if status == "blocked" else None,
            "error": _str(payload.get("error") or payload.get("summary")) if status == "failed" else None,
            "output": _compact_output(payload),
        }
    )
    if status == "failed":
        node["retry_policy"] = {"max_attempts": 1, "retry_on": ["failed"]}
        _mark_recoverable(node, action="restart_subagent", reason=node.get("error") or "Async subagent failed.")
    elif status == "interrupted":
        _mark_recoverable(node, action="restart_subagent", reason="Async subagent was interrupted.")
    elif status == "completed":
        node.update({"recoverable": False, "recovery_action": None, "recovery_reason": None, "recovery_error": None})
    plan["status"] = "blocked" if status in {"blocked", "failed", "interrupted"} else "running"


def _node_recovery_event(plan: dict[str, Any], nodes: list[dict[str, Any]], payload: dict[str, Any], event: dict[str, Any], event_type: str) -> None:
    node_id = _str(payload.get("node_id"))
    node = _find_by(nodes, "id", node_id) or _current_node(nodes)
    if not node:
        return
    action = _str(payload.get("action")) or _recovery_action_for(node)
    message = _str(payload.get("summary") or event.get("message"))
    recovery_id = _recovery_id(payload, event)
    if event_type == "node_recovery_requested":
        _append_recovery_history(node, recovery_id, action, "requested", event, message=message)
        node.update(
            {
                "recoverable": True,
                "recovery_action": action,
                "recovery_reason": message or node.get("recovery_reason"),
                "last_recovery_at": _event_time(event),
                "source_event_id": _str(event.get("id")) or node.get("source_event_id"),
            }
        )
        plan["status"] = "blocked"
    elif event_type == "node_recovery_started":
        output = dict(node.get("output") or {})
        if payload.get("new_task_id"):
            output["recovery_task_id"] = payload.get("new_task_id")
        if payload.get("old_task_id"):
            output["previous_task_id"] = payload.get("old_task_id")
        node["output"] = output
        _append_recovery_history(
            node,
            recovery_id,
            action,
            "started",
            event,
            old_task_id=_str(payload.get("old_task_id")),
            new_task_id=_str(payload.get("new_task_id")),
            message=message,
        )
        node.update(
            {
                "status": "running",
                "recoverable": False,
                "recovery_action": action,
                "recovery_attempts": int(node.get("recovery_attempts") or 0) + 1,
                "last_recovery_at": _event_time(event),
                "recovery_error": None,
                "blocked_reason": None,
                "error": None,
                "output": node.get("output") or output,
                "source_event_id": _str(event.get("id")) or node.get("source_event_id"),
            }
        )
        plan["status"] = "running"
    elif event_type == "node_recovery_completed":
        _append_recovery_history(node, recovery_id, action, "completed", event, message=message)
        node.update(
            {
                "status": "running" if _str(payload.get("keeps_running")) else "completed",
                "recoverable": False,
                "recovery_error": None,
                "completed_at": _event_time(event) if not _str(payload.get("keeps_running")) else node.get("completed_at"),
                "source_event_id": _str(event.get("id")) or node.get("source_event_id"),
            }
        )
        plan["status"] = "running" if node["status"] == "running" else plan.get("status", "running")
    elif event_type in {"node_recovery_failed", "node_recovery_rejected"}:
        _append_recovery_history(
            node,
            recovery_id,
            action,
            "failed" if event_type == "node_recovery_failed" else "rejected",
            event,
            error=_str(payload.get("error") or message),
            message=message,
        )
        node.update(
            {
                "status": "failed" if event_type == "node_recovery_failed" else "blocked",
                "recoverable": event_type == "node_recovery_failed",
                "recovery_action": action,
                "recovery_error": _str(payload.get("error") or message) or node.get("recovery_error"),
                "blocked_reason": message or node.get("blocked_reason"),
                "last_recovery_at": _event_time(event),
                "source_event_id": _str(event.get("id")) or node.get("source_event_id"),
            }
        )
        plan["status"] = "failed" if event_type == "node_recovery_failed" else "blocked"


def _normalize_node(raw: Any) -> dict[str, Any]:
    item = dict(raw or {}) if isinstance(raw, dict) else {}
    return {
        "id": _str(item.get("id")) or "node",
        "title": _str(item.get("title") or item.get("id") or "任务"),
        "description": _str(item.get("description")),
        "agent_id": _str(item.get("agent_id") or "build"),
        "kind": _str(item.get("kind") or "agent"),
        "status": _str(item.get("status") or "pending"),
        "depends_on": [_str(value) for value in item.get("depends_on") or [] if _str(value)],
        "input_contract": dict(item.get("input_contract") or {}),
        "output_contract": dict(item.get("output_contract") or {}),
        "retry_policy": dict(item.get("retry_policy") or {"max_attempts": 0, "retry_on": []}),
        "approval_policy": dict(item.get("approval_policy") or {"requires_approval": False, "tools": []}),
        "output": dict(item.get("output") or {}),
        "error": item.get("error"),
        "source_part_id": item.get("source_part_id"),
        "source_permission_part_id": item.get("source_permission_part_id"),
        "source_event_id": item.get("source_event_id"),
        "source_task_id": item.get("source_task_id"),
        "tool": item.get("tool"),
        "started_at": item.get("started_at"),
        "completed_at": item.get("completed_at"),
        "blocked_reason": item.get("blocked_reason"),
        "recoverable": bool(item.get("recoverable") or False),
        "recovery_action": item.get("recovery_action"),
        "recovery_reason": item.get("recovery_reason"),
        "recovery_attempts": _safe_int(item.get("recovery_attempts"), 0),
        "last_recovery_at": item.get("last_recovery_at"),
        "recovery_error": item.get("recovery_error"),
    }


def _append_node(nodes: list[dict[str, Any]], node: dict[str, Any]) -> dict[str, Any]:
    nodes.append(_normalize_node(node))
    return nodes[-1]


def _current_node(nodes: list[dict[str, Any]]) -> dict[str, Any] | None:
    for node in nodes:
        if node.get("status") in {"running", "blocked"} and node.get("id") != "execute_primary_agent":
            return node
    for node in nodes:
        if node.get("status") in {"running", "blocked"}:
            return node
    current_id = _current_node_id(nodes)
    return _find_by(nodes, "id", current_id) if current_id else None


def _primary_node(nodes: list[dict[str, Any]]) -> dict[str, Any] | None:
    return _find_by(nodes, "id", "execute_primary_agent") or _current_node(nodes)


def _find_by(nodes: list[dict[str, Any]], key: str, value: Any) -> dict[str, Any] | None:
    if not value:
        return None
    for node in nodes:
        if node.get(key) == value:
            return node
    return None


def _current_node_id(nodes: list[dict[str, Any]]) -> str | None:
    for node in nodes:
        if node.get("status") in {"failed", "interrupted"} and node.get("id") != "execute_primary_agent":
            return _str(node.get("id")) or None
    for node in nodes:
        if node.get("status") == "running" and node.get("id") != "execute_primary_agent":
            return _str(node.get("id")) or None
    for node in nodes:
        if node.get("status") == "blocked" and node.get("id") != "execute_primary_agent":
            return _str(node.get("id")) or None
    for node in nodes:
        if node.get("status") == "running":
            return _str(node.get("id")) or None
    for node in nodes:
        if node.get("status") == "blocked":
            return _str(node.get("id")) or None
    for node in nodes:
        if node.get("status") == "pending":
            return _str(node.get("id")) or None
    return None


def _edges_from_nodes(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {"from": dependency, "to": _str(node.get("id")), "type": "depends_on"}
        for node in nodes
        for dependency in node.get("depends_on") or []
        if dependency and node.get("id")
    ]


def _async_status(payload: dict[str, Any], event_type: str) -> str:
    raw = _str(payload.get("async_status") or payload.get("status") or event_type.removeprefix("async_subtask_"))
    if raw in {"completed"}:
        return "completed"
    if raw in {"failed"}:
        return "failed"
    if raw in {"cancelled", "canceled"}:
        return "interrupted"
    if raw in {"waiting_approval", "waiting_permission"} or _str(payload.get("child_status")) in {"waiting_approval", "waiting_permission"}:
        return "blocked"
    return "running"


def _mark_recoverable(node: dict[str, Any], *, action: str, reason: str) -> None:
    if node.get("status") == "completed":
        return
    node.update(
        {
            "recoverable": True,
            "recovery_action": action,
            "recovery_reason": reason,
        }
    )


def _recovery_action_for(node: dict[str, Any]) -> str:
    if node.get("kind") == "subagent" or node.get("source_task_id"):
        return "restart_subagent"
    if node.get("kind") == "tool" or node.get("tool"):
        return "retry_node"
    if node.get("status") == "blocked":
        return "resume_node"
    return "manual_review"


def _decision_type(payload: dict[str, Any]) -> str:
    decisions = payload.get("decisions")
    if isinstance(decisions, list) and decisions:
        first = decisions[0] if isinstance(decisions[0], dict) else {}
        return _str(first.get("type"))
    decision = payload.get("decision")
    if isinstance(decision, dict):
        return _str(decision.get("type"))
    return _str(payload.get("decision_type") or payload.get("type"))


def _recovery_id(payload: dict[str, Any], event: dict[str, Any]) -> str:
    return _str(payload.get("recovery_id") or event.get("recovery_id") or event.get("id"))


def _append_recovery_history(
    node: dict[str, Any],
    recovery_id: str,
    action: str,
    status: str,
    event: dict[str, Any],
    *,
    error: str = "",
    old_task_id: str = "",
    new_task_id: str = "",
    message: str = "",
) -> None:
    output = dict(node.get("output") or {})
    history = [dict(item) for item in output.get("recovery_history") or [] if isinstance(item, dict)]
    if recovery_id and any(item.get("recovery_id") == recovery_id and item.get("status") == status for item in history):
        node["output"] = output
        return
    item = {
        "recovery_id": recovery_id,
        "action": action,
        "status": status,
        "at": _event_time(event),
    }
    if message:
        item["message"] = message
    if error:
        item["error"] = error
    if old_task_id:
        item["old_task_id"] = old_task_id
    if new_task_id:
        item["new_task_id"] = new_task_id
    history.append(item)
    output["recovery_history"] = history[-20:]
    node["output"] = output


def _event_type(event: dict[str, Any]) -> str:
    return _str(event.get("event_type") or event.get("type") or event.get("event"))


def _payload(event: dict[str, Any]) -> dict[str, Any]:
    return dict(event.get("payload") or {}) if isinstance(event.get("payload"), dict) else {}


def _event_key(event_type: str, event: dict[str, Any], payload: dict[str, Any]) -> str:
    identity = _str(payload.get("recovery_id") or event.get("id") or payload.get("part_id") or payload.get("task_id") or payload.get("source_event_id"))
    return f"{event_type}:{identity}" if identity else ""


def _event_time(event: dict[str, Any]) -> str:
    return _str(event.get("created_at")) or _now()


def _compact_output(value: dict[str, Any]) -> dict[str, Any]:
    output: dict[str, Any] = {}
    if value.get("id"):
        output["part_id"] = value.get("id")
    for key in ("summary", "content", "status", "tool", "async_status", "child_status", "health_status"):
        if key in value and value[key] is not None:
            output[key] = str(value[key])[:1000] if isinstance(value[key], str) else value[key]
    part = value.get("part") if isinstance(value.get("part"), dict) else None
    if part:
        output["part_id"] = part.get("id")
        output["content"] = _str(part.get("content"))[:1000]
    return output


def _str(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _now() -> str:
    return datetime.now(UTC).isoformat()


__all__ = ["apply_execution_event", "apply_execution_event_to_session"]
