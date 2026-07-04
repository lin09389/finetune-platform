import importlib

import pytest

runtime_api = importlib.import_module("api.runtime")
main_module = importlib.import_module("main")


@pytest.mark.asyncio
async def test_runtime_bootstrap_aggregates_core_runtime_contract(monkeypatch):
    async def _list_backends():
        return {
            "current": "huggingface",
            "backends": [
                {"id": "huggingface", "name": "HuggingFace", "available": True},
                {"id": "ollama", "name": "Ollama", "available": False},
            ],
        }

    async def _list_models(backend=None):
        assert backend == "huggingface"
        return [
            {"id": "hf-default", "name": "HF Default"},
            {"id": "hf-alt", "name": "HF Alt"},
        ]

    async def _ollama_status():
        return {
            "running": False,
            "base_url": "http://ollama.local:11434",
            "models": [],
        }

    async def _collections():
        return {
            "collections": [
                {"name": "default", "count": 0},
                {"name": "project-docs", "count": 7},
            ]
        }

    async def _embedder_status():
        return {
            "loaded": True,
            "model_name": "text2vec-base-chinese",
            "dimension": 768,
        }

    async def _training_status():
        return {
            "is_training": False,
            "progress": None,
        }

    class _FakeInferenceGateway:
        async def list_backends(self):
            return await _list_backends()

        async def list_models(self, backend=None):
            return await _list_models(backend)

        async def ollama_status(self):
            return await _ollama_status()

    monkeypatch.setattr(runtime_api, "get_inference_gateway", lambda: _FakeInferenceGateway())
    monkeypatch.setattr(runtime_api.knowledge_routes, "list_collections", _collections)
    monkeypatch.setattr(runtime_api.knowledge_routes, "get_embedder_status", _embedder_status)
    monkeypatch.setattr(runtime_api.training_routes, "get_status", _training_status)

    payload = await runtime_api.get_runtime_bootstrap()

    assert payload["schema_version"] == "runtime.bootstrap.v1"
    assert payload["derived"]["runtime_status"] == "ready"
    assert payload["derived"]["available_model_count"] == 2
    assert payload["derived"]["warnings"] == []
    assert payload["observed"]["backend_status"] == "connected"
    assert payload["observed"]["inference"]["current_backend"] == "huggingface"
    assert payload["observed"]["inference"]["backends"][0]["id"] == "huggingface"
    assert payload["observed"]["inference"]["huggingface_models"][0]["id"] == "hf-default"
    assert payload["observed"]["inference"]["ollama"]["available"] is False
    assert payload["observed"]["knowledge"]["collections"][1]["id"] == "project-docs"
    assert payload["observed"]["knowledge"]["embedder_status"]["loaded"] is True
    assert payload["observed"]["training"]["is_training"] is False


@pytest.mark.asyncio
async def test_runtime_bootstrap_degrades_when_subsystems_fail(monkeypatch):
    async def _raise_error():
        raise RuntimeError("backend unavailable")

    async def _list_models(backend=None):
        return []

    async def _ollama_status():
        return {"running": False, "models": []}

    async def _collections():
        return {"collections": []}

    async def _embedder_status():
        return {"loaded": False, "error": "dependency_missing"}

    async def _training_status():
        return {"is_training": False, "progress": None}

    class _FakeInferenceGateway:
        async def list_backends(self):
            return await _raise_error()

        async def list_models(self, backend=None):
            return await _list_models(backend)

        async def ollama_status(self):
            return await _ollama_status()

    monkeypatch.setattr(runtime_api, "get_inference_gateway", lambda: _FakeInferenceGateway())
    monkeypatch.setattr(runtime_api.knowledge_routes, "list_collections", _collections)
    monkeypatch.setattr(runtime_api.knowledge_routes, "get_embedder_status", _embedder_status)
    monkeypatch.setattr(runtime_api.training_routes, "get_status", _training_status)

    payload = await runtime_api.get_runtime_bootstrap()

    assert payload["derived"]["runtime_status"] == "degraded"
    assert payload["observed"]["inference"]["current_backend"] == "huggingface"
    assert payload["observed"]["inference"]["backends"] == []
    assert any("inference.backends" in warning for warning in payload["derived"]["warnings"])
    assert payload["observed"]["knowledge"]["embedder_status"]["loaded"] is False


@pytest.mark.asyncio
async def test_api_info_advertises_runtime_bootstrap():
    payload = await main_module.api_info()

    assert payload["endpoints"]["runtime"] == "/runtime/bootstrap"
