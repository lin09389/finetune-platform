"""Internal engine that orchestrates phase-1 workflow execution."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from fastapi import HTTPException

from digital_team.models import AgentOutput, TaskStatus
from digital_team.repository import DigitalTeamRepository

from .definitions import RuntimeExecutionContext, StepDefinition, WorkflowDefinition
from .templates import get_workflow_definition

logger = logging.getLogger(__name__)


class AgentRuntimeEngine:
    def __init__(self, repository: DigitalTeamRepository, runner: Any):
        self.repository = repository
        self.runner = runner

    def get_workflow(self, template_id: str) -> WorkflowDefinition:
        workflow = get_workflow_definition(template_id)
        if workflow is None:
            raise HTTPException(status_code=400, detail="Unknown digital team template")
        return workflow

    async def start(self, project: dict[str, Any], project_context: str) -> dict[str, Any]:
        workflow = self.get_workflow(project["template_id"])
        step = workflow.step_by_key("plan")
        self.repository.update_project(
            project["id"],
            status="planning",
            current_stage=step.legacy_role,
        )
        self.repository.add_event(project["id"], None, "project_started", "system", "CEO Agent 开始拆解任务")
        context = self._context_from_project(project, project_context)
        await self._run_plan_step(project, step, context)
        return self.repository.get_project(project["id"]) or project

    async def approve(
        self,
        project: dict[str, Any],
        task: dict[str, Any],
        project_context: str,
        comment: str | None = None,
    ) -> dict[str, Any]:
        workflow = self.get_workflow(project["template_id"])
        self.repository.update_task(task["id"], status=TaskStatus.APPROVED.value)
        self.repository.add_event(project["id"], task["id"], "approval_granted", "user", comment or "审批通过")

        if task["role"] == workflow.step_by_key("plan").legacy_role:
            context = self._context_from_project(project, project_context)
            await self._run_implement_and_review(project, workflow, context, task)
        elif task["role"] == workflow.step_by_key("review").legacy_role:
            self.repository.update_project(
                project["id"],
                status="completed",
                current_stage="completed",
                completed_at=datetime.now().isoformat(),
            )
        return self.repository.get_project(project["id"]) or project

    async def reject(
        self,
        project: dict[str, Any],
        task: dict[str, Any],
        comment: str | None = None,
    ) -> dict[str, Any]:
        self.repository.update_task(task["id"], status=TaskStatus.FAILED.value, error=comment)
        self.repository.update_project(project["id"], status="failed")
        self.repository.add_event(project["id"], task["id"], "approval_rejected", "user", comment or "审批未通过")
        return self.repository.get_project(project["id"]) or project

    async def retry(self, project: dict[str, Any], task: dict[str, Any], project_context: str) -> dict[str, Any]:
        workflow = self.get_workflow(project["template_id"])
        context = self._context_from_project(project, project_context)
        if task["role"] == workflow.step_by_key("plan").legacy_role:
            return await self.start(project, project_context)
        if task["role"] in {
            workflow.step_by_key("implement").legacy_role,
            workflow.step_by_key("review").legacy_role,
        }:
            plan_task = next((item for item in project["tasks"] if item["role"] == workflow.step_by_key("plan").legacy_role), None)
            if not plan_task:
                raise HTTPException(status_code=400, detail="CEO task is required before retry")
            await self._run_implement_and_review(project, workflow, context, plan_task)
            return self.repository.get_project(project["id"]) or project
        raise HTTPException(status_code=400, detail="Unsupported task retry")

    async def _run_plan_step(
        self,
        project: dict[str, Any],
        step: StepDefinition,
        context: RuntimeExecutionContext,
    ) -> None:
        task = self.repository.create_task(
            project_id=project["id"],
            role=step.legacy_role,
            title=step.title,
            description=step.description,
            status=TaskStatus.RUNNING.value,
            input_data={"goal": project["goal"]},
            requires_approval=step.requires_approval,
        )
        try:
            output = await self._run_agent(step.agent_id, context, {"goal": project["goal"]})
            task_status = (
                TaskStatus.NEEDS_MANUAL_REVIEW.value
                if output.needs_manual_review
                else TaskStatus.AWAITING_APPROVAL.value
            )
            self.repository.update_task(task["id"], status=task_status, output=output.model_dump())
            self.repository.add_artifact(project["id"], task["id"], step.artifact_type, step.artifact_title, output.model_dump())
            self.repository.update_project(
                project["id"],
                status="awaiting_approval",
                current_stage="ceo_approval",
            )
            self.repository.add_event(
                project["id"],
                task["id"],
                "agent_output",
                step.legacy_role,
                "CEO Agent 已生成任务拆解，等待审批",
                output.model_dump(),
            )
        except Exception as exc:
            self._mark_step_failed(project["id"], task["id"], step.legacy_role, "ceo", exc)

    async def _run_implement_and_review(
        self,
        project: dict[str, Any],
        workflow: WorkflowDefinition,
        context: RuntimeExecutionContext,
        plan_task: dict[str, Any],
    ) -> None:
        implement_step = workflow.step_by_key("implement")
        review_step = workflow.step_by_key("review")

        self.repository.update_project(project["id"], status="implementing", current_stage=implement_step.legacy_role)
        developer_task = self.repository.create_task(
            project["id"],
            implement_step.legacy_role,
            implement_step.title,
            implement_step.description,
            TaskStatus.RUNNING.value,
            input_data={"ceo_output": plan_task.get("output", {})},
            requires_approval=implement_step.requires_approval,
        )
        try:
            developer_output = await self._run_agent(
                implement_step.agent_id,
                context,
                {"ceo_output": plan_task.get("output", {})},
            )
            dev_status = (
                TaskStatus.NEEDS_MANUAL_REVIEW.value
                if developer_output.needs_manual_review
                else TaskStatus.COMPLETED.value
            )
            self.repository.update_task(
                developer_task["id"],
                status=dev_status,
                output=developer_output.model_dump(),
                completed_at=None if developer_output.needs_manual_review else datetime.now().isoformat(),
            )
            self.repository.add_artifact(
                project["id"],
                developer_task["id"],
                implement_step.artifact_type,
                implement_step.artifact_title,
                developer_output.model_dump(),
            )
            self.repository.add_event(
                project["id"],
                developer_task["id"],
                "agent_output",
                implement_step.legacy_role,
                "程序员 Agent 已生成实现建议",
                developer_output.model_dump(),
            )
        except Exception as exc:
            self._mark_step_failed(project["id"], developer_task["id"], implement_step.legacy_role, "developer", exc)
            return

        self.repository.update_project(project["id"], status="reviewing", current_stage=review_step.legacy_role)
        reviewer_task = self.repository.create_task(
            project["id"],
            review_step.legacy_role,
            review_step.title,
            review_step.description,
            TaskStatus.RUNNING.value,
            input_data={"developer_output": developer_output.model_dump()},
            requires_approval=review_step.requires_approval,
        )
        try:
            reviewer_output = await self._run_agent(
                review_step.agent_id,
                context,
                {"developer_output": developer_output.model_dump()},
            )
            approved = self._review_approved(reviewer_output)
            next_status = "completed" if approved else "awaiting_approval"
            task_status = (
                TaskStatus.NEEDS_MANUAL_REVIEW.value
                if reviewer_output.needs_manual_review
                else (TaskStatus.COMPLETED.value if approved else TaskStatus.AWAITING_APPROVAL.value)
            )
            self.repository.update_task(reviewer_task["id"], status=task_status, output=reviewer_output.model_dump())
            self.repository.add_review(
                project["id"],
                reviewer_task["id"],
                approved=approved,
                summary=reviewer_output.summary,
                risks=reviewer_output.risks,
            )
            self.repository.add_artifact(
                project["id"],
                reviewer_task["id"],
                review_step.artifact_type,
                review_step.artifact_title,
                reviewer_output.model_dump(),
            )
            self.repository.update_project(
                project["id"],
                status=next_status,
                current_stage="completed" if approved else "reviewer_approval",
                completed_at=datetime.now().isoformat() if approved else None,
            )
            self.repository.add_event(
                project["id"],
                reviewer_task["id"],
                "agent_output",
                review_step.legacy_role,
                "质检 Agent 已完成审查" if approved else "质检 Agent 要求人工确认",
                reviewer_output.model_dump(),
            )
        except Exception as exc:
            self._mark_step_failed(project["id"], reviewer_task["id"], review_step.legacy_role, "reviewer", exc)

    async def _run_agent(
        self,
        agent_id: str,
        context: RuntimeExecutionContext,
        step_input: dict[str, Any],
    ) -> AgentOutput:
        if hasattr(self.runner, "execute"):
            return await self.runner.execute(agent_id, context, step_input)
        if agent_id == "planner":
            return await self.runner.run_ceo(
                goal=context.goal,
                project_path=context.project_path,
                project_context=context.project_context,
                provider=context.provider,
                model=context.model,
            )
        if agent_id == "implementer":
            return await self.runner.run_developer(
                goal=context.goal,
                ceo_output=step_input.get("ceo_output", {}),
                project_path=context.project_path,
                project_context=context.project_context,
                provider=context.provider,
                model=context.model,
            )
        if agent_id == "reviewer":
            return await self.runner.run_reviewer(
                goal=context.goal,
                developer_output=step_input.get("developer_output", {}),
                provider=context.provider,
                model=context.model,
            )
        raise RuntimeError(f"Unknown agent id: {agent_id}")

    def _context_from_project(self, project: dict[str, Any], project_context: str) -> RuntimeExecutionContext:
        return RuntimeExecutionContext(
            workflow_id=project["id"],
            goal=project["goal"],
            project_path=project.get("project_path"),
            project_context=project_context,
            provider=project["provider"],
            model=project.get("model"),
        )

    def _mark_step_failed(
        self,
        project_id: str,
        task_id: str,
        actor: str,
        stage: str,
        exc: Exception,
    ) -> None:
        logger.error("Runtime step failed: %s", exc, exc_info=True)
        self.repository.update_task(task_id, status=TaskStatus.FAILED.value, error=str(exc))
        self.repository.update_project(project_id, status="failed", current_stage=stage)
        self.repository.add_event(project_id, task_id, "error", actor, str(exc))

    def _review_approved(self, output: AgentOutput) -> bool:
        for artifact in output.artifacts:
            if isinstance(artifact, dict) and artifact.get("approved") is not None:
                return bool(artifact.get("approved"))
            if isinstance(artifact, dict) and isinstance(artifact.get("acceptance_result"), dict):
                return bool(artifact["acceptance_result"].get("approved"))
        return "通过" in output.summary and "不通过" not in output.summary
