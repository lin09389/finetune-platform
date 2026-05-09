"""Structured tool-call models for the workflow agent runtime."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from digital_team.models import AgentOutput


ToolName = Literal[
    "list_files",
    "search_code",
    "read_file",
    "inspect_project",
    "detect_project_commands",
    "get_git_status",
    "get_git_diff",
    "list_changed_files",
    "propose_patch",
    "propose_command",
    "read_execution_result",
    "read_test_failures",
    "delegate_agent",
    "finalize",
]


class AgentToolRequest(BaseModel):
    thought: str = ""
    tool: ToolName
    arguments: dict[str, Any] = Field(default_factory=dict)


class AgentToolResult(BaseModel):
    tool: str
    status: Literal["completed", "failed", "blocked"]
    summary: str = ""
    payload: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    permission_decision: Literal["allow", "deny", "ask"] | None = None
    blocked_reason: str | None = None
    replay_of_call_id: str | None = None


class AgentToolLoopState(BaseModel):
    workflow_id: str
    step_id: str | None = None
    agent_id: str
    iteration: int = 0
    max_iterations: int = 6
    results: list[AgentToolResult] = Field(default_factory=list)
    trace_id: str | None = None


class AgentToolLoopResponse(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    output: AgentOutput
    tool_calls: list[AgentToolResult] = Field(default_factory=list)
    needs_manual_review: bool = False
    trace_id: str | None = None
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    model_protocol_status: str | None = None
    last_model_output_preview: str | None = None
    parse_repair_count: int = 0
    fallback_summary_used: bool = False
