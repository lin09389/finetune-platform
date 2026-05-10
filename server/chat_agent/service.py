from __future__ import annotations

from typing import Any

from fastapi import HTTPException

from agent_runtime.models import WorkflowCreate
from agent_runtime.service import AgentRuntimeService

from .acceptance import AcceptanceReportGenerator
from .intent import ChatAgentIntentClassifier
from .models import ChatAgentIntentRequest, ChatAgentIntentResponse, ChatAgentRunCreate, ChatAgentRunEvent, ChatAgentRunResponse
from .repository import ChatAgentRepository


class ChatAgentService:
    def __init__(
        self,
        runtime: AgentRuntimeService,
        repository: ChatAgentRepository | None = None,
        classifier: ChatAgentIntentClassifier | None = None,
        acceptance_generator: AcceptanceReportGenerator | None = None,
    ):
        self.runtime = runtime
        self.repository = repository or ChatAgentRepository(runtime.repository.db_path)
        self.classifier = classifier or ChatAgentIntentClassifier()
        self.acceptance_generator = acceptance_generator or AcceptanceReportGenerator()

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
                autonomy_mode=request.autonomy_mode,
                approval_mode="manual",
            )
        )
        run = self.repository.create_run(
            chat_session_id=request.chat_session_id,
            trigger_message_id=request.message_id,
            workflow_id=workflow.workflow_id,
            intent_type=intent_type,
            summary=f"已创建 Agent 工作流：{workflow.title}",
            metadata={
                "template_id": workflow.template_id,
                "primary_agent_id": request.agent_id or "build",
                "compat_mode": "legacy_workflow",
                "new_agent_entrypoint": "/agent-sessions",
            },
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
        await self._ensure_acceptance_report(workflow)
        status = "completed" if workflow.status == "completed" else workflow.status
        run = self.repository.update_run(run_id, status=status, summary=self._summarize_workflow(workflow.model_dump()))
        return self._response(run)

    async def approve_step(self, step_id: str, approved: bool = True, comment: str | None = None) -> ChatAgentRunResponse:
        workflow = await self.runtime.approve_step(step_id, approved=approved, comment=comment)
        run = self.repository.get_run_by_workflow(workflow.workflow_id)
        if not run:
            raise HTTPException(status_code=404, detail="Chat agent run not found")
        await self._ensure_acceptance_report(workflow)
        self.repository.update_run(run["id"], status=workflow.status, summary=self._summarize_workflow(workflow.model_dump()))
        return self._response(self._get_run(run["id"]))

    async def approve_action(self, action_id: str):
        action = await self.runtime.approve_action(action_id)
        self._sync_action_run(action.workflow_id, "action_approved", action.id)
        return action

    async def reject_action(self, action_id: str):
        action = await self.runtime.reject_action(action_id)
        self._sync_action_run(action.workflow_id, "action_rejected", action.id)
        return action

    async def execute_action(self, action_id: str):
        action = await self.runtime.execute_action(action_id)
        event_type = "action_failed" if action.status == "failed" else "action_executed"
        self._sync_action_run(action.workflow_id, event_type, action.id)
        return action

    async def execute_action_with_repair(self, action_id: str):
        action = await self.runtime.execute_action(action_id)
        event_type = "action_failed" if action.status == "failed" else "action_executed"
        self._sync_action_run(action.workflow_id, event_type, action.id)
        if action.status == "failed":
            await self.runtime.repair_after_failed_action(action.id)
            self._sync_action_run(action.workflow_id, "repair_attempt", action.id)
        workflow = self.runtime.get_workflow(action.workflow_id)
        await self._ensure_acceptance_report(workflow)
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
        metadata = self._metadata_with_acceptance_report(workflow, observability, metadata)
        response_status = workflow.status if workflow else (run.get("status") or "created")
        final_summary = self._latest_output_summary(workflow.model_dump() if workflow and hasattr(workflow, "model_dump") else {})
        latest_tool_call = self._latest_tool_call(observability)
        latest_action = self._latest_action(observability)
        execution_state = metadata.get("execution_state")
        blocked_state = metadata.get("blocked_state")
        execution_message = metadata.get("execution_state_message") or self._stopped_state_message(
            response_status,
            metadata,
            final_summary,
            latest_action=latest_action,
            latest_tool_call=latest_tool_call,
        )
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
            status=response_status,
            intent_type=run.get("intent_type"),
            summary=run.get("summary") or "",
            final_summary=final_summary or None,
            execution_state=execution_state,
            execution_state_message=execution_message,
            recoverable=recoverable,
            model_protocol_status=metadata.get("model_protocol_status"),
            last_model_output_preview=metadata.get("last_model_output_preview"),
            parse_repair_count=int(metadata.get("parse_repair_count") or 0),
            fallback_summary_used=bool(metadata.get("fallback_summary_used")),
            acceptance_report=metadata.get("acceptance_report"),
            acceptance_report_source=metadata.get("acceptance_report_source"),
            acceptance_report_raw=metadata.get("acceptance_report_raw"),
            details_url=f"/workflows?workflow={workflow_id}" if workflow_id else None,
            active_agent_id=metadata.get("active_agent_id"),
            subagent_runs=list(metadata.get("subagent_runs") or []),
            auto_execution_policy=dict(metadata.get("auto_execution_policy") or {}),
            blocked_state=blocked_state,
            workflow=workflow,
            observability=observability,
            latest_event=events[-1] if events else None,
            latest_tool_call=latest_tool_call,
            latest_action=latest_action,
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
        metadata = workflow.get("metadata") if isinstance(workflow.get("metadata"), dict) else {}
        stopped_message = self._stopped_state_message(status, metadata or {}, final_summary)
        if stopped_message and status in {"failed", "needs_manual_review", "awaiting_approval"}:
            return stopped_message
        return f"Agent 状态：{status}，当前阶段：{current}"

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

    def _stopped_state_message(
        self,
        status: str | None,
        metadata: dict[str, Any],
        final_summary: str = "",
        *,
        latest_action: Any | None = None,
        latest_tool_call: Any | None = None,
    ) -> str:
        blocked_state = metadata.get("blocked_state")
        blocked_reason = ""
        if isinstance(blocked_state, dict):
            blocked_reason = str(blocked_state.get("message") or blocked_state.get("reason") or "").strip()
        state_message = str(metadata.get("execution_state_message") or "").strip()
        if status == "needs_manual_review":
            reason = blocked_reason or state_message or final_summary or "Agent 已暂停，需要人工确认后继续。"
            return f"需要人工处理：{reason}"
        if status == "failed":
            action_failure = self._action_failure_message(latest_action)
            tool_failure = self._tool_failure_message(latest_tool_call)
            reason = state_message or action_failure or tool_failure or final_summary or "动作或验证执行失败。"
            return f"执行失败：{reason}"
        if status == "awaiting_approval":
            reason = state_message or self._approval_message(latest_action) or final_summary or "Agent 正在等待你的审批。"
            return f"等待审批：{reason}"
        if status == "completed" and not final_summary:
            return "已完成：Agent 已结束运行，请查看验收报告和动作执行记录。"
        return state_message

    def _latest_tool_call(self, observability: Any | None) -> Any | None:
        calls = getattr(observability, "tool_calls", None) if observability is not None else None
        if not calls and isinstance(observability, dict):
            calls = observability.get("tool_calls")
        return calls[-1] if calls else None

    def _latest_action(self, observability: Any | None) -> Any | None:
        actions = getattr(observability, "actions", None) if observability is not None else None
        if not actions and isinstance(observability, dict):
            actions = observability.get("actions")
        return actions[-1] if actions else None

    def _field(self, item: Any | None, key: str, default: Any = None) -> Any:
        if item is None:
            return default
        if isinstance(item, dict):
            return item.get(key, default)
        return getattr(item, key, default)

    def _approval_message(self, action: Any | None) -> str:
        if not action or self._field(action, "status") != "pending_approval":
            return ""
        title = str(self._field(action, "title", "动作") or "动作")
        reason = str(self._field(action, "policy_reason", "") or "").strip()
        return f"{title}{f'，原因：{reason}' if reason else ''}"

    def _action_failure_message(self, action: Any | None) -> str:
        if not action or self._field(action, "status") != "failed":
            return ""
        title = str(self._field(action, "title", "动作") or "动作")
        failure = str(self._field(action, "failure_summary", "") or "").strip()
        return f"{title}{f'：{failure}' if failure else ' 执行失败'}"

    def _tool_failure_message(self, tool_call: Any | None) -> str:
        if not tool_call or self._field(tool_call, "status") not in {"failed", "blocked"}:
            return ""
        tool = str(self._field(tool_call, "tool_name", "工具") or "工具")
        reason = str(
            self._field(tool_call, "blocked_reason")
            or self._field(tool_call, "error")
            or self._field(tool_call, "result_summary")
            or ""
        ).strip()
        return f"{tool}{f'：{reason}' if reason else ' 调用失败'}"

    async def _ensure_acceptance_report(self, workflow: Any | None) -> None:
        if workflow is None:
            return
        workflow_data = workflow.model_dump() if hasattr(workflow, "model_dump") else dict(workflow)
        metadata = dict(workflow_data.get("metadata") or {})
        if metadata.get("acceptance_report"):
            return
        observability = self.runtime.get_observability(workflow_data["workflow_id"])
        if not self.acceptance_generator.should_generate(workflow_data, observability):
            return
        report, source, raw = await self.acceptance_generator.generate(workflow_data, observability)
        metadata.update(
            {
                "acceptance_report": report.model_dump(),
                "acceptance_report_source": source,
                "acceptance_report_raw": raw[:4000] if raw else "",
            }
        )
        self.runtime.repository.update_project(workflow_data["workflow_id"], metadata=metadata)

    def _metadata_with_acceptance_report(self, workflow: Any | None, observability: Any | None, metadata: dict[str, Any]) -> dict[str, Any]:
        if workflow is None or metadata.get("acceptance_report"):
            return metadata
        workflow_data = workflow.model_dump() if hasattr(workflow, "model_dump") else dict(workflow)
        if not self.acceptance_generator.should_generate(workflow_data, observability):
            return metadata
        report = self.acceptance_generator.build_fallback(workflow_data, observability)
        metadata = {
            **metadata,
            "acceptance_report": report.model_dump(),
            "acceptance_report_source": "fallback",
            "acceptance_report_raw": "generated_on_read",
        }
        self.runtime.repository.update_project(workflow_data["workflow_id"], metadata=metadata)
        return metadata
