from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from fastapi import BackgroundTasks

from agent_session.models import (
    AgentExecutionPlanRecoverRequest,
    AgentExecutionPlanRecoveryResponse,
    AgentPromptRequest,
)
from agent_session.services.utils import ensure_failed_metadata
from agent_session.state import ensure_session_state

if TYPE_CHECKING:
    from agent_session.service import AgentSessionService

logger = logging.getLogger(__name__)


class RecoveryService:
    def __init__(self, service: AgentSessionService) -> None:
        self.service = service

    async def recover_execution_node(
        self,
        session_id: str,
        node_id: str,
        request: AgentExecutionPlanRecoverRequest,
        background_tasks: BackgroundTasks,
    ) -> AgentExecutionPlanRecoveryResponse:
        repository = self.service.repository
        session = repository.get_session(session_id)
        if not session:
            raise ValueError("Agent session not found")
        metadata = ensure_session_state(dict(session.get("metadata") or {}))
        plan = metadata.get("execution_plan")
        if not isinstance(plan, dict):
            raise ValueError("Execution plan not found")
        node = self._find_execution_node(plan, node_id)
        if not node:
            raise ValueError("Execution plan node not found")
        if not bool(node.get("recoverable")):
            raise ValueError("Execution plan node is not recoverable")
        if self.service._has_running_prompt_task(session_id):
            raise ValueError("Agent session already has a running background task")

        action = str(request.action or node.get("recovery_action") or "").strip()
        if action not in {"retry_node", "resume_node", "restart_subagent", "manual_review"}:
            raise ValueError("Unsupported recovery action")
        instruction = (request.instruction or "").strip()
        existing_latch = self._get_recovery_latch(metadata, node_id)
        if existing_latch:
            workspace = self.service.lifecycle.get_workspace(session_id)
            return AgentExecutionPlanRecoveryResponse(
                session=workspace.session,
                execution_plan=workspace.execution_plan,
                workspace=workspace,
                node_id=node_id,
                action=str(existing_latch.get("action") or action),
                started_task_id=existing_latch.get("new_task_id"),
            )
        recovery_id = f"agrecovery_{uuid.uuid4().hex}"
        self._set_recovery_latch(session_id, node_id, recovery_id, action)
        self.service.event_service._event(
            session_id,
            "node_recovery_requested",
            "用户请求恢复执行节点。",
            {
                "session_id": session_id,
                "node_id": node_id,
                "recovery_id": recovery_id,
                "action": action,
                "instruction": instruction,
                "summary": "用户请求恢复执行节点。",
            },
        )

        started_task_id: str | None = None
        try:
            if action == "restart_subagent":
                started_task_id = await self._recover_subagent_node(session_id, node, instruction, recovery_id)
            else:
                self.service._start_recovery_prompt_background(session_id, node, action, instruction, recovery_id, background_tasks)
            self.service.failure_guard.reset_for_recovery(session_id)
        except Exception as exc:
            self.service.event_service._event(
                session_id,
                "node_recovery_failed",
                "节点恢复启动失败。",
                {
                    "session_id": session_id,
                    "node_id": node_id,
                    "recovery_id": recovery_id,
                    "action": action,
                    "error": str(exc)[:1200],
                    "summary": "节点恢复启动失败。",
                },
            )
            self._clear_recovery_latch(session_id, node_id)
            failed_session = repository.get_session(session_id) or session
            failed_metadata = ensure_session_state(dict(failed_session.get("metadata") or {}))
            self.service.state_machine.mark_failed(session_id, metadata=failed_metadata, status="needs_manual_review")
            raise

        workspace = self.service.lifecycle.get_workspace(session_id)
        return AgentExecutionPlanRecoveryResponse(
            session=workspace.session,
            execution_plan=workspace.execution_plan,
            workspace=workspace,
            node_id=node_id,
            action=action,
            started_task_id=started_task_id,
        )

    async def recover_async_subtasks(self) -> dict[str, Any]:
        self.service.model_call_coordinator._sync_async_service_model_call()
        return await self.service.async_subagent_service.recover_running_tasks()

    def recover_active_sessions_after_restart(self) -> dict[str, Any]:
        sessions = self.service.repository.list_sessions_by_status(self.service.ACTIVE_STATUSES)
        recovered = 0
        failed = 0
        for session in sessions:
            session_id = str(session.get("id") or "")
            if not session_id:
                continue
            metadata = dict(session.get("metadata") or {})
            if metadata.get("async_subagent") or metadata.get("async_task_id"):
                continue
            try:
                self._mark_session_lost_after_restart(session)
                recovered += 1
            except Exception:
                failed += 1
                logger.exception("Failed to mark stale Agent session after restart: %s", session_id)
        return {"recovered": recovered, "failed": failed, "session_ids": [str(item.get("id")) for item in sessions if item.get("id")]}

    async def shutdown_async_subtasks(self) -> None:
        prompt_shutdown = await self.service.background_manager.shutdown_prompt_tasks()
        if prompt_shutdown["interrupted"] or prompt_shutdown["remaining_tasks"] or prompt_shutdown["remaining_threads"]:
            logger.info("Agent prompt shutdown complete: %s", prompt_shutdown)
        await self.service.async_subagent_service.shutdown()

    def _get_recovery_latch(self, metadata: dict[str, Any], node_id: str) -> dict[str, Any] | None:
        latches = metadata.get("recovery_latches")
        if not isinstance(latches, dict):
            return None
        latch = latches.get(node_id)
        return dict(latch) if isinstance(latch, dict) else None

    def _set_recovery_latch(self, session_id: str, node_id: str, recovery_id: str, action: str) -> None:
        repository = self.service.repository
        session = repository.get_session(session_id)
        if not session:
            return
        metadata = ensure_session_state(dict(session.get("metadata") or {}))
        latches = dict(metadata.get("recovery_latches") or {})
        latches[node_id] = {"recovery_id": recovery_id, "action": action, "started_at": datetime.now().isoformat()}
        metadata["recovery_latches"] = latches
        repository.update_session(session_id, metadata=metadata)

    def _update_recovery_latch(self, session_id: str, node_id: str, **updates: Any) -> None:
        repository = self.service.repository
        session = repository.get_session(session_id)
        if not session:
            return
        metadata = ensure_session_state(dict(session.get("metadata") or {}))
        latches = dict(metadata.get("recovery_latches") or {})
        latch = dict(latches.get(node_id) or {})
        if not latch:
            return
        latch.update({key: value for key, value in updates.items() if value is not None})
        latches[node_id] = latch
        metadata["recovery_latches"] = latches
        repository.update_session(session_id, metadata=metadata)

    def _clear_recovery_latch(self, session_id: str, node_id: str) -> None:
        repository = self.service.repository
        session = repository.get_session(session_id)
        if not session:
            return
        metadata = ensure_session_state(dict(session.get("metadata") or {}))
        latches = dict(metadata.get("recovery_latches") or {})
        if node_id not in latches:
            return
        latches.pop(node_id, None)
        metadata["recovery_latches"] = latches
        repository.update_session(session_id, metadata=metadata)

    def _clear_recovery_latch_for_prompt(self, session_id: str, prompt_id: str) -> None:
        repository = self.service.repository
        session = repository.get_session(session_id)
        if not session:
            return
        metadata = ensure_session_state(dict(session.get("metadata") or {}))
        last_recovery = dict(metadata.get("last_recovery") or {})
        if last_recovery.get("active_prompt_id") != prompt_id:
            return
        node_id = str(last_recovery.get("node_id") or "")
        if node_id:
            self._clear_recovery_latch(session_id, node_id)

    def _start_recovery_prompt_background(
        self,
        session_id: str,
        node: dict[str, Any],
        action: str,
        instruction: str,
        recovery_id: str,
        background_tasks: BackgroundTasks,
    ) -> None:
        repository = self.service.repository
        prompt_id = f"agrecover_{uuid.uuid4().hex}"
        session = repository.get_session(session_id)
        if not session:
            raise ValueError("Agent session not found")
        metadata = ensure_session_state(dict(session.get("metadata") or {}))
        plan = dict(metadata.get("execution_plan") or {})
        if isinstance(plan, dict):
            plan["current_node_id"] = str(node.get("id") or "")
            metadata["execution_plan"] = plan
        now = datetime.now().isoformat()
        metadata["active_prompt_id"] = prompt_id
        metadata["background_run"] = True
        metadata["last_prompt_started_at"] = now
        metadata["last_recovery"] = {
            "node_id": str(node.get("id") or ""),
            "recovery_id": recovery_id,
            "action": action,
            "instruction": instruction,
            "active_prompt_id": prompt_id,
            "started_at": now,
        }
        prompt = self._recovery_prompt(node, action, instruction)
        self.service.state_machine.mark_running(session_id, metadata=metadata)
        self.service.event_service._event(
            session_id,
            "node_recovery_started",
            "节点恢复已进入后台执行。",
            {
                "session_id": session_id,
                "node_id": str(node.get("id") or ""),
                "recovery_id": recovery_id,
                "action": action,
                "active_prompt_id": prompt_id,
                "keeps_running": True,
                "summary": "节点恢复已进入后台执行。",
            },
        )
        background_tasks.add_task(self.service.background_manager._run_prompt_background, session_id, AgentPromptRequest(content=prompt), prompt_id)

    async def _recover_subagent_node(self, session_id: str, node: dict[str, Any], instruction: str, recovery_id: str) -> str:
        old_task_id = str(node.get("source_task_id") or "")
        task = self.service.repository.get_subtask(old_task_id) if old_task_id else None
        input_json = dict((task or {}).get("input_json") or {})
        agent_name = str((task or {}).get("agent_name") or node.get("agent_id") or "").strip()
        description = str(input_json.get("description") or node.get("description") or "").strip()
        if instruction:
            description = f"{description}\n\n恢复补充说明：{instruction}" if description else instruction
        if not agent_name or not description:
            raise ValueError("Subagent recovery requires agent name and description")
        self.service.model_call_coordinator._sync_async_service_model_call()
        recovered = await self.service.async_subagent_service.start_task(session_id, agent_name, description)
        new_task_id = str(recovered.get("task_id") or "")
        self._update_recovery_latch(session_id, str(node.get("id") or ""), new_task_id=new_task_id)
        self.service.event_service._event(
            session_id,
            "node_recovery_started",
            "子 Agent 节点已重启。",
            {
                "session_id": session_id,
                "node_id": str(node.get("id") or ""),
                "recovery_id": recovery_id,
                "action": "restart_subagent",
                "old_task_id": old_task_id,
                "new_task_id": new_task_id,
                "summary": "子 Agent 节点已重启。",
            },
        )
        return new_task_id

    @staticmethod
    def _recovery_prompt(node: dict[str, Any], action: str, instruction: str) -> str:
        import json
        details = {
            "node_id": node.get("id"),
            "title": node.get("title"),
            "kind": node.get("kind"),
            "status": node.get("status"),
            "tool": node.get("tool"),
            "source_part_id": node.get("source_part_id"),
            "source_task_id": node.get("source_task_id"),
            "error": node.get("error"),
            "blocked_reason": node.get("blocked_reason"),
            "recovery_action": action,
        }
        prompt = (
            "请从 Agent execution_plan 中的失败/阻塞节点继续恢复执行。\n"
            "不要盲目重放已有副作用；先读取上下文，判断已完成内容，再执行必要的最小后续步骤。\n"
            f"恢复节点：{json.dumps(details, ensure_ascii=False)}"
        )
        if instruction:
            prompt += f"\n用户补充恢复说明：{instruction}"
        return prompt

    def _mark_session_lost_after_restart(self, session: dict[str, Any]) -> None:
        session_id = str(session.get("id") or "")
        if not session_id:
            return
        message = "Agent 后台任务在服务重启或进程退出时中断，已停止自动执行。请查看 transcript 后重新发起。"
        repository = self.service.repository

        def write_recovery() -> None:
            current = repository.get_session(session_id) or session
            if str(current.get("status") or "") not in self.service.ACTIVE_STATUSES:
                return
            metadata = ensure_failed_metadata(
                current,
                message,
                failure_kind="process_restart",
                next_action="rerun_prompt",
                recoverable=True,
            )
            metadata["recovered_after_restart"] = True
            metadata["failure_kind"] = "process_restart"
            metadata["next_action"] = "rerun_prompt"
            metadata["recoverable"] = True
            summary = repository.add_part(
                session_id,
                "summary",
                status="completed",
                title="执行已中断",
                content=message,
                payload={
                    "summary": message,
                    "fallback": True,
                    "recovered_after_restart": True,
                    "failure_kind": "process_restart",
                    "next_action": "rerun_prompt",
                },
            )
            self.service.state_machine.mark_failed(session_id, metadata=metadata, status="needs_manual_review")
            event = repository.add_event(
                session_id,
                "session_failed",
                message,
                {
                    "session_id": session_id,
                    "part_id": summary.get("id"),
                    "part_type": "summary",
                    "status": "needs_manual_review",
                    "summary": message,
                    "error": message,
                    "fallback": True,
                    "recovered_after_restart": True,
                    "failure_kind": "process_restart",
                    "next_action": "rerun_prompt",
                },
            )
            self.service.event_service._notify_event(session_id, event)

        repository.run_write_with_retry(write_recovery)

    @staticmethod
    def _find_execution_node(plan: dict[str, Any], node_id: str) -> dict[str, Any] | None:
        for node in plan.get("nodes") or []:
            if isinstance(node, dict) and str(node.get("id") or "") == node_id:
                return node
        return None
