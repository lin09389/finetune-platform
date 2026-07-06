from __future__ import annotations

import asyncio
from datetime import datetime
from typing import TYPE_CHECKING, Any

from fastapi import BackgroundTasks

from agent_session.approval import permission_decisions
from agent_session.failure_guard import AgentLoopGuardTriggered
from agent_session.models import AgentSessionResponse
from agent_session.permission import validate_hitl_decisions
from core.db_manager import run_sync

if TYPE_CHECKING:
    from agent_session.service import AgentSessionService


class ApprovalService:
    def __init__(self, service: AgentSessionService) -> None:
        self.service = service

    def approve_permission(self, part_id: str, approved: bool) -> AgentSessionResponse:
        part = self.service.repository.get_part(part_id)
        if not part:
            raise ValueError("Agent part not found")
        return AgentSessionResponse(**self.service.event_service._attach_recovery_diagnostics(self._approve_deepagents_action(part, approved)))

    async def approve_permission_async(
        self,
        part_id: str,
        approved: bool,
        background_tasks: BackgroundTasks,
    ) -> AgentSessionResponse:
        return await self.decide_permission_async(
            part_id,
            [{"type": "approve" if approved else "reject"}],
            background_tasks,
        )

    def _record_permission_decision(self, part_id: str, decisions: list[dict[str, Any]]) -> tuple[AgentSessionResponse, dict[str, Any] | None]:
        part = self.service.repository.get_part(part_id)
        if not part:
            raise ValueError("Agent part not found")
        session = self.service.repository.get_session(part["session_id"]) or {}
        from agent_session.state import ensure_session_state
        metadata = ensure_session_state(dict(session.get("metadata") or {}))
        if metadata.get("runtime") != "deepagents":
            if len(decisions) != 1:
                raise ValueError("Legacy permission approvals accept exactly one decision")
            return self.approve_permission(part_id, decisions[0].get("type") == "approve"), None

        normalized_decisions = validate_hitl_decisions(part, decisions)
        result = self._decide_deepagents_permission(part, normalized_decisions)
        self.service.model_call_coordinator._sync_async_service_model_call()
        decision = permission_decisions(part_id, normalized_decisions)
        self._record_resume_decision(part["session_id"], decision)
        session = self.service.repository.get_session(part["session_id"]) or result
        session["parts"] = self.service.repository.list_parts(part["session_id"])
        return AgentSessionResponse(**self.service.event_service._attach_recovery_diagnostics(session)), decision

    def start_permission_resume_background(
        self,
        part_id: str,
        decisions: list[dict[str, Any]],
        background_tasks: BackgroundTasks,
    ) -> AgentSessionResponse:
        response, decision = self._record_permission_decision(part_id, decisions)
        if decision is not None and self._can_resume_permission(response):
            background_tasks.add_task(self._resume_permission_background, response.id, decision)
        return response

    def _can_resume_permission(self, response: AgentSessionResponse) -> bool:
        return self.service.deepagents_runner.model_call is not None or bool(response.provider)

    async def _resume_permission_background(self, session_id: str, decision: dict[str, Any]) -> None:
        loop = asyncio.get_running_loop()
        current_task = asyncio.current_task()
        if current_task is not None:
            with self.service.background_manager._prompt_tasks_lock:
                existing = self.service.background_manager._prompt_tasks.get(session_id)
                if existing is not None and not existing[1].done():
                    raise RuntimeError("Agent 任务正在执行中，无法启动新的恢复")
                self.service.background_manager._prompt_tasks[session_id] = (loop, current_task)
        try:
            self.service.model_call_coordinator._sync_async_service_model_call()
            await self.service.deepagents_runner.resume(session_id, decision)
        except AgentLoopGuardTriggered:
            return
        except asyncio.CancelledError:
            session = self.service.repository.get_session(session_id)
            if session and str(session.get("status") or "") not in self.service.TERMINAL_STATUSES:
                self.service.background_manager.interrupt_session(session_id, "权限审批后的 Agent 恢复执行已取消。")
            raise
        except Exception as exc:
            try:
                self.service.background_manager.record_prompt_failure(session_id, exc)
            except Exception as failure_exc:
                self.service.background_manager._record_background_failure_fallback(session_id, exc, failure_exc)
        finally:
            with self.service.background_manager._prompt_tasks_lock:
                record = self.service.background_manager._prompt_tasks.get(session_id)
                if record and record[1] is current_task:
                    self.service.background_manager._prompt_tasks.pop(session_id, None)

    async def decide_permission_async(self, part_id: str, decisions: list[dict[str, Any]], background_tasks: BackgroundTasks) -> AgentSessionResponse:
        response, decision = await run_sync(self._record_permission_decision, part_id, decisions)
        if decision is not None and self._can_resume_permission(response):
            background_tasks.add_task(self._resume_permission_background, response.id, decision)
        return response

    def _approve_deepagents_action(self, part: dict[str, Any], approved: bool) -> dict[str, Any]:
        session_id = str(part.get("session_id") or "")
        if not session_id:
            raise ValueError("Agent part session not found")
        session = self.service.repository.get_session(session_id) or {}
        from agent_session.state import ensure_session_state
        metadata = ensure_session_state(dict(session.get("metadata") or {}))
        next_status = "blocked" if not approved else "approved"
        updated = self.service.repository.update_part_if_status(part["id"], "pending", status=next_status)
        if updated is None:
            result = self.service.repository.get_session(session_id) or session
            result["parts"] = self.service.repository.list_parts(session_id)
            return result
        if not approved:
            self.service.state_machine.mark_failed(session_id, metadata=metadata, status="failed")
            event_type, event_message = "action_rejected", "动作已拒绝"
        else:
            self.service.state_machine.mark_waiting_approval(session_id, metadata=metadata)
            event_type, event_message = "action_approved", "动作已批准"
        event = self.service.repository.add_event(
            session_id,
            event_type,
            event_message,
            {
                "session_id": session_id,
                "part_id": part["id"],
                "part_type": part.get("type"),
                "status": next_status,
                "runtime": "deepagents",
                "part": updated,
            },
        )
        self.service.event_service._notify_event(session_id, event)
        result = self.service.repository.get_session(session_id) or session
        result["parts"] = self.service.repository.list_parts(session_id)
        return result

    def _decide_deepagents_permission(self, part: dict[str, Any], decisions: list[dict[str, Any]]) -> dict[str, Any]:
        session_id = str(part.get("session_id") or "")
        if not session_id:
            raise ValueError("Agent part session not found")
        session = self.service.repository.get_session(session_id) or {}
        from agent_session.state import ensure_session_state
        metadata = ensure_session_state(dict(session.get("metadata") or {}))
        payload = dict(part.get("payload") or {})
        payload["decisions"] = decisions
        payload["decided_at"] = datetime.now().isoformat()
        updated = self.service.repository.update_part_if_status(part["id"], "pending", status="approved", payload=payload)
        if not updated:
            raise ValueError("Permission part is not pending")
        metadata["pending_deepagents_interrupt"] = None
        self.service.state_machine.mark_running(session_id, metadata=metadata)
        event = self.service.repository.add_event(
            session_id,
            "permission_decided",
            "HITL 决策已提交，Agent 正在继续执行。",
            {
                "session_id": session_id,
                "part_id": part["id"],
                "part_type": part.get("type"),
                "status": "approved",
                "runtime": "deepagents",
                "decisions": decisions,
                "part": updated,
            },
        )
        self.service.event_service._notify_event(session_id, event)
        result = self.service.repository.get_session(session_id) or session
        result["parts"] = self.service.repository.list_parts(session_id)
        return result

    def _record_resume_decision(self, session_id: str, decision: dict[str, Any]) -> None:
        session = self.service.repository.get_session(session_id)
        if not session:
            return
        from agent_session.state import ensure_session_state
        metadata = ensure_session_state(dict(session.get("metadata") or {}))
        metadata["last_resume_decision"] = dict(decision)
        self.service.repository.update_session(session_id, metadata=metadata)
