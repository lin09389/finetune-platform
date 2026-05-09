"""Node implementations for the LangGraph workflow runtime."""

from __future__ import annotations

from typing import Any

from .langgraph_tools import execute_legacy_tool
from .state import WorkflowState


def _context_preview(state: WorkflowState) -> str:
    context_pack = state.get("context_pack") or {}
    combined = context_pack.get("combined")
    if isinstance(combined, str) and combined:
        return combined
    return ""


async def bootstrap_node(state: WorkflowState) -> dict[str, Any]:
    metadata = dict(state.get("metadata") or {})
    metadata.setdefault("phase", "bootstrap")
    if state.get("context_pack"):
        metadata.setdefault("context_ready", True)
    return {
        "metadata": metadata,
        "execution_state": state.get("execution_state") or "created",
    }


async def plan_node(state: WorkflowState) -> dict[str, Any]:
    metadata = dict(state.get("metadata") or {})
    metadata["current_phase"] = "plan"
    messages = list(state.get("messages") or [])
    context_preview = _context_preview(state)
    bridge_payload = None
    if context_preview:
        messages.append({"role": "system", "content": f"[plan_context]\n{context_preview}"})
        bridge_payload = '{"tool":"list_files","arguments":{"pattern":"**/*"}}'
    metadata["bridge_payload"] = bridge_payload
    return {
        "messages": messages,
        "current_step": "plan",
        "current_agent_id": metadata.get("primary_agent_id") or "planner",
        "execution_state": "planning",
        "metadata": metadata,
    }


async def implement_node(state: WorkflowState) -> dict[str, Any]:
    metadata = dict(state.get("metadata") or {})
    metadata["current_phase"] = "implement"
    messages = list(state.get("messages") or [])
    context_preview = _context_preview(state)
    bridge_payload = None
    if context_preview:
        messages.append({"role": "system", "content": f"[implement_context]\n{context_preview}"})
        bridge_payload = '{"tool":"detect_project_commands","arguments":{}}'
    metadata["bridge_payload"] = bridge_payload
    return {
        "messages": messages,
        "current_step": "implement",
        "current_agent_id": metadata.get("current_agent_id") or "implementer",
        "execution_state": "inspecting",
        "metadata": metadata,
    }


async def review_node(state: WorkflowState) -> dict[str, Any]:
    metadata = dict(state.get("metadata") or {})
    metadata["current_phase"] = "review"
    messages = list(state.get("messages") or [])
    context_preview = _context_preview(state)
    if context_preview:
        messages.append({"role": "system", "content": f"[review_context]\n{context_preview}"})
    needs_manual_review = bool(metadata.get("bridge_status") == "completed" and metadata.get("bridge_payload") is None)
    return {
        "messages": messages,
        "current_step": "review",
        "current_agent_id": metadata.get("review_agent_id") or "reviewer",
        "execution_state": "waiting_approval",
        "needs_approval": bool(state.get("needs_approval", True)),
        "needs_manual_review": needs_manual_review,
        "metadata": metadata,
    }


async def curate_memory_node(state: WorkflowState) -> dict[str, Any]:
    metadata = dict(state.get("metadata") or {})
    metadata["current_phase"] = "curate_memory"
    return {
        "current_step": "curate_memory",
        "execution_state": "completed",
        "metadata": metadata,
    }


async def execute_tool_bridge_node(state: WorkflowState) -> dict[str, Any]:
    metadata = dict(state.get("metadata") or {})
    bridge_payload = metadata.get("bridge_payload")
    executor = metadata.get("tool_executor")
    project = metadata.get("project") or {}
    if not bridge_payload or executor is None:
        metadata["bridge_status"] = "skipped"
        metadata["bridge_payload"] = None
        return {"metadata": metadata}
    result = execute_legacy_tool(
        executor,
        bridge_payload,
        workflow_id=state["workflow_id"],
        step_id=metadata.get("step_id"),
        agent_id=state.get("current_agent_id") or metadata.get("primary_agent_id") or "planner",
        project=project,
    )
    messages = list(state.get("messages") or [])
    messages.append({"role": "tool", "content": result})
    metadata["bridge_status"] = "completed"
    metadata["bridge_payload"] = None
    return {"messages": messages, "metadata": metadata}
