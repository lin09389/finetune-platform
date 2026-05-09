"""Shared LangGraph state for workflow execution.

This file defines the durable state shape that will be persisted through the
LangGraph checkpointer and exchanged between nodes.
"""

from __future__ import annotations

from typing import Any, Annotated, Literal, TypedDict

from langgraph.graph import add_messages

ExecutionState = Literal[
    "created",
    "planning",
    "inspecting",
    "proposing_patch",
    "waiting_permission",
    "waiting_approval",
    "applying_patch",
    "verifying",
    "repairing",
    "needs_manual_review",
    "completed",
    "failed",
]

AutonomyMode = Literal["safe_auto", "confirm_all", "read_only"]


class WorkflowState(TypedDict, total=False):
    """Durable workflow state stored by LangGraph.

    The state intentionally stays flexible during Phase 1 so the graph can be
    introduced without forcing a full rewrite of the legacy runtime payloads.
    """

    workflow_id: str
    goal: str
    project_path: str
    template_id: str
    autonomy_mode: AutonomyMode

    messages: Annotated[list[Any], add_messages]
    current_step: str
    current_agent_id: str
    step_index: int
    retry_count: int

    context_pack: dict[str, Any]
    artifacts: dict[str, Any]
    actions: list[dict[str, Any]]
    execution_state: ExecutionState
    needs_manual_review: bool
    needs_approval: bool
    approval_comment: str | None
    tool_trace: list[dict[str, Any]]
    metadata: dict[str, Any]
    interrupted: bool
