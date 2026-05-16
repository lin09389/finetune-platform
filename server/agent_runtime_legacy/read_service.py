from __future__ import annotations

import logging
from typing import Any

from fastapi import HTTPException

from agent_runtime_legacy.adapters import workflow_from_project
from agent_runtime_legacy.definitions import WorkflowDefinition, WorkflowView
from agent_runtime_legacy.models import (
    WorkflowActionResponse,
    WorkflowContextProfile,
    WorkflowContextSnapshotResponse,
    WorkflowMemoryEntryResponse,
    WorkflowObservabilityResponse,
    WorkflowResponse,
    WorkflowStepLogResponse,
    WorkflowStepResponse,
    WorkflowToolCallResponse,
)
from agent_runtime_legacy.repository import WorkflowRuntimeRepository

logger = logging.getLogger(__name__)


class LegacyWorkflowReadService:
    """Read-only access to retired workflow records."""

    def __init__(self, repository: WorkflowRuntimeRepository | None = None):
        self.repository = repository or WorkflowRuntimeRepository()

    def get_workflow(self, workflow_id: str) -> WorkflowResponse:
        return self._project_response(self._get_project(workflow_id))

    def list_timeline(self, workflow_id: str) -> list[dict[str, Any]]:
        self._get_project(workflow_id)
        return self.repository.list_events(workflow_id)

    def list_artifacts(self, workflow_id: str) -> list[dict[str, Any]]:
        self._get_project(workflow_id)
        return self.repository.list_artifacts(workflow_id)

    def get_observability(self, workflow_id: str) -> WorkflowObservabilityResponse:
        project = self._get_project(workflow_id)
        events = self.repository.list_events(workflow_id)
        metadata = dict(project.get("metadata") or {})
        return WorkflowObservabilityResponse(
            workflow_id=workflow_id,
            status=project["status"],
            current_stage=project.get("current_stage"),
            active_agent_id=metadata.get("active_agent_id"),
            subagent_runs=list(metadata.get("subagent_runs") or []),
            auto_execution_policy=dict(metadata.get("auto_execution_policy") or {}),
            blocked_state=metadata.get("blocked_state"),
            step_logs=self.list_step_logs(workflow_id),
            tool_calls=self.list_tool_calls(workflow_id),
            actions=self.list_actions(workflow_id),
            recent_events=events[-20:],
        )

    def list_step_logs(self, workflow_id: str) -> list[WorkflowStepLogResponse]:
        self._get_project(workflow_id)
        return [WorkflowStepLogResponse(**item) for item in self.repository.list_step_logs(workflow_id)]

    def list_tool_calls(self, workflow_id: str) -> list[WorkflowToolCallResponse]:
        self._get_project(workflow_id)
        return [WorkflowToolCallResponse(**item) for item in self.repository.list_tool_calls(workflow_id)]

    def list_actions(self, workflow_id: str) -> list[WorkflowActionResponse]:
        self._get_project(workflow_id)
        return [WorkflowActionResponse(**item) for item in self.repository.list_action_proposals(workflow_id)]

    def get_context_profile(self, workflow_id: str) -> WorkflowContextProfile:
        self._get_project(workflow_id)
        return WorkflowContextProfile(**self.repository.get_context_profile(workflow_id))

    def list_context_snapshots(self, workflow_id: str) -> list[WorkflowContextSnapshotResponse]:
        self._get_project(workflow_id)
        return [WorkflowContextSnapshotResponse(**item) for item in self.repository.list_context_snapshots(workflow_id)]

    def list_memory_entries(self, workflow_id: str) -> list[WorkflowMemoryEntryResponse]:
        self._get_project(workflow_id)
        return [WorkflowMemoryEntryResponse(**item) for item in self.repository.list_memory_entries(workflow_id)]

    def revert_memory_entry(self, memory_id: str) -> WorkflowMemoryEntryResponse:
        try:
            memory = self.repository.revert_memory_entry(memory_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Workflow memory not found") from exc
        external_key = memory.get("external_memory_id")
        if external_key:
            try:
                from memory.preference_learner import get_preference_learner

                get_preference_learner().delete_preference("default", external_key)
            except Exception as exc:
                logger.info("Failed to delete external preference %s: %s", external_key, exc)
        return WorkflowMemoryEntryResponse(**memory)

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
            active_agent_id=(project.get("metadata") or {}).get("active_agent_id"),
            steps=steps,
        )
