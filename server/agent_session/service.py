from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from datetime import datetime
from pathlib import Path
from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import BackgroundTasks
from fastapi import HTTPException

from context.deepagents import build_deepagents_context_pack
from core.config import settings
from core.db_manager import run_sync
from workspace.local_paths import get_allowed_workspace_roots

from .agent_registry import AgentRegistry
from .approval import permission_decisions
from .async_subagents import AsyncSubagentService
from .deepagents_runtime import DeepAgentsSessionRunner
from .events import AgentSessionEventBus
from .models import (
    AgentArtifactResponse,
    AgentPromptRequest,
    AgentSessionCreate,
    AgentSessionOverviewResponse,
    AgentSessionResponse,
)
from .repository import AgentSessionRepository
from .state import ensure_session_state, record_fallback_summary, set_phase

logger = logging.getLogger(__name__)
ModelCall = Callable[[list[dict[str, str]]], Awaitable[str]]


class AgentSessionService:
    _event_bus = AgentSessionEventBus()
    _event_queues = AgentSessionEventBus._queues
    _event_lock = AgentSessionEventBus._lock

    def __init__(
        self,
        repository: AgentSessionRepository | None = None,
        processor: Any | None = None,
        model_call: ModelCall | None = None,
    ):
        _ = processor
        self.repository = repository or AgentSessionRepository()
        self.model_call = model_call
        self.agent_registry = AgentRegistry()
        self.async_subagent_service = AsyncSubagentService(
            self.repository,
            self._notify_event,
            model_call=self.model_call,
            interrupt_session=self.interrupt_session,
        )
        self.deepagents_runner = DeepAgentsSessionRunner(
            repository=self.repository,
            notify_event=self._notify_event,
            model_call=self.model_call,
            async_subagent_service=self.async_subagent_service,
        )

    ACTIVE_STATUSES = {"running", "verifying", "repairing", "waiting_approval", "waiting_permission"}

    TERMINAL_STATUSES = {"completed", "failed", "interrupted", "needs_manual_review"}

    def subscribe_events(self, session_id: str) -> asyncio.Queue[dict[str, Any]]:
        return self._event_bus.subscribe(session_id)

    def unsubscribe_events(self, session_id: str, queue: asyncio.Queue[dict[str, Any]]) -> None:
        self._event_bus.unsubscribe(session_id, queue)

    def _notify_event(self, session_id: str, event: dict[str, Any]) -> None:
        self._event_bus.notify(session_id, event)

    def _sync_async_service_model_call(self) -> None:
        self.async_subagent_service.set_model_call(self.model_call)
        self.deepagents_runner.model_call = self.model_call

    async def start_async_subtask(self, session_id: str, subagent_type: str, description: str) -> dict[str, Any]:
        self._sync_async_service_model_call()
        return await self.async_subagent_service.start_task(session_id, subagent_type, description)

    def check_async_subtask(self, session_id: str, task_id: str) -> dict[str, Any]:
        return self.async_subagent_service.check_task(session_id, task_id)

    def list_async_subtasks(self, session_id: str, status_filter: str | None = None) -> dict[str, Any]:
        return self.async_subagent_service.list_tasks(session_id, status_filter)

    async def cancel_async_subtask(self, session_id: str, task_id: str, reason: str | None = None) -> dict[str, Any]:
        self._sync_async_service_model_call()
        return await self.async_subagent_service.cancel_task(session_id, task_id, reason)

    async def update_async_subtask(self, session_id: str, task_id: str, description: str) -> dict[str, Any]:
        self._sync_async_service_model_call()
        return await self.async_subagent_service.update_task(session_id, task_id, description)

    async def recover_async_subtasks(self) -> dict[str, Any]:
        self._sync_async_service_model_call()
        return await self.async_subagent_service.recover_running_tasks()

    async def shutdown_async_subtasks(self) -> None:
        await self.async_subagent_service.shutdown()

    def _event(self, session_id: str, event_type: str, message: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        enriched = dict(payload or {})
        enriched.setdefault("session_id", session_id)
        part_id = enriched.get("part_id")
        part = enriched.get("part") if isinstance(enriched.get("part"), dict) else None
        if part is None and isinstance(part_id, str) and part_id.startswith("agp_"):
            part = self.repository.get_part(part_id)
            if part:
                enriched["part"] = part
        if part:
            enriched.setdefault("part_type", part.get("type"))
            enriched.setdefault("status", part.get("status"))
            enriched.setdefault("summary", part.get("content") or part.get("title") or message)
        enriched.setdefault("summary", message)
        enriched.setdefault("chunk_type", self._stream_chunk_type(event_type, enriched, part))
        event = self.repository.add_event(session_id, event_type, message, enriched)
        self._notify_event(session_id, event)
        return event

    def _default_project_path(self) -> str:
        base_dir = settings.base_dir.resolve()
        workspace = base_dir.parent if base_dir.name == "server" else base_dir
        return str(workspace)

    def _validate_project_path(self, project_path: str | None) -> str:
        if not project_path or not project_path.strip():
            return self._default_project_path()
        resolved = Path(project_path).expanduser().resolve()
        if not resolved.exists():
            raise ValueError("project_path does not exist")
        if not resolved.is_dir():
            raise ValueError("project_path must be a directory")
        default_root = Path(self._default_project_path()).resolve()
        allowed_roots = get_allowed_workspace_roots({default_root, settings.base_dir.resolve(), Path.cwd().resolve()})
        if not any(resolved == allowed or resolved.is_relative_to(allowed) for allowed in allowed_roots):
            allowed = ", ".join(sorted(str(path) for path in allowed_roots))
            raise ValueError(f"project_path must be inside the workspace. Allowed roots: {allowed}")
        return str(resolved)

    def create_session(self, request: AgentSessionCreate) -> AgentSessionResponse:
        try:
            project_path = self._validate_project_path(request.project_path)
            provider, model = self._resolve_session_model_defaults(request.agent_id, request.provider, request.model)
            session = self.repository.create_session(
                {
                    "chat_session_id": request.chat_session_id,
                    "agent_id": request.agent_id,
                    "title": request.title or "Agent Session",
                    "project_path": project_path,
                    "provider": provider,
                    "model": model,
                    "metadata": {
                        "autonomy_mode": request.autonomy_mode or "safe_auto",
                        "deepagents_interrupt_on": True,
                    },
                }
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        session["parts"] = []
        return AgentSessionResponse(**self._attach_recovery_diagnostics(session))

    def _resolve_session_model_defaults(self, agent_id: str, provider: str | None, model: str | None) -> tuple[str | None, str | None]:
        if provider and model:
            return provider, model
        agent = self.agent_registry.get(agent_id)
        return provider or (agent.default_provider if agent else None), model or (agent.default_model if agent else None)

    def get_session(self, session_id: str) -> AgentSessionResponse:
        session = self.repository.get_session(session_id)
        if not session:
            raise ValueError("Agent session not found")
        session["parts"] = self.repository.list_parts(session_id)
        return AgentSessionResponse(**self._attach_recovery_diagnostics(session))

    def get_overview(self, session_id: str) -> AgentSessionOverviewResponse:
        session = self.get_session(session_id)
        metadata = dict(session.metadata or {})
        diagnostics = dict(metadata.get("diagnostics") or {})
        return AgentSessionOverviewResponse(
            session=session,
            task_plan=metadata.get("task_plan"),
            recent_events=list(diagnostics.get("recent_events") or []),
            artifacts=self._build_artifacts(session.parts),
            diagnostics=diagnostics,
        )

    async def prompt(self, session_id: str, request: AgentPromptRequest) -> AgentSessionResponse:
        session = self.repository.get_session(session_id)
        if not session:
            raise ValueError("Agent session not found")
        metadata = ensure_session_state(dict(session.get("metadata") or {}))
        if session.get("status") == "interrupted" or metadata.get("interrupt_requested"):
            return self.get_session(session_id)

        if request.provider or request.model:
            self.repository.update_session(
                session_id,
                provider=request.provider or session.get("provider"),
                model=request.model or session.get("model"),
                metadata=metadata,
            )
            session = self.repository.get_session(session_id) or session

        metadata = ensure_session_state(dict(session.get("metadata") or {}))
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
                "model_entry": "injected_model_call" if self.model_call is not None else "deepagents_init_chat_model",
                "fallback_used": False,
                "last_graph_error": None,
                "last_model_error": None,
            }
        )
        metadata["execution_trace"] = trace
        if self.model_call is not None:
            metadata["streaming_diagnostics"] = {
                "mode": "non_stream",
                "status": "disabled",
                "source": "injected_model_call",
                "reason": "测试或自定义 model_call 未提供 stream_model_call",
                "fallback_to_non_stream": True,
            }
        metadata["runtime"] = "deepagents"
        metadata["deepagents_thread_id"] = f"agent_session:{session_id}:deepagents"
        self.repository.update_session(session_id, metadata=metadata)
        session = self.repository.get_session(session_id) or session

        try:
            self._sync_async_service_model_call()
            result = await self.deepagents_runner.run_prompt(session_id, prompt_content, context_files=context_pack.files)
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
        if request.active_context or request.explicit_context:
            metadata["deep_context"] = {
                "active_context": request.active_context,
                "explicit_context": request.explicit_context,
            }
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

    def interrupt_session(self, session_id: str, reason: str | None = None) -> AgentSessionResponse:
        session = self.repository.get_session(session_id)
        if not session:
            raise ValueError("Agent session not found")
        if str(session.get("status") or "") in {"completed", "failed", "interrupted"}:
            return self.get_session(session_id)

        message = reason or "用户已中断 Agent 任务。"
        metadata = ensure_session_state(dict(session.get("metadata") or {}))
        metadata = set_phase(metadata, "interrupted")
        metadata["interrupt_requested"] = True
        metadata["interrupt_recorded"] = True
        metadata["interrupted_at"] = datetime.now().isoformat()
        metadata["active_prompt_id"] = None
        state = dict(metadata.get("state") or {})
        state["latest_error"] = message
        metadata["state"] = state

        for part in self.repository.list_parts(session_id):
            if part.get("status") == "running":
                payload = dict(part.get("payload") or {})
                payload["interrupted"] = True
                self.repository.update_part(
                    part["id"],
                    status="blocked",
                    title=part.get("title") or "已中断",
                    content=part.get("content") or message,
                    payload=payload,
                )

        self.repository.update_session(session_id, status="interrupted", metadata=metadata)
        self.repository.add_part(
            session_id,
            "summary",
            status="completed",
            title="已中断",
            content=f"{message} 已停止继续调用模型和工具，当前 transcript 已保留。",
            payload={"summary": message, "interrupted": True},
        )
        self.repository.add_event(
            session_id,
            "session_interrupted",
            message,
            {"session_id": session_id, "status": "interrupted", "summary": message, "interrupted": True},
        )
        return self.get_session(session_id)

    def record_prompt_failure(self, session_id: str, exc: Exception) -> dict[str, Any]:
        session = self.repository.get_session(session_id)
        if not session:
            raise ValueError("Agent session not found")
        message = f"模型调用失败或内部错误，已停止且没有继续执行动作。错误：{str(exc)[:600]}"
        metadata = self._ensure_failed_metadata(session, message)
        summary = self.repository.add_part(
            session_id,
            "summary",
            status="completed",
            title="最终结果",
            content=message,
            payload={"summary": message, "fallback": False, "error": str(exc)[:1200]},
        )
        self.repository.update_session(session_id, status="needs_manual_review", metadata=metadata)
        self._event(
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
        result = self.repository.get_session(session_id) or session
        result["parts"] = self.repository.list_parts(session_id)
        return result

    def approve_permission(self, part_id: str, approved: bool) -> AgentSessionResponse:
        part = self.repository.get_part(part_id)
        if not part:
            raise ValueError("Agent part not found")
        return AgentSessionResponse(**self._attach_recovery_diagnostics(self._approve_deepagents_action(part, approved)))

    async def approve_permission_async(self, part_id: str, approved: bool) -> AgentSessionResponse:
        return await self.decide_permission_async(part_id, [{"type": "approve" if approved else "reject"}])

    async def decide_permission_async(self, part_id: str, decisions: list[dict[str, Any]]) -> AgentSessionResponse:
        part = self.repository.get_part(part_id)
        if not part:
            raise ValueError("Agent part not found")
        session = self.repository.get_session(part["session_id"]) or {}
        metadata = ensure_session_state(dict(session.get("metadata") or {}))
        if metadata.get("runtime") == "deepagents":
            normalized_decisions = self._validate_hitl_decisions(part, decisions)
            result = self._decide_deepagents_permission(part, normalized_decisions)
            self._sync_async_service_model_call()
            decision = permission_decisions(part_id, normalized_decisions)
            self._record_resume_decision(part["session_id"], decision)
            if self.deepagents_runner.model_call is not None or session.get("provider"):
                await self.deepagents_runner.resume(part["session_id"], decision)
            return self.get_session(part["session_id"])
        if len(decisions) != 1:
            raise ValueError("Legacy permission approvals accept exactly one decision")
        return await run_sync(self.approve_permission, part_id, decisions[0].get("type") == "approve")

    def _approve_deepagents_action(self, part: dict[str, Any], approved: bool) -> dict[str, Any]:
        session_id = str(part.get("session_id") or "")
        if not session_id:
            raise ValueError("Agent part session not found")
        session = self.repository.get_session(session_id) or {}
        metadata = ensure_session_state(dict(session.get("metadata") or {}))
        if not approved:
            updated = self.repository.update_part(part["id"], status="blocked")
            metadata = set_phase(metadata, "failed")
            self.repository.update_session(session_id, status="failed", metadata=metadata)
            event = self.repository.add_event(
                session_id,
                "action_rejected",
                "动作已拒绝",
                {
                    "session_id": session_id,
                    "part_id": part["id"],
                    "part_type": part.get("type"),
                    "status": "blocked",
                    "runtime": "deepagents",
                    "part": updated,
                },
            )
            self._notify_event(session_id, event)
            result = self.repository.get_session(session_id) or session
            result["parts"] = self.repository.list_parts(session_id)
            return result

        updated = self.repository.update_part(part["id"], status="approved")
        metadata = set_phase(metadata, "waiting_approval")
        self.repository.update_session(session_id, status="waiting_approval", metadata=metadata)
        event = self.repository.add_event(
            session_id,
            "action_approved",
            "动作已批准",
            {
                "session_id": session_id,
                "part_id": part["id"],
                "part_type": part.get("type"),
                "status": "approved",
                "runtime": "deepagents",
                "part": updated,
            },
        )
        self._notify_event(session_id, event)
        result = self.repository.get_session(session_id) or session
        result["parts"] = self.repository.list_parts(session_id)
        return result

    def _decide_deepagents_permission(self, part: dict[str, Any], decisions: list[dict[str, Any]]) -> dict[str, Any]:
        session_id = str(part.get("session_id") or "")
        if not session_id:
            raise ValueError("Agent part session not found")
        session = self.repository.get_session(session_id) or {}
        metadata = ensure_session_state(dict(session.get("metadata") or {}))
        payload = dict(part.get("payload") or {})
        payload["decisions"] = decisions
        payload["decided_at"] = datetime.now().isoformat()
        updated = self.repository.update_part(part["id"], status="approved", payload=payload)
        metadata = set_phase(metadata, "running")
        metadata["pending_deepagents_interrupt"] = None
        self.repository.update_session(session_id, status="running", metadata=metadata)
        event = self.repository.add_event(
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
        self._notify_event(session_id, event)
        result = self.repository.get_session(session_id) or session
        result["parts"] = self.repository.list_parts(session_id)
        return result

    def _validate_hitl_decisions(self, part: dict[str, Any], decisions: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if part.get("type") != "permission":
            raise ValueError("HITL decisions only apply to permission parts")
        if part.get("status") != "pending":
            raise ValueError("Permission part is not pending")
        payload = dict(part.get("payload") or {})
        action_requests = payload.get("action_requests") if isinstance(payload.get("action_requests"), list) else []
        actions = payload.get("actions") if isinstance(payload.get("actions"), list) else []
        action_count = len(action_requests) or len(actions) or 1
        if len(decisions) != action_count:
            raise ValueError(f"Expected {action_count} HITL decision(s), got {len(decisions)}")

        normalized: list[dict[str, Any]] = []
        for index, raw_decision in enumerate(decisions):
            if not isinstance(raw_decision, dict):
                raise ValueError("Each HITL decision must be an object")
            decision_type = str(raw_decision.get("type") or "").strip()
            if decision_type not in {"approve", "edit", "reject", "respond"}:
                raise ValueError(f"Unsupported HITL decision type: {decision_type}")
            action = actions[index] if index < len(actions) and isinstance(actions[index], dict) else {}
            allowed = action.get("allowed_decisions") or payload.get("allowed_decisions") or ["approve", "edit", "reject", "respond"]
            allowed_set = {str(item) for item in allowed} if isinstance(allowed, (list, tuple)) else {"approve", "reject"}
            if decision_type not in allowed_set:
                raise ValueError(f"Decision '{decision_type}' is not allowed for action {index + 1}")

            decision: dict[str, Any] = {"type": decision_type}
            message = str(raw_decision.get("message") or "").strip()
            if decision_type in {"reject", "respond"}:
                if decision_type == "respond" and not message:
                    raise ValueError("Respond decisions require a message")
                if message:
                    decision["message"] = message
            if decision_type == "edit":
                edited_action = raw_decision.get("edited_action") or raw_decision.get("editedAction")
                if not isinstance(edited_action, dict):
                    raise ValueError("Edit decisions require edited_action")
                name = str(edited_action.get("name") or "").strip()
                args = edited_action.get("args")
                if not name:
                    raise ValueError("edited_action.name is required")
                if not isinstance(args, dict):
                    raise ValueError("edited_action.args must be an object")
                decision["edited_action"] = {"name": name, "args": dict(args)}
            normalized.append(decision)
        return normalized

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
        if computed_part is None or event_type == "part_delta":
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
            "agent_name": payload.get("agent_name"),
            "agent_role": payload.get("agent_role"),
            "task_id": payload.get("task_id"),
            "child_session_id": payload.get("child_session_id"),
            "async_status": payload.get("async_status"),
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
            "agent_name": None,
            "agent_role": None,
            "task_id": None,
            "child_session_id": None,
            "async_status": None,
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
        ui_state = self._build_ui_state(hydrated, parts, diagnostics, metadata)
        metadata["diagnostics"] = diagnostics
        metadata["ui_state"] = ui_state
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
            if event_type == "part_delta":
                status = str(payload.get("status") or (stored_part or {}).get("status") or "running")
            else:
                status = str(payload.get("status") or (stored_part or {}).get("status") or ("failed" if event_type == "model_stream_failed" else "running"))
            stored_payload = dict((stored_part or {}).get("payload") or {})
            if isinstance(payload.get("payload"), dict):
                stored_payload.update(payload.get("payload") or {})
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
        if event_type == "command_output":
            return "part_delta"
        if event_type in {"action_proposed", "action_approved", "action_rejected", "action_executed", "action_failed", "command_started", "command_completed", "command_failed"}:
            return "action"
        if event_type in {"model_stream_failed", "session_failed", "session_blocked", "session_interrupted"}:
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
        latest_action = self._latest_part(parts, {"permission"})
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

    def _build_ui_state(
        self,
        session: dict[str, Any],
        parts: list[dict[str, Any]],
        diagnostics: dict[str, Any],
        metadata: dict[str, Any],
    ) -> dict[str, Any]:
        latest = {
            "tool_call": self._compact_part(self._latest_part(parts, {"tool_call"})),
            "tool_result": self._compact_part(self._latest_part(parts, {"tool_result"})),
            "summary": self._compact_part(self._latest_part(parts, {"summary"})),
            "error": self._compact_part(self._latest_part(parts, {"error"})),
            "permission": self._compact_part(self._latest_part(parts, {"permission"})),
        }
        artifacts = []
        for artifact in self._build_artifacts(parts):
            item = artifact.model_dump() if hasattr(artifact, "model_dump") else artifact.dict()
            item["source"] = "legacy_diff"
            artifacts.append(item)
        return {
            "session_id": session.get("id"),
            "agent_id": session.get("agent_id"),
            "status": session.get("status"),
            "timeline": [self._ui_timeline_item(part) for part in parts],
            "pending_permission": self._pending_permission_ui(parts),
            "latest": latest,
            "artifacts": artifacts,
            "status_text": {
                "current_phase": diagnostics.get("current_phase") or metadata.get("current_phase"),
                "stop_reason": diagnostics.get("stop_reason"),
                "next_action": diagnostics.get("next_action"),
            },
        }

    @staticmethod
    def _ui_timeline_item(part: dict[str, Any]) -> dict[str, Any]:
        payload = part.get("payload") if isinstance(part.get("payload"), dict) else {}
        tool = payload.get("tool") or payload.get("name")
        if not tool and isinstance(payload.get("action"), dict):
            tool = payload["action"].get("name")
        if not tool and isinstance(payload.get("action_requests"), list) and payload["action_requests"]:
            first = payload["action_requests"][0]
            if isinstance(first, dict):
                tool = first.get("name")
        return {
            "id": part.get("id"),
            "part_id": part.get("id"),
            "session_id": part.get("session_id"),
            "type": part.get("type"),
            "status": part.get("status"),
            "title": part.get("title"),
            "content": part.get("content"),
            "tool": tool,
            "agent_name": payload.get("agent_name"),
            "agent_role": payload.get("agent_role"),
            "task_id": payload.get("task_id"),
            "child_session_id": payload.get("child_session_id"),
            "async_status": payload.get("async_status"),
            "created_at": part.get("created_at"),
            "updated_at": part.get("updated_at"),
            "payload": payload,
            "legacy": str(part.get("type") or "") in {"diff", "command"},
        }

    @classmethod
    def _pending_permission_ui(cls, parts: list[dict[str, Any]]) -> dict[str, Any] | None:
        part = cls._latest_part(parts, {"permission"})
        if not part or part.get("status") != "pending":
            return None
        payload = part.get("payload") if isinstance(part.get("payload"), dict) else {}
        actions = payload.get("actions") if isinstance(payload.get("actions"), list) else []
        if not actions:
            requests = payload.get("action_requests") if isinstance(payload.get("action_requests"), list) else []
            if requests:
                actions = requests
        if not actions:
            action_payload = payload.get("action") if isinstance(payload.get("action"), dict) else {}
            actions = [
                {
                    "name": payload.get("tool") or action_payload.get("name") or "tool",
                    "args": payload.get("args") or action_payload.get("args") or {},
                    "allowed_decisions": payload.get("allowed_decisions") or ["approve", "reject"],
                }
            ]
        normalized_actions = []
        for index, action in enumerate(actions):
            action = action if isinstance(action, dict) else {}
            allowed = action.get("allowed_decisions") or payload.get("allowed_decisions") or ["approve", "reject"]
            normalized_actions.append(
                {
                    "index": index,
                    "name": str(action.get("name") or f"tool_{index + 1}"),
                    "args": action.get("args") if isinstance(action.get("args"), dict) else {},
                    "description": str(action.get("description") or ""),
                    "allowed_decisions": [str(item) for item in allowed] if isinstance(allowed, list) else ["approve", "reject"],
                }
            )
        return {
            "part_id": part.get("id"),
            "status": part.get("status"),
            "title": part.get("title"),
            "content": part.get("content"),
            "actions": normalized_actions,
            "allowed_decisions": sorted({decision for action in normalized_actions for decision in action.get("allowed_decisions", [])}),
            "decisions_payload": {
                "action_requests": payload.get("action_requests") or [],
                "actions": payload.get("actions") or [],
                "allowed_decisions": payload.get("allowed_decisions") or [],
            },
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
            "agent_name": payload.get("agent_name"),
            "agent_role": payload.get("agent_role"),
            "task_id": payload.get("task_id"),
            "child_session_id": payload.get("child_session_id"),
            "async_status": payload.get("async_status"),
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
    def _build_artifacts(parts: list[Any]) -> list[AgentArtifactResponse]:
        artifacts: list[AgentArtifactResponse] = []
        seen: dict[str, int] = {}
        for part in parts:
            part_type = getattr(part, "type", None) if not isinstance(part, dict) else part.get("type")
            if part_type != "diff":
                continue
            payload = getattr(part, "payload", None) if not isinstance(part, dict) else part.get("payload")
            payload = dict(payload or {})
            nested_payload = payload.get("payload") if isinstance(payload.get("payload"), dict) else {}
            diff_source = payload.get("diff") or payload.get("file_changes") or nested_payload.get("diff") or nested_payload.get("file_changes")
            changed_files = payload.get("changed_files") or []
            title = getattr(part, "title", None) if not isinstance(part, dict) else part.get("title")
            content = getattr(part, "content", None) if not isinstance(part, dict) else part.get("content")
            status = getattr(part, "status", None) if not isinstance(part, dict) else part.get("status")
            part_id = getattr(part, "id", None) if not isinstance(part, dict) else part.get("id")
            fallback_summary = str(title or content or payload.get("policy_reason") or "文件变更")
            entries = diff_source if isinstance(diff_source, list) else [
                {"path": path, "status": status or "modified", "summary": fallback_summary, "diff": diff_source}
                for path in changed_files
            ]
            for entry in entries:
                entry = entry or {}
                path = str(entry.get("path") or entry.get("file_path") or entry.get("filename") or entry.get("name") or "").strip()
                if not path:
                    continue
                seen[path] = seen.get(path, 0) + 1
                preview = entry.get("diff") or entry.get("patch") or entry.get("content") or diff_source or ""
                artifacts.append(
                    AgentArtifactResponse(
                        id=f"{part_id}:{path}:{seen[path]}",
                        path=path,
                        status=str(entry.get("status") or entry.get("change_type") or entry.get("action") or status or "modified"),
                        summary=str(entry.get("summary") or entry.get("description") or fallback_summary),
                        preview=str(preview),
                        source_part_id=str(part_id or ""),
                    )
                )
        return artifacts[-24:]

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
        if status == "interrupted":
            reason = event_message or summary_text or latest_state_error or "用户已中断 Agent 任务。"
            return reason, "当前 transcript 已保留；需要继续时请发送新任务或重试。"
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

    def _record_agent_chain_failure(
        self,
        session_id: str,
        code: str,
        message: str,
        *,
        provider: str | None = None,
        model: str | None = None,
    ) -> dict[str, Any]:
        session = self.repository.get_session(session_id)
        if not session:
            raise ValueError("Agent session not found")
        metadata = ensure_session_state(dict(session.get("metadata") or {}))
        metadata = set_phase(metadata, "needs_manual_review")
        metadata["fallback_reason"] = None
        metadata["last_graph_error"] = message[:600] if code == "langgraph_init_failed" else metadata.get("last_graph_error")
        metadata["last_model_error"] = message[:600]
        trace = dict(metadata.get("execution_trace") or {})
        trace.update(
            {
                "runtime": metadata.get("runtime") or "pending",
                "provider": provider or session.get("provider") or "",
                "model": model or session.get("model") or "",
                "status": "failed",
                "failure_code": code,
                "fallback_used": False,
                "last_model_error": message[:600],
            }
        )
        metadata["execution_trace"] = trace
        summary = self.repository.add_part(
            session_id,
            "summary",
            status="completed",
            title="执行链路未启动",
            content=message,
            payload={"summary": message, "error_code": code, "fallback": False},
        )
        self.repository.update_session(session_id, status="needs_manual_review", metadata=metadata)
        self._event(
            session_id,
            "agent_chain_failed",
            message,
            {
                "session_id": session_id,
                "part_id": summary["id"],
                "part_type": "summary",
                "status": "needs_manual_review",
                "summary": message,
                "error_code": code,
                "fallback": False,
            },
        )
        result = self.repository.get_session(session_id) or session
        result["parts"] = self.repository.list_parts(session_id)
        return result

    def _record_resume_decision(self, session_id: str, decision: dict[str, Any]) -> None:
        session = self.repository.get_session(session_id)
        if not session:
            return
        metadata = ensure_session_state(dict(session.get("metadata") or {}))
        metadata["last_resume_decision"] = dict(decision)
        self.repository.update_session(session_id, metadata=metadata)

