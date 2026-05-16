from __future__ import annotations

from fastapi import HTTPException

from agent_runtime_legacy.models import (
    WorkflowAgentResponse,
    WorkflowStepTemplateResponse,
    WorkflowTemplateCreate,
    WorkflowTemplateResponse,
    WorkflowTemplateUpdate,
)
from agent_runtime_legacy.definitions import WorkflowDefinition
from agent_runtime_legacy.repository import WorkflowRuntimeRepository


class WorkflowTemplateService:
    def __init__(self, repository: WorkflowRuntimeRepository | None = None):
        self.repository = repository or WorkflowRuntimeRepository()

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

    def _get_workflow_definition(self, template_id: str) -> WorkflowDefinition:
        workflow = self.repository.get_template(template_id)
        if workflow is None:
            raise HTTPException(status_code=400, detail="Unknown workflow template")
        return workflow

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
