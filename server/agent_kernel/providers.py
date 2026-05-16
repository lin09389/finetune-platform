"""Shared provider resolution helpers for agent runtimes."""

from __future__ import annotations

from typing import Any

from ai.gateway import AnthropicMessagesProvider, OpenAICompatibleProvider, get_provider


def resolve_saved_provider(provider_name: str, key_data: dict[str, Any]):
    group_id = key_data.get("group_id", "")
    base_url = key_data.get("base_url", "")
    provider = get_provider(provider_name, group_id=group_id, base_url=base_url)
    if provider is not None:
        return provider

    interface_format = key_data.get("interface_format", "openai-compatible")
    default_model = key_data.get("default_model", "")
    if interface_format in {"openai-compatible", "openai-chat-completions"} and base_url:
        return OpenAICompatibleProvider(base_url=base_url, default_model=default_model)
    if interface_format == "anthropic-messages":
        return AnthropicMessagesProvider(base_url=base_url, default_model=default_model)
    return None
