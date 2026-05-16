"""Adapters between digital_team persistence shapes and runtime shapes."""

from __future__ import annotations

from typing import Any

from .definitions import WorkflowDefinition, WorkflowStepView, WorkflowView


def step_from_task(task: dict[str, Any], workflow: WorkflowDefinition) -> WorkflowStepView:
    if task.get("step_key"):
        step = workflow.step_by_key(task["step_key"])
    else:
        step = workflow.step_by_role(task["role"])
    return WorkflowStepView(
        id=task["id"],
        workflow_id=task["project_id"],
        step_key=step.key,
        agent_id=step.agent_id,
        legacy_role=step.legacy_role or task.get("role", step.agent_id),
        title=task["title"],
        description=task["description"],
        status=task["status"],
        requires_approval=bool(task.get("requires_approval")),
        input_data=task.get("input", {}) or {},
        output_data=task.get("output", {}) or {},
        error=task.get("error"),
    )


def workflow_from_project(project: dict[str, Any], workflow: WorkflowDefinition) -> WorkflowView:
    return WorkflowView(
        id=project["id"],
        title=project["title"],
        goal=project["goal"],
        template_id=workflow.id,
        status=project["status"],
        current_stage=project.get("current_stage"),
        provider=project["provider"],
        model=project.get("model"),
        project_path=project.get("project_path"),
        metadata=project.get("metadata", {}) or {},
        steps=[step_from_task(task, workflow) for task in project.get("tasks", [])],
    )
