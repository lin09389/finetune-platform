"""Public workflow-facing models backed by the internal agent runtime."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


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


class WorkflowAgentResponse(BaseModel):
    id: str
    name: str
    description: str = ""


class WorkflowStepTemplateResponse(BaseModel):
    key: str
    agent_id: str
    legacy_role: str
    title: str
    description: str
    artifact_type: str
    requires_approval: bool


class WorkflowTemplateResponse(BaseModel):
    id: str
    name: str
    description: str
    legacy_template_id: str
    agents: list[WorkflowAgentResponse] = Field(default_factory=list)
    steps: list[WorkflowStepTemplateResponse] = Field(default_factory=list)
    default_provider: str = "minimax"
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
