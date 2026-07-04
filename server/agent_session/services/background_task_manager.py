from __future__ import annotations

import asyncio
import logging
import threading
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from fastapi import BackgroundTasks

from agent_session.execution_plan import build_initial_execution_plan
from agent_session.failure_guard import AgentLoopGuardTriggered
from agent_session.models import AgentPromptRequest, AgentSessionResponse
from agent_session.runtime_policy import build_agent_runtime_policy
from agent_session.services.utils import ensure_failed_metadata
from agent_session.state import ensure_session_state
from context.deepagents import build_deepagents_context_pack
from core.db_manager import run_sync

if TYPE_CHECKING:
    from agent_session.service import AgentSessionService

logger = logging.getLogger(__name__)
PromptTaskRecord = tuple[asyncio.AbstractEventLoop, asyncio.Task[Any]]


class BackgroundTaskManagerService:
    def __init__(self, service: AgentSessionService) -> None:
        self.service = service
        self._prompt_tasks: dict[str, PromptTaskRecord] = {}
        self._prompt_tasks_lock = threading.Lock()

    def start_prompt_background(
        self,
        session_id: str,
        request: AgentPromptRequest,
        background_tasks: BackgroundTasks | None,
    ) -> AgentSessionResponse:
        repository = self.service.repository
        session = repository.get_session(session_id)
        if not session:
            raise ValueError("Agent session not found")

        if str(session.get("status") or "") in self.service.ACTIVE_STATUSES:
            repository.add_event(
                session_id,
                "prompt_already_running",
                "Agent 正在处理当前任务，未重复启动。",
                {"session_id": session_id, "status": session.get("status"), "summary": "Agent 正在处理当前任务，未重复启动。"},
            )
            return self.service.lifecycle.get_session(session_id)

        metadata = ensure_session_state(dict(session.get("metadata") or {}))
        prompt_id = f"agprompt_{uuid.uuid4().hex}"
        now = datetime.now().isoformat()
        metadata["active_prompt_id"] = prompt_id
        metadata["background_run"] = True
        metadata["last_prompt_started_at"] = now
        metadata["current_goal"] = request.content
        user_part = repository.add_part(
            session_id,
            "text",
            status="completed",
            title="我的消息",
            content=request.content,
            payload={"role": "user", "source": "prompt", "prompt_id": prompt_id},
        )
        effective_provider, effective_model = self.service.lifecycle._resolve_session_model_defaults(
            str(session.get("agent_id") or "build"),
            request.provider or session.get("provider"),
            request.model or session.get("model"),
        )
        model_configured = bool(
            metadata.get("model_configured")
            or (request.provider and request.model)
            or self.service.lifecycle._has_saved_cloud_model(effective_provider, effective_model)
        )
        metadata["model_configured"] = model_configured
        if effective_provider != session.get("provider") or effective_model != session.get("model"):
            session = repository.update_session(
                session_id,
                provider=effective_provider,
                model=effective_model,
                metadata=metadata,
            )
        if self.service.model_call is None and (not model_configured or not (effective_provider and effective_model)):
            agent_id = str(session.get("agent_id") or "build")
            policy = build_agent_runtime_policy(
                agent=self.service.agent_registry.get(agent_id),
                agent_id=agent_id,
                project_path=session.get("project_path"),
                metadata=metadata,
                provider=effective_provider,
                model=effective_model,
                runtime_kind="agent_session",
                thread_id=f"agent_session:{session_id}:deepagents",
                checkpointer=True,
                agent_registry=self.service.agent_registry,
            )
            metadata["execution_plan"] = build_initial_execution_plan(
                session={**session, "provider": effective_provider, "model": effective_model},
                policy=policy,
                goal=request.content,
                status="running",
            )
            metadata["active_prompt_id"] = None
            metadata["background_run"] = False
            metadata["last_prompt_started_at"] = now
            metadata["current_goal"] = request.content
            session = repository.update_session(session_id, metadata=metadata)
            result = self.record_prompt_failure(
                session_id,
                RuntimeError("Agent 模型未配置：请先在模型运行/Agent 工作台选择 provider 和 model。"),
            )
            return AgentSessionResponse(**self.service.event_service._attach_recovery_diagnostics(result))
        agent_id = str(session.get("agent_id") or "build")
        policy = build_agent_runtime_policy(
            agent=self.service.agent_registry.get(agent_id),
            agent_id=agent_id,
            project_path=session.get("project_path"),
            metadata=metadata,
            provider=effective_provider,
            model=effective_model,
            runtime_kind="agent_session",
            thread_id=f"agent_session:{session_id}:deepagents",
            checkpointer=True,
            agent_registry=self.service.agent_registry,
        )
        metadata["execution_plan"] = build_initial_execution_plan(
            session={**session, "provider": effective_provider, "model": effective_model},
            policy=policy,
            goal=request.content,
            status="running",
        )
        if request.active_context or request.explicit_context:
            metadata["deep_context"] = {
                "active_context": request.active_context,
                "explicit_context": request.explicit_context,
            }
        session = self.service.state_machine.mark_running(
            session_id,
            provider=effective_provider,
            model=effective_model,
            metadata=metadata,
        )
        self.service.event_service._event(
            session_id,
            "prompt_queued",
            "Agent 已进入后台执行。",
            {
                "session_id": session_id,
                "active_prompt_id": prompt_id,
                "status": "running",
                "summary": "Agent 已进入后台执行。",
                "part_id": user_part.get("id"),
                "part_type": "text",
                "part": user_part,
            },
        )
        if background_tasks is not None:
            background_tasks.add_task(self._run_prompt_background, session_id, request, prompt_id)
        session["parts"] = repository.list_parts(session_id)
        return AgentSessionResponse(**self.service.event_service._attach_recovery_diagnostics(session))

    async def start_prompt_detached(
        self,
        session_id: str,
        request: AgentPromptRequest,
    ) -> AgentSessionResponse:
        response = await run_sync(self.start_prompt_background, session_id, request, None)
        prompt_id = response.metadata.get("active_prompt_id") if isinstance(response.metadata, dict) else None
        if response.status == "running" and prompt_id:
            thread = threading.Thread(
                target=self._run_prompt_thread_entry,
                args=(session_id, request, str(prompt_id)),
                name=f"agent-prompt-{session_id}",
                daemon=True,
            )
            thread.start()
        return response

    async def prompt(self, session_id: str, request: AgentPromptRequest) -> AgentSessionResponse:
        repository = self.service.repository
        session = repository.get_session(session_id)
        if not session:
            raise ValueError("Agent session not found")
        metadata = ensure_session_state(dict(session.get("metadata") or {}))
        if session.get("status") == "interrupted" or metadata.get("interrupt_requested"):
            return self.service.lifecycle.get_session(session_id)

        if request.provider or request.model:
            resolved_provider, resolved_model = self.service.lifecycle._resolve_session_model_defaults(
                str(session.get("agent_id") or "build"),
                request.provider or session.get("provider"),
                request.model or session.get("model"),
            )
            metadata["model_configured"] = bool(request.provider and request.model) or self.service.lifecycle._has_saved_cloud_model(
                resolved_provider,
                resolved_model,
            )
            repository.update_session(
                session_id,
                provider=resolved_provider,
                model=resolved_model,
                metadata=metadata,
            )
            session = repository.get_session(session_id) or session

        metadata = ensure_session_state(dict(session.get("metadata") or {}))
        if self.service.model_call is None and not (session.get("provider") and session.get("model")):
            result = self.record_prompt_failure(
                session_id,
                RuntimeError("Agent 模型未配置：请先在模型运行/Agent 工作台选择 provider 和 model。"),
            )
            return AgentSessionResponse(**self.service.event_service._attach_recovery_diagnostics(result))

        context_pack = await build_deepagents_context_pack(
            goal=request.content,
            active_context=request.active_context,
            explicit_context=request.explicit_context,
            project_path=session.get("project_path"),
            session_id=session_id,
        )
        prompt_content = context_pack.prompt
        if context_pack.has_files:
            metadata["deep_context"] = {
                "active_context": request.active_context,
                "explicit_context": request.explicit_context,
                "context_engineering": context_pack.metadata,
            }
        trace = dict(metadata.get("execution_trace") or {})
        trace.update(
            {
                "provider": str(session.get("provider") or ""),
                "model": str(session.get("model") or ""),
                "model_entry": "injected_model_call" if self.service.model_call is not None else "deepagents_init_chat_model",
                "fallback_used": False,
                "last_graph_error": None,
                "last_model_error": None,
            }
        )
        metadata["execution_trace"] = trace
        if self.service.model_call is not None:
            metadata["streaming_diagnostics"] = {
                "mode": "non_stream",
                "status": "disabled",
                "source": "injected_model_call",
                "reason": "测试或自定义 model_call 未提供 stream_model_call",
                "fallback_to_non_stream": True,
            }
        metadata["runtime"] = "deepagents"
        metadata["deepagents_thread_id"] = f"agent_session:{session_id}:deepagents"
        repository.update_session(session_id, metadata=metadata)
        session = repository.get_session(session_id) or session

        try:
            self.service.model_call_coordinator._sync_async_service_model_call()
            result = await self.service.deepagents_runner.run_prompt(session_id, prompt_content, context_files=context_pack.files)
        except AgentLoopGuardTriggered:
            result = repository.get_session(session_id) or session
            result["parts"] = repository.list_parts(session_id)
        except Exception as exc:
            result = self.record_prompt_failure(session_id, exc)

        return AgentSessionResponse(**self.service.event_service._attach_recovery_diagnostics(result))

    def _run_prompt_thread_entry(self, session_id: str, request: AgentPromptRequest, prompt_id: str) -> None:
        loop = asyncio.new_event_loop()
        try:
            asyncio.set_event_loop(loop)
            task = loop.create_task(self._run_prompt_background(session_id, request, prompt_id))
            loop.run_until_complete(task)
        except Exception:
            logger.exception("Agent prompt background thread failed for session %s", session_id)
        finally:
            try:
                pending = [task for task in asyncio.all_tasks(loop) if not task.done()]
                for task in pending:
                    task.cancel()
                if pending:
                    loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
            finally:
                asyncio.set_event_loop(None)
                loop.close()

    async def _run_prompt_background(self, session_id: str, request: AgentPromptRequest, prompt_id: str) -> None:
        loop = asyncio.get_running_loop()
        current_task = asyncio.current_task()
        if current_task is not None:
            with self._prompt_tasks_lock:
                self._prompt_tasks[session_id] = (loop, current_task)
        try:
            if not self._is_active_prompt(session_id, prompt_id):
                return
            await self.service.prompt(session_id, request)
            session = self.service.repository.get_session(session_id)
            if session:
                self.service.state_machine.clear_active_prompt(session_id, prompt_id)
        except asyncio.CancelledError:
            session = self.service.repository.get_session(session_id)
            if session and str(session.get("status") or "") not in self.service.TERMINAL_STATUSES:
                self.interrupt_session(session_id, "Agent 后台任务已取消。")
        except Exception as exc:
            try:
                if self._is_active_prompt(session_id, prompt_id):
                    self.service.record_prompt_failure(session_id, exc)
            except Exception as failure_exc:
                if self._is_active_prompt(session_id, prompt_id):
                    self._record_background_failure_fallback(session_id, exc, failure_exc)
        finally:
            self.service.recovery_service._clear_recovery_latch_for_prompt(session_id, prompt_id)
            with self._prompt_tasks_lock:
                record = self._prompt_tasks.get(session_id)
                if record and record[1] is current_task:
                    self._prompt_tasks.pop(session_id, None)

    def _is_active_prompt(self, session_id: str, prompt_id: str) -> bool:
        session = self.service.repository.get_session(session_id)
        if not session:
            return False
        metadata = dict(session.get("metadata") or {})
        return metadata.get("active_prompt_id") == prompt_id

    def interrupt_session(self, session_id: str, reason: str | None = None) -> AgentSessionResponse:
        repository = self.service.repository
        session = repository.get_session(session_id)
        if not session:
            raise ValueError("Agent session not found")
        if str(session.get("status") or "") in self.service.TERMINAL_STATUSES:
            return self.service.lifecycle.get_session(session_id)

        message = reason or "用户已中断 Agent 任务。"
        self._cancel_prompt_task(session_id)
        for part in repository.list_parts(session_id):
            if part.get("status") == "running":
                payload = dict(part.get("payload") or {})
                payload["interrupted"] = True
                repository.update_part(
                    part["id"],
                    status="blocked",
                    title=part.get("title") or "已中断",
                    content=part.get("content") or message,
                    payload=payload,
                )

        self.service.state_machine.mark_interrupted(session_id, reason=message)
        repository.add_part(
            session_id,
            "summary",
            status="completed",
            title="已中断",
            content=f"{message} 已停止继续调用模型和工具，当前 transcript 已保留。",
            payload={"summary": message, "interrupted": True},
        )
        repository.add_event(
            session_id,
            "session_interrupted",
            message,
            {"session_id": session_id, "status": "interrupted", "summary": message, "interrupted": True},
        )
        return self.service.lifecycle.get_session(session_id)

    def _cancel_prompt_task(self, session_id: str) -> None:
        with self._prompt_tasks_lock:
            record = self._prompt_tasks.get(session_id)
        if not record:
            return
        loop, task = record
        if task.done():
            return
        loop.call_soon_threadsafe(task.cancel)

    def _has_running_prompt_task(self, session_id: str) -> bool:
        with self._prompt_tasks_lock:
            record = self._prompt_tasks.get(session_id)
        if not record:
            return False
        return not record[1].done()

    def record_prompt_failure(self, session_id: str, exc: Exception) -> dict[str, Any]:
        repository = self.service.repository
        session = repository.get_session(session_id)
        if not session:
            raise ValueError("Agent session not found")
        message = f"模型调用失败或内部错误，已停止且没有继续执行动作。错误：{str(exc)[:600]}"
        metadata = ensure_failed_metadata(session, message)
        summary = repository.add_part(
            session_id,
            "summary",
            status="completed",
            title="最终结果",
            content=message,
            payload={"summary": message, "fallback": False, "error": str(exc)[:1200]},
        )
        self.service.state_machine.mark_failed(session_id, metadata=metadata, status="needs_manual_review")
        self.service.event_service._event(
            session_id,
            "session_failed",
            message,
            {
                "session_id": session_id,
                "part_id": summary.get("id"),
                "part_type": "summary",
                "status": "completed",
                "summary": message,
                "error": str(exc)[:1200],
                "fallback": False,
            },
        )
        result = repository.get_session(session_id) or session
        result["parts"] = repository.list_parts(session_id)
        return result

    def _record_background_failure_fallback(self, session_id: str, original_exc: Exception, failure_exc: Exception) -> None:
        import logging
        logger = logging.getLogger(__name__)
        logger.exception(
            "Failed to record Agent background failure for session %s after original error: %s",
            session_id,
            original_exc,
            exc_info=failure_exc,
        )
        try:
            def write_failure() -> None:
                session = self.service.repository.get_session(session_id)
                if not session:
                    return
                message = (
                    "Agent 后台任务失败，且标准失败记录也失败。"
                    f"原始错误：{str(original_exc)[:500]}；记录错误：{str(failure_exc)[:500]}"
                )
                metadata = ensure_failed_metadata(session, message)
                self.service.state_machine.mark_failed(session_id, metadata=metadata, status="needs_manual_review")
                event = self.service.repository.add_event(
                    session_id,
                    "session_failed",
                    message,
                    {
                        "session_id": session_id,
                        "status": "needs_manual_review",
                        "summary": message,
                        "error": message,
                        "fallback": True,
                        "record_failure_error": str(failure_exc)[:1000],
                    },
                )
                self.service.event_service._notify_event(session_id, event)

            self.service.repository.run_write_with_retry(write_failure)
        except Exception:
            logger.exception("Failed to apply minimal Agent failure fallback for session %s", session_id)
