from __future__ import annotations

import importlib
import json
import os
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse
from fastapi.testclient import TestClient
from inference_provider.client import (
    InferenceServiceClient,
    InferenceServiceTimeout,
    InferenceServiceUnavailable,
    RemoteResponse,
)

from core.config import Settings


def _service_headers(key: str = "test-internal-key") -> dict[str, str]:
    return {"Authorization": f"Bearer {key}"}


def test_native_inference_service_requires_internal_authentication(monkeypatch):
    module = importlib.import_module("inference_server.app")
    monkeypatch.setattr(module.settings, "inference_internal_api_key", "test-internal-key")
    client = TestClient(module.app)

    assert client.get("/health").status_code == 200
    unauthorized = client.get("/internal/capabilities")
    assert unauthorized.status_code == 401
    assert unauthorized.json()["error"]["code"] == "invalid_internal_api_key"


def test_native_inference_capability_contract(monkeypatch):
    module = importlib.import_module("inference_server.app")
    monkeypatch.setattr(module.settings, "inference_internal_api_key", "test-internal-key")

    async def fake_backends():
        return {"current": "ollama", "backends": [{"name": "ollama", "available": True}]}

    async def fake_models():
        return SimpleNamespace(model_dump=lambda: {"data": [{"id": "qwen"}]})

    monkeypatch.setattr("api.inference.routes.list_backends", fake_backends)
    monkeypatch.setattr("api.inference.openai_routes.list_models", fake_models)
    response = TestClient(module.app).get("/internal/capabilities", headers=_service_headers())

    assert response.status_code == 200
    payload = response.json()
    assert payload["schema_version"] == "inference.capabilities.v1"
    assert payload["api"]["streaming"] is True
    assert payload["features"]["tool_calling"] is False
    assert payload["models"] == [{"id": "qwen"}]


@pytest.mark.asyncio
async def test_internal_client_overrides_user_authorization_and_preserves_streaming():
    upstream = FastAPI()

    @upstream.post("/v1/chat/completions")
    async def completion(request: Request):
        assert request.headers["authorization"] == "Bearer internal-secret"

        async def chunks():
            yield b'data: {"choices":[{"delta":{"content":"hi"}}]}\n\n'
            yield b"data: [DONE]\n\n"

        return StreamingResponse(chunks(), media_type="text/event-stream")

    settings = Settings(
        inference_execution_mode="service",
        inference_service_url="http://inference",
        inference_internal_api_key="internal-secret",
        inference_service_max_retries=0,
    )
    client = InferenceServiceClient(settings, transport=httpx.ASGITransport(app=upstream))
    assert client._client._trust_env is False
    response = await client.open_stream(
        "POST",
        "/v1/chat/completions",
        content=b"{}",
        headers={"Authorization": "Bearer user-token", "Content-Type": "application/json"},
    )
    body = b"".join([chunk async for chunk in response.aiter_raw()])
    await response.aclose()
    await client.aclose()

    assert b'"content":"hi"' in body
    assert body.endswith(b"data: [DONE]\n\n")


@pytest.mark.asyncio
async def test_control_proxy_returns_stable_unavailable_error(monkeypatch):
    proxy = importlib.import_module("api.inference_proxy")
    attempts = 0

    def unavailable(_request: httpx.Request):
        nonlocal attempts
        attempts += 1
        raise httpx.ConnectError("connection refused")

    settings = Settings(
        inference_execution_mode="service",
        inference_service_url="http://inference",
        inference_service_max_retries=1,
        inference_service_retry_delay_seconds=0,
    )
    client = InferenceServiceClient(settings, transport=httpx.MockTransport(unavailable))
    monkeypatch.setattr(proxy, "get_inference_service_client", lambda: client)
    app = FastAPI()
    app.include_router(proxy.router)

    response = TestClient(app).post(
        "/v1/chat/completions",
        json={"model": "qwen", "messages": [{"role": "user", "content": "hi"}]},
    )
    await client.aclose()

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "inference_service_unavailable"
    assert attempts == 2


def test_control_proxy_preserves_sse_frames(monkeypatch):
    proxy = importlib.import_module("api.inference_proxy")
    upstream = FastAPI()

    @upstream.post("/v1/chat/completions")
    async def stream_completion():
        async def chunks():
            yield b'data: {"choices":[{"delta":{"content":"token"}}]}\n\n'
            yield b"data: [DONE]\n\n"

        return StreamingResponse(chunks(), media_type="text/event-stream")

    settings = Settings(
        inference_execution_mode="service",
        inference_service_url="http://inference",
        inference_service_max_retries=0,
    )
    service_client = InferenceServiceClient(settings, transport=httpx.ASGITransport(app=upstream))
    monkeypatch.setattr(proxy, "get_inference_service_client", lambda: service_client)
    app = FastAPI()
    app.include_router(proxy.router)

    response = TestClient(app).post(
        "/v1/chat/completions",
        json={"model": "qwen", "messages": [{"role": "user", "content": "hi"}], "stream": True},
    )

    assert response.status_code == 200
    assert '"content":"token"' in response.text
    assert response.text.endswith("data: [DONE]\n\n")


def test_control_proxy_uses_opt_in_cloud_fallback(monkeypatch):
    proxy = importlib.import_module("api.inference_proxy")

    class UnavailableClient:
        async def request(self, *_args, **_kwargs):
            raise InferenceServiceUnavailable("native service down")

    fallback = {
        "id": "chatcmpl-fallback",
        "object": "chat.completion",
        "choices": [{"message": {"role": "assistant", "content": "cloud answer"}}],
    }
    monkeypatch.setattr(proxy, "get_inference_service_client", lambda: UnavailableClient())
    monkeypatch.setattr(proxy, "cloud_fallback_response", AsyncMock(return_value=fallback))
    app = FastAPI()
    app.include_router(proxy.router)

    response = TestClient(app).post(
        "/v1/chat/completions",
        json={"model": "qwen", "messages": [{"role": "user", "content": "hi"}]},
    )

    assert response.status_code == 200
    assert response.json()["choices"][0]["message"]["content"] == "cloud answer"


def test_control_proxy_does_not_hide_invalid_requests_with_fallback(monkeypatch):
    proxy = importlib.import_module("api.inference_proxy")

    class InvalidRequestClient:
        async def request(self, *_args, **_kwargs):
            body = {"error": {"code": "model_not_found", "message": "missing"}}
            return RemoteResponse(404, {"content-type": "application/json"}, json_bytes(body))

    fallback = AsyncMock(return_value={"unexpected": True})
    monkeypatch.setattr(proxy, "get_inference_service_client", lambda: InvalidRequestClient())
    monkeypatch.setattr(proxy, "cloud_fallback_response", fallback)
    app = FastAPI()
    app.include_router(proxy.router)

    response = TestClient(app).post(
        "/v1/chat/completions",
        json={"model": "missing", "messages": [{"role": "user", "content": "hi"}]},
    )

    assert response.status_code == 404
    fallback.assert_not_awaited()


def test_control_proxy_reports_read_timeout(monkeypatch):
    proxy = importlib.import_module("api.inference_proxy")

    class TimeoutClient:
        async def request(self, *_args, **_kwargs):
            raise InferenceServiceTimeout("generation timed out")

    monkeypatch.setattr(proxy, "get_inference_service_client", lambda: TimeoutClient())
    monkeypatch.setattr(proxy, "cloud_fallback_response", AsyncMock(return_value=None))
    app = FastAPI()
    app.include_router(proxy.router)
    response = TestClient(app).post(
        "/v1/chat/completions",
        json={"model": "qwen", "messages": [{"role": "user", "content": "hi"}]},
    )

    assert response.status_code == 504
    assert response.json()["error"]["code"] == "inference_timeout"


def test_public_proxy_strips_internal_model_path_headers(monkeypatch):
    proxy = importlib.import_module("api.inference_proxy")
    captured = {}

    class CapturingClient:
        async def request(self, *_args, **kwargs):
            captured.update(kwargs.get("headers") or {})
            body = {"choices": [{"message": {"content": "ok"}}]}
            return RemoteResponse(200, {"content-type": "application/json"}, json_bytes(body))

    monkeypatch.setattr(proxy, "get_inference_service_client", lambda: CapturingClient())
    app = FastAPI()
    app.include_router(proxy.router)
    response = TestClient(app).post(
        "/v1/chat/completions",
        headers={"X-Model-Path": "C:/outside/model", "X-LoRA-Adapter": "C:/outside/adapter"},
        json={"model": "qwen", "messages": [{"role": "user", "content": "hi"}]},
    )

    assert response.status_code == 200
    assert "x-model-path" not in captured
    assert "x-lora-adapter" not in captured


def test_control_profile_does_not_import_native_inference_runtime():
    script = (
        "import sys; import apps.combined; "
        "forbidden=[m for m in sys.modules if m in {'api.inference.routes','api.inference.scheduler'} "
        "or m.startswith('core.inference')]; "
        "assert not forbidden, forbidden"
    )
    env = dict(os.environ)
    env["INFERENCE_EXECUTION_MODE"] = "service"
    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=os.path.dirname(os.path.dirname(__file__)),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr


def test_agent_ollama_provider_routes_through_local_openai_service(monkeypatch):
    adapter = importlib.import_module("agent_session.model_adapter")
    captured = {}

    monkeypatch.setattr(adapter.settings, "inference_execution_mode", "service")
    monkeypatch.setattr(adapter.settings, "inference_service_url", "http://127.0.0.1:8020")
    monkeypatch.setattr(adapter.settings, "inference_internal_api_key", "internal-key")
    monkeypatch.setattr(
        "langchain.chat_models.init_chat_model",
        lambda **kwargs: captured.update(kwargs) or object(),
    )
    context = SimpleNamespace(provider="ollama", model="qwen3:8b", metadata={})

    adapter.get_chat_model(context)

    assert captured["model_provider"] == "openai"
    assert captured["model"] == "ollama/qwen3:8b"
    assert captured["base_url"] == "http://127.0.0.1:8020/v1"
    assert captured["api_key"] == "internal-key"


@pytest.mark.asyncio
async def test_evaluation_uses_remote_provider_in_service_mode(monkeypatch):
    evaluation = importlib.import_module("api.evaluation")
    requests = []

    class FakeClient:
        async def request(self, method, path, **kwargs):
            requests.append((method, path, kwargs))
            body = {
                "choices": [{"message": {"role": "assistant", "content": f"answer-{len(requests)}"}}]
            }
            return RemoteResponse(200, {"content-type": "application/json"}, json_bytes(body))

    settings = Settings(inference_execution_mode="service")
    monkeypatch.setattr(evaluation, "get_settings", lambda: settings)
    monkeypatch.setattr("inference_provider.client.get_inference_service_client", lambda: FakeClient())

    responses = await evaluation.run_model_inference_batch(
        model="qwen",
        prompts=["one", "two"],
        backend="ollama",
        max_tokens=32,
        temperature=0,
        lora_adapter="adapters/demo",
    )

    assert responses == ["answer-1", "answer-2"]
    assert all(item[1] == "/v1/chat/completions" for item in requests)
    payloads = [json.loads(item[2]["content"]) for item in requests]
    assert all(payload["model"] == "ollama/qwen" for payload in payloads)
    assert all(item[2]["headers"]["X-LoRA-Adapter"] == "adapters/demo" for item in requests)


def json_bytes(value) -> bytes:
    import json

    return json.dumps(value).encode()
