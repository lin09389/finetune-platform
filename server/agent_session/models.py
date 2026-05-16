from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from core.agent_run_state import AgentRunStateSnapshot


AgentSessionStatus = Literal[
    "idle",
    "running",
    "waiting_permission",
    "waiting_approval",
    "verifying",
    "repairing",
    "needs_manual_review",
    "interrupted",
    "completed",
    "failed",
]
AgentPartType = Literal["text", "tool_call", "tool_result", "diff", "command", "permission", "summary", "error"]
AgentPartStatus = Literal["pending", "running", "completed", "failed", "blocked", "approved", "executed"]
TaskStageStatus = Literal["pending", "running", "blocked", "completed", "failed", "waiting_approval"]
TaskNodeStatus = Literal["pending", "running", "blocked", "completed", "failed", "waiting_approval"]


class TaskNode(BaseModel):
    id: str
    title: str
    description: str | None = None
    tool: str | None = None
    args: dict[str, Any] = Field(default_factory=dict)
    status: TaskNodeStatus = "pending"
    depends_on: list[str] = Field(default_factory=list)
    summary: str | None = None
    artifacts: dict[str, Any] = Field(default_factory=dict)


class TaskStage(BaseModel):
    id: str
    title: str
    description: str | None = None
    status: TaskStageStatus = "pending"
    nodes: list[TaskNode] = Field(default_factory=list)
    summary: str | None = None


class TaskPlan(BaseModel):
    task_id: str
    goal: str
    stages: list[TaskStage] = Field(default_factory=list)
    status: Literal["planned", "running", "blocked", "completed", "failed"] = "planned"
    summary: str | None = None
    next_action: str | None = None


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


class AgentArtifactResponse(BaseModel):
    id: str
    path: str
    status: str
    summary: str
    preview: str = ""
    source_part_id: str


class AgentSessionOverviewResponse(BaseModel):
    session: AgentSessionResponse
    task_plan: dict[str, Any] | None = None
    recent_events: list[dict[str, Any]] = Field(default_factory=list)
    artifacts: list[AgentArtifactResponse] = Field(default_factory=list)
    diagnostics: dict[str, Any] = Field(default_factory=dict)


class LegacyAgentHistoryResponse(BaseModel):
    id: str
    source_runtime: Literal["workflow_legacy", "workflow_langgraph"]
    title: str
    goal: str
    summary: str = ""
    state: AgentRunStateSnapshot
    timeline: list[dict[str, Any]] = Field(default_factory=list)
    artifacts: list[dict[str, Any]] = Field(default_factory=list)
    observability: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: str | None = None
    updated_at: str | None = None


AgentSessionResponse.model_rebuild()
