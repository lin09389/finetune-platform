"""Workflow-facing facade for the internal multi-agent runtime."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from fastapi import HTTPException

from core.config import settings

from .adapters import workflow_from_project
from .definitions import WorkflowDefinition, WorkflowView
from .engine import AgentRuntimeEngine
from .models import (
    WorkflowAgentResponse,
    WorkflowCreate,
    WorkflowResponse,
    WorkflowTemplateCreate,
    WorkflowStepResponse,
    WorkflowStepTemplateResponse,
    WorkflowTemplateUpdate,
    WorkflowTemplateResponse,
)
from .repository import WorkflowRuntimeRepository
from .runner import AgentRuntimeRunner

logger = logging.getLogger(__name__)


class AgentRuntimeService:
    """Facade that exposes workflow language while reusing digital_team storage."""

    def __init__(
        self,
        repository: WorkflowRuntimeRepository | None = None,
        runner: AgentRuntimeRunner | None = None,
    ):
        self.repository = repository or WorkflowRuntimeRepository()
        self.runner = runner or AgentRuntimeRunner()
        self.engine = AgentRuntimeEngine(self.repository, self.runner)

    def list_templates(self) -> list[WorkflowTemplateResponse]:
        return [self._template_response(template) for template in self.repository.list_templates()]

    def get_template(self, template_id: str) -> WorkflowTemplateResponse:
        return self._template_response(self._get_workflow_definition(template_id))

    def create_template(self, request: WorkflowTemplateCreate) -> WorkflowTemplateResponse:
        try:
            return self._template_response(self.repository.create_template(request))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    def update_template(self, template_id: str, request: WorkflowTemplateUpdate) -> WorkflowTemplateResponse:
        try:
            return self._template_response(self.repository.update_template(template_id, request))
        except PermissionError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Workflow template not found") from exc

    def delete_template(self, template_id: str) -> dict[str, bool]:
        try:
            self.repository.delete_template(template_id)
            return {"deleted": True}
        except PermissionError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Workflow template not found") from exc

    def create_workflow(self, request: WorkflowCreate) -> WorkflowResponse:
        workflow = self._get_workflow_definition(request.template_id)
        if not workflow.is_enabled:
            raise HTTPException(status_code=400, detail="Workflow template is disabled")
        project_path = self._validate_project_path(request.project_path)
        data = request.model_dump()
        data["template_id"] = workflow.id
        data["project_path"] = project_path
        data["provider"] = data.get("provider") or workflow.default_provider
        data["model"] = data.get("model") or workflow.default_model
        data["approval_mode"] = data.get("approval_mode") or workflow.default_approval_mode
        project = self.repository.create_project(data)
        return self._project_response(project, workflow)

    def list_workflows(self) -> list[WorkflowResponse]:
        return [self._project_response(project) for project in self.repository.list_projects()]

    def get_workflow(self, workflow_id: str) -> WorkflowResponse:
        return self._project_response(self._get_project(workflow_id))

    async def run_workflow(self, workflow_id: str) -> WorkflowResponse:
        project = self._get_project(workflow_id)
        context = self._project_context(project.get("project_path"), project["goal"])
        updated = await self.engine.start(project, context)
        return self._project_response(updated)

    async def approve_step(
        self,
        step_id: str,
        approved: bool = True,
        comment: str | None = None,
    ) -> WorkflowResponse:
        task = self.repository.get_task(step_id)
        if not task:
            raise HTTPException(status_code=404, detail="Workflow step not found")
        project = self._get_project(task["project_id"])
        if not approved:
            updated = await self.engine.reject(project, task, comment)
            return self._project_response(updated)

        context = self._project_context(project.get("project_path"), project["goal"])
        updated = await self.engine.approve(project, task, context, comment)
        return self._project_response(updated)

    async def retry_step(self, step_id: str) -> WorkflowResponse:
        task = self.repository.get_task(step_id)
        if not task:
            raise HTTPException(status_code=404, detail="Workflow step not found")
        project = self._get_project(task["project_id"])
        context = self._project_context(project.get("project_path"), project["goal"])
        updated = await self.engine.retry(project, task, context)
        return self._project_response(updated)

    def list_timeline(self, workflow_id: str) -> list[dict[str, Any]]:
        self._get_project(workflow_id)
        return self.repository.list_events(workflow_id)

    def list_artifacts(self, workflow_id: str) -> list[dict[str, Any]]:
        self._get_project(workflow_id)
        return self.repository.list_artifacts(workflow_id)

    def _get_project(self, workflow_id: str) -> dict[str, Any]:
        project = self.repository.get_project(workflow_id)
        if not project:
            raise HTTPException(status_code=404, detail="Workflow not found")
        return project

    def _get_workflow_definition(self, template_id: str) -> WorkflowDefinition:
        workflow = self.repository.get_template(template_id)
        if workflow is None:
            raise HTTPException(status_code=400, detail="Unknown workflow template")
        return workflow

    def _project_response(
        self,
        project: dict[str, Any],
        workflow: WorkflowDefinition | None = None,
    ) -> WorkflowResponse:
        workflow = workflow or self._get_workflow_definition(project["template_id"])
        view = workflow_from_project(project, workflow)
        return self._workflow_response(view, project, workflow)

    def _workflow_response(
        self,
        view: WorkflowView,
        project: dict[str, Any],
        workflow: WorkflowDefinition,
    ) -> WorkflowResponse:
        steps = [
            WorkflowStepResponse(
                id=step.id,
                step_id=step.id,
                workflow_id=step.workflow_id,
                step_key=step.step_key,
                agent_id=step.agent_id,
                legacy_role=step.legacy_role,
                title=step.title,
                description=step.description,
                status=step.status,
                requires_approval=step.requires_approval,
                input_data=step.input_data,
                output_data=step.output_data,
                output=step.output_data,
                error=step.error,
            )
            for step in view.steps
        ]
        return WorkflowResponse(
            id=view.id,
            workflow_id=view.id,
            title=view.title,
            goal=view.goal,
            template_id=view.template_id,
            legacy_template_id=workflow.legacy_template_id,
            project_path=view.project_path,
            provider=view.provider,
            model=view.model,
            approval_mode=project["approval_mode"],
            status=view.status,
            current_stage=view.current_stage,
            created_at=project["created_at"],
            updated_at=project["updated_at"],
            completed_at=project.get("completed_at"),
            metadata=view.metadata,
            steps=steps,
        )

    def _template_response(self, workflow: WorkflowDefinition) -> WorkflowTemplateResponse:
        return WorkflowTemplateResponse(
            id=workflow.id,
            name=workflow.name,
            description=workflow.description,
            legacy_template_id=workflow.legacy_template_id,
            is_builtin=workflow.is_builtin,
            is_enabled=workflow.is_enabled,
            default_provider=workflow.default_provider,
            default_model=workflow.default_model,
            default_approval_mode=workflow.default_approval_mode,
            agents=[
                WorkflowAgentResponse(
                    id=agent.id,
                    agent_id=agent.id,
                    name=agent.name,
                    description=agent.description,
                    system_prompt=agent.system_prompt,
                    output_requirements=agent.output_requirements,
                )
                for agent in workflow.agents
            ],
            steps=[
                WorkflowStepTemplateResponse(
                    key=step.key,
                    step_key=step.key,
                    agent_id=step.agent_id,
                    legacy_role=step.legacy_role,
                    title=step.title,
                    description=step.description,
                    artifact_type=step.artifact_type,
                    requires_approval=step.requires_approval,
                    sort_order=step.sort_order,
                )
                for step in workflow.steps
            ],
        )

    def _validate_project_path(self, project_path: str | None) -> str | None:
        if not project_path or not project_path.strip():
            return None
        resolved = Path(project_path).resolve()
        cwd = Path.cwd().resolve()
        roots = {cwd, settings.base_dir.resolve()}
        for root in list(roots):
            if root.name == "server":
                roots.add(root.parent)

        workspace_env = os.getenv("WORKSPACE_ROOT") or os.getenv("PROJECT_ROOT")
        if workspace_env:
            roots.add(Path(workspace_env).resolve())

        if not any(resolved == root or resolved.is_relative_to(root) for root in roots):
            allowed = ", ".join(str(root) for root in sorted(roots, key=lambda item: str(item)))
            raise HTTPException(
                status_code=400,
                detail=f"project_path must be inside the workspace. Allowed roots: {allowed}",
            )
        return str(resolved)

    def _project_context(self, project_path: str | None, goal: str) -> str:
        if not project_path:
            return ""
        try:
            from context.service import get_context_service

            service = get_context_service()
            return service.get_context_for_chat(query=goal, project_path=project_path, max_length=1800)
        except Exception as exc:
            logger.info("Workflow project context unavailable: %s", exc)
            return ""
