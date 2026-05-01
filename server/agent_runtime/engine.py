"""Internal engine that orchestrates phase-1 workflow execution."""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from time import perf_counter
from typing import Any

from fastapi import HTTPException

from digital_team.models import AgentOutput, TaskStatus
from digital_team.repository import DigitalTeamRepository

from .definitions import RuntimeExecutionContext, StepDefinition, WorkflowDefinition
from .templates import get_workflow_definition

logger = logging.getLogger(__name__)


@dataclass
class StepRetryPolicy:
    """Policy governing automatic retries for step-level LLM failures."""

    max_retries: int = 1
    retry_on: tuple[type[Exception], ...] = (RuntimeError, TimeoutError, ConnectionError)
    backoff_seconds: float = 2.0


class AgentRuntimeEngine:
    def __init__(
        self,
        repository: DigitalTeamRepository,
        runner: Any,
        context_builder: Any | None = None,
        memory_curator: Any | None = None,
        action_service: Any | None = None,
        agent_registry: Any | None = None,
        retry_policy: StepRetryPolicy | None = None,
    ):
        self.repository = repository
        self.runner = runner
        self.context_builder = context_builder
        self.memory_curator = memory_curator
        self.action_service = action_service
        self.agent_registry = agent_registry
        self.retry_policy = retry_policy or StepRetryPolicy()

    def get_workflow(self, template_id: str) -> WorkflowDefinition:
        if hasattr(self.repository, "get_template"):
            workflow = self.repository.get_template(template_id)
            if workflow is not None:
                return workflow
        workflow = get_workflow_definition(template_id)
        if workflow is None:
            raise HTTPException(status_code=400, detail="Unknown digital team template")
        return workflow

    async def start(self, project: dict[str, Any], project_context: str = "") -> dict[str, Any]:
        workflow = self.get_workflow(project["template_id"])
        step = self._ordered_steps(workflow)[0]
        self.repository.update_project(
            project["id"],
            status="running",
            current_stage=step.key,
            metadata={**(project.get("metadata") or {}), "active_agent_id": (project.get("metadata") or {}).get("primary_agent_id") or step.agent_id},
        )
        self.repository.add_event(project["id"], None, "workflow_started", "system", f"{step.title} 开始执行")
        await self._run_until_pause(project, workflow, project_context, start_index=0, previous_outputs=[])
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

        steps = self._ordered_steps(workflow)
        current_index = self._step_index(steps, task)
        previous_outputs = [item.get("output", {}) for item in project.get("tasks", []) if item.get("output")]
        await self._run_until_pause(project, workflow, project_context, current_index + 1, previous_outputs)
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
        steps = self._ordered_steps(workflow)
        current_index = self._step_index(steps, task)
        previous_outputs = [
            item.get("output", {})
            for item in project.get("tasks", [])
            if item.get("sort_order", 0) < task.get("sort_order", current_index) and item.get("output")
        ]
        await self._run_until_pause(project, workflow, project_context, current_index, previous_outputs)
        return self.repository.get_project(project["id"]) or project

    async def _run_until_pause(
        self,
        project: dict[str, Any],
        workflow: WorkflowDefinition,
        project_context: str,
        start_index: int,
        previous_outputs: list[dict[str, Any]],
    ) -> None:
        steps = self._ordered_steps(workflow)
        if start_index >= len(steps):
            self.repository.update_project(
                project["id"],
                status="completed",
                current_stage="completed",
                completed_at=datetime.now().isoformat(),
            )
            self.repository.add_event(project["id"], None, "workflow_completed", "system", "工作流已完成")
            await self._curate_memory(project["id"])
            return

        for index in range(start_index, len(steps)):
            step = steps[index]
            output = await self._run_step(project, workflow, step, project_context, previous_outputs, index)
            if output is None:
                return
            previous_outputs.append(output.model_dump())
            if output.needs_manual_review or (
                step.requires_approval and not (step.agent_id == "reviewer" and self._review_approved(output))
            ):
                self.repository.update_project(
                    project["id"],
                    status="awaiting_approval",
                    current_stage=f"{step.key}_approval",
                )
                return

        self.repository.update_project(
            project["id"],
            status="completed",
            current_stage="completed",
            completed_at=datetime.now().isoformat(),
        )
        self.repository.add_event(project["id"], None, "workflow_completed", "system", "工作流已完成")
        await self._curate_memory(project["id"])

    async def _run_step(
        self,
        project: dict[str, Any],
        workflow: WorkflowDefinition,
        step: StepDefinition,
        project_context: str,
        previous_outputs: list[dict[str, Any]],
        index: int,
    ) -> AgentOutput | None:
        trace_id = str(uuid.uuid4())
        existing = next(
            (
                task
                for task in project.get("tasks", [])
                if task.get("step_key") == step.key and task.get("status") != TaskStatus.FAILED.value
            ),
            None,
        )
        if existing:
            task = existing
        else:
            try:
                task = self.repository.create_task(
                    project_id=project["id"],
                    role=step.agent_id,
                    title=step.title,
                    description=step.description,
                    status=TaskStatus.RUNNING.value,
                    input_data={"goal": project["goal"], "previous_outputs": previous_outputs},
                    requires_approval=step.requires_approval,
                    step_key=step.key,
                    sort_order=index,
                )
            except TypeError:
                task = self.repository.create_task(
                    project_id=project["id"],
                    role=step.legacy_role or step.agent_id,
                    title=step.title,
                    description=step.description,
                    status=TaskStatus.RUNNING.value,
                    input_data={"goal": project["goal"], "previous_outputs": previous_outputs},
                    requires_approval=step.requires_approval,
                )
        self.repository.update_project(project["id"], status="running", current_stage=step.key)
        self.repository.update_project(
            project["id"],
            metadata={**(project.get("metadata") or {}), "active_agent_id": step.agent_id, "blocked_state": None},
        )
        started_at = datetime.now().isoformat()
        start_time = perf_counter()
        if hasattr(self.repository, "add_step_log"):
            self.repository.add_step_log(
                project["id"],
                task["id"],
                step.key,
                step.agent_id,
                "started",
                provider=project.get("provider"),
                model=project.get("model"),
                input_summary=project.get("goal", "")[:500],
                started_at=started_at,
                metadata={"trace_id": trace_id},
            )

        # Retry loop
        last_exc: Exception | None = None
        for attempt in range(1 + self.retry_policy.max_retries):
            if attempt > 0:
                self.repository.add_event(
                    project["id"],
                    task["id"],
                    "step_retry_attempt",
                    step.agent_id,
                    f"{step.title} 第 {attempt + 1} 次尝试（前次失败：{last_exc}）",
                    {"attempt": attempt + 1, "previous_error": str(last_exc), "trace_id": trace_id},
                )
                await asyncio.sleep(self.retry_policy.backoff_seconds * attempt)

            try:
                output = await self._execute_step_core(
                    project, workflow, step, task, previous_outputs, project_context, trace_id,
                )
                # Success — record and return
                auto_approved_review = step.agent_id == "reviewer" and self._review_approved(output)
                task_status = (
                    TaskStatus.NEEDS_MANUAL_REVIEW.value
                    if output.needs_manual_review
                    else (
                        TaskStatus.AWAITING_APPROVAL.value
                        if step.requires_approval and not auto_approved_review
                        else TaskStatus.COMPLETED.value
                    )
                )
                self.repository.update_task(
                    task["id"],
                    status=task_status,
                    output=output.model_dump(),
                    completed_at=None if task_status in {TaskStatus.AWAITING_APPROVAL.value, TaskStatus.NEEDS_MANUAL_REVIEW.value} else datetime.now().isoformat(),
                )
                self.repository.add_artifact(
                    project["id"],
                    task["id"],
                    step.artifact_type,
                    step.artifact_title or step.title,
                    output.model_dump(),
                )
                if self.action_service:
                    self.action_service.extract_from_output(project["id"], task["id"], output)
                if step.agent_id == "reviewer":
                    self.repository.add_review(
                        project["id"],
                        task["id"],
                        approved=self._review_approved(output),
                        summary=output.summary,
                        risks=output.risks,
                    )
                self.repository.add_event(
                    project["id"],
                    task["id"],
                    "agent_output",
                    step.agent_id,
                    f"{step.title} 已完成" if task_status == TaskStatus.COMPLETED.value else f"{step.title} 等待审批",
                    {**output.model_dump(), "trace_id": trace_id},
                )
                if output.needs_manual_review:
                    self.repository.update_project(
                        project["id"],
                        metadata={
                            **(project.get("metadata") or {}),
                            "blocked_state": {"reason": output.summary, "step_key": step.key, "agent_id": step.agent_id},
                        },
                    )
                if hasattr(self.repository, "add_step_log"):
                    self.repository.add_step_log(
                        project["id"],
                        task["id"],
                        step.key,
                        step.agent_id,
                        "completed" if task_status == TaskStatus.COMPLETED.value else task_status,
                        provider=project.get("provider"),
                        model=project.get("model"),
                        input_summary=project.get("goal", "")[:500],
                        output_summary=output.summary[:1000],
                        started_at=started_at,
                        completed_at=datetime.now().isoformat(),
                        duration_ms=int((perf_counter() - start_time) * 1000),
                        metadata={"needs_manual_review": output.needs_manual_review, "trace_id": trace_id, "attempt": attempt + 1},
                    )
                return output

            except Exception as exc:
                last_exc = exc
                is_retryable = isinstance(exc, self.retry_policy.retry_on)
                if is_retryable and attempt < self.retry_policy.max_retries:
                    logger.warning(
                        "Step %s attempt %d failed (retryable): %s",
                        step.key, attempt + 1, exc,
                    )
                    continue
                # Final failure
                if hasattr(self.repository, "add_step_log"):
                    self.repository.add_step_log(
                        project["id"],
                        task["id"],
                        step.key,
                        step.agent_id,
                        "failed",
                        provider=project.get("provider"),
                        model=project.get("model"),
                        input_summary=project.get("goal", "")[:500],
                        error=str(exc),
                        started_at=started_at,
                        completed_at=datetime.now().isoformat(),
                        duration_ms=int((perf_counter() - start_time) * 1000),
                        metadata={"trace_id": trace_id, "attempt": attempt + 1, "total_attempts": attempt + 1},
                    )
                self._mark_step_failed(project["id"], task["id"], step.agent_id, step.key, exc)
                return None

        # Should not reach here, but safety net
        return None

    async def _execute_step_core(
        self,
        project: dict[str, Any],
        workflow: WorkflowDefinition,
        step: StepDefinition,
        task: dict[str, Any],
        previous_outputs: list[dict[str, Any]],
        project_context: str,
        trace_id: str,
    ) -> AgentOutput:
        """Core step execution logic, separated for retry wrapping."""
        agent = workflow.agent_by_id(step.agent_id)
        available_subagents = self._available_subagents(step.agent_id)
        context = self._context_for_step(project, workflow, step, task, previous_outputs, project_context)
        step_input = {
            "goal": project["goal"],
            "previous_outputs": previous_outputs,
            "context_pack": context.context_pack,
            "context_sources": context.context_sources,
            "agent": agent.model_dump(),
            "step": step.model_dump(),
            "available_subagents": [item.model_dump() if hasattr(item, "model_dump") else item for item in available_subagents],
        }
        if (
            step.agent_id in {"planner", "implementer", "reviewer"}
            and hasattr(self.runner, "execute_tool_loop")
            and self.action_service is not None
        ):
            return await self.runner.execute_tool_loop(
                step.agent_id,
                context,
                step_input,
                project=project,
                task=task,
                repository=self.repository,
                action_service=self.action_service,
                trace_id=trace_id,
            )
        return await self._run_agent(step.agent_id, context, step_input)

    def _ordered_steps(self, workflow: WorkflowDefinition) -> list[StepDefinition]:
        if not workflow.steps:
            raise HTTPException(status_code=400, detail="Workflow template has no steps")
        return sorted(workflow.steps, key=lambda item: item.sort_order)

    def _step_index(self, steps: list[StepDefinition], task: dict[str, Any]) -> int:
        task_key = task.get("step_key")
        for index, step in enumerate(steps):
            if task_key and step.key == task_key:
                return index
            if step.legacy_role and step.legacy_role == task.get("role"):
                return index
            if step.agent_id == task.get("role"):
                return index
        raise HTTPException(status_code=400, detail="Workflow step is not part of its template")

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

    def _context_for_step(
        self,
        project: dict[str, Any],
        workflow: WorkflowDefinition,
        step: StepDefinition,
        task: dict[str, Any],
        previous_outputs: list[dict[str, Any]],
        project_context: str,
    ) -> RuntimeExecutionContext:
        if self.context_builder:
            return self.context_builder.build_for_step(project, workflow, step, task, previous_outputs, project_context)
        return self._context_from_project(project, project_context)

    def _available_subagents(self, agent_id: str) -> list[Any]:
        if not self.agent_registry:
            return []
        if agent_id == "planner":
            targets = {"explore"}
        elif agent_id == "implementer":
            targets = {"explore", "review"}
        else:
            targets = set()
        return [agent for agent in self.agent_registry.list_agents(include_hidden=True) if agent.id in targets]

    async def _curate_memory(self, workflow_id: str) -> None:
        if not self.memory_curator:
            return
        try:
            await self.memory_curator.curate_completed_workflow(workflow_id)
        except Exception as exc:
            logger.info("Workflow memory curation failed: %s", exc)
            self.repository.add_event(workflow_id, None, "memory_warning", "system", f"工作流记忆沉淀失败：{exc}")

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
        summary = (output.summary or "").strip()
        next_action = (output.next_action or "").strip()
        approval_text = f"{summary}\n{next_action}"
        negative_markers = ("不通过", "未通过", "失败", "不能交付", "需要人工")
        positive_markers = ("审查通过", "已通过", "通过", "可交付", "已完成")
        return any(marker in approval_text for marker in positive_markers) and not any(
            marker in approval_text for marker in negative_markers
        )
