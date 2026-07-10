"""Unified model runtime center API.

This router provides the product-facing model access contract used by the
frontend model experience and Agent Workbench. It composes existing model,
model-center, and inference endpoints instead of creating another downloader or
runtime implementation.
"""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from api.model_center import get_model_suggestions, list_local_models
from agent_session.model_capabilities import local_agent_tool_calling_status
from api.models import get_models_list
from core.config import get_settings
from core.hardware_profile import build_hardware_profile
from core.utils import get_device_info

router = APIRouter()


class ModelRuntimeSelectionRequest(BaseModel):
    backend: Literal["huggingface", "ollama", "llama-cpp"]
    model_id: str | None = Field(default=None, description="Selected model id/tag/path")
    scope: Literal["global", "agent"] = "global"


_active_selection: dict[str, str | None] = {
    "backend": None,
    "model_id": None,
    "scope": "global",
}


def get_active_model_runtime_selection() -> dict[str, str | None]:
    """Return a copy of the active product-level inference selection."""
    return dict(_active_selection)


async def _resolve(value_or_awaitable: Any) -> Any:
    if inspect.isawaitable(value_or_awaitable):
        return await value_or_awaitable
    return value_or_awaitable


def _to_plain(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if hasattr(value, "dict"):
        return value.dict()
    if isinstance(value, list):
        return [_to_plain(item) for item in value]
    if isinstance(value, tuple):
        return [_to_plain(item) for item in value]
    if isinstance(value, dict):
        return {key: _to_plain(item) for key, item in value.items()}
    return value


async def _collect(
    label: str,
    collector: Callable[[], Awaitable[Any] | Any],
    fallback: Any,
    diagnostics: list[dict[str, str]],
) -> Any:
    try:
        return _to_plain(await _resolve(collector()))
    except Exception as exc:
        diagnostics.append({
            "kind": "collector_failed",
            "severity": "warning",
            "message": f"{label}: {exc}",
        })
        return fallback


def _format_bytes(size: Any) -> str:
    try:
        size_int = int(size or 0)
    except (TypeError, ValueError):
        size_int = 0
    if size_int <= 0:
        return "未知"
    units = ["B", "KB", "MB", "GB", "TB"]
    value = float(size_int)
    unit = units[0]
    for unit in units:
        if value < 1024 or unit == units[-1]:
            break
        value /= 1024
    return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"


def _model_capabilities(model_id: str, backend: str, config: dict[str, Any] | None = None) -> list[str]:
    from api.inference.scheduler import BackendType

    lowered = model_id.lower()
    capabilities = ["inference"]
    if backend == BackendType.OLLAMA.value:
        capabilities.append("chat")
        if local_agent_tool_calling_status("ollama", get_settings())["supported"]:
            capabilities.append("agent")
    elif backend == BackendType.HUGGINGFACE.value:
        capabilities.extend(["chat", "fine_tune", "evaluation"])
    elif backend == BackendType.LLAMACPP.value:
        capabilities.extend(["chat", "low_vram"])
    if "embed" in lowered or (config or {}).get("category") == "embedding":
        capabilities = ["embedding", "knowledge_base"]
    if "vision" in lowered or "vl" in lowered:
        capabilities.append("vision")
    return sorted(set(capabilities))


def _readiness_for_model(backend: str, backend_available: bool, capabilities: list[str]) -> dict[str, Any]:
    from api.inference.scheduler import BackendType

    if not backend_available:
        if backend == BackendType.OLLAMA.value:
            return {
                "state": "blocked",
                "label": "Ollama 未连接",
                "message": "启动 Ollama 后刷新即可作为 Agent 和聊天模型使用。",
                "fix_action": "start_ollama",
            }
        if backend == BackendType.LLAMACPP.value:
            return {
                "state": "blocked",
                "label": "缺少 llama.cpp 运行库",
                "message": "安装 llama-cpp-python 后可运行 GGUF 低显存模型。",
                "fix_action": "install_llama_cpp",
            }
    if "agent" in capabilities:
        return {
            "state": "ready",
            "label": "Agent 就绪",
            "message": "可直接作为 Agent Workbench 的默认模型。",
            "fix_action": None,
        }
    return {
        "state": "ready",
        "label": "本地推理就绪",
        "message": "可用于推理、评估或训练链路；当前本地推理服务不支持 Agent 工具调用。",
        "fix_action": None,
    }


def _normalize_backend_availability(backends_payload: dict[str, Any]) -> dict[str, bool]:
    from api.inference.scheduler import BackendType

    availability: dict[str, bool] = {
        BackendType.HUGGINGFACE.value: True,
        BackendType.OLLAMA.value: False,
        BackendType.LLAMACPP.value: False,
    }
    for backend in backends_payload.get("backends", []) if isinstance(backends_payload, dict) else []:
        if isinstance(backend, dict) and backend.get("id"):
            availability[str(backend["id"])] = bool(backend.get("available"))
    return availability


def _dedupe_models(models: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str]] = set()
    deduped: list[dict[str, Any]] = []
    for model in models:
        key = (str(model.get("backend") or ""), str(model.get("id") or model.get("name") or ""))
        if not key[1] or key in seen:
            continue
        seen.add(key)
        deduped.append(model)
    return deduped


def _normalize_local_models(
    legacy_models: list[dict[str, Any]],
    center_models: list[dict[str, Any]],
    ollama_models: list[dict[str, Any]],
    backend_available: dict[str, bool],
) -> list[dict[str, Any]]:
    from api.inference.scheduler import BackendType

    normalized: list[dict[str, Any]] = []

    for model in legacy_models:
        model_id = str(model.get("id") or model.get("name") or "")
        if not model_id:
            continue
        backend = BackendType.HUGGINGFACE.value
        capabilities = _model_capabilities(model_id, backend, model.get("config"))
        normalized.append({
            "id": model_id,
            "name": model.get("name") or model_id,
            "backend": backend,
            "source": model.get("config", {}).get("source") or "local",
            "path": model.get("path"),
            "size": model.get("size") or 0,
            "size_label": model.get("size_formatted") or _format_bytes(model.get("size")),
            "capabilities": capabilities,
            "readiness": _readiness_for_model(backend, backend_available.get(backend, True), capabilities),
            "recommended_for": ["chat", "fine_tune", "evaluation"],
            "metadata": {
                "type": model.get("type"),
                "quantized": model.get("quantized"),
                "created_at": model.get("created_at"),
            },
        })

    for model in center_models:
        model_id = str(model.get("id") or model.get("name") or "")
        if not model_id:
            continue
        backend = BackendType.HUGGINGFACE.value
        config = model.get("config") if isinstance(model.get("config"), dict) else {}
        capabilities = _model_capabilities(model_id, backend, config)
        normalized.append({
            "id": model_id,
            "name": model.get("name") or model_id,
            "backend": backend,
            "source": config.get("source") or "model-center",
            "path": model.get("path"),
            "size": model.get("size") or 0,
            "size_label": _format_bytes(model.get("size")),
            "capabilities": capabilities,
            "readiness": _readiness_for_model(backend, backend_available.get(backend, True), capabilities),
            "recommended_for": ["chat", "fine_tune", "evaluation"],
            "metadata": {
                "created_at": model.get("created_at"),
                "config": config,
            },
        })

    for model in ollama_models:
        model_id = str(model.get("name") or model.get("id") or "")
        if not model_id:
            continue
        backend = BackendType.OLLAMA.value
        capabilities = _model_capabilities(model_id, backend)
        normalized.append({
            "id": model_id,
            "name": model_id,
            "backend": backend,
            "source": "ollama",
            "path": None,
            "size": model.get("size") or 0,
            "size_label": _format_bytes(model.get("size")),
            "capabilities": capabilities,
            "readiness": _readiness_for_model(backend, backend_available.get(backend, False), capabilities),
            "recommended_for": ["agent", "chat"] if "agent" in capabilities else ["chat"],
            "metadata": {
                "modified_at": model.get("modified_at"),
            },
        })

    return _dedupe_models(normalized)


def _recommended_models(hardware_profile: dict[str, Any], suggestions: dict[str, Any]) -> list[dict[str, Any]]:
    profile = str(hardware_profile.get("profile") or "").lower()
    recommended_vram = str(hardware_profile.get("recommended_quantization") or "int4")
    raw_suggestions = suggestions.get("suggestions", []) if isinstance(suggestions, dict) else []
    cards: list[dict[str, Any]] = []
    for item in raw_suggestions[:6]:
        if not isinstance(item, dict):
            continue
        repo_id = item.get("repo_id")
        if not repo_id:
            continue
        cards.append({
            "repo_id": repo_id,
            "name": item.get("name") or repo_id,
            "description": item.get("description") or "",
            "size": item.get("size") or "未知",
            "source": item.get("source") or "modelscope",
            "category": item.get("category") or "chat",
            "fit": "best" if ("low" in profile or "4gb" in profile) and "0.5" in str(repo_id).lower() else "good",
            "why": f"适合当前设备的 {recommended_vram.upper()} / 低显存优先策略。",
        })
    return cards


def _derive_summary(models: list[dict[str, Any]], backend_available: dict[str, bool]) -> dict[str, Any]:
    agent_ready = [model for model in models if "agent" in model.get("capabilities", []) and model.get("readiness", {}).get("state") == "ready"]
    local_ready = [model for model in models if model.get("readiness", {}).get("state") == "ready"]
    if agent_ready:
        state = "ready"
        headline = "Agent 和本地对话已就绪"
    elif local_ready:
        state = "degraded"
        headline = "本地模型可用；Agent 需要支持工具调用的模型"
    else:
        state = "setup_required"
        headline = "还没有可直接运行的本地模型"
    from api.inference.scheduler import BackendType

    return {
        "state": state,
        "headline": headline,
        "total_models": len(models),
        "agent_ready_models": len(agent_ready),
        "local_ready_models": len(local_ready),
        "ollama_available": bool(backend_available.get(BackendType.OLLAMA.value)),
    }


def _agent_defaults(models: list[dict[str, Any]]) -> dict[str, Any]:
    for model in models:
        if "agent" in model.get("capabilities", []) and model.get("readiness", {}).get("state") == "ready":
            return {
                "ready": True,
                "provider": "ollama",
                "model": model["id"],
                "model_string": f"ollama:{model['id']}",
                "message": "Agent Workbench 会优先使用该 Ollama 模型。",
            }
    return {
        "ready": False,
        "provider": None,
        "model": None,
        "model_string": None,
        "message": "Agent 需要支持工具调用的 provider:model；当前本地推理服务仅支持文本聊天，请配置云端模型。",
    }


def _quick_actions(summary: dict[str, Any], agent: dict[str, Any]) -> list[dict[str, Any]]:
    actions = [
        {
            "id": "download_recommended",
            "label": "下载推荐模型",
            "kind": "primary" if summary["state"] == "setup_required" else "secondary",
            "target": "/model-runtime/download",
        },
        {
            "id": "import_local",
            "label": "导入本地目录",
            "kind": "secondary",
            "target": "/model-center/import",
        },
    ]
    if not agent.get("ready"):
        actions.insert(0, {
            "id": "configure_agent_model",
            "label": "配置 Agent 模型",
            "kind": "primary",
            "target": "/cloud-api",
        })
    else:
        actions.insert(0, {
            "id": "open_agent",
            "label": "用当前模型启动 Agent",
            "kind": "primary",
            "target": "/agent",
        })
    return actions


@router.get("/overview")
async def get_model_runtime_overview():
    """Return the unified model access overview for local and Agent runtimes."""
    from api.inference import routes as inference_routes
    from api.inference.scheduler import BackendType, get_scheduler

    diagnostics: list[dict[str, str]] = []
    scheduler = get_scheduler()
    settings = get_settings()

    backends_payload = await _collect(
        "inference.backends",
        inference_routes.list_backends,
        {"current": scheduler.get_stats().get("default_backend", "huggingface"), "backends": []},
        diagnostics,
    )
    ollama_payload = await _collect(
        "inference.ollama",
        inference_routes.get_ollama_status,
        {"running": False, "models": []},
        diagnostics,
    )
    legacy_models = await _collect("models.local", get_models_list, [], diagnostics)
    center_models = await _collect("model_center.local", list_local_models, [], diagnostics)
    suggestions = await _collect("model_center.suggestions", get_model_suggestions, {"suggestions": []}, diagnostics)

    backend_available = _normalize_backend_availability(backends_payload if isinstance(backends_payload, dict) else {})
    if isinstance(ollama_payload, dict):
        backend_available[BackendType.OLLAMA.value] = bool(ollama_payload.get("running"))

    local_models = _normalize_local_models(
        legacy_models if isinstance(legacy_models, list) else [],
        center_models if isinstance(center_models, list) else [],
        ollama_payload.get("models", []) if isinstance(ollama_payload, dict) else [],
        backend_available,
    )
    device_info = get_device_info(use_cache=False)
    hardware_profile = build_hardware_profile(device_info)
    agent = _agent_defaults(local_models)
    summary = _derive_summary(local_models, backend_available)

    selected_backend = _active_selection.get("backend") or (
        BackendType.OLLAMA.value if agent.get("ready") else None
    ) or (
        backends_payload.get("current") if isinstance(backends_payload, dict) else None
    ) or scheduler.get_stats().get("default_backend", "huggingface")

    return {
        "schema_version": "model.runtime.overview.v1",
        "generated_at": datetime.now().isoformat(),
        "summary": summary,
        "active_selection": {
            "backend": selected_backend,
            "model_id": _active_selection.get("model_id") or agent.get("model"),
            "scope": _active_selection.get("scope") or "global",
        },
        "agent": agent,
        "backends": backends_payload.get("backends", []) if isinstance(backends_payload, dict) else [],
        "local_models": local_models,
        "recommended_models": _recommended_models(hardware_profile, suggestions),
        "quick_actions": _quick_actions(summary, agent),
        "environment": {
            "models_dir": str(settings.models_dir_resolved),
            "model_source": settings.model_source,
            "ollama_base_url": settings.ollama_base_url,
            "hardware_profile": hardware_profile,
        },
        "diagnostics": diagnostics,
    }


@router.post("/selection")
async def set_model_runtime_selection(request: ModelRuntimeSelectionRequest):
    """Set the product-level model selection and switch the inference backend."""
    from api.inference.scheduler import BackendType, get_scheduler

    if request.scope == "agent":
        tool_status = local_agent_tool_calling_status(request.backend, get_settings())
        if not tool_status["supported"]:
            raise HTTPException(status_code=400, detail={
                "message": tool_status["message"],
                "code": "agent_tool_calling_unsupported",
                "next_action": "configure_cloud_model",
            })

    try:
        get_scheduler().set_default_backend(request.backend)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    _active_selection.update({
        "backend": request.backend,
        "model_id": request.model_id,
        "scope": request.scope,
    })
    return {
        "schema_version": "model.runtime.selection.v1",
        "selected": dict(_active_selection),
        "agent": {
            "provider": "ollama" if request.backend == BackendType.OLLAMA.value and request.model_id else None,
            "model": request.model_id if request.backend == BackendType.OLLAMA.value else None,
            "model_string": f"ollama:{request.model_id}" if request.backend == BackendType.OLLAMA.value and request.model_id else None,
        },
    }
