"""Agent model capability checks shared by session setup and model UI APIs.

DeepAgents always binds tools.  The local OpenAI-compatible inference service
currently supports text chat only, so advertising it as an Agent target would
defer a deterministic configuration error until an agent is already running.
"""

from __future__ import annotations

from typing import Any


def saved_cloud_agent_model_configured(repository: Any) -> bool:
    """Check for a usable saved cloud model without exposing credentials."""
    try:
        providers = ["deepseek", "openrouter", "openai", *repository.custom_provider_ids()]
        for provider in dict.fromkeys(provider for provider in providers if provider):
            key_data = repository.get(provider)
            if not isinstance(key_data, dict) or not key_data.get("api_key"):
                continue
            if key_data.get("default_model") or key_data.get("models"):
                return True
    except Exception:
        return False
    return False


def local_agent_tool_calling_status(
    provider: str | None,
    settings: Any,
) -> dict[str, Any]:
    """Return the tool-calling boundary for a selected local provider.

    Direct Ollama is left available in ``in_process`` mode because LangChain's
    Ollama integration can negotiate tools with capable models.  All local
    traffic in ``service`` mode goes through the platform's text-only
    OpenAI-compatible endpoint and must be rejected before execution.
    """
    normalized = str(provider or "").strip().lower()
    execution_mode = str(getattr(settings, "inference_execution_mode", "service"))
    is_local_service = normalized == "local" or (
        normalized == "ollama" and execution_mode == "service"
    )
    if is_local_service:
        return {
            "supported": False,
            "execution_mode": execution_mode,
            "message": (
                "当前本地推理服务仅支持文本聊天，不支持 Agent 所需的工具调用。"
                "请配置支持工具调用的云端 provider:model，或在确认模型支持工具调用后使用 in_process Ollama。"
            ),
        }
    return {
        "supported": True,
        "execution_mode": execution_mode,
        "message": None,
    }


def agent_model_tool_calling_status(provider: str | None, settings: Any) -> dict[str, Any]:
    """Return whether the provider can enter the DeepAgents tool loop."""
    normalized = str(provider or "").strip().lower()
    if normalized in {"local", "ollama"}:
        return local_agent_tool_calling_status(normalized, settings)
    return {
        "supported": bool(normalized),
        "execution_mode": str(getattr(settings, "inference_execution_mode", "service")),
        "message": None if normalized else "请选择 Agent 的 provider:model。",
    }
