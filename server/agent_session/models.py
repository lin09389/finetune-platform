from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


AgentSessionStatus = Literal[
    "idle",
    "running",
    "waiting_permission",
    "waiting_approval",
    "verifying",
    "repairing",
    "needs_manual_review",
    "completed",
    "failed",
]
AgentPartType = Literal["text", "tool_call", "tool_result", "diff", "command", "permission", "summary", "error"]
AgentPartStatus = Literal["pending", "running", "completed", "failed", "blocked", "approved", "executed"]


class AgentSessionCreate(BaseModel):
    chat_session_id: str | None = None
    agent_id: str = "build"
    title: str | None = None
    project_path: str | None = None
    provider: str | None = None
    model: str | None = None
    autonomy_mode: str | None = None


class AgentPromptRequest(BaseModel):
    content: str
    provider: str | None = None
    model: str | None = None


class AgentSessionResponse(BaseModel):
    id: str
    chat_session_id: str | None = None
    agent_id: str
    status: AgentSessionStatus
    title: str
    project_path: str | None = None
    provider: str | None = None
    model: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: str
    updated_at: str
    parts: list["AgentPartResponse"] = Field(default_factory=list)


class AgentPartResponse(BaseModel):
    id: str
    session_id: str
    type: AgentPartType
    status: AgentPartStatus | None = None
    title: str | None = None
    content: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: str
    updated_at: str


class AgentEventResponse(BaseModel):
    id: str
    session_id: str
    event_type: str
    message: str
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: str


class AgentApprovalResponse(BaseModel):
    part: AgentPartResponse
    session: AgentSessionResponse


AgentSessionResponse.model_rebuild()
