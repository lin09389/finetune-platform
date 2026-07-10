"""Provider construction with one compatibility normalization point."""

from __future__ import annotations

from typing import Any

from ai.gateway import AnthropicMessagesProvider, OpenAICompatibleProvider, get_provider


def normalize_base_url(value: str | None) -> str:
    url = str(value or "").strip()
    return url.replace("/anthropic", "") if "api.deepseek.com" in url and "/anthropic" in url else url


def resolve_provider(provider_id: str, config: dict[str, Any], *, group_id: str = "", base_url: str = "", version: str = "") -> Any | None:
    effective_base_url = normalize_base_url(base_url or config.get("base_url"))
    provider = get_provider(provider_id, group_id=group_id or config.get("group_id", ""), base_url=effective_base_url, version=version)
    if provider is not None:
        return provider
    interface = config.get("interface_format", "openai-compatible")
    if interface in {"openai-compatible", "openai-chat-completions"} and effective_base_url:
        return OpenAICompatibleProvider(base_url=effective_base_url, default_model=config.get("default_model", ""))
    if interface == "anthropic-messages" and effective_base_url:
        return AnthropicMessagesProvider(base_url=effective_base_url, default_model=config.get("default_model", ""))
    return None
