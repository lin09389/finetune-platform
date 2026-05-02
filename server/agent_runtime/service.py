"""Workflow-facing facade for the internal multi-agent runtime."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from fastapi import HTTPException

from core.config import settings

from .actions import WorkflowActionService
from .agent_registry import AgentRegistry
from .adapters import workflow_from_project
from .context_builder import WorkflowContextBuilder
from .definitions import WorkflowDefinition, WorkflowView
from .engine import AgentRuntimeEngine
from .memory_curator import WorkflowMemoryCurator
from .models import (
    WorkflowContextProfile,
    WorkflowContextProfileUpdate,
    WorkflowContextSnapshotResponse,
    WorkflowActionResponse,
    WorkflowMemoryEntryResponse,
    WorkflowObservabilityResponse,
    WorkflowStepLogResponse,
    WorkflowToolCallResponse,
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
        agent_registry: AgentRegistry | None = None,
    ):
        self.repository = repository or WorkflowRuntimeRepository()
        self.runner = runner or AgentRuntimeRunner()
        self.agent_registry = agent_registry or AgentRegistry()
        self.context_builder = WorkflowContextBuilder(self.repository)
        self.memory_curator = WorkflowMemoryCurator(self.repository)
        self.action_service = WorkflowActionService(self.repository)
        self.engine = AgentRuntimeEngine(
            self.repository,
            self.runner,
            self.context_builder,
            self.memory_curator,
            self.action_service,
            self.agent_registry,
        )

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
        primary_agent_id = getattr(request, "agent_id", None) or "build"
        if self.agent_registry.get(primary_agent_id) is None:
            raise HTTPException(status_code=400, detail="Unknown agent id")
        data = request.model_dump()
        data["template_id"] = workflow.id
        data["project_path"] = project_path
        data["provider"] = data.get("provider") or workflow.default_provider
        data["model"] = data.get("model") or workflow.default_model
        data["approval_mode"] = data.get("approval_mode") or workflow.default_approval_mode
        project = self.repository.create_project(data)
        autonomy_mode = data.get("autonomy_mode") if data.get("autonomy_mode") in {"safe_auto", "confirm_all", "read_only"} else "safe_auto"
        metadata = {
            **(project.get("metadata") or {}),
            "primary_agent_id": primary_agent_id,
            "active_agent_id": primary_agent_id,
            "autonomy_mode": autonomy_mode,
            "subagent_runs": [],
            "auto_execution_policy": {
                "mode": autonomy_mode,
                "patch": "safe_small_patch",
                "command": "allowlisted_short_command",
            },
        }
        self.repository.update_project(project["id"], metadata=metadata)
        project = self._get_project(project["id"])
        return self._project_response(project, workflow)

    def list_workflows(self) -> list[WorkflowResponse]:
        return [self._project_response(project) for project in self.repository.list_projects()]

    def get_workflow(self, workflow_id: str) -> WorkflowResponse:
        return self._project_response(self._get_project(workflow_id))

    async def run_workflow(self, workflow_id: str) -> WorkflowResponse:
        project = self._get_project(workflow_id)
        updated = await self.engine.start(project)
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

        updated = await self.engine.approve(project, task, "", comment)
        return self._project_response(updated)

    async def retry_step(self, step_id: str) -> WorkflowResponse:
        task = self.repository.get_task(step_id)
        if not task:
            raise HTTPException(status_code=404, detail="Workflow step not found")
        project = self._get_project(task["project_id"])
        updated = await self.engine.retry(project, task, "")
        return self._project_response(updated)

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

    async def approve_action(self, action_id: str) -> WorkflowActionResponse:
        action = self.action_service.approve(action_id)
        if action.get("action_type") == "permission_request":
            action = await self._replay_permission_request(action)
        return WorkflowActionResponse(**action)

    def reject_action(self, action_id: str) -> WorkflowActionResponse:
        return WorkflowActionResponse(**self.action_service.reject(action_id))

    def execute_action(self, action_id: str) -> WorkflowActionResponse:
        return WorkflowActionResponse(**self.action_service.execute(action_id))

    async def _replay_permission_request(self, action: dict[str, Any]) -> dict[str, Any]:
        payload = dict(action.get("payload") or {})
        workflow_id = action.get("workflow_id")
        step_id = action.get("step_id")
        if not workflow_id or not step_id:
            return action

        project = self._get_project(workflow_id)
        metadata = dict(project.get("metadata") or {})
        overrides = list(metadata.get("permission_overrides") or [])
        overrides.append(
            {
                "permission": payload.get("permission"),
                "pattern": payload.get("pattern"),
                "tool_name": payload.get("tool_name"),
                "tool_arguments": payload.get("tool_arguments"),
                "agent_id": payload.get("agent_id"),
                "replay_of_call_id": payload.get("replay_of_call_id"),
            }
        )
        metadata["permission_overrides"] = overrides
        self.repository.update_project(workflow_id, metadata=metadata)
        self.repository.add_event(
            workflow_id,
            step_id,
            "permission_approved",
            "user",
            "权限请求已批准，正在重放工具调用",
            {
                "action_id": action["id"],
                "tool_name": payload.get("tool_name"),
                "replay_of_call_id": payload.get("replay_of_call_id"),
            },
        )
        task = self.repository.get_task(step_id)
        if task:
            project = self._get_project(workflow_id)
            await self.engine.retry(project, task, "")
        return self.action_service._get_action(action["id"])

    async def repair_after_failed_action(self, action_id: str) -> WorkflowActionResponse | None:
        action = self.action_service._get_action(action_id)
        if action.get("status") != "failed":
            return WorkflowActionResponse(**action)
        project = self._get_project(action["workflow_id"])
        metadata = dict(project.get("metadata") or {})
        attempts = int(metadata.get("repair_attempts") or 0)
        max_attempts = int(metadata.get("max_repair_attempts") or 1)
        if attempts >= max_attempts:
            metadata["repair_attempts"] = attempts
            metadata["max_repair_attempts"] = max_attempts
            self.repository.update_project(
                project["id"],
                status="needs_manual_review",
                current_stage="repair_manual_review",
                metadata=metadata,
            )
            self.repository.add_event(
                project["id"],
                action.get("step_id"),
                "repair_skipped",
                "system",
                "修复次数已达上限，需要人工确认",
                {"action_id": action_id, "repair_attempts": attempts},
            )
            return None

        metadata["repair_attempts"] = attempts + 1
        metadata["max_repair_attempts"] = max_attempts
        self.repository.update_project(project["id"], metadata=metadata)
        self.repository.add_event(
            project["id"],
            action.get("step_id"),
            "repair_attempt_started",
            "implementer",
            "动作执行失败，Agent 正在生成一次修复建议",
            {"action_id": action_id, "repair_attempts": attempts + 1},
        )
        if hasattr(self.runner, "repair_after_action_failure"):
            output = await self.runner.repair_after_action_failure(project, action)
            proposals = self.action_service.extract_from_output(project["id"], action.get("step_id"), output)
            self.repository.add_event(
                project["id"],
                action.get("step_id"),
                "repair_attempt_completed",
                "implementer",
                "修复建议已生成" if proposals else "修复建议需要人工审查",
                {"action_id": action_id, "repair_attempts": attempts + 1, "proposal_count": len(proposals)},
            )
            if proposals:
                return WorkflowActionResponse(**proposals[-1])
        return None

    def get_context_profile(self, workflow_id: str) -> WorkflowContextProfile:
        self._get_project(workflow_id)
        return WorkflowContextProfile(**self.repository.get_context_profile(workflow_id))

    def update_context_profile(self, workflow_id: str, request: WorkflowContextProfileUpdate) -> WorkflowContextProfile:
        project = self._get_project(workflow_id)
        data = request.model_dump()
        data["project_path"] = self._validate_project_path(data.get("project_path")) if data.get("project_path") else None
        profile = self.repository.upsert_context_profile(workflow_id, data)
        if data.get("project_path") != project.get("project_path"):
            self.repository.update_project(workflow_id, project_path=data.get("project_path"))
        self.repository.add_event(workflow_id, None, "context_profile_updated", "user", "工作流上下文配置已更新", data)
        return WorkflowContextProfile(**profile)

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

    def list_agents(self, primary_only: bool = False) -> list[dict[str, Any]]:
        agents = self.agent_registry.list_primary_agents() if primary_only else self.agent_registry.list_agents()
        return [agent.model_dump() for agent in agents]

    def get_agent(self, agent_id: str) -> dict[str, Any]:
        agent = self.agent_registry.get(agent_id)
        if agent is None:
            raise HTTPException(status_code=404, detail="Agent not found")
        return agent.model_dump()

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
