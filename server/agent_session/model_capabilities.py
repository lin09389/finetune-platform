"""Agent / local inference tool-calling capability fact source.

DeepAgents always binds tools.  This module is the **single pure fact source**
for every published tool-calling signal used by Agent setup, ``GET /api/info``,
and the local inference capability surface.

Phase 2 truth (must not lie):
- The local OpenAI-compatible Chat Completions endpoint accepts tools only for
  the **Ollama** backend (passthrough to Ollama ``/api/chat``).
- HuggingFace and llama-cpp remain fail-closed for tools.
- Backend ids match ``BackendType`` values (``llama-cpp``, not ``llamacpp``).
- Agent ``provider=ollama`` is tool-capable in both ``service`` (endpoint) and
  ``in_process`` (LangChain Ollama) modes; ``provider=local`` stays fail-closed
  because it may resolve to a non-Ollama backend.
- Cloud providers are treated as tool-capable once a provider id is selected;
  credential presence is reported separately (non-secret).
"""

from __future__ import annotations

from typing import Any

# Canonical local inference backends (must match ``BackendType`` / list_backends ids).
LOCAL_INFERENCE_BACKENDS: tuple[str, ...] = ("huggingface", "ollama", "llama-cpp")

# Non-canonical aliases that still mean a local backend (legacy / typos / engine ids).
_LOCAL_BACKEND_ALIASES: dict[str, str] = {
    "llamacpp": "llama-cpp",
    "llama_cpp": "llama-cpp",
    "llama-cpp-python": "llama-cpp",
    "hf": "huggingface",
}

# Names that Agent/model-runtime may pass when probing local tool calling.
LOCAL_AGENT_PROVIDER_ALIASES: frozenset[str] = frozenset(
    {
        "local",
        "ollama",
        "huggingface",
        "llama-cpp",
        *_LOCAL_BACKEND_ALIASES.keys(),
    }
)

# Recommended cloud providers for Agent (configuration UX; not a secret).
RECOMMENDED_CLOUD_AGENT_PROVIDERS: tuple[str, ...] = ("deepseek", "openrouter", "openai")

_SERVICE_TEXT_ONLY_MESSAGE = (
    "当前本地后端不支持 Agent 所需的工具调用。"
    "请使用 Ollama（provider=ollama 或 model=ollama/...），"
    "或配置支持工具调用的云端 provider:model。"
)

_SELECT_PROVIDER_MESSAGE = "请选择 Agent 的 provider:model。"

_ENDPOINT_VIA = "local_chat_completions"
_ENDPOINT_OLLAMA_VIA = "local_chat_completions_ollama"
_LANGCHAIN_OLLAMA_VIA = "langchain_ollama_in_process"


def _execution_mode(settings: Any) -> str:
    return str(getattr(settings, "inference_execution_mode", "service") or "service").strip().lower()


def _normalize_name(value: str | None) -> str:
    return str(value or "").strip().lower()


def _canonicalize_local_backend(name: str) -> str | None:
    """Map provider/backend aliases to a canonical ``BackendType`` id, or None."""
    if not name:
        return None
    if name in LOCAL_INFERENCE_BACKENDS:
        return name
    return _LOCAL_BACKEND_ALIASES.get(name)


def local_endpoint_backend_tool_calling_status(
    backend: str | None,
    settings: Any | None = None,
) -> dict[str, Any]:
    """Whether the local OpenAI-compatible endpoint accepts tools for ``backend``.

    Phase 2: Ollama is supported via tools passthrough; HF / llama-cpp are not.

    Backend keys are canonical ``BackendType`` values (``llama-cpp``).
    """
    _ = settings  # reserved for future mode/feature flags
    raw = _normalize_name(backend)
    name = _canonicalize_local_backend(raw) or raw
    if name == "ollama":
        return {
            "backend": name,
            "supported": True,
            "via": _ENDPOINT_OLLAMA_VIA,
            "message": None,
        }
    if name not in LOCAL_INFERENCE_BACKENDS:
        return {
            "backend": name or None,
            "supported": False,
            "via": _ENDPOINT_VIA,
            "message": _SERVICE_TEXT_ONLY_MESSAGE,
        }
    return {
        "backend": name,
        "supported": False,
        "via": _ENDPOINT_VIA,
        "message": _SERVICE_TEXT_ONLY_MESSAGE,
    }


def build_local_backend_tool_calling_breakdown(
    settings: Any | None = None,
) -> dict[str, dict[str, Any]]:
    """Per-backend tool-calling facts for the local Chat Completions endpoint."""
    return {
        backend: local_endpoint_backend_tool_calling_status(backend, settings)
        for backend in LOCAL_INFERENCE_BACKENDS
    }


def build_inference_tool_calling_features(settings: Any | None = None) -> dict[str, Any]:
    """Features fragment for inference ``/internal/capabilities`` (backend-aware)."""
    breakdown = build_local_backend_tool_calling_breakdown(settings)
    by_backend = {name: bool(info["supported"]) for name, info in breakdown.items()}
    return {
        "tool_calling": any(by_backend.values()),
        "tool_calling_by_backend": by_backend,
        "tool_calling_details": {
            name: {
                "supported": bool(info["supported"]),
                "via": info.get("via"),
                "message": info.get("message"),
            }
            for name, info in breakdown.items()
        },
    }


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
    """Return the tool-calling boundary for a selected local provider/backend.

    - ``ollama``: tool-capable in **service** (local OpenAI facade → Ollama) and
      **in_process** (LangChain Ollama) modes.
    - ``local`` / huggingface / llama-cpp: fail closed (``local`` may resolve to HF).

    Accepts canonical ``BackendType`` ids (``llama-cpp``) and legacy aliases
    (``llamacpp``).
    """
    normalized = _normalize_name(provider)
    execution_mode = _execution_mode(settings)
    canonical_backend = _canonicalize_local_backend(normalized)

    # Non-Ollama local backends / generic local: fail closed.
    if normalized == "local" or canonical_backend in {"huggingface", "llama-cpp"}:
        endpoint = local_endpoint_backend_tool_calling_status(
            "huggingface" if normalized == "local" else (canonical_backend or normalized),
            settings,
        )
        return {
            "supported": False,
            "execution_mode": execution_mode,
            "message": endpoint["message"],
            "via": endpoint["via"],
            "backend": endpoint.get("backend"),
        }

    if normalized == "ollama" or canonical_backend == "ollama":
        endpoint = local_endpoint_backend_tool_calling_status("ollama", settings)
        if execution_mode == "service":
            return {
                "supported": bool(endpoint["supported"]),
                "execution_mode": execution_mode,
                "message": endpoint.get("message"),
                "via": endpoint.get("via") or _ENDPOINT_OLLAMA_VIA,
                "backend": "ollama",
            }
        # in_process: LangChain Ollama can bind tools directly.
        return {
            "supported": True,
            "execution_mode": execution_mode,
            "message": None,
            "via": _LANGCHAIN_OLLAMA_VIA,
            "backend": "ollama",
        }

    # Unknown local-ish name that was explicitly classified as local: fail closed.
    if normalized in LOCAL_AGENT_PROVIDER_ALIASES:
        return {
            "supported": False,
            "execution_mode": execution_mode,
            "message": _SERVICE_TEXT_ONLY_MESSAGE,
            "via": _ENDPOINT_VIA,
            "backend": canonical_backend or normalized,
        }

    if not normalized:
        return {
            "supported": False,
            "execution_mode": execution_mode,
            "message": _SELECT_PROVIDER_MESSAGE,
            "via": None,
            "backend": None,
        }

    # Not a known local provider — caller should use agent_model_tool_calling_status
    # for cloud routing; keep fail-closed if this helper is misused.
    return {
        "supported": False,
        "execution_mode": execution_mode,
        "message": _SERVICE_TEXT_ONLY_MESSAGE,
        "via": _ENDPOINT_VIA,
        "backend": normalized,
    }


def agent_model_tool_calling_status(provider: str | None, settings: Any) -> dict[str, Any]:
    """Return whether the provider can enter the DeepAgents tool loop.

    Local/backend names (including ``llama-cpp`` and aliases) always go through
    ``local_agent_tool_calling_status`` so the two public helpers never disagree.
    """
    normalized = _normalize_name(provider)
    execution_mode = _execution_mode(settings)
    if not normalized:
        return {
            "supported": False,
            "execution_mode": execution_mode,
            "message": _SELECT_PROVIDER_MESSAGE,
            "via": None,
            "backend": None,
        }
    if (
        normalized in LOCAL_AGENT_PROVIDER_ALIASES
        or _canonicalize_local_backend(normalized) is not None
        or normalized == "local"
    ):
        return local_agent_tool_calling_status(normalized, settings)
    return {
        "supported": True,
        "execution_mode": execution_mode,
        "message": None,
        "via": "cloud_provider",
        "backend": None,
    }


def recommended_agent_providers(
    settings: Any,
    *,
    cloud_model_configured: bool = False,
) -> list[str]:
    """Ordered, non-secret recommendations for Agent model setup."""
    recommended: list[str] = list(RECOMMENDED_CLOUD_AGENT_PROVIDERS)
    ollama = local_agent_tool_calling_status("ollama", settings)
    if ollama.get("supported"):
        recommended.append("ollama")
    # cloud_model_configured does not remove cloud recommendations; it only
    # signals readiness.  Keep the list stable for UI guidance.
    _ = cloud_model_configured
    return recommended


def build_agent_model_runtime_payload(
    settings: Any,
    *,
    cloud_model_configured: bool,
) -> dict[str, Any]:
    """Structured ``agent_model_runtime`` block for ``GET /api/info``."""
    local_status = local_agent_tool_calling_status("local", settings)
    ollama_status = local_agent_tool_calling_status("ollama", settings)
    breakdown = build_local_backend_tool_calling_breakdown(settings)
    return {
        "cloud_model_configured": bool(cloud_model_configured),
        "local_tool_calling_supported": bool(local_status["supported"]),
        "local_tool_calling_message": local_status.get("message"),
        "inference_execution_mode": local_status["execution_mode"],
        "backends": {
            name: {
                "tool_calling": bool(info["supported"]),
                "via": info.get("via"),
                "message": info.get("message"),
            }
            for name, info in breakdown.items()
        },
        "providers": {
            "local": {
                "tool_calling_supported": bool(local_status["supported"]),
                "message": local_status.get("message"),
                "via": local_status.get("via"),
            },
            "ollama": {
                "tool_calling_supported": bool(ollama_status["supported"]),
                "message": ollama_status.get("message"),
                "via": ollama_status.get("via"),
            },
        },
        "recommended_agent_providers": recommended_agent_providers(
            settings,
            cloud_model_configured=cloud_model_configured,
        ),
    }


__all__ = [
    "LOCAL_AGENT_PROVIDER_ALIASES",
    "LOCAL_INFERENCE_BACKENDS",
    "RECOMMENDED_CLOUD_AGENT_PROVIDERS",
    "agent_model_tool_calling_status",
    "build_agent_model_runtime_payload",
    "build_inference_tool_calling_features",
    "build_local_backend_tool_calling_breakdown",
    "local_agent_tool_calling_status",
    "local_endpoint_backend_tool_calling_status",
    "recommended_agent_providers",
    "saved_cloud_agent_model_configured",
]
