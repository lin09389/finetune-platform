from __future__ import annotations

from typing import Any, Literal, TypedDict


ExecutionState = Literal[
    "created",
    "running",
    "waiting_permission",
    "waiting_approval",
    "needs_manual_review",
    "completed",
    "failed",
]


class AgentSessionGraphState(TypedDict, total=False):
    session_id: str
    prompt: str
    messages: list[dict[str, str]]
    pending_tool_calls: list[dict[str, Any]]
    tool_results: list[dict[str, Any]]
    pending_part_id: str | None
    pending_permission_call: dict[str, Any] | None
    final_summary: str | None
    phase: str
    repair_attempts: int
    protocol_repair_count: int
    execution_state: ExecutionState
    iterations: int
    last_model_raw: str
    streaming_enabled: bool
    streaming_part_id: str | None
    streaming_failed: bool
    last_stream_error: str | None
    streaming_raw: str
