from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.inference import routes
from api.inference.backends.base import GenerationResult
from api.inference.scheduler import ModelScheduler


def test_chat_exposes_backend_error_metadata(monkeypatch):
    app = FastAPI()
    app.include_router(routes.router, prefix="/inference")

    async def fake_execute_with_protection(_backend_name, do_chat, _fallback_chat):
        return GenerationResult(
            text="",
            tokens_generated=0,
            finish_reason="error",
            model="broken-model",
            metadata={"error": "Ollama API error: 404"},
        )

    monkeypatch.setattr(
        routes.circuit_breaker,
        "execute_with_protection",
        fake_execute_with_protection,
    )

    response = TestClient(app).post(
        "/inference/chat",
        json={
            "model": "broken-model",
            "messages": [{"role": "user", "content": "hello"}],
            "options": {"backend": "ollama", "max_tokens": 32, "temperature": 0.2},
            "memory": {"enabled": False, "auto_extract": False, "auto_retrieve": False},
            "knowledge": {"use_knowledge": False, "auto_retrieve": False, "include_sources": False},
            "context": {"use_context": False},
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["raw_response"]["finish_reason"] == "error"
    assert payload["raw_response"]["error"] == "Ollama API error: 404"


def test_scheduler_reloads_when_lora_runtime_variant_changes(monkeypatch):
    class DummyBackend:
        def __init__(self):
            self.loads = []

        async def load_model(self, path, runtime_policy=None, **kwargs):
            self.loads.append((path, (runtime_policy or {}).get("lora_adapter")))
            return True

        async def unload_model(self):
            return True

    async def exercise():
        scheduler = ModelScheduler()
        backend = DummyBackend()

        async def get_backend(_backend_name):
            return backend

        monkeypatch.setattr(scheduler, "get_backend", get_backend)
        base_lease = await scheduler.acquire_model("base", "base", "huggingface")
        assert base_lease is not None
        await scheduler.release_model("base")

        adapter_lease = await scheduler.acquire_model(
            "base",
            "base",
            "huggingface",
            lora_adapter="adapter-a",
        )
        assert adapter_lease is not None
        await scheduler.release_model("base")
        return backend.loads

    import asyncio

    assert asyncio.run(exercise()) == [("base", None), ("base", "adapter-a")]


def test_scheduler_never_unloads_an_active_lease(monkeypatch):
    class DummyBackend:
        def __init__(self):
            self.loads = []
            self.unloads = 0

        async def load_model(self, path, runtime_policy=None, **kwargs):
            self.loads.append(path)
            return True

        async def unload_model(self):
            self.unloads += 1
            return True

    async def exercise():
        scheduler = ModelScheduler()
        backend = DummyBackend()

        async def get_backend(_backend_name):
            return backend

        monkeypatch.setattr(scheduler, "get_backend", get_backend)
        first = await scheduler.acquire_model("first", "first", "huggingface")
        assert first is not None

        pending = asyncio.create_task(
            scheduler.acquire_model("second", "second", "huggingface")
        )
        await asyncio.sleep(0.05)
        assert not pending.done()
        assert backend.unloads == 0

        await scheduler.release_model("first")
        second = await asyncio.wait_for(pending, timeout=1)
        assert second is not None
        assert backend.unloads == 1

    import asyncio

    asyncio.run(exercise())


def test_generate_cache_key_separates_lora_variants():
    base = routes.GenerateRequest(
        model="base",
        prompt="hello",
        options={"backend": "huggingface", "temperature": 0.1},
    )
    adapted = routes.GenerateRequest(
        model="base",
        prompt="hello",
        lora_adapter="adapter-a",
        options={"backend": "huggingface", "temperature": 0.1},
    )

    assert routes._build_generate_cache_key(base, "huggingface") != routes._build_generate_cache_key(
        adapted,
        "huggingface",
    )


def test_generate_resolves_deployment_alias_to_adapter(monkeypatch):
    captured = {}

    class DummyBackend:
        async def generate(self, prompt, config):
            return GenerationResult(
                text="deployed answer",
                tokens_generated=2,
                finish_reason="stop",
                model="deployed-alias",
                prompt_tokens=1,
                total_tokens=3,
                latency_ms=5,
            )

    class DummyScheduler:
        async def get_backend(self, backend):
            captured["backend"] = backend
            return DummyBackend()

        async def acquire_model(self, model_name, model_path, backend, **kwargs):
            captured.update(
                {
                    "model_name": model_name,
                    "model_path": model_path,
                    "acquire_backend": backend,
                    "lora_adapter": kwargs.get("lora_adapter"),
                }
            )

            class Lease:
                metadata = {}

            return Lease()

        async def release_model(self, model_name):
            captured["released"] = model_name

        def get_stats(self):
            return {"default_backend": "huggingface"}

    async def execute(_backend_name, do_generate, _fallback):
        return await do_generate()

    monkeypatch.setattr(routes, "get_scheduler", lambda: DummyScheduler())
    monkeypatch.setattr(
        routes,
        "_resolve_deployment_target",
        lambda _name: {
            "model_path": "C:/models/base",
            "backend": "huggingface",
            "lora_adapter": "C:/outputs/adapter",
        },
    )
    monkeypatch.setattr(routes.circuit_breaker, "execute_with_protection", execute)

    app = FastAPI()
    app.include_router(routes.router, prefix="/inference")
    response = TestClient(app).post(
        "/inference/generate",
        json={
            "model": "deployed-alias",
            "prompt": "hello",
            "options": {"backend": "ollama", "temperature": 0.7, "max_tokens": 16},
        },
    )

    assert response.status_code == 200
    assert response.json()["response"] == "deployed answer"
    assert captured == {
        "backend": "huggingface",
        "model_name": "deployed-alias",
        "model_path": "C:/models/base",
        "acquire_backend": "huggingface",
        "lora_adapter": "C:/outputs/adapter",
        "released": "deployed-alias",
    }
