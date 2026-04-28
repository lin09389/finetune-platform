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
    project_path: str | None = None
    force_agent: bool = False


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
    details_url: str | None = None
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
