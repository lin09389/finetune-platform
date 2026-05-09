"""Conditional routing helpers for the LangGraph workflow graph."""

from __future__ import annotations

from typing import Any

from .state import WorkflowState


def route_after_actions(state: WorkflowState) -> str:
    if state.get("needs_manual_review"):
        return "interrupt_review"
    if state.get("needs_approval"):
        return "interrupt_approval"
    return "next_step"


def should_continue_tool_loop(state: WorkflowState) -> str:
    messages = state.get("messages") or []
    last_msg: Any = messages[-1] if messages else None
    tool_calls = getattr(last_msg, "tool_calls", None)
    if tool_calls:
        return "tools"
    return "evaluate_actions"
