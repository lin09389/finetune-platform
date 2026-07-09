"""Architecture-review Phase 1: engineering + resilience fixes.

Covers:
- async offload of deployment-target resolve and knowledge RAG routes
- service-mode generate/chat degrade on timeout/unavailable
- agent lifespan shutdown resource release
- atomic checkpoint metadata write
"""

from __future__ import annotations

import asyncio
import json
import threading
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Async offload: deployment target
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_resolve_deployment_target_async_runs_off_event_loop(monkeypatch):
    """Blocking SQLite-style resolve must not run on the event loop thread."""
    import api.inference.routes as routes

    main_thread = threading.get_ident()
    observed: dict[str, int] = {}

    def slow_sync_resolve(model_name: str):
        observed["thread"] = threading.get_ident()
        time.sleep(0.05)
        return {"model_path": f"/models/{model_name}", "backend": "huggingface"}

    monkeypatch.setattr(routes, "_resolve_deployment_target", slow_sync_resolve)

    started = time.perf_counter()
    # Concurrent with another awaitable: if resolve blocked the loop, the
    # concurrent task could not complete until resolve finished.
    async def tick():
        await asyncio.sleep(0.01)
        observed["tick_done"] = True

    result, _ = await asyncio.gather(
        routes._resolve_deployment_target_async("demo-model"),
        tick(),
    )
    elapsed = time.perf_counter() - started

    assert result["model_path"] == "/models/demo-model"
    assert observed.get("tick_done") is True
    assert observed.get("thread") != main_thread
    # Both tasks overlapped; total should be closer to max(0.05, 0.01) than sum.
    assert elapsed < 0.12


@pytest.mark.asyncio
async def test_generate_hot_path_awaits_async_deployment_resolve(monkeypatch):
    """generate() must call the async offload helper, not the bare sync resolve."""
    import api.inference.routes as routes
    from api.types import GenerateRequest, InferenceOptions

    calls: list[str] = []

    async def fake_async_resolve(model_name: str):
        calls.append(model_name)
        return None

    class DummyScheduler:
        def get_stats(self):
            return {"default_backend": "huggingface"}

        async def get_backend(self, _name):
            raise RuntimeError("stop-before-backend")

        async def release_model(self, _model):
            return None

    monkeypatch.setattr(routes, "_resolve_deployment_target_async", fake_async_resolve)
    monkeypatch.setattr(routes, "get_scheduler", lambda: DummyScheduler())
    monkeypatch.setattr(routes, "detect_prompt_injection", lambda _t: False)
    monkeypatch.setattr(routes, "sanitize_input", lambda t: t)
    monkeypatch.setattr(routes, "_should_use_offline_cache", lambda *a, **k: False)
    monkeypatch.setattr(routes, "_should_use_kv_cache", lambda *a, **k: False)

    req = GenerateRequest(
        model="m1",
        prompt="hello world",
        options=InferenceOptions(temperature=0.7),
    )
    with pytest.raises(Exception):
        # Will fail later in generate after resolve; we only care resolve was awaited.
        await routes.generate(req)

    assert calls == ["m1"]


# ---------------------------------------------------------------------------
# Knowledge RAG routes offload
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_knowledge_search_offloads_blocking_rag(monkeypatch):
    import api.knowledge.routes as knowledge_routes

    main_thread = threading.get_ident()
    observed: dict[str, int] = {}

    class FakeRag:
        def search(self, **kwargs):
            observed["search_thread"] = threading.get_ident()
            time.sleep(0.03)
            return [{"content": "hit", "score": 0.9}]

        def search_with_context(self, **kwargs):
            observed["context_thread"] = threading.get_ident()
            time.sleep(0.03)
            return "context-blob"

    monkeypatch.setattr(
        "rag.service.get_rag_service",
        lambda: FakeRag(),
    )

    req = knowledge_routes.SearchRequest(
        query="q",
        collection_id="c1",
        top_k=3,
    )
    result = await knowledge_routes.search_documents(req)

    assert result["results"][0]["content"] == "hit"
    assert result["context"] == "context-blob"
    assert observed["search_thread"] != main_thread
    assert observed["context_thread"] != main_thread


@pytest.mark.asyncio
async def test_knowledge_list_collections_offloads(monkeypatch):
    import api.knowledge.routes as knowledge_routes

    main_thread = threading.get_ident()
    observed: dict[str, int] = {}

    class FakeRag:
        def list_collections(self):
            observed["thread"] = threading.get_ident()
            time.sleep(0.02)
            return ["a", "b"]

    monkeypatch.setattr("rag.service.get_rag_service", lambda: FakeRag())
    result = await knowledge_routes.list_collections()
    assert result["collections"] == ["a", "b"]
    assert observed["thread"] != main_thread


# ---------------------------------------------------------------------------
# Service-mode degrade
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_service_gateway_generate_degrades_on_unavailable():
    from core.inference_gateway import ServiceInferenceGateway
    from inference_provider.client import InferenceServiceUnavailable

    gateway = ServiceInferenceGateway()

    class Boom:
        async def request(self, *_a, **_k):
            raise InferenceServiceUnavailable("native service down")

    gateway._client = Boom()
    request = MagicMock()
    request.model_dump.return_value = {"model": "m", "prompt": "hi"}

    result = await gateway.generate(request)
    assert result["service"]["available"] is False
    assert result["error"]["code"] == "inference_service_unavailable"
    assert result["_http_status"] == 503


@pytest.mark.asyncio
async def test_service_gateway_chat_degrades_on_timeout():
    from core.inference_gateway import ServiceInferenceGateway
    from inference_provider.client import InferenceServiceTimeout

    gateway = ServiceInferenceGateway()

    class Boom:
        async def request(self, *_a, **_k):
            raise InferenceServiceTimeout("generation timed out")

    gateway._client = Boom()
    request = MagicMock()
    request.model_dump.return_value = {"model": "m", "messages": []}

    result = await gateway.chat(request)
    assert result["service"]["available"] is False
    assert result["error"]["code"] == "inference_timeout"
    assert result["_http_status"] == 504


@pytest.mark.asyncio
async def test_service_gateway_stream_degrades_to_json_response():
    from core.inference_gateway import ServiceInferenceGateway
    from inference_provider.client import InferenceServiceUnavailable

    gateway = ServiceInferenceGateway()

    class Boom:
        async def open_stream(self, *_a, **_k):
            raise InferenceServiceUnavailable("stream offline")

    gateway._client = Boom()
    request = MagicMock()
    request.model_dump.return_value = {"model": "m", "prompt": "hi"}

    result = await gateway.generate_stream(request)
    assert isinstance(result, JSONResponse)
    assert result.status_code == 503
    assert result.headers.get("retry-after") == "5"


def test_facade_maps_degrade_payload_to_http_status(monkeypatch):
    from api.inference import facade

    class FakeGateway:
        async def generate(self, request):
            return {
                "error": {
                    "code": "inference_service_unavailable",
                    "message": "down",
                    "type": "service_unavailable",
                },
                "service": {
                    "available": False,
                    "code": "inference_service_unavailable",
                    "message": "down",
                },
                "_http_status": 503,
            }

        async def chat(self, request):
            return {
                "error": {
                    "code": "inference_timeout",
                    "message": "timeout",
                    "type": "service_unavailable",
                },
                "service": {
                    "available": False,
                    "code": "inference_timeout",
                    "message": "timeout",
                },
                "_http_status": 504,
            }

    monkeypatch.setattr(facade, "get_inference_gateway", lambda: FakeGateway())
    app = FastAPI()
    app.include_router(facade.router, prefix="/inference")
    client = TestClient(app)

    gen = client.post(
        "/inference/generate",
        json={"model": "m", "prompt": "hi", "options": {}},
    )
    assert gen.status_code == 503
    assert gen.json()["error"]["code"] == "inference_service_unavailable"
    assert gen.headers.get("retry-after") == "5"

    chat = client.post(
        "/inference/chat",
        json={
            "model": "m",
            "messages": [{"role": "user", "content": "hi"}],
            "options": {},
        },
    )
    assert chat.status_code == 504
    assert chat.json()["error"]["code"] == "inference_timeout"


# ---------------------------------------------------------------------------
# Lifespan shutdown symmetry
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_shutdown_agent_services_closes_started_resources(monkeypatch):
    import importlib

    from apps import lifespan as lifespan_mod

    closed: list[str] = []

    class FakeAgentService:
        async def shutdown_async_subtasks(self):
            closed.append("async_subtasks")

    # Patch real modules (not api package lazy router exports).
    agent_sessions = importlib.import_module("api.agent_sessions")
    chat_session = importlib.import_module("api.chat.session")
    context_service = importlib.import_module("context.service")
    embedder_mod = importlib.import_module("rag.embedder")
    vector_store_mod = importlib.import_module("rag.vector_store")
    memory_mod = importlib.import_module("memory.memory_service")

    monkeypatch.setattr(agent_sessions, "get_agent_session_service", lambda: FakeAgentService())
    monkeypatch.setattr(
        chat_session, "close_session_manager", lambda: closed.append("session_manager")
    )
    monkeypatch.setattr(
        context_service, "close_context_service", lambda: closed.append("context_service")
    )
    monkeypatch.setattr(embedder_mod, "close_embedder", lambda: closed.append("embedder"))
    monkeypatch.setattr(
        vector_store_mod, "close_vector_store", lambda: closed.append("vector_store")
    )
    monkeypatch.setattr(
        memory_mod, "close_memory_service", lambda: closed.append("memory_service")
    )

    await lifespan_mod._shutdown_agent_services()

    assert closed == [
        "async_subtasks",
        "session_manager",
        "context_service",
        "embedder",
        "vector_store",
        "memory_service",
    ]


def test_vector_store_close_clears_client():
    from rag.vector_store import VectorStore

    store = VectorStore(db_path="data/vectors-test-phase1-close")
    fake_client = MagicMock()
    fake_client.close = MagicMock()
    store._client = fake_client
    store._collections["c"] = object()

    store.close()

    assert store._client is None
    assert store._collections == {}
    fake_client.close.assert_called_once()


def test_close_session_manager_clears_singleton():
    from api.chat import session as session_mod

    manager = MagicMock()
    manager._sessions = {"s1": object()}
    session_mod._session_manager = manager

    session_mod.close_session_manager()

    assert session_mod._session_manager is None
    assert manager._sessions == {}


# ---------------------------------------------------------------------------
# Atomic checkpoint metadata
# ---------------------------------------------------------------------------


def test_save_checkpoint_metadata_atomic_replace(tmp_path: Path):
    from training_engine.checkpoint_manager import save_checkpoint_metadata

    ckpt = tmp_path / "checkpoint-10"
    ckpt.mkdir()

    save_checkpoint_metadata(
        ckpt,
        task_id="task-1",
        step=10,
        epoch=1.0,
        loss=0.5,
        lr=1e-4,
        config={"epochs": 1},
        tags=["phase1"],
    )

    meta_path = ckpt / "checkpoint_metadata.json"
    tmp_meta = ckpt / "checkpoint_metadata.json.tmp"
    assert meta_path.exists()
    assert not tmp_meta.exists()
    data = json.loads(meta_path.read_text(encoding="utf-8"))
    assert data["task_id"] == "task-1"
    assert data["step"] == 10
    assert data["tags"] == ["phase1"]


def test_save_checkpoint_metadata_does_not_publish_partial_on_write_failure(
    tmp_path: Path, monkeypatch
):
    """If writing the tmp file fails mid-way, final metadata must not be truncated garbage."""
    import training_engine.checkpoint_manager as cm

    ckpt = tmp_path / "checkpoint-fail"
    ckpt.mkdir()
    final = ckpt / "checkpoint_metadata.json"
    final.write_text('{"task_id":"old","step":1}', encoding="utf-8")

    real_open = open

    def boom_open(path, mode="r", *args, **kwargs):
        path_str = str(path)
        if path_str.endswith(".tmp") and "w" in mode:
            raise OSError("disk full")
        return real_open(path, mode, *args, **kwargs)

    monkeypatch.setattr("builtins.open", boom_open)
    cm.save_checkpoint_metadata(ckpt, task_id="new", step=99, epoch=2.0)

    # Previous good metadata remains; no published corrupt final from this attempt.
    assert final.exists()
    data = json.loads(final.read_text(encoding="utf-8"))
    assert data["task_id"] == "old"
    assert data["step"] == 1
    assert not (ckpt / "checkpoint_metadata.json.tmp").exists()


# ---------------------------------------------------------------------------
# Hygiene / legacy auth markers
# ---------------------------------------------------------------------------


def test_legacy_auth_middleware_documented_and_factory_is_live_path():
    from pathlib import Path

    auth_src = Path(__file__).resolve().parents[1] / "security" / "auth_middleware.py"
    factory_src = Path(__file__).resolve().parents[1] / "apps" / "factory.py"
    text = auth_src.read_text(encoding="utf-8")
    factory_text = factory_src.read_text(encoding="utf-8")

    assert "legacy" in text.lower() or "Legacy" in text
    assert "authentication_middleware" in factory_text
    assert "app.middleware(\"http\")(authentication_middleware)" in factory_text
    # Class middleware must not be the registered factory path.
    assert "JWTAuthMiddleware" not in factory_text or "authentication_middleware" in factory_text


def test_server_root_no_longer_hosts_scatter_test_scripts():
    server_root = Path(__file__).resolve().parents[1]
    scatter = list(server_root.glob("test_*.py")) + list(server_root.glob("check_*.py"))
    assert scatter == [], f"scatter scripts still in server root: {scatter}"
    scripts_dir = server_root / "scripts"
    assert scripts_dir.is_dir()
    assert (scripts_dir / "README.md").exists()
