"""Public workflow-facing models backed by the internal agent runtime."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, model_validator

IDENTIFIER_PATTERN = r"^[a-z0-9_-]+$"


class WorkflowCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=120)
    goal: str = Field(..., min_length=1)
    template_id: str = "software_delivery"
    project_path: str | None = None
    chat_session_id: str | None = None
    include_project_context: bool = True
    include_chat_context: bool = False
    include_memory: bool = True
    max_context_chars: int = Field(default=6000, ge=500, le=30000)
    provider: str = "minimax"
    model: str | None = None
    agent_id: str | None = None
    approval_mode: str = "manual"


class WorkflowApprovalRequest(BaseModel):
    approved: bool = True
    comment: str | None = None


class WorkflowAgentConfig(BaseModel):
    agent_id: str = Field(..., pattern=IDENTIFIER_PATTERN)
    name: str = Field(..., min_length=1, max_length=80)
    description: str = ""
    system_prompt: str = Field(..., min_length=1)
    output_requirements: str = ""


class WorkflowStepConfig(BaseModel):
    step_key: str = Field(..., pattern=IDENTIFIER_PATTERN)
    agent_id: str = Field(..., pattern=IDENTIFIER_PATTERN)
    title: str = Field(..., min_length=1, max_length=120)
    description: str = ""
    artifact_type: str = Field(..., pattern=IDENTIFIER_PATTERN)
    requires_approval: bool = True
    sort_order: int = 0


class WorkflowTemplateCreate(BaseModel):
    id: str = Field(..., pattern=IDENTIFIER_PATTERN)
    name: str = Field(..., min_length=1, max_length=120)
    description: str = ""
    default_provider: str = "minimax"
    default_model: str | None = None
    default_approval_mode: str = "manual"
    is_enabled: bool = True
    agents: list[WorkflowAgentConfig] = Field(..., min_length=1)
    steps: list[WorkflowStepConfig] = Field(..., min_length=1)

    @model_validator(mode="after")
    def validate_step_agents(self):
        agent_ids = {agent.agent_id for agent in self.agents}
        for step in self.steps:
            if step.agent_id not in agent_ids:
                raise ValueError(f"step {step.step_key} references unknown agent {step.agent_id}")
        return self


class WorkflowTemplateUpdate(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    description: str = ""
    default_provider: str = "minimax"
    default_model: str | None = None
    default_approval_mode: str = "manual"
    is_enabled: bool = True
    agents: list[WorkflowAgentConfig] = Field(..., min_length=1)
    steps: list[WorkflowStepConfig] = Field(..., min_length=1)

    @model_validator(mode="after")
    def validate_step_agents(self):
        agent_ids = {agent.agent_id for agent in self.agents}
        for step in self.steps:
            if step.agent_id not in agent_ids:
                raise ValueError(f"step {step.step_key} references unknown agent {step.agent_id}")
        return self


class WorkflowAgentResponse(BaseModel):
    id: str
    agent_id: str
    name: str
    description: str = ""
    system_prompt: str = ""
    output_requirements: str = ""


class WorkflowStepTemplateResponse(BaseModel):
    key: str
    step_key: str
    agent_id: str
    legacy_role: str
    title: str
    description: str
    artifact_type: str
    requires_approval: bool
    sort_order: int = 0


class WorkflowTemplateResponse(BaseModel):
    id: str
    name: str
    description: str
    legacy_template_id: str
    is_builtin: bool = False
    is_enabled: bool = True
    agents: list[WorkflowAgentResponse] = Field(default_factory=list)
    steps: list[WorkflowStepTemplateResponse] = Field(default_factory=list)
    default_provider: str = "minimax"
    default_model: str | None = None
    default_approval_mode: str = "manual"


class WorkflowContextProfile(BaseModel):
    workflow_id: str
    project_path: str | None = None
    chat_session_id: str | None = None
    include_project_context: bool = True
    include_chat_context: bool = False
    include_memory: bool = True
    max_context_chars: int = 6000
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: str | None = None
    updated_at: str | None = None


class WorkflowContextProfileUpdate(BaseModel):
    project_path: str | None = None
    chat_session_id: str | None = None
    include_project_context: bool = True
    include_chat_context: bool = False
    include_memory: bool = True
    max_context_chars: int = Field(default=6000, ge=500, le=30000)
    metadata: dict[str, Any] = Field(default_factory=dict)


class WorkflowContextSnapshotResponse(BaseModel):
    id: str
    workflow_id: str
    step_id: str | None = None
    step_key: str | None = None
    context_type: str
    content: str
    sources: list[dict[str, Any]] = Field(default_factory=list)
    char_count: int
    created_at: str


class WorkflowMemoryEntryResponse(BaseModel):
    id: str
    workflow_id: str
    source_step_id: str | None = None
    memory_type: str
    memory_key: str
    memory_value: dict[str, Any] = Field(default_factory=dict)
    content: str
    confidence: float
    status: str
    external_memory_id: str | None = None
    created_at: str
    updated_at: str
    reverted_at: str | None = None


class WorkflowStepLogResponse(BaseModel):
    id: str
    workflow_id: str
    step_id: str | None = None
    step_key: str | None = None
    agent_id: str | None = None
    status: str
    provider: str | None = None
    model: str | None = None
    input_summary: str = ""
    output_summary: str = ""
    error: str | None = None
    started_at: str | None = None
    completed_at: str | None = None
    duration_ms: int | None = None
    trace_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: str


class WorkflowToolCallResponse(BaseModel):
    id: str
    workflow_id: str
    step_id: str | None = None
    agent_id: str | None = None
    tool_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    status: str
    result_summary: str = ""
    result_payload: dict[str, Any] = Field(default_factory=dict)
    permission_decision: str | None = None
    blocked_reason: str | None = None
    replay_of_call_id: str | None = None
    trace_id: str | None = None
    raw_model_output: str | None = None
    sanitized_model_output: str | None = None
    parse_error: str | None = None
    protocol_repair_attempted: bool = False
    error: str | None = None
    started_at: str | None = None
    completed_at: str | None = None
    duration_ms: int | None = None
    created_at: str


class WorkflowActionExecutionResponse(BaseModel):
    id: str
    action_id: str
    workflow_id: str
    status: str
    stdout: str = ""
    stderr: str = ""
    exit_code: int | None = None
    duration_ms: int | None = None
    error: str | None = None
    created_at: str


class WorkflowActionResponse(BaseModel):
    id: str
    workflow_id: str
    step_id: str | None = None
    action_type: str
    title: str
    description: str = ""
    payload: dict[str, Any] = Field(default_factory=dict)
    status: str
    created_by: str = "agent"
    execution_mode: str | None = None
    policy_decision: str | None = None
    policy_reason: str | None = None
    auto_executed_at: str | None = None
    execution_state: str | None = None
    changed_files: list[str] = Field(default_factory=list)
    applied_hunks: int | None = None
    failure_summary: str = ""
    approved_at: str | None = None
    rejected_at: str | None = None
    executed_at: str | None = None
    created_at: str
    updated_at: str
    executions: list[WorkflowActionExecutionResponse] = Field(default_factory=list)


class WorkflowObservabilityResponse(BaseModel):
    workflow_id: str
    status: str
    current_stage: str | None = None
    active_agent_id: str | None = None
    subagent_runs: list[dict[str, Any]] = Field(default_factory=list)
    auto_execution_policy: dict[str, Any] = Field(default_factory=dict)
    blocked_state: dict[str, Any] | None = None
    step_logs: list[WorkflowStepLogResponse] = Field(default_factory=list)
    tool_calls: list[WorkflowToolCallResponse] = Field(default_factory=list)
    actions: list[WorkflowActionResponse] = Field(default_factory=list)
    recent_events: list[dict[str, Any]] = Field(default_factory=list)
    total_token_usage: dict[str, int] = Field(default_factory=dict)


class WorkflowStepResponse(BaseModel):
    id: str
    step_id: str
    workflow_id: str
    step_key: str
    agent_id: str
    legacy_role: str
    title: str
    description: str
    status: str
    requires_approval: bool
    input_data: dict[str, Any] = Field(default_factory=dict)
    output_data: dict[str, Any] = Field(default_factory=dict)
    output: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None


class WorkflowResponse(BaseModel):
    id: str
    workflow_id: str
    title: str
    goal: str
    template_id: str
    legacy_template_id: str
    project_path: str | None = None
    provider: str
    model: str | None = None
    approval_mode: str
    status: str
    current_stage: str | None = None
    created_at: str
    updated_at: str
    completed_at: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    active_agent_id: str | None = None
    steps: list[WorkflowStepResponse] = Field(default_factory=list)
