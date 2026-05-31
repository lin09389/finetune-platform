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
    "interrupted",
    "completed",
    "failed",
]
AgentPartType = Literal["text", "tool_call", "tool_result", "diff", "command", "permission", "summary", "error"]
AgentPartStatus = Literal["pending", "running", "completed", "failed", "blocked", "approved", "executed"]
AgentAsyncTaskStatus = Literal["pending", "running", "completed", "failed", "cancelled"]
AgentHitlDecisionType = Literal["approve", "edit", "reject", "respond"]
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
    active_context: dict[str, Any] | None = None
    explicit_context: list[dict[str, Any]] = Field(default_factory=list)


class AgentAsyncTaskStartRequest(BaseModel):
    subagent_type: str
    description: str


class AgentAsyncTaskUpdateRequest(BaseModel):
    description: str


class AgentAsyncTaskCancelRequest(BaseModel):
    reason: str | None = None


class AgentAsyncTaskResponse(BaseModel):
    task_id: str
    parent_session_id: str
    child_session_id: str | None = None
    previous_child_session_ids: list[str] = Field(default_factory=list)
    agent_name: str
    status: AgentAsyncTaskStatus
    input: dict[str, Any] = Field(default_factory=dict)
    result: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    restart_count: int = 0
    created_at: str
    updated_at: str
    started_at: str | None = None
    completed_at: str | None = None
    cancelled_at: str | None = None
    last_checked_at: str | None = None


class AgentAsyncTaskListResponse(BaseModel):
    tasks: list[AgentAsyncTaskResponse] = Field(default_factory=list)
    status_filter: str = "all"


class AgentHitlEditedAction(BaseModel):
    name: str
    args: dict[str, Any] = Field(default_factory=dict)


class AgentHitlDecision(BaseModel):
    type: AgentHitlDecisionType
    message: str | None = None
    edited_action: AgentHitlEditedAction | None = None


class AgentHitlDecisionRequest(BaseModel):
    decisions: list[AgentHitlDecision]


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


AgentSessionResponse.model_rebuild()
