"""Tests for the inference facade delegating through the gateway."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.inference import facade


class _FakeGateway:
    """Lightweight stand-in for the active inference gateway."""

    def __init__(self):
        self.calls = []

    async def generate_stream(self, request):
        self.calls.append(("generate_stream", request))
        return "data: ok\n\n"

    async def chat(self, request):
        self.calls.append(("chat", request))
        return {"chat": "ok"}

    async def chat_stream(self, request):
        self.calls.append(("chat_stream", request))
        return "data: ok\n\n"

    async def get_cache_status(self):
        self.calls.append(("get_cache_status", None))
        return {"cache": "ok"}

    async def clear_cache(self):
        self.calls.append(("clear_cache", None))
        return {"cleared": True}

    async def get_performance_stats(self, model_id=None):
        self.calls.append(("get_performance_stats", model_id))
        return {"stats": model_id}

    async def get_performance_recommendations(self):
        self.calls.append(("get_performance_recommendations", None))
        return {"recommendations": []}

    async def clear_performance_history(self):
        self.calls.append(("clear_performance_history", None))
        return {"cleared": True}

    async def get_performance_prometheus(self):
        self.calls.append(("get_performance_prometheus", None))
        return "metrics ok"

    async def get_metrics_alias(self):
        self.calls.append(("get_metrics_alias", None))
        return {"metrics": "ok"}


@pytest.fixture
def gateway_app(monkeypatch):
    """Return a FastAPI app with the inference facade wired to a fake gateway."""
    fake = _FakeGateway()
    monkeypatch.setattr("api.inference.facade.get_inference_gateway", lambda: fake)
    app = FastAPI()
    app.include_router(facade.router, prefix="/inference")
    return app, fake


def test_facade_generate_stream_delegates_to_gateway(gateway_app):
    app, fake = gateway_app
    client = TestClient(app)
    response = client.post("/inference/generate/stream", json={"prompt": "hello", "model": "m1"})
    assert response.status_code == 200
    assert fake.calls[0][0] == "generate_stream"


def test_facade_chat_delegates_to_gateway(gateway_app):
    app, fake = gateway_app
    client = TestClient(app)
    response = client.post("/inference/chat", json={"messages": [{"role": "user", "content": "hi"}], "model": "m1"})
    assert response.status_code == 200
    assert response.json() == {"chat": "ok"}
    assert fake.calls[0][0] == "chat"


def test_facade_chat_stream_delegates_to_gateway(gateway_app):
    app, fake = gateway_app
    client = TestClient(app)
    response = client.post("/inference/chat/stream", json={"messages": [{"role": "user", "content": "hi"}], "model": "m1"})
    assert response.status_code == 200
    assert fake.calls[0][0] == "chat_stream"


def test_facade_cache_status_delegates_to_gateway(gateway_app):
    app, fake = gateway_app
    client = TestClient(app)
    response = client.get("/inference/cache/status")
    assert response.status_code == 200
    assert response.json() == {"cache": "ok"}
    assert fake.calls[0][0] == "get_cache_status"


def test_facade_clear_cache_delegates_to_gateway(gateway_app):
    app, fake = gateway_app
    client = TestClient(app)
    response = client.post("/inference/cache/clear")
    assert response.status_code == 200
    assert fake.calls[0][0] == "clear_cache"


def test_facade_performance_stats_delegates_to_gateway(gateway_app):
    app, fake = gateway_app
    client = TestClient(app)
    response = client.get("/inference/performance?model_id=m1")
    assert response.status_code == 200
    assert response.json() == {"stats": "m1"}
    assert fake.calls[0] == ("get_performance_stats", "m1")


def test_facade_performance_recommendations_delegates_to_gateway(gateway_app):
    app, fake = gateway_app
    client = TestClient(app)
    response = client.get("/inference/performance/recommendations")
    assert response.status_code == 200
    assert fake.calls[0][0] == "get_performance_recommendations"


def test_facade_clear_performance_history_delegates_to_gateway(gateway_app):
    app, fake = gateway_app
    client = TestClient(app)
    response = client.post("/inference/performance/clear")
    assert response.status_code == 200
    assert fake.calls[0][0] == "clear_performance_history"


def test_facade_performance_prometheus_delegates_to_gateway(gateway_app):
    app, fake = gateway_app
    client = TestClient(app)
    response = client.get("/inference/performance/prometheus")
    assert response.status_code == 200
    assert fake.calls[0][0] == "get_performance_prometheus"


def test_facade_metrics_alias_delegates_to_gateway(gateway_app):
    app, fake = gateway_app
    client = TestClient(app)
    response = client.get("/inference/metrics")
    assert response.status_code == 200
    assert fake.calls[0][0] == "get_metrics_alias"


@pytest.mark.asyncio
async def test_service_gateway_forwards_to_inference_server(monkeypatch):
    """ServiceInferenceGateway must forward facade endpoints to the 8020 service."""
    from core.inference_gateway import ServiceInferenceGateway

    fake_response = MagicMock()
    fake_response.status_code = 200
    fake_response.headers = {"content-type": "application/json"}
    fake_response.content = b'{"forwarded": true}'
    fake_response.json.return_value = {"forwarded": True}
    fake_response.aiter_raw = AsyncMock()

    async def _fake_request(self, method, path, **kwargs):
        _fake_request.calls.append((method, path, kwargs))
        return fake_response

    _fake_request.calls = []

    async def _fake_open_stream(self, method, path, **kwargs):
        _fake_open_stream.calls.append((method, path, kwargs))
        return fake_response

    _fake_open_stream.calls = []

    async def _fake_get_json(self, path, *, params=None):
        _fake_get_json.calls.append((path, params))
        return {"forwarded": True}

    _fake_get_json.calls = []

    monkeypatch.setattr("inference_provider.client.InferenceServiceClient.request", _fake_request)
    monkeypatch.setattr("inference_provider.client.InferenceServiceClient.open_stream", _fake_open_stream)
    monkeypatch.setattr("inference_provider.client.InferenceServiceClient.get_json", _fake_get_json)

    gateway = ServiceInferenceGateway()

    request = MagicMock()
    request.model_dump.return_value = {"prompt": "hello"}
    await gateway.chat(request)
    assert _fake_request.calls[-1][:2] == ("POST", "/inference/chat")

    await gateway.get_cache_status()
    assert _fake_get_json.calls[-1][0] == "/inference/cache/status"
