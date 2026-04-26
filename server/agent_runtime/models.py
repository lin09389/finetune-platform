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
    provider: str = "minimax"
    model: str | None = None
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
    steps: list[WorkflowStepResponse] = Field(default_factory=list)
