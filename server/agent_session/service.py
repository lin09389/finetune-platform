from __future__ import annotations

from pathlib import Path
from typing import Any

from agent_runtime.runner import resolve_saved_provider
from security.encryption import secure_storage

from .models import AgentPromptRequest, AgentSessionCreate, AgentSessionResponse
from .processor import AgentSessionProcessor, ModelCall
from .repository import AgentSessionRepository


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
        return AgentSessionResponse(**session)

    def get_session(self, session_id: str) -> AgentSessionResponse:
        session = self.repository.get_session(session_id)
        if not session:
            raise ValueError("Agent session not found")
        session["parts"] = self.repository.list_parts(session_id)
        return AgentSessionResponse(**session)

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
        return AgentSessionResponse(**result)

    def approve_permission(self, part_id: str, approved: bool) -> AgentSessionResponse:
        return AgentSessionResponse(**self.processor.approve_part(part_id, approved))

    def approve_action(self, part_id: str, approved: bool) -> AgentSessionResponse:
        return AgentSessionResponse(**self.processor.approve_part(part_id, approved))

    def execute_action(self, part_id: str) -> AgentSessionResponse:
        return AgentSessionResponse(**self.processor.execute_part(part_id))

    def list_events(self, session_id: str) -> list[dict[str, Any]]:
        return self.repository.list_events(session_id)

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
