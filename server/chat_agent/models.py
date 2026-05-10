from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from agent_runtime.models import WorkflowActionResponse, WorkflowObservabilityResponse, WorkflowResponse, WorkflowToolCallResponse


class ChatAgentRunCreate(BaseModel):
    chat_session_id: str | None = None
    message_id: str | None = None
    content: str = Field(..., min_length=1)
    template_id: str = "software_delivery"
    provider: str | None = None
    model: str | None = None
    agent_id: str | None = None
    project_path: str | None = None
    autonomy_mode: Literal["safe_auto", "confirm_all", "read_only"] = "safe_auto"
    force_agent: bool = False


class ChatAgentIntentRequest(BaseModel):
    content: str = Field(..., min_length=1)
    provider: str | None = None
    model: str | None = None
    agent_id: str | None = None
    template_id: str | None = None
    chat_session_id: str | None = None
    routing_mode: Literal["auto", "chat", "agent"] = "auto"


class ChatAgentIntentResponse(BaseModel):
    mode: Literal["chat", "agent", "workflow"]
    confidence: float = Field(default=0.5, ge=0, le=1)
    reason: str
    source: Literal["local_rule", "cloud", "fallback", "manual"]
    suggested_agent_id: str | None = None
    suggested_template_id: str | None = None


class ChatAgentApprovalRequest(BaseModel):
    approved: bool = True
    comment: str | None = None


class ChatAgentAcceptanceReport(BaseModel):
    result: Literal["passed", "partial", "blocked", "failed"]
    summary: str
    completed_items: list[str] = Field(default_factory=list)
    changed_files: list[str] = Field(default_factory=list)
    commands_run: list[str] = Field(default_factory=list)
    verification_result: str = ""
    blocking_reason: str = ""
    next_action: str = ""


class ChatAgentRunResponse(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    id: str
    mode: Literal["chat", "agent"]
    chat_session_id: str | None = None
    trigger_message_id: str | None = None
    workflow_id: str | None = None
    status: str
    intent_type: str | None = None
    summary: str = ""
    final_summary: str | None = None
    execution_state: str | None = None
    execution_state_message: str | None = None
    recoverable: bool = False
    model_protocol_status: str | None = None
    last_model_output_preview: str | None = None
    parse_repair_count: int = 0
    fallback_summary_used: bool = False
    acceptance_report: ChatAgentAcceptanceReport | None = None
    acceptance_report_source: str | None = None
    acceptance_report_raw: str | None = None
    details_url: str | None = None
    active_agent_id: str | None = None
    subagent_runs: list[dict[str, Any]] = Field(default_factory=list)
    auto_execution_policy: dict[str, Any] = Field(default_factory=dict)
    blocked_state: dict[str, Any] | None = None
    workflow: WorkflowResponse | None = None
    observability: WorkflowObservabilityResponse | None = None
    latest_event: dict[str, Any] | None = None
    latest_tool_call: WorkflowToolCallResponse | None = None
    latest_action: WorkflowActionResponse | None = None


class ChatAgentRunEvent(BaseModel):
    event_type: str
    run_id: str
    workflow_id: str | None = None
    message: str
    payload: dict[str, Any] = Field(default_factory=dict)


class ChatAgentActionResponse(BaseModel):
    run: ChatAgentRunResponse | None = None
    action: WorkflowActionResponse
