from __future__ import annotations

from importlib import import_module

import pytest

model_runtime = import_module("api.model_runtime")


class _FakeScheduler:
    def __init__(self) -> None:
        self.default_backend = "huggingface"

    def get_stats(self):
        return {"default_backend": self.default_backend}

    def set_default_backend(self, backend: str):
        if backend not in {"huggingface", "ollama", "llama-cpp"}:
            raise ValueError("bad backend")
        self.default_backend = backend


@pytest.fixture(autouse=True)
def reset_selection(monkeypatch):
    scheduler = _FakeScheduler()

    def _fake_get_device_info(use_cache=False):
        _ = use_cache
        return {"memory_total": 4.0, "device": "cpu"}

    model_runtime._active_selection.update({
        "backend": None,
        "model_id": None,
        "scope": "global",
    })
    monkeypatch.setattr(model_runtime, "get_scheduler", lambda: scheduler)
    monkeypatch.setattr(model_runtime, "get_device_info", _fake_get_device_info)
    monkeypatch.setattr(
        model_runtime,
        "build_hardware_profile",
        lambda _device: {
            "profile": "low_vram",
            "recommended_backend": "ollama",
            "recommended_quantization": "int4",
        },
    )
    return scheduler


@pytest.mark.asyncio
async def test_model_runtime_overview_guides_setup_when_no_models(monkeypatch):
    async def _backends():
        return {
            "current": "huggingface",
            "backends": [
                {"id": "huggingface", "name": "HuggingFace", "available": True},
                {"id": "ollama", "name": "Ollama", "available": False},
            ],
        }

    async def _ollama_status():
        return {"running": False, "base_url": "http://localhost:11434", "models": []}

    monkeypatch.setattr(model_runtime.inference_routes, "list_backends", _backends)
    monkeypatch.setattr(model_runtime.inference_routes, "get_ollama_status", _ollama_status)
    monkeypatch.setattr(model_runtime, "get_models_list", lambda: [])
    monkeypatch.setattr(model_runtime, "list_local_models", lambda: [])
    monkeypatch.setattr(
        model_runtime,
        "get_model_suggestions",
        lambda: {
            "suggestions": [
                {
                    "repo_id": "Qwen/Qwen2.5-0.5B-Instruct",
                    "name": "Qwen2.5 0.5B",
                    "description": "small chat model",
                    "size": "~1GB",
                    "source": "modelscope",
                    "category": "chat",
                }
            ]
        },
    )

    payload = await model_runtime.get_model_runtime_overview()

    assert payload["schema_version"] == "model.runtime.overview.v1"
    assert payload["summary"]["state"] == "setup_required"
    assert payload["agent"]["ready"] is False
    assert payload["quick_actions"][0]["id"] == "setup_ollama"
    assert payload["recommended_models"][0]["repo_id"] == "Qwen/Qwen2.5-0.5B-Instruct"


@pytest.mark.asyncio
async def test_model_runtime_overview_promotes_ollama_model_for_agent(monkeypatch):
    async def _backends():
        return {
            "current": "ollama",
            "backends": [
                {"id": "huggingface", "name": "HuggingFace", "available": True},
                {"id": "ollama", "name": "Ollama", "available": True},
            ],
        }

    async def _ollama_status():
        return {
            "running": True,
            "base_url": "http://localhost:11434",
            "models": [{"name": "qwen2.5:7b", "size": 4_000_000_000}],
        }

    monkeypatch.setattr(model_runtime.inference_routes, "list_backends", _backends)
    monkeypatch.setattr(model_runtime.inference_routes, "get_ollama_status", _ollama_status)
    monkeypatch.setattr(model_runtime, "get_models_list", lambda: [])
    monkeypatch.setattr(model_runtime, "list_local_models", lambda: [])
    monkeypatch.setattr(model_runtime, "get_model_suggestions", lambda: {"suggestions": []})

    payload = await model_runtime.get_model_runtime_overview()

    assert payload["summary"]["state"] == "ready"
    assert payload["agent"] == {
        "ready": True,
        "provider": "ollama",
        "model": "qwen2.5:7b",
        "model_string": "ollama:qwen2.5:7b",
        "message": "Agent Workbench 会优先使用该 Ollama 模型。",
    }
    assert payload["local_models"][0]["recommended_for"] == ["agent", "chat"]


@pytest.mark.asyncio
async def test_model_runtime_selection_switches_backend(reset_selection):
    payload = await model_runtime.set_model_runtime_selection(
        model_runtime.ModelRuntimeSelectionRequest(
            backend="ollama",
            model_id="qwen2.5:7b",
            scope="agent",
        )
    )

    assert reset_selection.default_backend == "ollama"
    assert payload["selected"]["backend"] == "ollama"
    assert payload["selected"]["model_id"] == "qwen2.5:7b"
    assert payload["agent"]["model_string"] == "ollama:qwen2.5:7b"


def test_model_runtime_normalizes_model_center_entries_without_config():
    models = model_runtime._normalize_local_models(
        legacy_models=[],
        center_models=[
            {
                "id": "imported-model",
                "name": "Imported Model",
                "path": "C:/models/imported-model",
                "size": 123,
                "config": None,
            }
        ],
        ollama_models=[],
        backend_available={"huggingface": True},
    )

    assert models[0]["id"] == "imported-model"
    assert models[0]["source"] == "model-center"
    assert models[0]["metadata"]["config"] == {}
