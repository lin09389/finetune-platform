from __future__ import annotations

import logging
from collections.abc import AsyncGenerator, Awaitable, Callable
from typing import Any

from ai.providers import resolve_saved_provider
from security.encryption import secure_storage

ModelCall = Callable[[list[dict[str, str]]], Awaitable[str]]
StreamModelCall = Callable[[list[dict[str, str]]], AsyncGenerator[dict[str, Any], None]]

logger = logging.getLogger(__name__)


class AgentSessionCloudError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class AgentSessionProviderResolver:
    """Resolve cloud provider config and create model call adapters."""

    def __init__(self, storage: Any = secure_storage, provider_resolver: Any = resolve_saved_provider):
        self.storage = storage
        self.provider_resolver = provider_resolver

    def resolve_cloud_provider_config(self, session: dict[str, Any]):
        provider_name = str(session.get("provider") or "")
        if not provider_name:
            raise AgentSessionCloudError("missing_provider", "没有选择云端模型 provider")
        key_data = self.storage.get(f"cloud_{provider_name}_key") or {}
        if not isinstance(key_data, dict):
            raise AgentSessionCloudError("invalid_provider_config", f"{provider_name} 的云端配置格式无效")
        api_key = str(key_data.get("api_key") or "")
        if not api_key:
            raise AgentSessionCloudError("missing_api_key", f"未配置 {provider_name} 的 API Key")
        provider = self.provider_resolver(provider_name, key_data)
        if provider is None:
            raise AgentSessionCloudError("unsupported_provider", f"不支持的云端服务商：{provider_name}")
        model = str(session.get("model") or key_data.get("default_model") or provider.get_default_model() or "")
        if not model:
            raise AgentSessionCloudError("missing_model", f"未配置 {provider_name} 的默认模型")
        return provider, api_key, model

    def cloud_model_call(self, session: dict[str, Any]) -> ModelCall:
        async def call(messages: list[dict[str, str]]) -> str:
            provider_name = session.get("provider")
            logger.info(
                "agent_session.cloud model_call enter: session_id=%s provider=%s model=%s message_count=%s",
                session.get("id") or "",
                provider_name or "",
                session.get("model") or "",
                len(messages),
            )
            if not provider_name:
                raise AgentSessionCloudError("missing_provider", "没有选择云端模型 provider")
            provider, api_key, model = self.resolve_cloud_provider_config(session)
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
                logger.exception(
                    "agent_session.cloud model_call failed: session_id=%s provider=%s model=%s",
                    session.get("id") or "",
                    provider_name,
                    model,
                )
                raise AgentSessionCloudError("cloud_model_call_failed", f"云端模型调用失败：{message}") from exc
            logger.info(
                "agent_session.cloud model_call success: session_id=%s provider=%s model=%s content_length=%s",
                session.get("id") or "",
                provider_name,
                model,
                len(str(response.get("content", ""))),
            )
            return response.get("content", "")

        return call

    def cloud_stream_model_call(self, session: dict[str, Any]) -> StreamModelCall:
        provider_name = session.get("provider")
        provider, api_key, model = self.resolve_cloud_provider_config(session)

        async def stream(messages: list[dict[str, str]]):
            logger.info(
                "agent_session.cloud chat_stream enter: session_id=%s provider=%s model=%s message_count=%s",
                session.get("id") or "",
                provider_name,
                model,
                len(messages),
            )
            try:
                async for chunk in provider.chat_stream(
                    messages=messages,
                    model=model,
                    api_key=api_key,
                    temperature=0.2,
                    max_tokens=2400,
                ):
                    if isinstance(chunk, dict):
                        logger.debug(
                            "agent_session.cloud chat_stream chunk: session_id=%s provider=%s keys=%s",
                            session.get("id") or "",
                            provider_name,
                            sorted(chunk.keys()),
                        )
                    yield chunk
                logger.info(
                    "agent_session.cloud chat_stream exit: session_id=%s provider=%s model=%s",
                    session.get("id") or "",
                    provider_name,
                    model,
                )
            except Exception:
                logger.exception(
                    "agent_session.cloud chat_stream failed: session_id=%s provider=%s model=%s",
                    session.get("id") or "",
                    provider_name,
                    model,
                )
                raise

        return stream
