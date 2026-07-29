"""DeepAgents cloud / official model resolver.

DeepAgents works with LangChain chat models that support tool calling. Production
resolution prefers the official ``init_chat_model`` path, then falls back to an
OpenAI-compatible client for providers that speak the OpenAI Chat Completions
API (DeepSeek, OpenRouter, OpenAI) when the official package is missing.
"""

from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any

from .deepagents_compat import patch_torch_pytree_for_transformers

patch_torch_pytree_for_transformers()

from cloud_models import CloudProviderRepository  # noqa: E402
from langchain_core.language_models.chat_models import BaseChatModel  # noqa: E402

from core.config import settings  # noqa: E402
from security.encryption import secure_storage  # noqa: E402

from .execution_context import RuntimeExecutionContext  # noqa: E402
from .model_capabilities import local_agent_tool_calling_status  # noqa: E402

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

# Providers that can use ChatOpenAI-compatible transport as a fallback.
OPENAI_COMPAT_PROVIDERS: frozenset[str] = frozenset({"openai", "deepseek", "openrouter"})

# Default public API bases (always normalized to end with /v1 for OpenAI clients).
DEFAULT_OPENAI_COMPAT_BASE_URLS: dict[str, str] = {
    "deepseek": "https://api.deepseek.com/v1",
    "openrouter": "https://openrouter.ai/api/v1",
}


@dataclass(frozen=True)
class OfficialModelSpec:
    provider: str
    model: str
    model_string: str
    transport: str = "direct"


@dataclass(frozen=True)
class CloudModelResolution:
    """Non-secret summary of how a cloud model client was (or would be) built."""

    provider: str
    model: str
    model_string: str
    path: str  # official | fallback | error
    has_api_key: bool
    base_url_normalized: str | None
    message: str | None = None


_PROFILES_REGISTERED = False

# Last successful (or attempted) chat-model resolution for execution_trace (Phase 4).
_last_chat_model_resolution: ContextVar[dict[str, Any] | None] = ContextVar(
    "agent_last_chat_model_resolution",
    default=None,
)


def get_last_chat_model_resolution() -> dict[str, Any] | None:
    """Return non-secret resolution facts from the most recent get_chat_model call."""
    value = _last_chat_model_resolution.get()
    return dict(value) if isinstance(value, dict) else None


def _record_chat_model_resolution(**fields: Any) -> dict[str, Any]:
    payload = {key: value for key, value in fields.items() if value is not None}
    _last_chat_model_resolution.set(payload)
    return payload


def get_chat_model(context: RuntimeExecutionContext) -> BaseChatModel:
    """Resolve a tool-capable LangChain chat model for DeepAgents."""
    spec = resolve_official_model_spec(context)
    if spec is None:
        provider = str(context.provider or "")
        model = str(context.model or "")
        _record_chat_model_resolution(
            model_entry="error",
            path="error",
            fallback_used=False,
            provider=provider,
            model=model,
            last_model_error="unresolved provider:model",
        )
        raise ProviderAdapterError(
            "DeepAgents 现在只接受官方 LangChain 模型格式。"
            f"当前 provider={provider!r}, model={model!r}。"
            "请使用 provider:model，例如 openai:gpt-4o、ollama:qwen3:8b、openrouter:z-ai/glm-5.1。"
        )
    if spec.transport == "local_inference_service":
        return _get_local_inference_service_chat_model(spec, context)

    kwargs = _model_kwargs_for_spec(spec, context)
    try:
        _require_cloud_api_key(spec, kwargs)
    except ProviderAdapterError as exc:
        _record_chat_model_resolution(
            model_entry="error",
            path="error",
            fallback_used=False,
            provider=spec.provider,
            model=spec.model,
            model_string=spec.model_string,
            last_model_error=str(exc)[:600],
        )
        raise

    try:
        model = init_official_chat_model(spec, context, kwargs=kwargs)
        _record_chat_model_resolution(
            model_entry="official_init_chat_model",
            path="official",
            fallback_used=False,
            provider=spec.provider,
            model=spec.model,
            model_string=spec.model_string,
            base_url=kwargs.get("base_url"),
            has_api_key=bool(kwargs.get("api_key")),
        )
        return model
    except Exception as official_exc:
        if _should_use_openai_compat_fallback(spec, official_exc):
            try:
                model = init_openai_compat_chat_model(spec, context, kwargs=kwargs)
                _record_chat_model_resolution(
                    model_entry="openai_compat_fallback",
                    path="fallback",
                    fallback_used=True,
                    provider=spec.provider,
                    model=spec.model,
                    model_string=spec.model_string,
                    base_url=kwargs.get("base_url"),
                    has_api_key=bool(kwargs.get("api_key")),
                    official_error=_safe_error_text(official_exc),
                )
                return model
            except Exception as fallback_exc:
                message = (
                    f"DeepAgents 模型 {spec.model_string} 官方初始化失败，且 OpenAI 兼容回退也失败。"
                    f"官方错误：{_safe_error_text(official_exc)}；回退错误：{_safe_error_text(fallback_exc)}。"
                    f"请确认已配置有效的 {spec.provider} API Key，并安装 agent 依赖（uv sync --extra agent）。"
                )
                _record_chat_model_resolution(
                    model_entry="error",
                    path="error",
                    fallback_used=True,
                    provider=spec.provider,
                    model=spec.model,
                    model_string=spec.model_string,
                    last_model_error=message[:600],
                )
                raise ProviderAdapterError(message) from fallback_exc
        message = f"DeepAgents 官方模型 {spec.model_string} 初始化失败：{_safe_error_text(official_exc)}"
        _record_chat_model_resolution(
            model_entry="error",
            path="error",
            fallback_used=False,
            provider=spec.provider,
            model=spec.model,
            model_string=spec.model_string,
            last_model_error=message[:600],
        )
        raise ProviderAdapterError(message) from official_exc


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


def init_official_chat_model(
    spec: OfficialModelSpec,
    context: RuntimeExecutionContext,
    *,
    kwargs: dict[str, Any] | None = None,
) -> BaseChatModel:
    register_default_provider_profiles()
    from langchain.chat_models import init_chat_model

    init_kwargs = kwargs if kwargs is not None else _model_kwargs_for_spec(spec, context)
    return init_chat_model(model=spec.model, model_provider=spec.provider, **init_kwargs)


def init_openai_compat_chat_model(
    spec: OfficialModelSpec,
    context: RuntimeExecutionContext,
    *,
    kwargs: dict[str, Any] | None = None,
) -> BaseChatModel:
    """Build ChatOpenAI against an OpenAI-compatible base_url (DeepSeek/OpenRouter/OpenAI)."""
    from langchain_openai import ChatOpenAI

    if spec.provider not in OPENAI_COMPAT_PROVIDERS:
        raise ProviderAdapterError(
            f"provider={spec.provider!r} 不支持 OpenAI 兼容回退。请安装对应的 LangChain provider 包。"
        )
    init_kwargs = dict(kwargs if kwargs is not None else _model_kwargs_for_spec(spec, context))
    _require_cloud_api_key(spec, init_kwargs)
    base_url = normalize_openai_compat_base_url(spec.provider, init_kwargs.get("base_url"))
    if base_url:
        init_kwargs["base_url"] = base_url
    elif spec.provider in DEFAULT_OPENAI_COMPAT_BASE_URLS:
        init_kwargs["base_url"] = DEFAULT_OPENAI_COMPAT_BASE_URLS[spec.provider]

    # ChatOpenAI constructor kwargs (subset of init_chat_model kwargs).
    chat_kwargs: dict[str, Any] = {
        "model": spec.model,
        "temperature": init_kwargs.get("temperature", 0),
        "api_key": init_kwargs["api_key"],
    }
    if init_kwargs.get("base_url"):
        chat_kwargs["base_url"] = init_kwargs["base_url"]
    if init_kwargs.get("timeout") is not None:
        chat_kwargs["timeout"] = init_kwargs["timeout"]
    if init_kwargs.get("max_retries") is not None:
        chat_kwargs["max_retries"] = init_kwargs["max_retries"]
    if init_kwargs.get("max_tokens") is not None:
        chat_kwargs["max_tokens"] = init_kwargs["max_tokens"]
    if isinstance(init_kwargs.get("extra_body"), dict):
        chat_kwargs["extra_body"] = init_kwargs["extra_body"]
    # Local Ollama facade rejects tools+stream; force non-stream for tool_calling.
    if "disable_streaming" in init_kwargs:
        chat_kwargs["disable_streaming"] = init_kwargs["disable_streaming"]
    elif spec.transport == "local_inference_service":
        chat_kwargs["disable_streaming"] = "tool_calling"

    # Local 127.0.0.1 inference must not go through Windows system HTTP proxy
    # (otherwise ChatOpenAI → :8020 returns opaque 502 via the proxy).
    if spec.transport == "local_inference_service" or init_kwargs.get("bypass_http_proxy"):
        import httpx

        timeout = init_kwargs.get("timeout")
        chat_kwargs["http_client"] = httpx.Client(trust_env=False, timeout=timeout)
        chat_kwargs["http_async_client"] = httpx.AsyncClient(trust_env=False, timeout=timeout)
    return ChatOpenAI(**chat_kwargs)


def normalize_openai_compat_base_url(provider: str, base_url: str | None) -> str | None:
    """Ensure OpenAI-compatible base URLs end with ``/v1`` when a host is known."""
    raw = str(base_url or "").strip()
    if not raw:
        raw = DEFAULT_OPENAI_COMPAT_BASE_URLS.get(provider, "")
    if not raw:
        return None
    cleaned = raw.rstrip("/")
    # Already a /v1 endpoint (or /v1beta etc. for some gateways — keep as-is if /v1 present).
    if cleaned.endswith("/v1") or "/v1/" in cleaned + "/":
        if cleaned.endswith("/v1"):
            return cleaned
        # e.g. https://host/v1/something — keep host path as provided but ensure trailing not doubled
        return cleaned
    return f"{cleaned}/v1"


def describe_cloud_model_resolution(
    context: RuntimeExecutionContext,
    *,
    force_fallback: bool = False,
) -> CloudModelResolution:
    """Build a non-secret resolution plan for tests and diagnostics (no network)."""
    spec = resolve_official_model_spec(context)
    if spec is None:
        return CloudModelResolution(
            provider=str(context.provider or ""),
            model=str(context.model or ""),
            model_string="",
            path="error",
            has_api_key=False,
            base_url_normalized=None,
            message="无法解析 provider:model。",
        )
    if spec.transport == "local_inference_service":
        if _is_ollama_local_service_route(context, spec):
            ollama_status = local_agent_tool_calling_status("ollama", settings)
            base = f"{settings.inference_service_url.rstrip('/')}/v1"
            if ollama_status.get("supported"):
                return CloudModelResolution(
                    provider="ollama",
                    model=spec.model,
                    model_string=spec.model_string,
                    path="local_ollama_service",
                    has_api_key=bool(settings.inference_internal_api_key),
                    base_url_normalized=base,
                    message=None,
                )
            return CloudModelResolution(
                provider="ollama",
                model=spec.model,
                model_string=spec.model_string,
                path="error",
                has_api_key=bool(settings.inference_internal_api_key),
                base_url_normalized=base,
                message=str(ollama_status.get("message") or "Ollama 工具调用不可用。"),
            )
        status = local_agent_tool_calling_status("local", settings)
        return CloudModelResolution(
            provider=spec.provider,
            model=spec.model,
            model_string=spec.model_string,
            path="error",
            has_api_key=False,
            base_url_normalized=None,
            message=str(status.get("message") or "本地推理服务不支持 Agent 工具调用。"),
        )
    kwargs = _model_kwargs_for_spec(spec, context)
    has_key = bool(str(kwargs.get("api_key") or "").strip())
    base = None
    if spec.provider in OPENAI_COMPAT_PROVIDERS:
        base = normalize_openai_compat_base_url(spec.provider, kwargs.get("base_url"))
    if spec.provider in OPENAI_COMPAT_PROVIDERS and not has_key:
        return CloudModelResolution(
            provider=spec.provider,
            model=spec.model,
            model_string=spec.model_string,
            path="error",
            has_api_key=False,
            base_url_normalized=base,
            message=_missing_api_key_message(spec.provider),
        )
    path = "fallback" if force_fallback and spec.provider in OPENAI_COMPAT_PROVIDERS else "official"
    if force_fallback and spec.provider not in OPENAI_COMPAT_PROVIDERS:
        path = "error"
        return CloudModelResolution(
            provider=spec.provider,
            model=spec.model,
            model_string=spec.model_string,
            path=path,
            has_api_key=has_key,
            base_url_normalized=base,
            message=f"provider={spec.provider!r} 不支持 OpenAI 兼容回退。",
        )
    return CloudModelResolution(
        provider=spec.provider,
        model=spec.model,
        model_string=spec.model_string,
        path=path,
        has_api_key=has_key,
        base_url_normalized=base,
        message=None,
    )


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


def _model_kwargs_for_spec(spec: OfficialModelSpec, context: RuntimeExecutionContext) -> dict[str, Any]:
    """Build init kwargs including secrets (never log the returned api_key)."""
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

    # Cloud / direct providers: repository key is LANGCHAIN provider id
    # (deepseek/openai/openrouter). Also try original alias if different.
    key_data = cloud_provider_repository.get(spec.provider)
    if not isinstance(key_data, dict):
        key_data = {}
    # OpenRouter/DeepSeek keys are stored under their provider ids.
    kwargs = {
        "temperature": 0,
        "timeout": settings.agent_cloud_model_timeout_seconds,
        "max_retries": settings.agent_cloud_model_max_retries,
    }
    metadata = context.metadata if isinstance(context.metadata, dict) else {}
    api_key = str(metadata.get("api_key") or key_data.get("api_key") or "").strip()
    if api_key:
        kwargs["api_key"] = api_key
    base_url = metadata.get("base_url") or key_data.get("base_url")
    if spec.provider in OPENAI_COMPAT_PROVIDERS:
        normalized = normalize_openai_compat_base_url(spec.provider, base_url if base_url else None)
        if normalized:
            kwargs["base_url"] = normalized
    elif base_url:
        kwargs["base_url"] = str(base_url).rstrip("/")
    model_params = metadata.get("model_params")
    if isinstance(model_params, dict):
        kwargs = _merge_model_kwargs(kwargs, model_params)
        # Re-normalize base_url if model_params overwrote it.
        if spec.provider in OPENAI_COMPAT_PROVIDERS and kwargs.get("base_url"):
            kwargs["base_url"] = normalize_openai_compat_base_url(spec.provider, kwargs.get("base_url"))
    return kwargs


# Back-compat name used by older tests / imports.
def _official_model_kwargs(spec: OfficialModelSpec, context: RuntimeExecutionContext) -> dict[str, Any]:
    return _model_kwargs_for_spec(spec, context)


def _require_cloud_api_key(spec: OfficialModelSpec, kwargs: dict[str, Any]) -> None:
    if spec.transport != "direct":
        return
    if spec.provider not in OPENAI_COMPAT_PROVIDERS:
        return
    if str(kwargs.get("api_key") or "").strip():
        return
    raise ProviderAdapterError(_missing_api_key_message(spec.provider))


def _missing_api_key_message(provider: str) -> str:
    return (
        f"未配置 {provider} API Key，无法启动 Agent 云端模型。"
        f"请在模型运行/云端配置中填写有效的 {provider} API Key 后重试。"
    )


def _should_use_openai_compat_fallback(spec: OfficialModelSpec, exc: BaseException) -> bool:
    if spec.transport != "direct":
        return False
    if spec.provider not in OPENAI_COMPAT_PROVIDERS:
        return False
    text = str(exc).lower()
    markers = (
        "requires the langchain",
        "langchain-deepseek",
        "langchain_deepseek",
        "langchain-openai",
        "langchain_openai",
        "no module named",
        "modulenotfounderror",
        "importerror",
        "cannot import",
        "package is not installed",
        "pip install",
    )
    return any(marker in text for marker in markers)


def _safe_error_text(exc: BaseException, *, limit: int = 400) -> str:
    text = str(exc) or type(exc).__name__
    # Never echo obvious key material if a library included it.
    lowered = text.lower()
    for token in ("sk-", "api_key", "authorization", "bearer "):
        if token in lowered:
            return type(exc).__name__
    return text[:limit]


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


def _is_ollama_local_service_route(context: RuntimeExecutionContext, spec: OfficialModelSpec) -> bool:
    provider = str(context.provider or "").strip().lower()
    if provider == "ollama" or provider.startswith("ollama:"):
        return True
    model = str(spec.model or "")
    if model.startswith("ollama/") or model.startswith("ollama:"):
        return True
    model_string = str(spec.model_string or "")
    return model_string.startswith("ollama:") or model_string.startswith("ollama/")


def _get_local_inference_service_chat_model(
    spec: OfficialModelSpec,
    context: RuntimeExecutionContext,
) -> BaseChatModel:
    """Route tool-capable Ollama through the local OpenAI-compatible inference service."""
    if _is_ollama_local_service_route(context, spec):
        ollama_status = local_agent_tool_calling_status("ollama", settings)
        if ollama_status.get("supported"):
            kwargs = _model_kwargs_for_spec(spec, context)
            # Local /v1 rejects tools+stream (unsupported_stream_tools). DeepAgents
            # may astream_events; disable streaming for tool_calling so bind_tools
            # paths never send stream=true with tools.
            kwargs["disable_streaming"] = "tool_calling"
            # ChatOpenAI talks to inference_server /v1 which passthroughs tools to Ollama.
            model = init_openai_compat_chat_model(
                OfficialModelSpec(
                    provider="openai",
                    model=spec.model,
                    model_string=spec.model_string,
                    transport="local_inference_service",
                ),
                context,
                kwargs=kwargs,
            )
            _record_chat_model_resolution(
                model_entry="local_ollama_service",
                path="local_ollama_service",
                fallback_used=False,
                provider="ollama",
                model=spec.model,
                model_string=spec.model_string,
                base_url=kwargs.get("base_url"),
                has_api_key=bool(kwargs.get("api_key")),
                disable_streaming="tool_calling",
            )
            return model
        message = str(ollama_status.get("message") or "Ollama 工具调用不可用。")
        _record_chat_model_resolution(
            model_entry="error",
            path="error",
            fallback_used=False,
            provider="ollama",
            model=spec.model,
            last_model_error=message[:600],
        )
        raise ProviderAdapterError(message)

    status = local_agent_tool_calling_status("local", settings)
    message = status["message"] or "本地推理服务不支持 Agent 工具调用。"
    _record_chat_model_resolution(
        model_entry="error",
        path="error",
        fallback_used=False,
        provider=str(context.provider or "local"),
        model=spec.model,
        last_model_error=message[:600],
    )
    raise ProviderAdapterError(message)


def _local_service_spec(provider: str, model: str, model_string: str) -> OfficialModelSpec:
    routed_model = model if provider == "local" or "/" in model else f"{provider}/{model}"
    return OfficialModelSpec(
        provider="openai",
        model=routed_model,
        model_string=model_string,
        transport="local_inference_service",
    )


__all__ = [
    "DEFAULT_OPENAI_COMPAT_BASE_URLS",
    "LANGCHAIN_PROVIDER_ALIASES",
    "OPENAI_COMPAT_PROVIDERS",
    "CloudModelResolution",
    "OfficialModelSpec",
    "ProviderAdapterError",
    "describe_cloud_model_resolution",
    "get_chat_model",
    "get_last_chat_model_resolution",
    "init_official_chat_model",
    "init_openai_compat_chat_model",
    "normalize_openai_compat_base_url",
    "resolve_official_model_spec",
]
