from __future__ import annotations

import asyncio
import logging
import threading
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from fastapi import BackgroundTasks

from agent_session.errors import AgentConfigurationError
from agent_session.failure_guard import AgentLoopGuardTriggered
from agent_session.goal_planner import (
    GOAL_PLAN_STATUS_ATTACHED,
    GOAL_PLAN_STATUS_FAILED,
    attach_goal_plan_before_build_prompt_sync,
    build_goal_plan_diagnostics,
)
from agent_session.models import AgentPromptRequest, AgentSessionResponse
from agent_session.phase_tool_router import bootstrap_build_phase_routing
from agent_session.runtime_contract import resolve_orchestration_mode
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
        self._prompt_threads: dict[str, threading.Thread] = {}
        self._shutdown_started = threading.Event()
        self._session_start_locks: dict[str, threading.Lock] = {}
        self._session_start_locks_lock = threading.Lock()

    def _session_start_lock(self, session_id: str) -> threading.Lock:
        with self._session_start_locks_lock:
            lock = self._session_start_locks.get(session_id)
            if lock is None:
                lock = threading.Lock()
                self._session_start_locks[session_id] = lock
            return lock

    def start_prompt_background(
        self,
        session_id: str,
        request: AgentPromptRequest,
        background_tasks: BackgroundTasks | None,
    ) -> AgentSessionResponse:
        if self._shutdown_started.is_set():
            raise RuntimeError("Agent service is shutting down; new background prompts are unavailable")
        repository = self.service.repository
        with self._session_start_lock(session_id):
            session = repository.get_session(session_id)
            if not session:
                raise ValueError("Agent session not found")

            if str(session.get("status") or "") in self.service.ACTIVE_STATUSES or self._has_running_prompt_task(session_id):
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
            agent_id = str(session.get("agent_id") or "build")
            effective_provider, effective_model, model_configured = self.service.lifecycle.resolve_session_model_availability(
                agent_id,
                request.provider or session.get("provider"),
                request.model or session.get("model"),
            )
            metadata["model_configured"] = model_configured
            metadata["model_configuration"] = self.service.lifecycle.get_model_configuration_status(
                effective_provider,
                effective_model,
                model_configured,
            )
            metadata["failure_kind"] = None
            metadata["next_action"] = None
            if effective_provider != session.get("provider") or effective_model != session.get("model"):
                session = repository.update_session(
                    session_id,
                    provider=effective_provider,
                    model=effective_model,
                    metadata=metadata,
                )
            if self.service.model_call is None and (not model_configured or not (effective_provider and effective_model)):
                metadata["failure_kind"] = "configuration_error"
                metadata["next_action"] = "configure_model"
                metadata["background_run"] = False
                metadata["active_prompt_id"] = None
                metadata["latest_error"] = str(
                    metadata["model_configuration"]["message"]
                    or "Agent 模型未配置：请先在模型运行/Agent 工作台选择 provider 和 model。"
                )
                repository.update_session(session_id, metadata=metadata)
                raise AgentConfigurationError(metadata["latest_error"])

            metadata["active_prompt_id"] = prompt_id
            metadata["background_run"] = True
            metadata["last_prompt_started_at"] = now
            metadata["current_goal"] = request.content
            from agent_session.session_progress import reset_tool_metrics

            metadata = reset_tool_metrics(metadata)
            user_part = repository.add_part(
                session_id,
                "text",
                status="completed",
                title="我的消息",
                content=request.content,
                payload={"role": "user", "source": "prompt", "prompt_id": prompt_id},
            )
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
            metadata = attach_goal_plan_before_build_prompt_sync(
                self.service.model_call_coordinator,
                metadata=metadata,
                session={
                    **session,
                    "provider": effective_provider,
                    "model": effective_model,
                    "metadata": metadata,
                },
                policy=policy,
                user_goal=request.content,
                plan_status="running",
            )
            goal_plan_status = str(metadata.get("goal_plan_status") or "")
            if goal_plan_status == GOAL_PLAN_STATUS_ATTACHED:
                self.service.event_service._event(
                    session_id,
                    "goal_plan_attached",
                    "已生成结构化 Goal Plan，Build 将按该计划推进。",
                    {
                        "session_id": session_id,
                        "summary": "已生成结构化 Goal Plan，Build 将按该计划推进。",
                        "goal_plan_status": goal_plan_status,
                        "schema_version": (metadata.get("execution_plan") or {}).get("goal_plan", {}).get("schema_version"),
                    },
                )
            elif goal_plan_status == GOAL_PLAN_STATUS_FAILED:
                diagnostics = dict(metadata.get("goal_plan_diagnostics") or build_goal_plan_diagnostics(error="unknown", attempts=0))
                self.service.event_service._event(
                    session_id,
                    "goal_plan_failed",
                    str(diagnostics.get("summary") or "Goal Plan 生成失败，将继续现有 Build 流程。"),
                    {
                        "session_id": session_id,
                        "summary": diagnostics.get("summary"),
                        "goal_plan_status": goal_plan_status,
                        "goal_plan_diagnostics": diagnostics,
                    },
                )
            if agent_id == "build" and str(metadata.get("task_mode") or session.get("task_mode") or "build") not in {
                "train",
                "hybrid",
            }:
                metadata = bootstrap_build_phase_routing(
                    metadata=metadata,
                    session={
                        **session,
                        "provider": effective_provider,
                        "model": effective_model,
                        "metadata": metadata,
                    },
                    agent_registry=self.service.agent_registry,
                    orchestration_mode=resolve_orchestration_mode(metadata),
                    provider=effective_provider,
                    model=effective_model,
                )
                phase_projection = metadata.get("phase_tool_projection") or {}
                self.service.event_service._event(
                    session_id,
                    "phase_routing_initialized",
                    "Build phase routing initialized.",
                    {
                        "session_id": session_id,
                        "summary": "Build phase routing initialized.",
                        "phase_state": metadata.get("phase_state"),
                        "phase_tool_projection": {
                            "phase": phase_projection.get("phase"),
                            "routing_mode": phase_projection.get("routing_mode"),
                            "application": phase_projection.get("application"),
                            "allowed_tools": phase_projection.get("allowed_tools"),
                            "blocked_reasons": phase_projection.get("blocked_reasons"),
                        },
                    },
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
                daemon=False,
            )
            with self._prompt_tasks_lock:
                self._prompt_threads[session_id] = thread
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
            metadata["model_configured"] = bool(
                (request.provider and request.model)
                or self.service.lifecycle._is_local_tool_capable_provider(resolved_provider)
                or self.service.lifecycle._has_saved_cloud_model(
                    resolved_provider,
                    resolved_model,
                )
            )
            metadata["model_configuration"] = self.service.lifecycle.get_model_configuration_status(
                resolved_provider,
                resolved_model,
                bool(metadata["model_configured"]),
            )
            repository.update_session(
                session_id,
                provider=resolved_provider,
                model=resolved_model,
                metadata=metadata,
            )
            session = repository.get_session(session_id) or session

        metadata = ensure_session_state(dict(session.get("metadata") or {}))
        provider, model, configured = self.service.lifecycle.resolve_session_model_availability(
            str(session.get("agent_id") or "build"),
            session.get("provider"),
            session.get("model"),
        )
        if self.service.model_call is None and (not configured or not (provider and model)):
            status = self.service.lifecycle.get_model_configuration_status(provider, model, configured)
            raise AgentConfigurationError(str(status["message"] or "Agent 模型未配置：请先在模型运行/Agent 工作台选择 provider 和 model。"))
        if provider != session.get("provider") or model != session.get("model"):
            repository.update_session(session_id, provider=provider, model=model, metadata=metadata)
            session = repository.get_session(session_id) or session

        preparing_part = repository.add_part(
            session_id,
            "text",
            status="running",
            title="正在准备上下文",
            content="正在检索项目上下文与记忆…",
            payload={"role": "assistant", "source": "context_preparing"},
        )
        self.service.event_service._event(
            session_id,
            "context_preparing",
            "正在检索项目上下文与记忆…",
            {
                "session_id": session_id,
                "part_id": preparing_part.get("id"),
                "part_type": "text",
                "status": "running",
                "summary": "正在检索项目上下文与记忆…",
                "part": preparing_part,
            },
        )
        # Phase B0: optional per-prompt scope override + discover verify recipe.
        from agent_session.task_scope import (
            VERIFY_RECIPE_KEY,
            apply_task_scope_to_metadata,
            discover_verify_recipe,
            get_task_scope,
        )

        if request.clear_scope or request.scope_paths is not None or request.scope_notes is not None:
            if request.clear_scope:
                metadata = apply_task_scope_to_metadata(
                    metadata,
                    session.get("project_path"),
                    clear=True,
                )
            else:
                existing_scope = get_task_scope(metadata) or {}
                paths = (
                    request.scope_paths
                    if request.scope_paths is not None
                    else list(existing_scope.get("paths") or [])
                )
                notes = (
                    request.scope_notes
                    if request.scope_notes is not None
                    else existing_scope.get("notes")
                )
                metadata = apply_task_scope_to_metadata(
                    metadata,
                    session.get("project_path"),
                    paths=paths,
                    notes=notes if isinstance(notes, str) or notes is None else str(notes),
                )
        verify_recipe = discover_verify_recipe(session.get("project_path"))
        if verify_recipe:
            metadata[VERIFY_RECIPE_KEY] = {
                "sources": verify_recipe.get("sources"),
                "commands": verify_recipe.get("commands"),
                # markdown kept for context pack; avoid bloating if huge
                "markdown": verify_recipe.get("markdown"),
            }
        task_scope = get_task_scope(metadata)
        context_pack = await build_deepagents_context_pack(
            goal=request.content,
            active_context=request.active_context,
            explicit_context=request.explicit_context,
            project_path=session.get("project_path"),
            session_id=session_id,
            task_scope=task_scope,
            verify_recipe=verify_recipe,
        )
        repository.update_part(
            preparing_part["id"],
            status="completed",
            title="上下文已就绪",
            content="项目上下文与记忆检索完成，正在调用模型…",
        )
        self.service.event_service._event(
            session_id,
            "context_ready",
            "项目上下文与记忆检索完成，正在调用模型…",
            {
                "session_id": session_id,
                "part_id": preparing_part.get("id"),
                "part_type": "text",
                "status": "completed",
                "summary": "项目上下文与记忆检索完成，正在调用模型…",
            },
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
                # Refined to official / openai_compat_fallback / local_ollama_service after graph build.
                "model_entry": (
                    "injected_model_call"
                    if self.service.model_call is not None
                    else "pending_model_resolution"
                ),
                "fallback_used": False,
                "last_graph_error": None,
                "last_model_error": None,
                "last_tool_error": None,
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
        task: asyncio.Task[Any] | None = None
        try:
            asyncio.set_event_loop(loop)
            task = loop.create_task(self._run_prompt_background(session_id, request, prompt_id))
            loop.run_until_complete(task)
        except Exception:
            logger.exception("Agent prompt background thread failed for session %s", session_id)
        finally:
            try:
                pending = [pending_task for pending_task in asyncio.all_tasks(loop) if not pending_task.done()]
                for pending_task in pending:
                    pending_task.cancel()
                if pending:
                    loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
            finally:
                asyncio.set_event_loop(None)
                loop.close()
                with self._prompt_tasks_lock:
                    if self._prompt_threads.get(session_id) is threading.current_thread():
                        self._prompt_threads.pop(session_id, None)

    def _session_max_seconds(self) -> float:
        try:
            from core.config import settings

            # Config Field enforces ge=60 for env values; allow lower only when
            # tests monkeypatch settings for fast timeout coverage.
            raw = int(getattr(settings, "agent_session_max_seconds", 3600) or 3600)
            return float(max(1, raw))
        except Exception:
            return 3600.0

    async def _await_with_session_timeout(self, awaitable: Any, *, label: str) -> Any:
        """Enforce a wall-clock budget around long prompt/resume work."""
        timeout = self._session_max_seconds()
        try:
            return await asyncio.wait_for(awaitable, timeout=timeout)
        except TimeoutError as exc:
            raise TimeoutError(
                f"Agent {label} exceeded wall-clock limit of {int(timeout)} seconds "
                f"(AGENT_SESSION_MAX_SECONDS)."
            ) from exc

    async def _run_prompt_background(self, session_id: str, request: AgentPromptRequest, prompt_id: str) -> None:
        loop = asyncio.get_running_loop()
        current_task = asyncio.current_task()
        if current_task is not None:
            with self._prompt_tasks_lock:
                self._prompt_tasks[session_id] = (loop, current_task)
        try:
            if not self._is_active_prompt(session_id, prompt_id):
                return
            await self._await_with_session_timeout(self.service.prompt(session_id, request), label="prompt")
            session = self.service.repository.get_session(session_id)
            if session:
                self.service.state_machine.clear_active_prompt(session_id, prompt_id)
        except asyncio.CancelledError:
            session = self.service.repository.get_session(session_id)
            if session and str(session.get("status") or "") not in self.service.TERMINAL_STATUSES:
                self.interrupt_session(session_id, "Agent 后台任务已取消。")
            raise
        except TimeoutError as exc:
            try:
                if self._is_active_prompt(session_id, prompt_id):
                    self._record_session_timeout(session_id, exc)
            except Exception as failure_exc:
                if self._is_active_prompt(session_id, prompt_id):
                    self._record_background_failure_fallback(session_id, exc, failure_exc)
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
            # Release the per-session start lock once the prompt task is done so
            # the _session_start_locks dict doesn't grow unbounded over many sessions.
            with self._session_start_locks_lock:
                self._session_start_locks.pop(session_id, None)

    def _freeze_running_parts(
        self,
        session_id: str,
        *,
        reason: str,
        flag_key: str,
        title: str | None = None,
    ) -> None:
        """Mark in-flight parts blocked so the timeline matches a terminal session."""
        repository = self.service.repository
        for part in repository.list_parts(session_id):
            if part.get("status") != "running":
                continue
            payload = dict(part.get("payload") or {})
            payload[flag_key] = True
            repository.update_part(
                part["id"],
                status="blocked",
                title=part.get("title") or title or "已停止",
                content=part.get("content") or reason,
                payload=payload,
            )

    def _record_session_timeout(self, session_id: str, exc: Exception) -> None:
        """Persist a recoverable timeout terminal state for wall-clock budget violations."""
        repository = self.service.repository
        session = repository.get_session(session_id)
        if not session:
            raise ValueError("Agent session not found")
        message = str(exc)[:600] or "Agent 任务已超时。"
        # Best-effort cancel of the in-process task (subprocess tools may still
        # run briefly; part freeze keeps the transcript consistent either way).
        self._cancel_prompt_task(session_id)
        self._freeze_running_parts(
            session_id,
            reason=message,
            flag_key="timed_out",
            title="已超时",
        )
        # Re-read after part updates so ensure_failed_metadata sees latest metadata.
        session = repository.get_session(session_id) or session
        metadata = ensure_failed_metadata(
            session,
            message,
            failure_kind="timeout",
            next_action="rerun_prompt",
            recoverable=True,
        )
        summary = repository.add_part(
            session_id,
            "summary",
            status="completed",
            title="任务超时",
            content=message,
            payload={
                "summary": message,
                "failure_kind": "timeout",
                "next_action": "rerun_prompt",
                "timeout": True,
            },
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
                "status": "needs_manual_review",
                "summary": message,
                "error": message,
                "failure_kind": "timeout",
                "next_action": "rerun_prompt",
            },
        )

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
        self._freeze_running_parts(
            session_id,
            reason=message,
            flag_key="interrupted",
            title="已中断",
        )

        metadata = ensure_session_state(dict((repository.get_session(session_id) or session).get("metadata") or {}))
        metadata["failure_kind"] = "user_interrupted"
        metadata["next_action"] = "rerun_prompt"
        metadata["recoverable"] = True
        self.service.state_machine.mark_interrupted(session_id, reason=message, metadata=metadata)
        repository.add_part(
            session_id,
            "summary",
            status="completed",
            title="已中断",
            content=f"{message} 已停止继续调用模型和工具，当前 transcript 已保留。",
            payload={"summary": message, "interrupted": True, "failure_kind": "user_interrupted", "next_action": "rerun_prompt"},
        )
        repository.add_event(
            session_id,
            "session_interrupted",
            message,
            {
                "session_id": session_id,
                "status": "interrupted",
                "summary": message,
                "interrupted": True,
                "failure_kind": "user_interrupted",
                "next_action": "rerun_prompt",
            },
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

    async def shutdown_prompt_tasks(self, timeout_seconds: float = 10.0) -> dict[str, int]:
        """Persist interruption and cancel prompt work before app shutdown.

        Detached prompts run in non-daemon threads, while approval/recovery
        prompts run as asyncio tasks.  Both are tracked here so shutdown does
        not leave their sessions in ``running`` when the process exits.
        """
        self._shutdown_started.set()
        with self._prompt_tasks_lock:
            task_records = dict(self._prompt_tasks)
            thread_records = dict(self._prompt_threads)
        session_ids = set(task_records) | set(thread_records)
        interrupted = 0
        for session_id in session_ids:
            try:
                self.service.repository.run_write_with_retry(
                    lambda session_id=session_id: self.interrupt_session(
                        session_id,
                        "Agent 服务正在关闭，后台任务已安全中断。",
                    )
                )
                interrupted += 1
            except ValueError:
                # The session was removed while shutdown was in progress.
                continue
            except Exception:
                logger.exception("Failed to persist Agent shutdown interruption for session %s", session_id)

        deadline = asyncio.get_running_loop().time() + max(timeout_seconds, 0.0)
        for _session_id, (loop, task) in task_records.items():
            if not task.done():
                loop.call_soon_threadsafe(task.cancel)
        for thread in thread_records.values():
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0 or not thread.is_alive():
                continue
            await asyncio.to_thread(thread.join, remaining)

        with self._prompt_tasks_lock:
            remaining_tasks = sum(not task.done() for _, task in self._prompt_tasks.values())
            remaining_threads = sum(thread.is_alive() for thread in self._prompt_threads.values())
        if remaining_tasks or remaining_threads:
            logger.warning(
                "Agent prompt shutdown timed out: tasks=%s threads=%s; sessions are persisted as interrupted",
                remaining_tasks,
                remaining_threads,
            )
        return {
            "interrupted": interrupted,
            "remaining_tasks": remaining_tasks,
            "remaining_threads": remaining_threads,
        }

    def record_prompt_failure(self, session_id: str, exc: Exception) -> dict[str, Any]:
        repository = self.service.repository
        session = repository.get_session(session_id)
        if not session:
            raise ValueError("Agent session not found")
        message = f"模型调用失败或内部错误，已停止且没有继续执行动作。错误：{str(exc)[:600]}"
        metadata = ensure_failed_metadata(session, message, failure_kind="runtime_error", next_action="manual_review", recoverable=True)
        # Phase 4: keep a durable, non-secret failure fingerprint on execution_trace.
        try:
            from agent_session.model_adapter import get_last_chat_model_resolution

            resolution = get_last_chat_model_resolution() or {}
        except Exception:
            resolution = {}
        trace = dict(metadata.get("execution_trace") or {})
        if resolution:
            for key in (
                "model_entry",
                "path",
                "fallback_used",
                "provider",
                "model",
                "model_string",
                "base_url",
                "has_api_key",
                "official_error",
            ):
                if key in resolution and resolution[key] is not None:
                    trace[key] = resolution[key]
        error_text = str(exc)[:600]
        trace["last_model_error"] = error_text
        trace["last_graph_error"] = error_text
        metadata["execution_trace"] = trace
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
                "status": "needs_manual_review",
                "summary": message,
                "error": str(exc)[:1200],
                "fallback": False,
                "failure_kind": "runtime_error",
                "next_action": "manual_review",
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
                metadata = ensure_failed_metadata(session, message, failure_kind="runtime_error", next_action="manual_review", recoverable=True)
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
                        "failure_kind": "runtime_error",
                        "next_action": "manual_review",
                    },
                )
                self.service.event_service._notify_event(session_id, event)

            self.service.repository.run_write_with_retry(write_failure)
        except Exception:
            logger.exception("Failed to apply minimal Agent failure fallback for session %s", session_id)
