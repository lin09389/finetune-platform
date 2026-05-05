from __future__ import annotations

from pathlib import Path
from typing import Any

from agent_runtime.runner import resolve_saved_provider
from security.encryption import secure_storage

from .models import AgentPromptRequest, AgentSessionCreate, AgentSessionResponse
from .processor import AgentSessionProcessor, ModelCall
from .repository import AgentSessionRepository
from .state import ensure_session_state


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
        result = await self.processor.prompt(session_id, request.content, model_call=model_call)
        return AgentSessionResponse(**self._attach_recovery_diagnostics(result))

    def approve_permission(self, part_id: str, approved: bool) -> AgentSessionResponse:
        return AgentSessionResponse(**self._attach_recovery_diagnostics(self.processor.approve_part(part_id, approved)))

    def approve_action(self, part_id: str, approved: bool) -> AgentSessionResponse:
        return AgentSessionResponse(**self._attach_recovery_diagnostics(self.processor.approve_part(part_id, approved)))

    def execute_action(self, part_id: str) -> AgentSessionResponse:
        return AgentSessionResponse(**self._attach_recovery_diagnostics(self.processor.execute_part(part_id)))

    def list_events(self, session_id: str) -> list[dict[str, Any]]:
        return self.repository.list_events(session_id)

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
                return (
                    '{"tool":"finalize","arguments":{"summary":'
                    '"还没有为本次 Agent Session 选择云端模型，因此只创建了会话。请在聊天页选择 provider/model 后重试。"}}'
                )
            key_data = secure_storage.get(f"cloud_{provider_name}_key") or {}
            api_key = key_data.get("api_key", "")
            if not api_key:
                return (
                    '{"tool":"finalize","arguments":{"summary":'
                    f'"未配置 {provider_name} 的 API Key，无法继续执行 Agent。"}}'
                )
            provider = resolve_saved_provider(provider_name, key_data)
            if provider is None:
                return (
                    '{"tool":"finalize","arguments":{"summary":'
                    f'"不支持的云端服务商：{provider_name}。"}}'
                )
            model = session.get("model") or key_data.get("default_model") or provider.get_default_model()
            response = await provider.chat(
                messages=messages,
                model=model,
                api_key=api_key,
                temperature=0.2,
                max_tokens=2400,
            )
            return response.get("content", "")

        return call
