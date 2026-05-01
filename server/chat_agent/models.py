from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from agent_runtime.models import WorkflowActionResponse, WorkflowObservabilityResponse, WorkflowResponse


class ChatAgentRunCreate(BaseModel):
    chat_session_id: str | None = None
    message_id: str | None = None
    content: str = Field(..., min_length=1)
    template_id: str = "software_delivery"
    provider: str | None = None
    model: str | None = None
    agent_id: str | None = None
    project_path: str | None = None
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
    mode: Literal["chat", "agent"]
    confidence: float = Field(default=0.5, ge=0, le=1)
    reason: str
    source: Literal["local_rule", "cloud", "fallback", "manual"]
    suggested_agent_id: str | None = None
    suggested_template_id: str | None = None


class ChatAgentApprovalRequest(BaseModel):
    approved: bool = True
    comment: str | None = None


class ChatAgentRunResponse(BaseModel):
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
    details_url: str | None = None
    active_agent_id: str | None = None
    subagent_runs: list[dict[str, Any]] = Field(default_factory=list)
    auto_execution_policy: dict[str, Any] = Field(default_factory=dict)
    blocked_state: dict[str, Any] | None = None
    workflow: WorkflowResponse | None = None
    observability: WorkflowObservabilityResponse | None = None
    latest_event: dict[str, Any] | None = None


class ChatAgentRunEvent(BaseModel):
    event_type: str
    run_id: str
    workflow_id: str | None = None
    message: str
    payload: dict[str, Any] = Field(default_factory=dict)


class ChatAgentActionResponse(BaseModel):
    run: ChatAgentRunResponse | None = None
    action: WorkflowActionResponse
