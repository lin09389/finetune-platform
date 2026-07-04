from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx
import main as main_module
import pytest
from fastapi.testclient import TestClient
from main import app
from openai import AsyncOpenAI

from api.inference.backends.base import GenerationConfig, GenerationResult
from api.inference.backends.ollama_resilient import OllamaResilientBackend

client = TestClient(app)

pytestmark = pytest.mark.usefixtures("inference_in_process")


class FakeBackend:
    def __init__(self) -> None:
        self.model_name = None
        self.chat_calls = []
        self.stream_calls = []
        self.stream_error: Exception | None = None
        self.chat_error: Exception | None = None
        self.result = GenerationResult(
            text="Hello from the unified runtime",
            tokens_generated=6,
            prompt_tokens=4,
            total_tokens=10,
            latency_ms=12.5,
            model="mock-model",
            finish_reason="stop",
        )

    async def chat(self, messages, config):
        self.chat_calls.append((messages, config))
        if self.chat_error:
            raise self.chat_error
        return self.result

    async def chat_stream(self, messages, config):
        self.stream_calls.append((messages, config))
        yield "Hello"
        if self.stream_error:
            raise self.stream_error
        yield " runtime"

    async def count_tokens(self, text: str) -> int:
        return max(len(text) // 4, 1) if text else 0


class FakeScheduler:
    def __init__(self, backend: FakeBackend) -> None:
        self.backend = backend
        self.default_backend = "huggingface"
        self.available = True
        self.acquire_error: Exception | None = None
        self.acquired = []
        self.released = []

    def get_stats(self):
        return {"default_backend": self.default_backend}

    async def is_backend_available(self, backend_name):
        return self.available

    def resolve_model_path(self, model_name, backend_name):
        return f"/models/{backend_name}/{model_name}"

    async def acquire_model(self, model_name, model_path, backend_name, **kwargs):
        self.acquired.append((model_name, model_path, backend_name, kwargs))
        if self.acquire_error:
            raise self.acquire_error
        return SimpleNamespace(name=model_name)

    async def get_backend(self, backend_name):
        return self.backend

    async def release_model(self, model_name):
        self.released.append(model_name)
        return True


class FakeOllamaResponse:
    status = 200

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False

    async def json(self):
        return {
            "message": {"content": "ok"},
            "eval_count": 1,
            "prompt_eval_count": 2,
        }


class FakeOllamaSession:
    def __init__(self) -> None:
        self.payload = None

    def post(self, url, json):
        self.payload = json
        return FakeOllamaResponse()


@pytest.fixture
def runtime():
    backend = FakeBackend()
    scheduler = FakeScheduler(backend)
    catalog = [
        {
            "name": "mock-model",
            "backend": "huggingface",
            "path": "/models/mock-model",
        },
        {
            "name": "ollama-model:latest",
            "backend": "ollama",
        },
    ]
    with (
        patch("api.inference.openai_routes.get_scheduler", return_value=scheduler),
        patch("api.inference.openai_routes._list_runtime_models", AsyncMock(return_value=catalog)),
        patch("api.inference.openai_routes._active_runtime_selection", return_value={}),
        patch("api.deployment.resolve_deployed_model", return_value=None),
    ):
        yield backend, scheduler, catalog


def _events(response) -> list[str]:
    return [line.removeprefix("data: ") for line in response.text.splitlines() if line.startswith("data: ")]


def test_list_models_uses_all_runtime_backends(runtime):
    response = client.get("/v1/models")

    assert response.status_code == 200
    data = response.json()
    assert data["object"] == "list"
    assert data["data"] == [
        {
            "id": "mock-model",
            "object": "model",
            "created": data["data"][0]["created"],
            "owned_by": "finetune-platform",
            "backend": "huggingface",
            "canonical_id": "huggingface/mock-model",
            "source": "local",
        },
        {
            "id": "ollama-model:latest",
            "object": "model",
            "created": data["data"][1]["created"],
            "owned_by": "finetune-platform",
            "backend": "ollama",
            "canonical_id": "ollama/ollama-model:latest",
            "source": "local",
        },
    ]


def test_duplicate_model_names_are_listed_with_canonical_ids(runtime):
    _, _, catalog = runtime
    catalog.append({"name": "mock-model", "backend": "ollama"})

    response = client.get("/v1/models")

    assert response.status_code == 200
    ids = [model["id"] for model in response.json()["data"]]
    assert ids == [
        "huggingface/mock-model",
        "ollama-model:latest",
        "ollama/mock-model",
    ]


def test_chat_routes_by_catalog_and_preserves_zero_values_and_stop(runtime):
    backend, scheduler, _ = runtime
    payload = {
        "model": "mock-model",
        "messages": [
            {"role": "developer", "content": "Be concise."},
            {"role": "user", "content": "Hello"},
        ],
        "temperature": 0,
        "top_p": 0,
        "max_completion_tokens": 32,
        "stop": "END",
    }

    response = client.post("/v1/chat/completions", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["object"] == "chat.completion"
    assert data["choices"][0]["message"]["content"] == "Hello from the unified runtime"
    assert data["usage"] == {"prompt_tokens": 4, "completion_tokens": 6, "total_tokens": 10}
    assert data["id"].startswith("chatcmpl-")
    messages, config = backend.chat_calls[0]
    assert messages[0] == {"role": "system", "content": "Be concise."}
    assert config.temperature == 0
    assert config.top_p == 0
    assert config.max_tokens == 32
    assert config.stop_sequences == ["END"]
    assert scheduler.acquired[0][:3] == (
        "mock-model",
        "/models/mock-model",
        "huggingface",
    )
    assert scheduler.released == ["mock-model"]


def test_sync_backend_failure_is_an_openai_error_and_releases_lease(runtime):
    backend, scheduler, _ = runtime
    backend.result = GenerationResult(
        text="",
        tokens_generated=0,
        model="mock-model",
        finish_reason="error",
        metadata={"error": "GPU out of memory"},
    )

    response = client.post(
        "/v1/chat/completions",
        json={"model": "mock-model", "messages": [{"role": "user", "content": "Hello"}]},
    )

    assert response.status_code == 502
    assert response.json()["error"]["code"] == "inference_error"
    assert scheduler.released == ["mock-model"]


def test_sync_backend_exception_is_an_openai_error_and_releases_lease(runtime):
    backend, scheduler, _ = runtime
    backend.chat_error = RuntimeError("CUDA failure")

    response = client.post(
        "/v1/chat/completions",
        json={"model": "mock-model", "messages": [{"role": "user", "content": "Hello"}]},
    )

    assert response.status_code == 502
    assert response.json()["error"]["code"] == "inference_error"
    assert scheduler.released == ["mock-model"]


def test_stream_has_stable_id_finish_chunk_usage_and_done(runtime):
    backend, scheduler, _ = runtime
    response = client.post(
        "/v1/chat/completions",
        json={
            "model": "ollama/ollama-model:latest",
            "messages": [{"role": "user", "content": "Hello"}],
            "stream": True,
            "stream_options": {"include_usage": True},
        },
    )

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-cache"
    assert response.headers["x-accel-buffering"] == "no"
    events = _events(response)
    chunks = [json.loads(event) for event in events[:-1]]
    assert events[-1] == "[DONE]"
    assert len({chunk["id"] for chunk in chunks}) == 1
    assert chunks[0]["choices"][0]["delta"] == {"role": "assistant"}
    assert chunks[-2]["choices"][0]["finish_reason"] == "stop"
    assert chunks[-1]["choices"] == []
    assert chunks[-1]["usage"]["total_tokens"] > 0
    _, config = backend.stream_calls[0]
    assert config.stream is True
    assert scheduler.released == ["ollama-model:latest"]


def test_stream_failure_emits_error_without_successful_done(runtime):
    backend, scheduler, _ = runtime
    backend.stream_error = RuntimeError("Ollama disconnected")

    response = client.post(
        "/v1/chat/completions",
        json={
            "model": "mock-model",
            "messages": [{"role": "user", "content": "Hello"}],
            "stream": True,
        },
    )

    events = _events(response)
    assert response.status_code == 200
    assert "[DONE]" not in events
    assert json.loads(events[-1])["error"]["code"] == "inference_error"
    assert scheduler.released == ["mock-model"]


@pytest.mark.parametrize(
    ("extra_payload", "param", "code"),
    [
        ({"tools": [{"type": "function", "function": {"name": "x"}}]}, "tools", "unsupported_tools"),
        ({"presence_penalty": 1}, "presence_penalty", "unsupported_penalty"),
        ({"n": 2}, "n", "unsupported_parameter"),
        ({"response_format": {"type": "json_object"}}, "response_format", "unsupported_response_format"),
        ({"parallel_tool_calls": False}, "parallel_tool_calls", "unsupported_tools"),
        ({"stream_options": {"include_usage": True}}, "stream_options", "invalid_stream_options"),
    ],
)
def test_unsupported_features_fail_explicitly(runtime, extra_payload, param, code):
    payload = {
        "model": "mock-model",
        "messages": [{"role": "user", "content": "Hello"}],
        **extra_payload,
    }

    response = client.post("/v1/chat/completions", json=payload)

    assert response.status_code == 400
    assert response.json()["error"]["param"] == param
    assert response.json()["error"]["code"] == code


def test_unknown_model_is_not_replaced_with_fake_default(runtime):
    response = client.post(
        "/v1/chat/completions",
        json={"model": "missing", "messages": [{"role": "user", "content": "Hello"}]},
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "model_not_found"


def test_unavailable_backend_fails_before_stream_headers(runtime):
    _, scheduler, _ = runtime
    scheduler.available = False

    response = client.post(
        "/v1/chat/completions",
        json={
            "model": "ollama-model:latest",
            "messages": [{"role": "user", "content": "Hello"}],
            "stream": True,
        },
    )

    assert response.status_code == 503
    assert response.headers["content-type"].startswith("application/json")
    assert response.json()["error"]["code"] == "backend_unavailable"


def test_model_load_exception_fails_before_stream_headers(runtime):
    _, scheduler, _ = runtime
    scheduler.acquire_error = RuntimeError("loader crashed")

    response = client.post(
        "/v1/chat/completions",
        json={
            "model": "mock-model",
            "messages": [{"role": "user", "content": "Hello"}],
            "stream": True,
        },
    )

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "model_load_failed"


def test_active_runtime_selection_resolves_duplicate_raw_model(runtime):
    backend, scheduler, catalog = runtime
    catalog.append({"name": "mock-model", "backend": "ollama"})

    with patch(
        "api.inference.openai_routes._active_runtime_selection",
        return_value={"backend": "ollama", "model_id": "mock-model"},
    ):
        response = client.post(
            "/v1/chat/completions",
            json={"model": "mock-model", "messages": [{"role": "user", "content": "Hello"}]},
        )

    assert response.status_code == 200
    assert scheduler.acquired[0][2] == "ollama"
    assert backend.model_name == "mock-model"


def test_conflicting_canonical_model_and_header_is_rejected(runtime):
    response = client.post(
        "/v1/chat/completions",
        headers={"X-Backend": "ollama"},
        json={
            "model": "huggingface/mock-model",
            "messages": [{"role": "user", "content": "Hello"}],
        },
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "backend_conflict"


def test_validation_errors_use_openai_error_envelope(runtime):
    response = client.post(
        "/v1/chat/completions",
        json={"model": "mock-model", "messages": [], "temperature": 3},
    )

    assert response.status_code == 400
    assert response.json()["error"]["type"] == "invalid_request_error"


def test_cors_preflight_allows_backend_selection_header(runtime):
    response = client.options(
        "/v1/chat/completions",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "x-backend,content-type",
        },
    )

    assert response.status_code == 200
    assert "x-backend" in response.headers["access-control-allow-headers"].lower()


def test_authentication_failure_uses_openai_error_envelope(runtime):
    with patch.object(main_module.settings, "enable_auth", True):
        response = client.get("/v1/models")

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    assert response.json()["error"] == {
        "message": "Missing bearer token",
        "type": "authentication_error",
        "param": None,
        "code": "invalid_api_key",
    }


@pytest.mark.asyncio
async def test_ollama_sync_chat_preserves_unified_generation_config():
    backend = OllamaResilientBackend({"model_name": "mock-model"})
    backend._is_loaded = True
    session = FakeOllamaSession()
    backend._get_session = AsyncMock(return_value=session)
    config = GenerationConfig(
        max_tokens=23,
        temperature=0,
        top_p=0,
        repetition_penalty=1.2,
        stop_sequences=["END"],
    )

    result = await backend.chat([{"role": "user", "content": "Hello"}], config)

    assert result.text == "ok"
    assert session.payload["options"]["num_predict"] == 23
    assert session.payload["options"]["temperature"] == 0
    assert session.payload["options"]["top_p"] == 0
    assert session.payload["options"]["repeat_penalty"] == 1.2
    assert session.payload["options"]["stop"] == ["END"]


@pytest.mark.asyncio
async def test_official_openai_sdk_can_list_complete_and_stream(runtime):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http_client:
        sdk = AsyncOpenAI(
            api_key="local-test-token",
            base_url="http://test/v1",
            http_client=http_client,
        )

        models = await sdk.models.list()
        completion = await sdk.chat.completions.create(
            model="mock-model",
            messages=[{"role": "user", "content": "Hello"}],
            temperature=0,
        )
        stream = await sdk.chat.completions.create(
            model="mock-model",
            messages=[{"role": "user", "content": "Hello"}],
            stream=True,
        )
        streamed_chunks = [chunk.choices[0].delta.content or "" async for chunk in stream]
        streamed_text = "".join(streamed_chunks)

    assert [model.id for model in models.data] == ["mock-model", "ollama-model:latest"]
    assert completion.choices[0].message.content == "Hello from the unified runtime"
    assert streamed_text == "Hello runtime"
