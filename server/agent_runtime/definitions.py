"""Internal runtime definitions for the phase-1 multi-agent engine."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class AgentDefinition(BaseModel):
    id: str
    name: str
    description: str = ""


class StepDefinition(BaseModel):
    key: str
    agent_id: str
    legacy_role: str
    title: str
    description: str
    artifact_type: str
    artifact_title: str
    requires_approval: bool = True


class WorkflowDefinition(BaseModel):
    id: str
    name: str
    description: str
    legacy_template_id: str
    agents: list[AgentDefinition] = Field(default_factory=list)
    steps: list[StepDefinition] = Field(default_factory=list)

    def step_by_key(self, key: str) -> StepDefinition:
        for step in self.steps:
            if step.key == key:
                return step
        raise KeyError(f"Unknown step key: {key}")

    def step_by_role(self, legacy_role: str) -> StepDefinition:
        for step in self.steps:
            if step.legacy_role == legacy_role:
                return step
        raise KeyError(f"Unknown legacy role: {legacy_role}")


class RuntimeExecutionContext(BaseModel):
    workflow_id: str
    goal: str
    project_path: str | None = None
    project_context: str = ""
    provider: str
    model: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class WorkflowStepView(BaseModel):
    id: str
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
    error: str | None = None


class WorkflowView(BaseModel):
    id: str
    title: str
    goal: str
    template_id: str
    status: str
    current_stage: str | None = None
    provider: str
    model: str | None = None
    project_path: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    steps: list[WorkflowStepView] = Field(default_factory=list)
