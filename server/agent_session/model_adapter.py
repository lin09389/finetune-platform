"""DeepAgents official model resolver.

DeepAgents works with LangChain chat models that support tool calling. This module
keeps the agent runtime aligned with the official `provider:model` contract and
uses `langchain.chat_models.init_chat_model` as the only production model entry.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .deepagents_compat import patch_torch_pytree_for_transformers

patch_torch_pytree_for_transformers()

from langchain_core.language_models.chat_models import BaseChatModel  # noqa: E402

from core.config import settings  # noqa: E402
from security.encryption import secure_storage  # noqa: E402
from cloud_models import CloudProviderRepository  # noqa: E402

from .model_capabilities import local_agent_tool_calling_status  # noqa: E402
from .execution_context import RuntimeExecutionContext  # noqa: E402

cloud_provider_repository = CloudProviderRepository(secure_storage)


class ProviderAdapterError(RuntimeError):
    """Raised when a DeepAgents model string cannot be resolved."""


LANGCHAIN_PROVIDER_ALIASES = {
    "anthropic": "anthropic",
    "baseten": "baseten",
    "deepseek": "deepseek",
    "fireworks": "fireworks",
    "google-genai": "google_genai",
    "google_genai": "google_genai",
    "google-vertexai": "google_vertexai",
    "google_vertexai": "google_vertexai",
    "local": "openai",
    "ollama": "ollama",
    "openai": "openai",
    "openrouter": "openrouter",
}


@dataclass(frozen=True)
class OfficialModelSpec:
    provider: str
    model: str
    model_string: str
    transport: str = "direct"


_PROFILES_REGISTERED = False


def get_chat_model(context: RuntimeExecutionContext) -> BaseChatModel:
    spec = resolve_official_model_spec(context)
    if spec is None:
        provider = str(context.provider or "")
        model = str(context.model or "")
        raise ProviderAdapterError(
            "DeepAgents 现在只接受官方 LangChain 模型格式。"
            f"当前 provider={provider!r}, model={model!r}。"
            "请使用 provider:model，例如 openai:gpt-4o、ollama:qwen3:8b、openrouter:z-ai/glm-5.1。"
        )
    if spec.transport == "local_inference_service":
        status = local_agent_tool_calling_status("local", settings)
        raise ProviderAdapterError(status["message"])
    try:
        return init_official_chat_model(spec, context)
    except Exception as exc:
        raise ProviderAdapterError(f"DeepAgents 官方模型 {spec.model_string} 初始化失败：{exc}") from exc


def resolve_official_model_spec(context: RuntimeExecutionContext) -> OfficialModelSpec | None:
    model_name = str(context.model or "").strip()
    provider_name = str(context.provider or "").strip()
    if _is_provider_model_string(model_name):
        provider, model = model_name.split(":", 1)
        if _uses_local_inference_service(provider):
            return _local_service_spec(provider, model, model_name)
        normalized = LANGCHAIN_PROVIDER_ALIASES[provider]
        return OfficialModelSpec(provider=normalized, model=model, model_string=model_name)
    if _is_provider_model_string(provider_name):
        provider, model = provider_name.split(":", 1)
        if _uses_local_inference_service(provider):
            return _local_service_spec(provider, model, provider_name)
        normalized = LANGCHAIN_PROVIDER_ALIASES[provider]
        return OfficialModelSpec(provider=normalized, model=model, model_string=provider_name)
    if provider_name in LANGCHAIN_PROVIDER_ALIASES and model_name:
        if _uses_local_inference_service(provider_name):
            return _local_service_spec(provider_name, model_name, f"{provider_name}:{model_name}")
        normalized = LANGCHAIN_PROVIDER_ALIASES[provider_name]
        return OfficialModelSpec(provider=normalized, model=model_name, model_string=f"{provider_name}:{model_name}")
    return None


def init_official_chat_model(spec: OfficialModelSpec, context: RuntimeExecutionContext) -> BaseChatModel:
    register_default_provider_profiles()
    from langchain.chat_models import init_chat_model

    kwargs = _official_model_kwargs(spec, context)
    return init_chat_model(model=spec.model, model_provider=spec.provider, **kwargs)


def register_default_provider_profiles() -> None:
    global _PROFILES_REGISTERED
    if _PROFILES_REGISTERED:
        return
    try:
        from deepagents import ProviderProfile, register_provider_profile
    except Exception:
        _PROFILES_REGISTERED = True
        return
    for provider in LANGCHAIN_PROVIDER_ALIASES.values():
        try:
            register_provider_profile(provider, ProviderProfile(init_kwargs={"temperature": 0}))
        except Exception:
            continue
    _PROFILES_REGISTERED = True


def _official_model_kwargs(spec: OfficialModelSpec, context: RuntimeExecutionContext) -> dict[str, Any]:
    if spec.transport == "local_inference_service":
        metadata = context.metadata if isinstance(context.metadata, dict) else {}
        kwargs: dict[str, Any] = {
            "temperature": 0,
            "timeout": settings.inference_service_read_timeout_seconds,
            "max_retries": settings.inference_service_max_retries,
            "api_key": settings.inference_internal_api_key,
            "base_url": f"{settings.inference_service_url.rstrip('/')}/v1",
        }
        model_params = metadata.get("model_params")
        return _merge_model_kwargs(kwargs, model_params) if isinstance(model_params, dict) else kwargs

    key_data = cloud_provider_repository.get(spec.provider)
    if not isinstance(key_data, dict):
        key_data = {}
    kwargs: dict[str, Any] = {
        "temperature": 0,
        "timeout": settings.agent_cloud_model_timeout_seconds,
        "max_retries": settings.agent_cloud_model_max_retries,
    }
    metadata = context.metadata if isinstance(context.metadata, dict) else {}
    api_key = str(metadata.get("api_key") or key_data.get("api_key") or "")
    if api_key:
        kwargs["api_key"] = api_key
    base_url = metadata.get("base_url") or key_data.get("base_url")
    if base_url and spec.provider in {"openai", "deepseek", "openrouter"}:
        kwargs["base_url"] = base_url
    model_params = metadata.get("model_params")
    if isinstance(model_params, dict):
        kwargs = _merge_model_kwargs(kwargs, model_params)
    return kwargs


def _merge_model_kwargs(defaults: dict[str, Any], overrides: dict[str, Any]) -> dict[str, Any]:
    merged = dict(defaults)
    for key, value in overrides.items():
        if key == "extra_body" and isinstance(value, dict) and isinstance(merged.get("extra_body"), dict):
            nested = dict(merged["extra_body"])
            nested.update(value)
            merged[key] = nested
        else:
            merged[key] = value
    return merged


def _is_provider_model_string(value: str) -> bool:
    if ":" not in value:
        return False
    provider, model = value.split(":", 1)
    if len(provider) == 1 and provider.isalpha():
        return False
    return bool(provider in LANGCHAIN_PROVIDER_ALIASES and model)


def _uses_local_inference_service(provider: str) -> bool:
    return provider == "local" or (
        provider == "ollama" and settings.inference_execution_mode == "service"
    )


def _local_service_spec(provider: str, model: str, model_string: str) -> OfficialModelSpec:
    routed_model = model if provider == "local" or "/" in model else f"{provider}/{model}"
    return OfficialModelSpec(
        provider="openai",
        model=routed_model,
        model_string=model_string,
        transport="local_inference_service",
    )


__all__ = [
    "LANGCHAIN_PROVIDER_ALIASES",
    "OfficialModelSpec",
    "ProviderAdapterError",
    "get_chat_model",
    "init_official_chat_model",
    "resolve_official_model_spec",
]
