from __future__ import annotations

from typing import TYPE_CHECKING, Any

from agent_session.events import TASK_CONTEXT_INITIALIZED_EVENT
from agent_session.execution_plan_events import apply_execution_event_to_session
from agent_session.models import AgentArtifactResponse, AgentSessionPreferences

if TYPE_CHECKING:
    from agent_session.service import AgentSessionService


class EventBroadcastService:
    def __init__(self, service: AgentSessionService) -> None:
        self.service = service

    def subscribe_events(self, session_id: str) -> Any:
        return self.service._event_bus.subscribe(session_id)

    def unsubscribe_events(self, session_id: str, queue: Any) -> None:
        self.service._event_bus.unsubscribe(session_id, queue)

    def subscribe_global_events(self) -> Any:
        return self.service._event_bus.subscribe_global()

    def unsubscribe_global_events(self, queue: Any) -> None:
        self.service._event_bus.unsubscribe_global(queue)

    def _notify_event(self, session_id: str, event: dict[str, Any]) -> None:
        apply_execution_event_to_session(self.service.repository, session_id, event)
        self._clear_recovery_latches_for_event(session_id, event)
        self.service._event_bus.notify(session_id, event)
        self.service.failure_guard.observe_event(session_id, event)

    def _clear_recovery_latches_for_event(self, session_id: str, event: dict[str, Any]) -> None:
        event_type = str(event.get("event_type") or "")
        payload = dict(event.get("payload") or {}) if isinstance(event.get("payload"), dict) else {}
        if event_type in {"node_recovery_failed", "node_recovery_rejected", "node_recovery_completed"}:
            node_id = str(payload.get("node_id") or "")
            if node_id:
                self.service.recovery_service._clear_recovery_latch(session_id, node_id)
            return
        if event_type not in {"async_subtask_completed", "async_subtask_failed", "async_subtask_cancelled"}:
            return
        task_id = str(payload.get("task_id") or "")
        if not task_id:
            return
        session = self.service.repository.get_session(session_id)
        if not session:
            return
        from agent_session.state import ensure_session_state
        metadata = ensure_session_state(dict(session.get("metadata") or {}))
        latches = dict(metadata.get("recovery_latches") or {})
        for node_id, latch in list(latches.items()):
            if isinstance(latch, dict) and latch.get("new_task_id") == task_id:
                latches.pop(node_id, None)
        metadata["recovery_latches"] = latches
        self.service.repository.update_session(session_id, metadata=metadata)

    def _event(self, session_id: str, event_type: str, message: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        enriched = dict(payload or {})
        enriched.setdefault("session_id", session_id)
        part_id = enriched.get("part_id")
        part = enriched.get("part") if isinstance(enriched.get("part"), dict) else None
        if part is None and isinstance(part_id, str) and part_id.startswith("agp_"):
            part = self.service.repository.get_part(part_id)
            if part:
                enriched["part"] = part
        if part:
            enriched.setdefault("part_type", part.get("type"))
            enriched.setdefault("status", part.get("status"))
            enriched.setdefault("summary", part.get("content") or part.get("title") or message)
        enriched.setdefault("summary", message)
        enriched.setdefault("chunk_type", self._stream_chunk_type(event_type, enriched, part))
        event = self.service.repository.add_event(session_id, event_type, message, enriched)
        self._notify_event(session_id, event)
        return event

    def publish_task_context_initialized(
        self,
        session_id: str,
        *,
        workspace_id: str | None,
        workspace_label: str,
        task_mode: str | None,
    ) -> dict[str, Any]:
        """Publish the display-safe task context before the session can run."""
        return self._event(
            session_id,
            TASK_CONTEXT_INITIALIZED_EVENT,
            "Task context initialized",
            {
                "workspace_id": workspace_id,
                "workspace_label": workspace_label,
                "task_mode": task_mode,
            },
        )

    def build_stream_chunk(self, event: dict[str, Any]) -> dict[str, Any]:
        payload = dict(event.get("payload") or {})
        session_id = str(event.get("session_id") or payload.get("session_id") or "")
        session = self.service.repository.get_session(session_id) or {}
        payload_chunk_type = payload.get("chunk_type")
        payload_part = payload.get("part")
        event_type = str(event.get("event_type") or "")
        computed_part = payload_part if isinstance(payload_part, dict) else None
        if computed_part is None or event_type in {"part_delta", "model_stream_started", "model_stream_completed", "model_stream_failed"}:
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
            "health_status": payload.get("health_status"),
            "delta": payload.get("delta"),
            "content": payload.get("content"),
            "summary": payload.get("summary") or event.get("message"),
            "part": computed_part,
        }

    def build_session_snapshot_chunk(self, session_id: str) -> dict[str, Any]:
        session = self.service.repository.get_session(session_id)
        if not session:
            return {"chunk_type": "session_snapshot", "session_id": session_id, "session_status": "unknown", "parts": [], "payload": {}}
        parts = self.service.repository.list_parts(session_id)
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

    def _attach_recovery_diagnostics(self, session: dict[str, Any]) -> dict[str, Any]:
        hydrated = dict(session)
        session_id = str(hydrated.get("id") or "")
        parts = list(hydrated.get("parts") or self.service.repository.list_parts(session_id))
        events = self.service.repository.list_events(session_id) if session_id else []
        from agent_session.state import ensure_session_state
        metadata = ensure_session_state(dict(hydrated.get("metadata") or {}))
        preferences = self._session_preferences(metadata)
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
        state = dict(metadata.get("state") or {})
        metadata["latest_error"] = diagnostics.get("latest_error") or metadata.get("latest_error") or state.get("latest_error")
        metadata["stop_reason"] = diagnostics.get("stop_reason") or metadata.get("stop_reason")
        metadata["next_action"] = metadata.get("next_action") or diagnostics.get("next_action")
        hydrated["metadata"] = metadata
        hydrated["preferences"] = preferences.model_dump()
        hydrated["parts"] = parts
        return hydrated

    @staticmethod
    def _session_preferences(metadata: dict[str, Any]) -> AgentSessionPreferences:
        raw = metadata.get("ui_preferences")
        raw = raw if isinstance(raw, dict) else {}
        display_title = raw.get("display_title")
        display_title = display_title.strip()[:80] if isinstance(display_title, str) and display_title.strip() else None
        return AgentSessionPreferences(
            display_title=display_title,
            pinned=bool(raw.get("pinned")),
            archived=bool(raw.get("archived")),
            updated_at=str(raw.get("updated_at") or "") or None,
        )

    def _stream_part_snapshot(self, event: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any] | None:
        session_id = str(event.get("session_id") or payload.get("session_id") or "")
        event_type = str(event.get("event_type") or "")
        part_id = payload.get("part_id")
        stored_part = self.service.repository.get_part(str(part_id)) if isinstance(part_id, str) and part_id.startswith("agp_") else None
        payload_part = payload.get("part") if isinstance(payload.get("part"), dict) else {}
        if stored_part is None and not part_id:
            return None
        if event_type in {"part_delta", "model_stream_started", "model_stream_completed", "model_stream_failed"}:
            part_type = str(payload.get("part_type") or (stored_part or {}).get("type") or "text")
            if event_type == "part_delta":
                status = str(payload.get("status") or (stored_part or {}).get("status") or "running")
            elif event_type == "model_stream_completed":
                status = self._completed_stream_status(payload, stored_part, payload_part)
            else:
                status = str(payload.get("status") or (stored_part or {}).get("status") or ("failed" if event_type == "model_stream_failed" else "running"))
            stored_payload = dict((stored_part or {}).get("payload") or {})
            if isinstance(payload.get("payload"), dict):
                stored_payload.update(payload.get("payload") or {})
            if isinstance(payload_part.get("payload"), dict):
                stored_payload.update(payload_part.get("payload") or {})
            if payload.get("streaming"):
                stored_payload["streaming"] = True
            elif event_type == "model_stream_completed":
                stored_payload["streaming"] = False
            return {
                "id": str(part_id or ""),
                "session_id": session_id,
                "type": part_type,
                "status": status,
                "title": payload_part.get("title") or (stored_part or {}).get("title") or ("流式输出失败" if event_type == "model_stream_failed" else "生成中"),
                "content": self._completed_stream_content(payload, stored_part, payload_part) if event_type == "model_stream_completed" else str(payload.get("content") or (stored_part or {}).get("content") or payload_part.get("content") or ""),
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
    def _completed_stream_status(payload: dict[str, Any], stored_part: dict[str, Any] | None, payload_part: dict[str, Any]) -> str:
        explicit = str(payload.get("status") or "").strip()
        if explicit:
            return explicit
        candidates = [
            str((stored_part or {}).get("status") or "").strip(),
            str(payload_part.get("status") or "").strip(),
        ]
        if "completed" in candidates:
            return "completed"
        for candidate in candidates:
            if candidate and candidate != "running":
                return candidate
        return "completed"

    @staticmethod
    def _completed_stream_content(payload: dict[str, Any], stored_part: dict[str, Any] | None, payload_part: dict[str, Any]) -> str:
        explicit = payload.get("content")
        if explicit is not None:
            return str(explicit)
        stored_status = str((stored_part or {}).get("status") or "").strip()
        payload_status = str(payload_part.get("status") or "").strip()
        if stored_status == "completed":
            return str((stored_part or {}).get("content") or "")
        if payload_status == "completed":
            return str(payload_part.get("content") or "")
        return str((stored_part or {}).get("content") or payload_part.get("content") or "")

    @staticmethod
    def _stream_chunk_type(event_type: str, payload: dict[str, Any], part: dict[str, Any] | None) -> str:
        if event_type.startswith("async_subtask_") or payload.get("agent_role") == "async_subagent":
            return "async_task"
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
        if event_type in {
            "tool_call_failed",
            "loop_guard_triggered",
            "model_stream_failed",
            "session_failed",
            "session_blocked",
            "session_interrupted",
        }:
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
            "content": EventBroadcastService._truncate(str(part.get("content") or ""), 240),
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
            "failure_summary": EventBroadcastService._truncate(str(payload.get("failure_summary") or ""), 240),
        }

    @staticmethod
    def _compact_event(event: dict[str, Any] | None) -> dict[str, Any] | None:
        if not event:
            return None
        return {
            "id": event.get("id"),
            "event_type": event.get("event_type"),
            "message": EventBroadcastService._truncate(str(event.get("message") or ""), 240),
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
            if (
                state.get("next_action") == "continue_approval"
                or str((latest_event or {}).get("event_type") or "") == "session_recovered_after_restart"
            ):
                return (
                    event_message or "服务已重启，待审批状态与执行断点已保留。",
                    "请继续批准或拒绝当前工具调用，无需重新发送任务。",
                )
            reason = action_reason or event_message or "有修改或命令需要确认。"
            return reason, "请确认待处理的修改或验证命令。"
        if status == "waiting_permission":
            if (
                state.get("next_action") == "continue_approval"
                or str((latest_event or {}).get("event_type") or "") == "session_recovered_after_restart"
            ):
                return (
                    event_message or "服务已重启，待权限确认的状态已保留。",
                    "请继续批准或拒绝该工具调用，无需重新发送任务。",
                )
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
