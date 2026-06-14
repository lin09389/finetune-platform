from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .runtime_policy import AgentRuntimePolicy


PLAN_SCHEMA_VERSION = "agent.execution.plan.v1"
PLAN_STATUS_BY_SESSION_STATUS = {
    "idle": "planned",
    "running": "running",
    "verifying": "running",
    "repairing": "running",
    "waiting_permission": "blocked",
    "waiting_approval": "blocked",
    "completed": "completed",
    "failed": "failed",
    "needs_manual_review": "blocked",
    "interrupted": "interrupted",
}
VALID_NODE_STATUSES = {"pending", "running", "blocked", "completed", "failed", "interrupted", "waiting_approval", "waiting_permission"}
VALID_RECOVERY_ACTIONS = {"retry_node", "resume_node", "restart_subagent", "manual_review"}


def build_initial_execution_plan(
    *,
    session: dict[str, Any],
    policy: AgentRuntimePolicy,
    goal: str,
    status: str = "running",
) -> dict[str, Any]:
    now = _now()
    session_id = str(session.get("id") or "")
    agent_id = str(session.get("agent_id") or policy.agent_id or "build")
    plan_status = PLAN_STATUS_BY_SESSION_STATUS.get(status, status)
    nodes = [
        _node(
            "understand_task",
            "理解任务与运行约束",
            "读取用户目标、runtime policy、resource profile，并确认当前执行边界。",
            agent_id,
            status="completed" if plan_status == "running" else "pending",
            input_contract={"goal": "user_prompt", "runtime_policy": policy.schema_version},
            output_contract={"summary": "task_understanding", "constraints": "runtime_policy_constraints"},
        ),
        _node(
            "execute_primary_agent",
            "执行主 Agent 任务",
            "由主 Agent 根据目标调用工具、写文件或启动后续子任务。",
            agent_id,
            status="running" if plan_status == "running" else "pending",
            depends_on=["understand_task"],
            input_contract={
                "goal": "user_prompt",
                "available_tools": policy.tools,
                "resource_profile": policy.resource_profile.schema_version,
            },
            output_contract=policy.output_contract,
            retry_policy=_retry_policy(policy),
            approval_policy=_approval_policy(policy),
        ),
        _node(
            "summarize_result",
            "汇总结果与下一步",
            "把执行结果、风险、变更文件、验证建议整理成用户可读总结。",
            agent_id,
            status="pending",
            depends_on=["execute_primary_agent"],
            input_contract={"primary_output": "execute_primary_agent.output"},
            output_contract=policy.output_contract,
        ),
    ]
    return {
        **policy.execution_plan.model_dump(),
        "schema_version": PLAN_SCHEMA_VERSION,
        "plan_id": f"plan_{session_id}" if session_id else f"plan_{agent_id}",
        "session_id": session_id or None,
        "goal": goal,
        "status": plan_status,
        "current_node_id": _current_node_id(nodes),
        "nodes": nodes,
        "edges": _edges_from_nodes(nodes),
        "created_at": now,
        "updated_at": now,
    }


def normalize_execution_plan(
    raw: Any,
    *,
    session: dict[str, Any],
    policy: AgentRuntimePolicy,
    goal: str | None = None,
) -> dict[str, Any]:
    if isinstance(raw, dict) and raw.get("schema_version") == PLAN_SCHEMA_VERSION:
        plan = {**policy.execution_plan.model_dump(), **raw}
        plan["nodes"] = [_normalize_node(item, policy.agent_id) for item in plan.get("nodes") or []]
        plan["edges"] = list(plan.get("edges") or _edges_from_nodes(plan["nodes"]))
        plan.setdefault("plan_id", f"plan_{session.get('id')}")
        plan.setdefault("session_id", session.get("id"))
        plan.setdefault("goal", goal or "")
        plan.setdefault("status", "planned")
        plan["current_node_id"] = plan.get("current_node_id") or _current_node_id(plan["nodes"])
        plan["updated_at"] = _now()
        return plan
    return build_initial_execution_plan(
        session=session,
        policy=policy,
        goal=str(goal or ""),
        status=str(session.get("status") or "planned"),
    )


def validate_execution_plan(plan: Any) -> list[str]:
    if not isinstance(plan, dict) or plan.get("schema_version") != PLAN_SCHEMA_VERSION:
        return ["execution_plan schema is missing or unsupported"]
    warnings: list[str] = []
    nodes = plan.get("nodes")
    if not isinstance(nodes, list):
        return ["execution_plan nodes must be a list"]
    ids: set[str] = set()
    for index, raw in enumerate(nodes):
        if not isinstance(raw, dict):
            warnings.append(f"node[{index}] is not an object")
            continue
        node_id = str(raw.get("id") or "").strip()
        if not node_id:
            warnings.append(f"node[{index}] is missing id")
        elif node_id in ids:
            warnings.append(f"duplicate node id: {node_id}")
        ids.add(node_id)
        status = str(raw.get("status") or "pending")
        if status not in VALID_NODE_STATUSES:
            warnings.append(f"node {node_id or index} has invalid status: {status}")
        action = raw.get("recovery_action")
        if action is not None and str(action) not in VALID_RECOVERY_ACTIONS:
            warnings.append(f"node {node_id or index} has invalid recovery_action: {action}")
        try:
            attempts = int(raw.get("recovery_attempts") or 0)
            if attempts < 0:
                warnings.append(f"node {node_id or index} has negative recovery_attempts")
        except (TypeError, ValueError):
            warnings.append(f"node {node_id or index} has invalid recovery_attempts")
    current = plan.get("current_node_id")
    if current and str(current) not in ids:
        warnings.append(f"current_node_id points to missing node: {current}")
    for edge in plan.get("edges") or []:
        if not isinstance(edge, dict):
            warnings.append("edge is not an object")
            continue
        source = str(edge.get("from") or "")
        target = str(edge.get("to") or "")
        if source and source not in ids:
            warnings.append(f"edge source missing node: {source}")
        if target and target not in ids:
            warnings.append(f"edge target missing node: {target}")
    return warnings


def repair_execution_plan(plan: Any, *, default_agent_id: str = "build") -> tuple[dict[str, Any], list[str]]:
    if not isinstance(plan, dict) or plan.get("schema_version") != PLAN_SCHEMA_VERSION:
        return plan if isinstance(plan, dict) else {}, validate_execution_plan(plan)
    warnings = validate_execution_plan(plan)
    repaired = dict(plan)
    nodes: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, raw in enumerate(repaired.get("nodes") or []):
        node = _normalize_node(raw, default_agent_id)
        original_id = node["id"]
        if not original_id or original_id in seen:
            suffix = 2
            base = original_id or f"node_{index + 1}"
            candidate = f"{base}_{suffix}"
            while candidate in seen:
                suffix += 1
                candidate = f"{base}_{suffix}"
            node["id"] = candidate
        seen.add(node["id"])
        if node["status"] not in VALID_NODE_STATUSES:
            node["status"] = "pending"
        if node.get("recovery_action") is not None and str(node.get("recovery_action")) not in VALID_RECOVERY_ACTIONS:
            node["recovery_action"] = None
        if int(node.get("recovery_attempts") or 0) < 0:
            node["recovery_attempts"] = 0
        node["depends_on"] = [dependency for dependency in node.get("depends_on") or [] if dependency in seen or dependency in {item.get("id") for item in nodes}]
        nodes.append(node)
    node_ids = {node["id"] for node in nodes}
    edges = [
        {"from": str(edge.get("from")), "to": str(edge.get("to")), "type": str(edge.get("type") or "depends_on")}
        for edge in repaired.get("edges") or _edges_from_nodes(nodes)
        if isinstance(edge, dict) and str(edge.get("from") or "") in node_ids and str(edge.get("to") or "") in node_ids
    ]
    repaired["nodes"] = nodes
    repaired["edges"] = edges or _edges_from_nodes(nodes)
    current = str(repaired.get("current_node_id") or "")
    repaired["current_node_id"] = current if current in node_ids else _current_node_id(nodes)
    repaired["updated_at"] = repaired.get("updated_at") or _now()
    return repaired, warnings


def sync_execution_plan_status(metadata: dict[str, Any], session_status: str, *, error: str | None = None) -> dict[str, Any]:
    raw = metadata.get("execution_plan")
    if not isinstance(raw, dict) or raw.get("schema_version") != PLAN_SCHEMA_VERSION:
        return metadata
    plan = dict(raw)
    target = PLAN_STATUS_BY_SESSION_STATUS.get(session_status, session_status)
    plan["status"] = target
    plan["updated_at"] = _now()
    nodes = [_normalize_node(item, str(plan.get("agent_id") or "build")) for item in plan.get("nodes") or []]
    current_id = str(plan.get("current_node_id") or _current_node_id(nodes) or "")
    if target == "completed":
        nodes = [{**node, "status": "completed"} for node in nodes]
        plan["current_node_id"] = None
    elif target in {"failed", "interrupted", "blocked"}:
        updated = []
        for node in nodes:
            if node["id"] == current_id or node["status"] == "running":
                node = {**node, "status": "blocked" if target == "blocked" else "failed"}
                if error:
                    node["error"] = error
            updated.append(node)
        nodes = updated
        plan["current_node_id"] = current_id or _current_node_id(nodes)
    elif target == "running":
        if not any(node["status"] == "running" for node in nodes):
            resume_index = None
            for index, node in enumerate(nodes):
                if current_id and node["id"] == current_id and node["status"] in {"pending", "blocked", "failed"}:
                    resume_index = index
                    break
            if resume_index is None:
                for index, node in enumerate(nodes):
                    if node["status"] == "pending":
                        resume_index = index
                        break
            if resume_index is not None:
                nodes[resume_index] = {**nodes[resume_index], "status": "running", "error": None}
                for index, node in enumerate(nodes):
                    if index != resume_index and node["status"] == "running":
                        nodes[index] = {**node, "status": "pending"}
        plan["current_node_id"] = _current_node_id(nodes)
    plan["nodes"] = nodes
    plan["edges"] = list(plan.get("edges") or _edges_from_nodes(nodes))
    metadata["execution_plan"] = plan
    return metadata


def todos_from_execution_plan(plan: Any) -> list[dict[str, Any]]:
    if not isinstance(plan, dict) or plan.get("schema_version") != PLAN_SCHEMA_VERSION:
        return []
    todos: list[dict[str, Any]] = []
    for node in plan.get("nodes") or []:
        if not isinstance(node, dict):
            continue
        todos.append(
            {
                "id": str(node.get("id") or f"node_{len(todos) + 1}"),
                "title": str(node.get("title") or node.get("id") or "任务"),
                "status": _todo_status(str(node.get("status") or "pending")),
                "summary": str(node.get("description") or ""),
                "owner_agent": str(node.get("agent_id") or "") or None,
                "source": "execution_plan",
                "linked_task_id": node.get("source_task_id"),
            }
        )
    return todos


def _node(
    node_id: str,
    title: str,
    description: str,
    agent_id: str,
    *,
    status: str = "pending",
    depends_on: list[str] | None = None,
    input_contract: dict[str, Any] | None = None,
    output_contract: dict[str, Any] | None = None,
    retry_policy: dict[str, Any] | None = None,
    approval_policy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "id": node_id,
        "title": title,
        "description": description,
        "agent_id": agent_id,
        "kind": "agent",
        "status": status,
        "depends_on": list(depends_on or []),
        "input_contract": input_contract or {},
        "output_contract": output_contract or {},
        "retry_policy": retry_policy or {"max_attempts": 0, "retry_on": []},
        "approval_policy": approval_policy or {"requires_approval": False, "tools": []},
        "output": {},
        "error": None,
        "source_part_id": None,
        "source_permission_part_id": None,
        "source_event_id": None,
        "source_task_id": None,
        "tool": None,
        "started_at": None,
        "completed_at": None,
        "blocked_reason": None,
        "recoverable": False,
        "recovery_action": None,
        "recovery_reason": None,
        "recovery_attempts": 0,
        "last_recovery_at": None,
        "recovery_error": None,
    }


def _normalize_node(raw: Any, default_agent_id: str) -> dict[str, Any]:
    item = dict(raw or {}) if isinstance(raw, dict) else {}
    return {
        "id": str(item.get("id") or f"node_{abs(hash(str(item))) % 10000}"),
        "title": str(item.get("title") or item.get("id") or "任务"),
        "description": str(item.get("description") or ""),
        "agent_id": str(item.get("agent_id") or default_agent_id or "build"),
        "kind": str(item.get("kind") or "agent"),
        "status": str(item.get("status") or "pending"),
        "depends_on": [str(value) for value in item.get("depends_on") or []],
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


def _edges_from_nodes(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    edges: list[dict[str, Any]] = []
    for node in nodes:
        for dependency in node.get("depends_on") or []:
            edges.append({"from": str(dependency), "to": str(node.get("id") or ""), "type": "depends_on"})
    return edges


def _current_node_id(nodes: list[dict[str, Any]]) -> str | None:
    for node in nodes:
        if node.get("status") == "running":
            return str(node.get("id"))
    for node in nodes:
        if node.get("status") in {"pending", "blocked"}:
            return str(node.get("id"))
    return None


def _retry_policy(policy: AgentRuntimePolicy) -> dict[str, Any]:
    recovery = dict(policy.recovery_policy or {})
    return {"max_attempts": 1 if recovery.get("restart_recovery") else 0, "retry_on": ["failed"] if recovery.get("restart_recovery") else []}


def _approval_policy(policy: AgentRuntimePolicy) -> dict[str, Any]:
    interrupt = dict(policy.interrupt_on or {})
    tools = [name for name, enabled in interrupt.items() if enabled]
    return {"requires_approval": bool(tools), "tools": tools}


def _todo_status(status: str) -> str:
    if status in {"running"}:
        return "in_progress"
    if status in {"completed"}:
        return "completed"
    if status in {"blocked", "failed", "waiting_approval", "waiting_permission", "interrupted"}:
        return "blocked"
    return "pending"


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


__all__ = [
    "PLAN_SCHEMA_VERSION",
    "build_initial_execution_plan",
    "normalize_execution_plan",
    "repair_execution_plan",
    "sync_execution_plan_status",
    "todos_from_execution_plan",
    "validate_execution_plan",
]
