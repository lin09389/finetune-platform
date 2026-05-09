from __future__ import annotations

import json
import logging
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import BackgroundTasks

from agent_runtime.runner import resolve_saved_provider
from core.config import settings
from core.db_manager import run_sync
from security.encryption import secure_storage

from .langgraph import AgentSessionGraphRunner
from .models import AgentPromptRequest, AgentSessionCreate, AgentSessionResponse
from .processor import AgentSessionProcessor, ModelCall
from .repository import AgentSessionRepository
from .state import ensure_session_state, record_fallback_summary, set_phase

logger = logging.getLogger(__name__)


class AgentSessionService:
    def __init__(
        self,
        repository: AgentSessionRepository | None = None,
        processor: AgentSessionProcessor | None = None,
        model_call: ModelCall | None = None,
    ):
        self.repository = repository or AgentSessionRepository()
        self.processor = processor or AgentSessionProcessor(self.repository)
        self.model_call = model_call
        self._graph_runner: AgentSessionGraphRunner | bool | None = None
        self._graph_runner_error: str | None = None

    ACTIVE_STATUSES = {"running", "verifying", "repairing", "waiting_approval", "waiting_permission"}

    async def _get_graph_runner(self) -> AgentSessionGraphRunner | None:
        if not settings.agent_session_langgraph_enabled:
            return None
        if self._graph_runner is None:
            try:
                self._graph_runner = AgentSessionGraphRunner(
                    repository=self.repository,
                    processor=self.processor,
                    model_call=self.model_call,
                )
                await self._graph_runner.get_graph()
                self._graph_runner_error = None
            except Exception as exc:
                logger.warning("agent_session LangGraph init failed, falling back to processor: %s", exc)
                self._graph_runner = False
                self._graph_runner_error = str(exc)
        return self._graph_runner or None

    def create_session(self, request: AgentSessionCreate) -> AgentSessionResponse:
        session = self.repository.create_session(
            {
                "chat_session_id": request.chat_session_id,
                "agent_id": request.agent_id,
                "title": request.title or "Agent Session",
                "project_path": request.project_path or str(Path.cwd()),
                "provider": request.provider,
                "model": request.model,
                "metadata": {"autonomy_mode": request.autonomy_mode or "safe_auto"},
            }
        )
        session["parts"] = []
        return AgentSessionResponse(**self._attach_recovery_diagnostics(session))

    def get_session(self, session_id: str) -> AgentSessionResponse:
        session = self.repository.get_session(session_id)
        if not session:
            raise ValueError("Agent session not found")
        session["parts"] = self.repository.list_parts(session_id)
        return AgentSessionResponse(**self._attach_recovery_diagnostics(session))

    async def prompt(self, session_id: str, request: AgentPromptRequest) -> AgentSessionResponse:
        session = self.repository.get_session(session_id)
        if not session:
            raise ValueError("Agent session not found")
        if request.provider or request.model:
            metadata = dict(session.get("metadata") or {})
            self.repository.update_session(session_id, provider=request.provider or session.get("provider"), model=request.model or session.get("model"), metadata=metadata)
            session = self.repository.get_session(session_id) or session
        model_call = self.model_call or self._cloud_model_call(session)
        stream_model_call = None
        metadata = ensure_session_state(dict(session.get("metadata") or {}))
        if self.model_call is None:
            try:
                stream_model_call = self._cloud_stream_model_call(session)
                metadata["streaming_diagnostics"] = {
                    "mode": "chat_stream",
                    "status": "configured",
                    "provider": session.get("provider") or "",
                    "model": session.get("model") or "",
                    "source": "cloud_provider",
                    "fallback_to_non_stream": False,
                }
            except (ValueError, TypeError) as exc:
                stream_model_call = None
                metadata["streaming_diagnostics"] = {
                    "mode": "non_stream",
                    "status": "unavailable",
                    "provider": session.get("provider") or "",
                    "model": session.get("model") or "",
                    "source": "cloud_provider",
                    "reason": str(exc)[:300],
                    "fallback_to_non_stream": True,
                }
        else:
            metadata["streaming_diagnostics"] = {
                "mode": "non_stream",
                "status": "disabled",
                "source": "injected_model_call",
                "reason": "测试或自定义 model_call 未提供 stream_model_call",
                "fallback_to_non_stream": True,
            }
        self.repository.update_session(session_id, metadata=metadata)
        session = self.repository.get_session(session_id) or session
        try:
            runner = await self._get_graph_runner() if stream_model_call is None else None
            if runner is not None:
                initial_state = self._build_langgraph_initial_state(session_id, request.content)
                try:
                    await runner.run_prompt(initial_state)
                    result = self.repository.get_session(session_id) or session
                    result["parts"] = self.repository.list_parts(session_id)
                except Exception as exc:
                    logger.warning("agent_session LangGraph prompt failed, falling back to processor: %s", exc)
                    self._record_langgraph_fallback(session_id, str(exc))
                    result = await self.processor.prompt(session_id, request.content, model_call=model_call, stream_model_call=stream_model_call)
            else:
                if settings.agent_session_langgraph_enabled and stream_model_call is None and self._graph_runner_error:
                    self._record_langgraph_fallback(session_id, self._graph_runner_error)
                result = await self.processor.prompt(session_id, request.content, model_call=model_call, stream_model_call=stream_model_call)
        except Exception as exc:
            result = self.record_prompt_failure(session_id, exc)
        return AgentSessionResponse(**self._attach_recovery_diagnostics(result))

    def start_prompt_background(
        self,
        session_id: str,
        request: AgentPromptRequest,
        background_tasks: BackgroundTasks,
    ) -> AgentSessionResponse:
        session = self.repository.get_session(session_id)
        if not session:
            raise ValueError("Agent session not found")

        if str(session.get("status") or "") in self.ACTIVE_STATUSES:
            self.repository.add_event(
                session_id,
                "prompt_already_running",
                "Agent 正在处理当前任务，未重复启动。",
                {"session_id": session_id, "status": session.get("status"), "summary": "Agent 正在处理当前任务，未重复启动。"},
            )
            return self.get_session(session_id)

        metadata = ensure_session_state(dict(session.get("metadata") or {}))
        prompt_id = f"agprompt_{uuid.uuid4().hex}"
        now = datetime.now().isoformat()
        metadata["active_prompt_id"] = prompt_id
        metadata["background_run"] = True
        metadata["last_prompt_started_at"] = now
        metadata["current_goal"] = request.content
        metadata = set_phase(metadata, "running")
        session = self.repository.update_session(
            session_id,
            status="running",
            provider=request.provider or session.get("provider"),
            model=request.model or session.get("model"),
            metadata=metadata,
        )
        self.repository.add_event(
            session_id,
            "prompt_queued",
            "Agent 已进入后台执行。",
            {"session_id": session_id, "active_prompt_id": prompt_id, "status": "running", "summary": "Agent 已进入后台执行。"},
        )
        background_tasks.add_task(self._run_prompt_background, session_id, request, prompt_id)
        session["parts"] = self.repository.list_parts(session_id)
        return AgentSessionResponse(**self._attach_recovery_diagnostics(session))

    async def _run_prompt_background(self, session_id: str, request: AgentPromptRequest, prompt_id: str) -> None:
        try:
            await self.prompt(session_id, request)
            session = self.repository.get_session(session_id)
            if session:
                metadata = ensure_session_state(dict(session.get("metadata") or {}))
                if metadata.get("active_prompt_id") == prompt_id:
                    metadata["last_prompt_completed_at"] = datetime.now().isoformat()
                    metadata["active_prompt_id"] = None
                    self.repository.update_session(session_id, metadata=metadata)
        except Exception as exc:
            try:
                self.record_prompt_failure(session_id, exc)
            except Exception:
                # Background task failures must never escape into the server loop.
                pass

    def record_prompt_failure(self, session_id: str, exc: Exception) -> dict[str, Any]:
        session = self.repository.get_session(session_id)
        if not session:
            raise ValueError("Agent session not found")
        message = f"Agent 执行时发生内部错误，已停止且没有继续执行动作。错误：{str(exc)[:600]}"
        metadata = self._ensure_failed_metadata(session, message)
        summary = self.repository.add_part(
            session_id,
            "summary",
            status="completed",
            title="最终结果",
            content=message,
            payload={"summary": message, "fallback": True, "error": str(exc)[:1200]},
        )
        self.repository.update_session(session_id, status="needs_manual_review", metadata=metadata)
        self.repository.add_event(
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
                "fallback": True,
            },
        )
        result = self.repository.get_session(session_id) or session
        result["parts"] = self.repository.list_parts(session_id)
        return result

    def approve_permission(self, part_id: str, approved: bool) -> AgentSessionResponse:
        return AgentSessionResponse(**self._attach_recovery_diagnostics(self.processor.approve_part(part_id, approved)))

    async def approve_permission_async(self, part_id: str, approved: bool) -> AgentSessionResponse:
        part = self.repository.get_part(part_id)
        if not part:
            raise ValueError("Agent part not found")
        session = self.repository.get_session(part["session_id"]) or {}
        metadata = ensure_session_state(dict(session.get("metadata") or {}))
        if settings.agent_session_langgraph_enabled and metadata.get("runtime") == "langgraph":
            runner = await self._get_graph_runner()
            if runner is None:
                raise RuntimeError("LangGraph is not available for this session")
            self._record_resume_decision(part["session_id"], {"interrupt_kind": "permission_request", "part_id": part_id, "approved": approved})
            await runner.resume(
                part["session_id"],
                {"interrupt_kind": "permission_request", "part_id": part_id, "approved": approved},
            )
            return self.get_session(part["session_id"])
        return await run_sync(self.approve_permission, part_id, approved)

    def approve_action(self, part_id: str, approved: bool) -> AgentSessionResponse:
        return AgentSessionResponse(**self._attach_recovery_diagnostics(self.processor.approve_part(part_id, approved)))

    async def approve_action_async(self, part_id: str, approved: bool) -> AgentSessionResponse:
        part = self.repository.get_part(part_id)
        if not part:
            raise ValueError("Agent part not found")
        session = self.repository.get_session(part["session_id"]) or {}
        metadata = ensure_session_state(dict(session.get("metadata") or {}))
        if settings.agent_session_langgraph_enabled and metadata.get("runtime") == "langgraph":
            result = self.processor.approve_part(part_id, approved)
            if not approved:
                runner = await self._get_graph_runner()
                if runner is None:
                    raise RuntimeError("LangGraph is not available for this session")
                self._record_resume_decision(part["session_id"], {"interrupt_kind": "action_approval", "part_id": part_id, "approved": False})
                await runner.resume(part["session_id"], {"interrupt_kind": "action_approval", "part_id": part_id, "approved": False})
            return AgentSessionResponse(**self._attach_recovery_diagnostics(result))
        return await run_sync(self.approve_action, part_id, approved)

    def execute_action(self, part_id: str) -> AgentSessionResponse:
        return AgentSessionResponse(**self._attach_recovery_diagnostics(self.processor.execute_part(part_id)))

    async def execute_action_async(self, part_id: str) -> AgentSessionResponse:
        part = self.repository.get_part(part_id)
        if not part:
            raise ValueError("Agent part not found")
        session = self.repository.get_session(part["session_id"]) or {}
        metadata = ensure_session_state(dict(session.get("metadata") or {}))
        if settings.agent_session_langgraph_enabled and metadata.get("runtime") == "langgraph":
            runner = await self._get_graph_runner()
            if runner is None:
                raise RuntimeError("LangGraph is not available for this session")
            self._record_resume_decision(part["session_id"], {"interrupt_kind": "action_approval", "part_id": part_id, "decision": "executed"})
            await runner.execute_action_and_resume(
                part_id,
                {"interrupt_kind": "action_approval", "part_id": part_id, "decision": "executed"},
            )
            return self.get_session(part["session_id"])
        return await run_sync(self.execute_action, part_id)

    def list_events(self, session_id: str, since_event_id: str | None = None) -> list[dict[str, Any]]:
        return self.repository.list_events_after(session_id, since_event_id)

    def build_stream_chunk(self, event: dict[str, Any]) -> dict[str, Any]:
        payload = dict(event.get("payload") or {})
        session_id = str(event.get("session_id") or payload.get("session_id") or "")
        session = self.repository.get_session(session_id) or {}
        payload_chunk_type = payload.get("chunk_type")
        payload_part = payload.get("part")
        event_type = str(event.get("event_type") or "")
        computed_part = payload_part if isinstance(payload_part, dict) else None
        if computed_part is None:
            computed_part = self._stream_part_snapshot(event, payload)
        chunk_type = payload_chunk_type if isinstance(payload_chunk_type, str) else self._stream_chunk_type(event_type, payload, computed_part)
        return {
            "id": event.get("id"),
            "session_id": session_id,
            "created_at": event.get("created_at"),
            "event_type": event_type,
            "chunk_type": chunk_type,
            "message": str(event.get("message") or ""),
            "payload": payload,
            "session_status": session.get("status"),
            "agent_id": session.get("agent_id"),
            "phase": payload.get("phase"),
            "tool": payload.get("tool"),
            "delta": payload.get("delta"),
            "content": payload.get("content"),
            "summary": payload.get("summary") or event.get("message"),
            "part": computed_part,
        }

    def build_session_snapshot_chunk(self, session_id: str) -> dict[str, Any]:
        session = self.repository.get_session(session_id)
        if not session:
            return {"chunk_type": "session_snapshot", "session_id": session_id, "session_status": "unknown", "parts": [], "payload": {}}
        parts = self.repository.list_parts(session_id)
        session["parts"] = parts
        hydrated = self._attach_recovery_diagnostics(session)
        return {
            "id": f"snap_{session_id}",
            "session_id": session_id,
            "created_at": hydrated.get("updated_at") or hydrated.get("created_at") or "",
            "event_type": "session_snapshot",
            "chunk_type": "session_snapshot",
            "message": "Session state snapshot",
            "payload": {},
            "session_status": hydrated.get("status"),
            "agent_id": hydrated.get("agent_id"),
            "phase": None,
            "tool": None,
            "delta": None,
            "content": None,
            "summary": None,
            "part": None,
            "session_snapshot": hydrated,
        }

    def _ensure_failed_metadata(self, session: dict[str, Any], message: str) -> dict[str, Any]:
        metadata = ensure_session_state(dict(session.get("metadata") or {}))
        metadata = record_fallback_summary(metadata)
        metadata = set_phase(metadata, "needs_manual_review")
        metadata["latest_error"] = message
        metadata["model_protocol_status"] = "needs_manual_review"
        state = dict(metadata.get("state") or {})
        state["latest_error"] = message
        metadata["state"] = state
        return metadata

    def _attach_recovery_diagnostics(self, session: dict[str, Any]) -> dict[str, Any]:
        hydrated = dict(session)
        session_id = str(hydrated.get("id") or "")
        parts = list(hydrated.get("parts") or self.repository.list_parts(session_id))
        events = self.repository.list_events(session_id) if session_id else []
        metadata = ensure_session_state(dict(hydrated.get("metadata") or {}))
        diagnostics = self._build_diagnostics(hydrated, parts, events, metadata)
        metadata["diagnostics"] = diagnostics
        metadata["latest_event"] = diagnostics.get("latest_event")
        metadata["latest_tool_call"] = diagnostics.get("latest_tool_call")
        metadata["latest_tool_result"] = diagnostics.get("latest_tool_result")
        metadata["latest_action"] = diagnostics.get("latest_action")
        metadata["latest_command"] = diagnostics.get("latest_command")
        metadata["latest_summary"] = diagnostics.get("latest_summary")
        metadata["latest_error"] = diagnostics.get("latest_error")
        metadata["stop_reason"] = diagnostics.get("stop_reason")
        metadata["next_action"] = diagnostics.get("next_action")
        hydrated["metadata"] = metadata
        hydrated["parts"] = parts
        return hydrated

    def _stream_part_snapshot(self, event: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any] | None:
        session_id = str(event.get("session_id") or payload.get("session_id") or "")
        event_type = str(event.get("event_type") or "")
        part_id = payload.get("part_id")
        stored_part = self.repository.get_part(str(part_id)) if isinstance(part_id, str) and part_id.startswith("agp_") else None
        if stored_part is None and not part_id:
            return None
        if event_type in {"part_delta", "model_stream_started", "model_stream_failed"}:
            part_type = str(payload.get("part_type") or (stored_part or {}).get("type") or "text")
            status = str(payload.get("status") or (stored_part or {}).get("status") or ("failed" if event_type == "model_stream_failed" else "running"))
            stored_payload = dict((stored_part or {}).get("payload") or {})
            if payload.get("streaming"):
                stored_payload["streaming"] = True
            return {
                "id": str(part_id or ""),
                "session_id": session_id,
                "type": part_type,
                "status": status,
                "title": (stored_part or {}).get("title") or ("流式输出失败" if event_type == "model_stream_failed" else "生成中"),
                "content": str(payload.get("content") or (stored_part or {}).get("content") or ""),
                "payload": stored_payload,
                "created_at": (stored_part or {}).get("created_at") or event.get("created_at"),
                "updated_at": event.get("created_at"),
            }
        if stored_part is not None:
            return stored_part
        return {
            "id": str(part_id or ""),
            "session_id": session_id,
            "type": str(payload.get("part_type") or "text"),
            "status": str(payload.get("status") or "completed"),
            "title": None,
            "content": str(payload.get("content") or payload.get("summary") or event.get("message") or ""),
            "payload": payload,
            "created_at": event.get("created_at"),
            "updated_at": event.get("created_at"),
        }

    @staticmethod
    def _stream_chunk_type(event_type: str, payload: dict[str, Any], part: dict[str, Any] | None) -> str:
        if event_type == "phase_change":
            return "phase"
        if event_type == "model_stream_started":
            return "part_start"
        if event_type == "part_delta":
            return "part_delta"
        if event_type == "model_stream_completed":
            return "part_complete"
        if event_type == "tool_call_started":
            return "tool_call"
        if event_type == "tool_call_completed":
            return "tool_result"
        if event_type == "summary_completed":
            return "summary"
        if event_type == "permission_asked":
            return "permission_request"
        if event_type in {"action_proposed", "action_approved", "action_rejected", "action_executed", "action_failed", "command_completed", "command_failed"}:
            return "action"
        if event_type in {"model_stream_failed", "session_failed", "session_blocked"}:
            return "error"
        if event_type in {"session_started", "prompt_queued", "prompt_already_running"}:
            return "status"
        if part is not None:
            return "part_snapshot"
        if payload.get("tool"):
            return "tool"
        return "event"

    def _build_diagnostics(
        self,
        session: dict[str, Any],
        parts: list[dict[str, Any]],
        events: list[dict[str, Any]],
        metadata: dict[str, Any],
    ) -> dict[str, Any]:
        status = str(session.get("status") or "idle")
        state = dict(metadata.get("state") or {})
        latest_event = events[-1] if events else None
        latest_tool_call = self._latest_part(parts, {"tool_call"})
        latest_tool_result = self._latest_part(parts, {"tool_result"})
        latest_action = self._latest_part(parts, {"diff", "command", "permission"})
        latest_command = self._latest_part(parts, {"command"})
        latest_summary = self._latest_part(parts, {"summary"})
        latest_error = self._latest_part(parts, {"error"})
        stop_reason, next_action = self._explain_status(
            status,
            state,
            latest_summary,
            latest_error,
            latest_action,
            latest_event,
        )
        return {
            "status": status,
            "current_phase": state.get("current_phase") or metadata.get("current_phase") or status,
            "latest_event": self._compact_event(latest_event),
            "latest_tool_call": self._compact_part(latest_tool_call),
            "latest_tool_result": self._compact_part(latest_tool_result),
            "latest_action": self._compact_part(latest_action),
            "latest_command": self._compact_part(latest_command),
            "latest_summary": self._compact_part(latest_summary),
            "latest_error": self._compact_part(latest_error),
            "recent_events": [self._compact_event(event) for event in events[-5:]],
            "stop_reason": stop_reason,
            "next_action": next_action,
            "refresh_safe": True,
        }

    @staticmethod
    def _latest_part(parts: list[dict[str, Any]], part_types: set[str]) -> dict[str, Any] | None:
        for part in reversed(parts):
            if str(part.get("type")) in part_types:
                return part
        return None

    @staticmethod
    def _compact_part(part: dict[str, Any] | None) -> dict[str, Any] | None:
        if not part:
            return None
        payload = part.get("payload") if isinstance(part.get("payload"), dict) else {}
        return {
            "id": part.get("id"),
            "type": part.get("type"),
            "status": part.get("status"),
            "title": part.get("title"),
            "content": AgentSessionService._truncate(str(part.get("content") or ""), 240),
            "policy_decision": payload.get("policy_decision") or payload.get("execution_mode"),
            "risk_level": payload.get("risk_level"),
            "policy_reason": payload.get("policy_reason"),
            "changed_files": payload.get("changed_files") or [],
            "exit_code": payload.get("exit_code"),
            "failure_summary": AgentSessionService._truncate(str(payload.get("failure_summary") or ""), 240),
        }

    @staticmethod
    def _compact_event(event: dict[str, Any] | None) -> dict[str, Any] | None:
        if not event:
            return None
        return {
            "id": event.get("id"),
            "event_type": event.get("event_type"),
            "message": AgentSessionService._truncate(str(event.get("message") or ""), 240),
            "created_at": event.get("created_at"),
            "payload": event.get("payload") if isinstance(event.get("payload"), dict) else {},
        }

    @staticmethod
    def _explain_status(
        status: str,
        state: dict[str, Any],
        latest_summary: dict[str, Any] | None,
        latest_error: dict[str, Any] | None,
        latest_action: dict[str, Any] | None,
        latest_event: dict[str, Any] | None,
    ) -> tuple[str, str]:
        summary_text = str((latest_summary or {}).get("content") or "").strip()
        error_text = str((latest_error or {}).get("content") or "").strip()
        action_payload = latest_action.get("payload") if latest_action and isinstance(latest_action.get("payload"), dict) else {}
        action_reason = str((action_payload or {}).get("policy_reason") or (latest_action or {}).get("content") or "").strip()
        event_message = str((latest_event or {}).get("message") or "").strip()
        latest_state_error = str(state.get("latest_error") or "").strip()

        if status == "completed":
            return summary_text or event_message or "任务已完成。", "可以查看结果，或继续提出下一步需求。"
        if status == "waiting_approval":
            reason = action_reason or event_message or "有修改或命令需要确认。"
            return reason, "请确认待处理的修改或验证命令。"
        if status == "waiting_permission":
            return event_message or "有工具调用需要权限确认。", "请批准或拒绝该工具调用。"
        if status == "needs_manual_review":
            reason = summary_text or error_text or latest_state_error or event_message or "Agent 已停在需要人工处理的状态。"
            return reason, "请根据上方原因调整需求、手动确认动作，或让 Agent 继续修复。"
        if status == "failed":
            reason = error_text or latest_state_error or summary_text or event_message or "执行失败。"
            return reason, "请查看失败详情后重试，或改用只读/确认模式。"
        if status in {"running", "verifying", "repairing"}:
            phase = str(state.get("current_phase") or status)
            return event_message or f"Agent 正在处理：{phase}。", "等待当前步骤完成，或刷新运行状态查看最新进展。"
        return event_message or "会话已创建，等待输入。", "发送一个开发目标开始执行。"

    @staticmethod
    def _truncate(value: str, limit: int) -> str:
        if len(value) <= limit:
            return value
        return value[:limit].rstrip() + "...[truncated]"

    def _cloud_model_call(self, session: dict[str, Any]) -> ModelCall:
        async def call(messages: list[dict[str, str]]) -> str:
            provider_name = session.get("provider")
            if not provider_name:
                return self._local_fallback_model_response(messages, "没有选择云端模型")
            key_data = secure_storage.get(f"cloud_{provider_name}_key") or {}
            api_key = key_data.get("api_key", "")
            if not api_key:
                return self._local_fallback_model_response(messages, f"未配置 {provider_name} 的 API Key")
            provider = resolve_saved_provider(provider_name, key_data)
            if provider is None:
                return self._local_fallback_model_response(messages, f"不支持的云端服务商：{provider_name}")
            model = session.get("model") or key_data.get("default_model") or provider.get_default_model()
            try:
                response = await provider.chat(
                    messages=messages,
                    model=model,
                    api_key=api_key,
                    temperature=0.2,
                    max_tokens=2400,
                )
            except Exception as exc:
                message = str(exc).replace('"', "'")[:600]
                return self._local_fallback_model_response(messages, f"云端模型调用失败：{message}")
            return response.get("content", "")

        return call

    def _cloud_stream_model_call(self, session: dict[str, Any]):
        from collections.abc import AsyncGenerator

        provider_name = session.get("provider")
        key_data = (secure_storage.get(f"cloud_{provider_name}_key") or {}) if provider_name else {}
        if not provider_name:
            raise ValueError("没有选择云端模型")
        api_key = key_data.get("api_key", "") if isinstance(key_data, dict) else ""
        if not api_key:
            raise ValueError(f"未配置 {provider_name} 的 API Key")
        provider = resolve_saved_provider(provider_name, key_data)
        if provider is None:
            raise ValueError(f"不支持的云端服务商：{provider_name}")
        model = (session.get("model") or key_data.get("default_model", "")) if isinstance(key_data, dict) else (session.get("model") or "")
        if not model:
            model = provider.get_default_model()

        async def stream(messages: list[dict[str, str]]):
            async for chunk in provider.chat_stream(
                messages=messages,
                model=model,
                api_key=api_key,
                temperature=0.2,
                max_tokens=2400,
            ):
                yield chunk

        return stream

    def _local_fallback_model_response(self, messages: list[dict[str, str]], reason: str) -> str:
        latest_user = next((item.get("content", "") for item in reversed(messages) if item.get("role") == "user"), "")
        transcript = "\n".join(item.get("content", "") for item in messages[-6:])
        if "工具结果" in latest_user or "工具结果" in transcript:
            return json.dumps(
                {
                    "tool": "finalize",
                    "arguments": {
                        "summary": f"已完成本地只读兜底流程。原因：{reason}。已根据工具结果生成总结；未写入文件，也未执行命令。"
                    },
                },
                ensure_ascii=False,
            )

        explicit_files = self._extract_requested_files(transcript)
        read_only = any(marker in transcript for marker in ("不要写文件", "不写文件", "只读", "读取", "看看", "分析"))
        if explicit_files and read_only:
            return (
                "云端模型暂不可用，我先按本地只读规则读取你明确指定的文件。\n"
                + json.dumps(
                    [{"tool": "read", "arguments": {"path": path}} for path in explicit_files[:6]],
                    ensure_ascii=False,
                )
            )
        return json.dumps(
            {
                "tool": "finalize",
                "arguments": {
                    "summary": f"Agent 无法调用云端模型，已安全停止。原因：{reason}。未写入文件，也未执行命令。"
                },
            },
            ensure_ascii=False,
        )

    @staticmethod
    def _extract_requested_files(text: str) -> list[str]:
        files: list[str] = []
        for token in re.findall(r"[\w./\\-]+\.(?:py|ts|tsx|css|md|json)", text):
            normalized = token.strip("`'\"，。,；;：:（）()[]{}").replace("\\", "/")
            if normalized and normalized not in files:
                files.append(normalized)
        return files

    def _build_langgraph_initial_state(self, session_id: str, prompt: str) -> dict[str, Any]:
        session = self.repository.get_session(session_id)
        if not session:
            raise ValueError("Agent session not found")
        metadata = ensure_session_state(dict(session.get("metadata") or {}))
        metadata["runtime"] = "langgraph"
        metadata["checkpoint"] = "sqlite"
        metadata["fallback_reason"] = None
        metadata["last_graph_error"] = None
        metadata["last_resume_decision"] = None
        self.repository.update_session(session_id, metadata=metadata)
        return {
            "session_id": session_id,
            "prompt": prompt,
            "messages": [],
            "pending_tool_calls": [],
            "tool_results": [],
            "pending_part_id": None,
            "pending_permission_call": None,
            "final_summary": None,
            "phase": metadata.get("current_phase") or "running",
            "repair_attempts": int(metadata.get("repair_attempts") or 0),
            "protocol_repair_count": int(metadata.get("protocol_repair_count") or 0),
            "execution_state": "created",
            "iterations": 0,
            "last_model_raw": "",
        }

    def _record_langgraph_fallback(self, session_id: str, reason: str) -> None:
        session = self.repository.get_session(session_id)
        if not session:
            return
        metadata = ensure_session_state(dict(session.get("metadata") or {}))
        metadata["fallback_reason"] = reason[:600]
        metadata["last_graph_error"] = reason[:600]
        self.repository.update_session(session_id, metadata=metadata)

    def _record_resume_decision(self, session_id: str, decision: dict[str, Any]) -> None:
        session = self.repository.get_session(session_id)
        if not session:
            return
        metadata = ensure_session_state(dict(session.get("metadata") or {}))
        metadata["last_resume_decision"] = dict(decision)
        self.repository.update_session(session_id, metadata=metadata)
