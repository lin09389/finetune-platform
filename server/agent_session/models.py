from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from .status import AgentAsyncTaskStatus, AgentSessionStatus

AgentPartType = Literal["text", "tool_call", "tool_result", "diff", "command", "permission", "summary", "error"]
AgentPartStatus = Literal["pending", "running", "completed", "failed", "blocked", "approved", "executed"]
AgentAsyncTaskHealthStatus = Literal["ok", "waiting", "attention", "failed", "cancelled"]
AgentHitlDecisionType = Literal["approve", "edit", "reject", "respond"]
AgentExecutionRecoveryAction = Literal["retry_node", "resume_node", "restart_subagent", "manual_review"]
TaskMode = Literal["build", "train", "hybrid"]


class AgentSessionCreate(BaseModel):
    chat_session_id: str | None = None
    agent_id: str = "build"
    title: str | None = None
    project_path: str | None = None
    workspace_id: str | None = None
    task_mode: TaskMode | None = None
    provider: str | None = None
    model: str | None = None
    autonomy_mode: str | None = None
    enabled_skill_sources: list[str] | None = None


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


class AgentExecutionPlanRecoverRequest(BaseModel):
    action: AgentExecutionRecoveryAction | None = None
    instruction: str | None = None


class AgentSessionPreferences(BaseModel):
    display_title: str | None = None
    pinned: bool = False
    archived: bool = False
    updated_at: str | None = None


class AgentSessionPreferencesUpdate(BaseModel):
    display_title: str | None = Field(default=None, max_length=80)
    pinned: bool | None = None
    archived: bool | None = None


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
    diagnostics: dict[str, Any] = Field(default_factory=dict)
    events: list[dict[str, Any]] = Field(default_factory=list)
    duration_ms: int | None = None
    queue_wait_ms: int | None = None
    health_status: AgentAsyncTaskHealthStatus = "waiting"
    child_status: str | None = None
    has_pending_permission: bool = False
    pending_permission_part_id: str | None = None


class AgentAsyncTaskListResponse(BaseModel):
    tasks: list[AgentAsyncTaskResponse] = Field(default_factory=list)
    status_filter: str = "all"


class AgentAsyncTaskEventResponse(BaseModel):
    id: str
    task_id: str
    parent_session_id: str
    child_session_id: str | None = None
    event_type: str
    status: str | None = None
    message: str
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: str


class AgentAsyncTaskMetricsResponse(BaseModel):
    total: int = 0
    by_status: dict[str, int] = Field(default_factory=dict)
    running: int = 0
    failed: int = 0
    cancelled: int = 0
    completed: int = 0
    attention: int = 0
    recovery_count: int = 0
    event_count: int = 0
    last_event: dict[str, Any] | None = None


class AgentHitlEditedAction(BaseModel):
    name: str
    args: dict[str, Any] = Field(default_factory=dict)


class AgentHitlDecision(BaseModel):
    type: AgentHitlDecisionType
    message: str | None = None
    edited_action: AgentHitlEditedAction | None = None


class AgentHitlDecisionRequest(BaseModel):
    decisions: list[AgentHitlDecision]


class AgentFrontendDiagnosticsReport(BaseModel):
    version: int = 1
    sessionId: str
    protocolVersion: str = "agent.session.v1"
    unknownEvents: int = Field(default=0, ge=0)
    parseFailures: int = Field(default=0, ge=0)
    reconnects: int = Field(default=0, ge=0)
    recoveryRequested: int = Field(default=0, ge=0)
    recoverySucceeded: int = Field(default=0, ge=0)
    recoveryFailed: int = Field(default=0, ge=0)
    attentionByKind: dict[str, int] = Field(default_factory=dict)
    updatedAt: str | None = None


class AgentFrontendDiagnosticsBatch(BaseModel):
    reports: list[AgentFrontendDiagnosticsReport] = Field(default_factory=list, max_length=100)


class AgentSessionResponse(BaseModel):
    id: str
    chat_session_id: str | None = None
    agent_id: str
    status: AgentSessionStatus
    title: str
    project_path: str | None = None
    workspace_id: str | None = None
    task_mode: TaskMode | None = None
    provider: str | None = None
    model: str | None = None
    preferences: AgentSessionPreferences = Field(default_factory=AgentSessionPreferences)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: str
    updated_at: str
    parts: list[AgentPartResponse] = Field(default_factory=list)


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


class AgentTodoItem(BaseModel):
    id: str
    title: str
    status: Literal["pending", "in_progress", "completed", "blocked"] = "pending"
    summary: str = ""
    owner_agent: str | None = None
    source: str = "workspace"
    linked_artifact_id: str | None = None
    linked_task_id: str | None = None


class AgentWorkspacePlan(BaseModel):
    todos: list[AgentTodoItem] = Field(default_factory=list)
    source: str = "empty"
    updated_at: str | None = None


class AgentWorkspaceSource(BaseModel):
    kind: str
    id: str | None = None
    label: str | None = None


class AgentWorkspaceArtifact(BaseModel):
    id: str
    artifact_type: str
    type: str | None = None
    title: str
    summary: str = ""
    status: str = "ready"
    source: AgentWorkspaceSource | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    source_part_id: str | None = None
    source_task_id: str | None = None
    producer_agent: str | None = None
    created_at: str | None = None


class AgentWorkspaceChangedFile(BaseModel):
    path: str
    status: str = "modified"
    summary: str = ""
    source_part_id: str | None = None


class AgentWorkspaceAsyncTasks(BaseModel):
    tasks: list[AgentAsyncTaskResponse] = Field(default_factory=list)
    metrics: AgentAsyncTaskMetricsResponse = Field(default_factory=AgentAsyncTaskMetricsResponse)


class AgentWorkspaceNextAction(BaseModel):
    id: str
    action_type: str
    title: str
    summary: str = ""
    priority: str = "low"
    source_artifact_id: str | None = None
    source_task_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class AgentExecutionTimelineItem(BaseModel):
    id: str
    type: Literal["tool_call", "tool_result", "command", "permission", "summary", "error", "recovery"]
    title: str
    status: str | None = None
    summary: str = ""
    source_part_id: str
    created_at: str | None = None
    duration_ms: int | None = None
    payload_excerpt: dict[str, Any] = Field(default_factory=dict)


class AgentWorkspaceMount(BaseModel):
    path: str
    kind: str
    label: str
    writable: bool = False
    description: str = ""


class AgentWorkspaceSkillSource(BaseModel):
    name: str
    virtual_path: str
    priority: int = 0
    available: bool = True
    enabled: bool = True


class AgentExecutionPlanResponse(BaseModel):
    schema_version: str = "agent.execution.plan.v1"
    runtime: str = "deepagents"
    backend_mode: str = "workspace"
    thread_id: str | None = None
    recursion_limit: int | None = None
    checkpointer: bool = True
    state_machine: str = "agent_session.v1"
    plan_id: str | None = None
    session_id: str | None = None
    goal: str = ""
    status: str = "planned"
    current_node_id: str | None = None
    nodes: list[dict[str, Any]] = Field(default_factory=list)
    edges: list[dict[str, Any]] = Field(default_factory=list)
    created_at: str | None = None
    updated_at: str | None = None
    lifecycle: list[str] = Field(default_factory=list)


class AgentResourceProfileResponse(BaseModel):
    schema_version: str = "agent.resource.profile.v1"
    agent: dict[str, Any] = Field(default_factory=dict)
    memory: dict[str, Any] = Field(default_factory=dict)
    skills: dict[str, Any] = Field(default_factory=dict)
    mounts: list[AgentWorkspaceMount] = Field(default_factory=list)


class AgentRuntimePolicyResponse(BaseModel):
    schema_version: str = "agent.runtime.policy.v1"
    runtime_kind: str = "agent_session"
    agent_id: str = "build"
    agent_name: str = "Build"
    mode: str = "all"
    readonly: bool = False
    workspace_root: str | None = None
    provider: str | None = None
    model: str | None = None
    capabilities: dict[str, bool] = Field(default_factory=dict)
    tools: dict[str, Any] = Field(default_factory=dict)
    output_contract: dict[str, Any] = Field(default_factory=dict)
    recovery_policy: dict[str, Any] = Field(default_factory=dict)
    handoff_targets: list[str] = Field(default_factory=list)
    async_subagent_targets: list[str] = Field(default_factory=list)
    filesystem_profile: str = "deny_all"
    interrupt_on: dict[str, Any] | None = None
    enabled_skill_sources: list[str] | None = None
    skill_sources: list[AgentWorkspaceSkillSource] = Field(default_factory=list)
    vfs_mounts: list[AgentWorkspaceMount] = Field(default_factory=list)
    memory_files: list[str] = Field(default_factory=list)
    resource_profile: AgentResourceProfileResponse = Field(default_factory=AgentResourceProfileResponse)
    execution_plan: AgentExecutionPlanResponse = Field(default_factory=AgentExecutionPlanResponse)


class AgentWorkspaceRuntimeContext(BaseModel):
    workspace_root: str | None = None
    vfs_mounts: list[AgentWorkspaceMount] = Field(default_factory=list)
    skill_sources: list[AgentWorkspaceSkillSource] = Field(default_factory=list)
    memory_files: list[str] = Field(default_factory=list)
    policy: AgentRuntimePolicyResponse | None = None
    resource_profile: AgentResourceProfileResponse | None = None
    execution_plan: AgentExecutionPlanResponse | None = None


class AgentWorkspaceResponse(BaseModel):
    session: AgentSessionResponse
    status_text: dict[str, Any] = Field(default_factory=dict)
    timeline: list[dict[str, Any]] = Field(default_factory=list)
    pending_permission: dict[str, Any] | None = None
    plan: AgentWorkspacePlan = Field(default_factory=AgentWorkspacePlan)
    todos: list[AgentTodoItem] = Field(default_factory=list)
    diagnostics: dict[str, Any] = Field(default_factory=dict)
    async_tasks: AgentWorkspaceAsyncTasks = Field(default_factory=AgentWorkspaceAsyncTasks)
    artifacts: list[AgentWorkspaceArtifact] = Field(default_factory=list)
    changed_files: list[AgentWorkspaceChangedFile] = Field(default_factory=list)
    next_actions: list[AgentWorkspaceNextAction] = Field(default_factory=list)
    execution_timeline: list[AgentExecutionTimelineItem] = Field(default_factory=list)
    recent_events: list[dict[str, Any]] = Field(default_factory=list)
    runtime: AgentWorkspaceRuntimeContext = Field(default_factory=AgentWorkspaceRuntimeContext)
    runtime_policy: AgentRuntimePolicyResponse | None = None
    resource_profile: AgentResourceProfileResponse | None = None
    execution_plan: AgentExecutionPlanResponse | None = None
    vfs_mounts: list[AgentWorkspaceMount] = Field(default_factory=list)
    skill_sources: list[AgentWorkspaceSkillSource] = Field(default_factory=list)


class AgentExecutionPlanRecoveryResponse(BaseModel):
    session: AgentSessionResponse
    execution_plan: AgentExecutionPlanResponse | None = None
    workspace: AgentWorkspaceResponse
    node_id: str
    action: AgentExecutionRecoveryAction
    started_task_id: str | None = None


class AgentSkillManifestResponse(BaseModel):
    name: str
    description: str = ""
    virtual_skill_file: str | None = None
    source: str | None = None
    allowed_tools: list[str] = Field(default_factory=list)


class AgentSkillSourceResponse(BaseModel):
    name: str
    virtual_path: str
    priority: int = 0
    available: bool = True
    enabled_by_default: bool = True
    skills: list[AgentSkillManifestResponse] = Field(default_factory=list)


class AgentSkillRegistryResponse(BaseModel):
    sources: list[AgentSkillSourceResponse] = Field(default_factory=list)
    runtime_policy: AgentRuntimePolicyResponse | None = None
    resource_profile: AgentResourceProfileResponse | None = None


class AgentMemoryFileResponse(BaseModel):
    id: str
    path: str
    relative_path: str
    scope: str
    namespace: str
    content: str
    writable: bool = False
    version: int = 1
    updated_at: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentSessionOverviewResponse(BaseModel):
    session: AgentSessionResponse
    recent_events: list[dict[str, Any]] = Field(default_factory=list)
    artifacts: list[AgentArtifactResponse] = Field(default_factory=list)
    diagnostics: dict[str, Any] = Field(default_factory=dict)


AgentSessionResponse.model_rebuild()
