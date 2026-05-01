from __future__ import annotations

from typing import Any

from fastapi import HTTPException

from agent_runtime.models import WorkflowCreate
from agent_runtime.service import AgentRuntimeService

from .intent import ChatAgentIntentClassifier
from .models import ChatAgentIntentRequest, ChatAgentIntentResponse, ChatAgentRunCreate, ChatAgentRunEvent, ChatAgentRunResponse
from .repository import ChatAgentRepository


class ChatAgentService:
    def __init__(
        self,
        runtime: AgentRuntimeService,
        repository: ChatAgentRepository | None = None,
        classifier: ChatAgentIntentClassifier | None = None,
    ):
        self.runtime = runtime
        self.repository = repository or ChatAgentRepository(runtime.repository.db_path)
        self.classifier = classifier or ChatAgentIntentClassifier()

    def create_run(self, request: ChatAgentRunCreate) -> ChatAgentRunResponse:
        should_agent, intent_type = self.classifier.classify(request.content, request.force_agent)
        if not should_agent:
            return ChatAgentRunResponse(
                id="",
                mode="chat",
                chat_session_id=request.chat_session_id,
                trigger_message_id=request.message_id,
                status="chat",
                intent_type=intent_type,
                summary="继续普通对话",
            )

        workflow = self.runtime.create_workflow(
            WorkflowCreate(
                title=request.content.strip()[:30],
                goal=request.content.strip(),
                template_id=request.template_id or "software_delivery",
                project_path=request.project_path,
                chat_session_id=request.chat_session_id,
                include_chat_context=bool(request.chat_session_id),
                include_project_context=True,
                include_memory=True,
                max_context_chars=6000,
                provider=request.provider or "minimax",
                model=request.model,
                agent_id=request.agent_id or "build",
                approval_mode="manual",
            )
        )
        run = self.repository.create_run(
            chat_session_id=request.chat_session_id,
            trigger_message_id=request.message_id,
            workflow_id=workflow.workflow_id,
            intent_type=intent_type,
            summary=f"已创建 Agent 工作流：{workflow.title}",
            metadata={"template_id": workflow.template_id, "primary_agent_id": request.agent_id or "build"},
        )
        return self._response(run, workflow=workflow)

    async def classify_intent(self, request: ChatAgentIntentRequest) -> ChatAgentIntentResponse:
        decision = await self.classifier.route(
            request.content,
            routing_mode=request.routing_mode,
            provider=request.provider,
            model=request.model,
            agent_id=request.agent_id,
            template_id=request.template_id,
        )
        return ChatAgentIntentResponse(**decision)

    def get_run(self, run_id: str) -> ChatAgentRunResponse:
        return self._response(self._get_run(run_id))

    async def run(self, run_id: str) -> ChatAgentRunResponse:
        run = self._get_run(run_id)
        workflow_id = run.get("workflow_id")
        if not workflow_id:
            raise HTTPException(status_code=400, detail="Chat agent run has no workflow")
        self.repository.update_run(run_id, status="running")
        workflow = await self.runtime.run_workflow(workflow_id)
        status = "completed" if workflow.status == "completed" else workflow.status
        run = self.repository.update_run(run_id, status=status, summary=self._summarize_workflow(workflow.model_dump()))
        return self._response(run, workflow=workflow)

    async def approve_step(self, step_id: str, approved: bool = True, comment: str | None = None) -> ChatAgentRunResponse:
        workflow = await self.runtime.approve_step(step_id, approved=approved, comment=comment)
        run = self.repository.get_run_by_workflow(workflow.workflow_id)
        if not run:
            raise HTTPException(status_code=404, detail="Chat agent run not found")
        self.repository.update_run(run["id"], status=workflow.status, summary=self._summarize_workflow(workflow.model_dump()))
        return self._response(self._get_run(run["id"]), workflow=workflow)

    async def approve_action(self, action_id: str):
        action = await self.runtime.approve_action(action_id)
        self._sync_action_run(action.workflow_id, "action_approved", action.id)
        return action

    def reject_action(self, action_id: str):
        action = self.runtime.reject_action(action_id)
        self._sync_action_run(action.workflow_id, "action_rejected", action.id)
        return action

    def execute_action(self, action_id: str):
        action = self.runtime.execute_action(action_id)
        event_type = "action_failed" if action.status == "failed" else "action_executed"
        self._sync_action_run(action.workflow_id, event_type, action.id)
        return action

    async def execute_action_with_repair(self, action_id: str):
        action = self.runtime.execute_action(action_id)
        event_type = "action_failed" if action.status == "failed" else "action_executed"
        self._sync_action_run(action.workflow_id, event_type, action.id)
        if action.status == "failed":
            await self.runtime.repair_after_failed_action(action.id)
            self._sync_action_run(action.workflow_id, "repair_attempt", action.id)
        return action

    def list_tool_calls(self, run_id: str):
        run = self._get_run(run_id)
        workflow_id = run.get("workflow_id")
        if not workflow_id:
            return []
        return self.runtime.list_tool_calls(workflow_id)

    def list_events(self, run_id: str) -> list[ChatAgentRunEvent]:
        run = self._get_run(run_id)
        workflow_id = run.get("workflow_id")
        if not workflow_id:
            return []
        events = self.runtime.list_timeline(workflow_id)
        return [self._event_from_workflow(run_id, workflow_id, event) for event in events]

    def _get_run(self, run_id: str) -> dict[str, Any]:
        run = self.repository.get_run(run_id)
        if not run:
            raise HTTPException(status_code=404, detail="Chat agent run not found")
        return run

    def _response(self, run: dict[str, Any], workflow: Any | None = None) -> ChatAgentRunResponse:
        workflow_id = run.get("workflow_id")
        workflow = workflow or (self.runtime.get_workflow(workflow_id) if workflow_id else None)
        observability = self.runtime.get_observability(workflow_id) if workflow_id else None
        events = self.runtime.list_timeline(workflow_id) if workflow_id else []
        metadata = dict((workflow.metadata if workflow else {}) or {})
        final_summary = self._latest_output_summary(workflow.model_dump() if workflow and hasattr(workflow, "model_dump") else {})
        execution_state = metadata.get("execution_state")
        blocked_state = metadata.get("blocked_state")
        recoverable = bool(
            workflow
            and (
                workflow.status in {"running", "awaiting_approval", "needs_manual_review"}
                or metadata.get("permission_pending")
                or blocked_state
            )
        )
        return ChatAgentRunResponse(
            id=run["id"],
            mode="agent",
            chat_session_id=run.get("chat_session_id"),
            trigger_message_id=run.get("trigger_message_id"),
            workflow_id=workflow_id,
            status=run.get("status") or (workflow.status if workflow else "created"),
            intent_type=run.get("intent_type"),
            summary=run.get("summary") or "",
            final_summary=final_summary or None,
            execution_state=execution_state,
            execution_state_message=metadata.get("execution_state_message"),
            recoverable=recoverable,
            details_url=f"/workflows?workflow={workflow_id}" if workflow_id else None,
            active_agent_id=metadata.get("active_agent_id"),
            subagent_runs=list(metadata.get("subagent_runs") or []),
            auto_execution_policy=dict(metadata.get("auto_execution_policy") or {}),
            blocked_state=blocked_state,
            workflow=workflow,
            observability=observability,
            latest_event=events[-1] if events else None,
        )

    def _event_from_workflow(self, run_id: str, workflow_id: str, event: dict[str, Any]) -> ChatAgentRunEvent:
        payload = dict(event.get("payload") or {})
        payload.update({"workflow_event_id": event.get("id"), "step_id": event.get("step_id") or event.get("task_id")})
        return ChatAgentRunEvent(
            event_type=str(event.get("event_type") or "workflow_event"),
            run_id=run_id,
            workflow_id=workflow_id,
            message=str(event.get("message") or ""),
            payload=payload,
        )

    def _sync_action_run(self, workflow_id: str, message_type: str, action_id: str) -> None:
        run = self.repository.get_run_by_workflow(workflow_id)
        if not run:
            return
        self.repository.add_run_message(run["id"], message_type, action_id=action_id)
        workflow = self.runtime.get_workflow(workflow_id)
        self.repository.update_run(run["id"], status=message_type, summary=self._summarize_workflow(workflow.model_dump()))

    def _summarize_workflow(self, workflow: dict[str, Any]) -> str:
        status = workflow.get("status", "running")
        current = workflow.get("current_stage") or "workflow"
        final_summary = self._latest_output_summary(workflow)
        if final_summary and status in {"completed", "awaiting_approval", "needs_manual_review"}:
            prefix = "最终结果" if status == "completed" else "当前结果"
            return f"{prefix}：{final_summary}"
        return f"Agent 工作流状态：{status}，当前阶段：{current}"

    def _latest_output_summary(self, workflow: dict[str, Any]) -> str:
        steps = workflow.get("steps") or workflow.get("tasks") or []
        if not isinstance(steps, list):
            return ""
        for step in reversed(steps):
            if not isinstance(step, dict):
                continue
            output = step.get("output") or step.get("output_data") or {}
            if not isinstance(output, dict):
                continue
            summary = str(output.get("summary") or "").strip()
            if summary:
                return summary
        return ""
