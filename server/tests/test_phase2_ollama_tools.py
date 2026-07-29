"""Phase 2: Ollama tools passthrough on local OpenAI-compatible Chat Completions."""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from agent_session.model_capabilities import (
    agent_model_tool_calling_status,
    build_inference_tool_calling_features,
    local_agent_tool_calling_status,
    local_endpoint_backend_tool_calling_status,
)
from fastapi.testclient import TestClient
from main import app

from api.inference.backends.base import GenerationResult
from api.inference.openai_tool_bridge import (
    backend_allows_tools,
    build_ollama_chat_payload,
    ollama_tool_calls_to_openai,
    openai_messages_to_ollama,
    request_requires_tools,
)

client = TestClient(app)
pytestmark = pytest.mark.usefixtures("inference_in_process")


class FakeBackend:
    def __init__(self, backend_name: str = "huggingface") -> None:
        self.backend_name = backend_name
        self.model_name = None
        self.chat_calls: list[tuple] = []
        self.result = GenerationResult(
            text="Hello from the unified runtime",
            tokens_generated=6,
            prompt_tokens=4,
            total_tokens=10,
            latency_ms=12.5,
            model="mock-model",
            finish_reason="stop",
        )

    async def chat(self, messages, config, *, tools=None, tool_choice=None):
        self.chat_calls.append((messages, config, tools, tool_choice))
        return self.result

    async def chat_stream(self, messages, config):
        yield "Hello"
        yield " runtime"

    async def count_tokens(self, text: str) -> int:
        return max(len(text) // 4, 1) if text else 0


class FakeScheduler:
    def __init__(self, backend: FakeBackend, default_backend: str = "huggingface") -> None:
        self.backend = backend
        self.default_backend = default_backend
        self.available = True
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
        return SimpleNamespace(name=model_name)

    async def get_backend(self, backend_name):
        self.backend.backend_name = backend_name
        return self.backend

    async def release_model(self, model_name):
        self.released.append(model_name)
        return True


@pytest.fixture
def runtime_hf():
    backend = FakeBackend("huggingface")
    scheduler = FakeScheduler(backend, default_backend="huggingface")
    catalog = [
        {"name": "mock-model", "backend": "huggingface", "path": "/models/mock-model"},
        {"name": "ollama-model:latest", "backend": "ollama"},
    ]
    with (
        patch("api.inference.openai_routes.get_scheduler", return_value=scheduler),
        patch("api.inference.openai_routes._list_runtime_models", AsyncMock(return_value=catalog)),
        patch("api.inference.openai_routes._active_runtime_selection", return_value={}),
        patch("api.deployment.resolve_deployed_model", return_value=None),
    ):
        yield backend, scheduler, catalog


@pytest.fixture
def runtime_ollama():
    backend = FakeBackend("ollama")
    backend.result = GenerationResult(
        text="",
        tokens_generated=3,
        prompt_tokens=2,
        total_tokens=5,
        model="ollama-model:latest",
        finish_reason="tool_calls",
        metadata={
            "tool_calls": [
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {"name": "ls", "arguments": json.dumps({"path": "/workspace"})},
                }
            ]
        },
    )
    scheduler = FakeScheduler(backend, default_backend="ollama")
    catalog = [
        {"name": "mock-model", "backend": "huggingface", "path": "/models/mock-model"},
        {"name": "ollama-model:latest", "backend": "ollama"},
    ]
    with (
        patch("api.inference.openai_routes.get_scheduler", return_value=scheduler),
        patch("api.inference.openai_routes._list_runtime_models", AsyncMock(return_value=catalog)),
        patch("api.inference.openai_routes._active_runtime_selection", return_value={}),
        patch("api.deployment.resolve_deployed_model", return_value=None),
    ):
        yield backend, scheduler, catalog


def _tools_payload():
    return [
        {
            "type": "function",
            "function": {
                "name": "ls",
                "description": "list dir",
                "parameters": {
                    "type": "object",
                    "properties": {"path": {"type": "string"}},
                    "required": ["path"],
                },
            },
        }
    ]


def test_openai_message_content_blocks_normalize_to_string():
    from api.inference.openai_schemas import ChatCompletionMessage, ChatCompletionRequest

    msg = ChatCompletionMessage(
        role="system",
        content=[{"type": "text", "text": "hello "}, {"type": "text", "text": "world"}],
    )
    assert msg.content == "hello world"
    req = ChatCompletionRequest(
        model="ollama/qwen2.5:3b",
        messages=[
            ChatCompletionMessage(role="user", content=[{"type": "text", "text": "list files"}]),
        ],
        tools=[{"type": "function", "function": {"name": "ls", "parameters": {"type": "object"}}}],
        stream=False,
    )
    assert req.messages[0].content == "list files"


def test_bridge_request_requires_tools_and_backend_gate():
    assert backend_allows_tools("ollama") is True
    assert backend_allows_tools("huggingface") is False
    assert backend_allows_tools("llama-cpp") is False
    msgs = [SimpleNamespace(role="user", content="hi", tool_calls=None)]
    assert request_requires_tools(tools=_tools_payload(), tool_choice=None, messages=msgs) is True
    assert request_requires_tools(tools=None, tool_choice=None, messages=msgs) is False
    tool_msgs = [SimpleNamespace(role="tool", content="ok", tool_calls=None)]
    assert request_requires_tools(tools=None, tool_choice=None, messages=tool_msgs) is True


def test_bridge_openai_to_ollama_payload_includes_tools_and_history():
    messages = [
        SimpleNamespace(role="user", content="list", tool_calls=None, tool_call_id=None, name=None),
        SimpleNamespace(
            role="assistant",
            content="",
            tool_calls=[
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {"name": "ls", "arguments": '{"path":"/workspace"}'},
                }
            ],
            tool_call_id=None,
            name=None,
        ),
        SimpleNamespace(role="tool", content="a.py", tool_calls=None, tool_call_id="call_1", name="ls"),
    ]
    payload = build_ollama_chat_payload(
        model="qwen",
        messages=messages,
        tools=_tools_payload(),
        tool_choice="auto",
        stream=False,
    )
    assert payload["model"] == "qwen"
    assert payload["tools"][0]["function"]["name"] == "ls"
    assert payload["tool_choice"] == "auto"
    assert payload["messages"][1]["tool_calls"][0]["function"]["name"] == "ls"
    assert isinstance(payload["messages"][1]["tool_calls"][0]["function"]["arguments"], dict)
    assert payload["messages"][2]["role"] == "tool"
    assert payload["messages"][2]["content"] == "a.py"


def test_bridge_ollama_tool_calls_map_to_openai():
    mapped = ollama_tool_calls_to_openai(
        [{"function": {"name": "ls", "arguments": {"path": "/workspace"}}}]
    )
    assert mapped[0]["type"] == "function"
    assert mapped[0]["function"]["name"] == "ls"
    assert json.loads(mapped[0]["function"]["arguments"]) == {"path": "/workspace"}
    assert mapped[0]["id"]


def test_hf_rejects_tools_with_unsupported_tools(runtime_hf):
    response = client.post(
        "/v1/chat/completions",
        json={
            "model": "mock-model",
            "messages": [{"role": "user", "content": "hi"}],
            "tools": _tools_payload(),
        },
    )
    assert response.status_code == 400
    body = response.json()
    assert body["error"]["code"] == "unsupported_tools"
    assert body["error"]["param"] == "tools"
    assert "Ollama" in body["error"]["message"] or "不支持" in body["error"]["message"]


def test_llama_cpp_header_rejects_tools(runtime_hf):
    response = client.post(
        "/v1/chat/completions",
        headers={"x-backend": "llama-cpp"},
        json={
            "model": "mock-model",
            "messages": [{"role": "user", "content": "hi"}],
            "tools": _tools_payload(),
        },
    )
    # May 400 unsupported_tools or 503 if backend unavailable — tools must not succeed.
    assert response.status_code in {400, 503}
    if response.status_code == 400:
        assert response.json()["error"]["code"] == "unsupported_tools"


def test_ollama_accepts_tools_and_returns_openai_tool_calls(runtime_ollama):
    backend, scheduler, _ = runtime_ollama
    response = client.post(
        "/v1/chat/completions",
        json={
            "model": "ollama-model:latest",
            "messages": [{"role": "user", "content": "List /workspace with ls"}],
            "tools": _tools_payload(),
            "tool_choice": "auto",
            "stream": False,
        },
    )
    assert response.status_code == 200, response.text
    data = response.json()
    message = data["choices"][0]["message"]
    assert message["tool_calls"][0]["function"]["name"] == "ls"
    assert data["choices"][0]["finish_reason"] == "tool_calls"
    assert backend.chat_calls
    messages, config, tools, tool_choice = backend.chat_calls[0]
    assert tools and tools[0]["function"]["name"] == "ls"
    assert tool_choice == "auto"
    assert messages[0]["role"] == "user"
    assert scheduler.released == ["ollama-model:latest"]


def test_ollama_accepts_tool_role_history(runtime_ollama):
    backend, _, _ = runtime_ollama
    backend.result = GenerationResult(
        text="done",
        tokens_generated=1,
        prompt_tokens=1,
        total_tokens=2,
        model="ollama-model:latest",
        finish_reason="stop",
        metadata={},
    )
    response = client.post(
        "/v1/chat/completions",
        json={
            "model": "ollama-model:latest",
            "messages": [
                {"role": "user", "content": "list"},
                {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {
                            "id": "call_1",
                            "type": "function",
                            "function": {"name": "ls", "arguments": "{\"path\":\"/workspace\"}"},
                        }
                    ],
                },
                {"role": "tool", "tool_call_id": "call_1", "content": "a.py"},
            ],
            "tools": _tools_payload(),
        },
    )
    assert response.status_code == 200, response.text
    messages, _, tools, _ = backend.chat_calls[0]
    assert any(m.get("role") == "tool" for m in messages)
    assert any(m.get("tool_calls") for m in messages if m.get("role") == "assistant")
    assert tools


def test_ollama_stream_with_tools_rejected(runtime_ollama):
    response = client.post(
        "/v1/chat/completions",
        json={
            "model": "ollama-model:latest",
            "messages": [{"role": "user", "content": "hi"}],
            "tools": _tools_payload(),
            "stream": True,
        },
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "unsupported_stream_tools"


def test_capability_facts_ollama_endpoint_true_others_false():
    settings = SimpleNamespace(inference_execution_mode="service")
    assert local_endpoint_backend_tool_calling_status("ollama", settings)["supported"] is True
    assert local_endpoint_backend_tool_calling_status("huggingface", settings)["supported"] is False
    assert local_endpoint_backend_tool_calling_status("llama-cpp", settings)["supported"] is False
    features = build_inference_tool_calling_features(settings)
    assert features["tool_calling"] is True
    assert features["tool_calling_by_backend"]["ollama"] is True
    assert features["tool_calling_by_backend"]["huggingface"] is False

    ollama_service = local_agent_tool_calling_status("ollama", settings)
    assert ollama_service["supported"] is True
    assert ollama_service["via"] == "local_chat_completions_ollama"
    assert local_agent_tool_calling_status("local", settings)["supported"] is False
    assert agent_model_tool_calling_status("ollama", settings)["supported"] is True
    assert agent_model_tool_calling_status("local", settings)["supported"] is False


def test_ollama_service_chat_model_disables_streaming_for_tool_calling(monkeypatch):
    """Regression: tool-bound Agent path must not stream tools to /v1 (unsupported_stream_tools)."""
    import agent_session.model_adapter as adapter
    from agent_session.model_adapter import get_chat_model
    from langchain_core.messages import AIMessage, HumanMessage
    from langchain_core.outputs import ChatGeneration, ChatResult
    from langchain_openai import ChatOpenAI

    monkeypatch.setattr(adapter.settings, "inference_execution_mode", "service", raising=False)
    monkeypatch.setattr(adapter.settings, "inference_service_url", "http://127.0.0.1:8020", raising=False)
    monkeypatch.setattr(adapter.settings, "inference_internal_api_key", "internal-key", raising=False)

    model = get_chat_model(SimpleNamespace(provider="ollama", model="qwen3:8b", metadata={}))
    assert isinstance(model, ChatOpenAI)
    assert model.disable_streaming == "tool_calling"

    def ls(path: str) -> str:
        """List a directory."""
        return "ok"

    bound = model.bind_tools([ls])
    # Captures whether the underlying client would request stream=True.
    seen_stream_flags: list[bool | None] = []

    def fake_generate(self, messages, stop=None, run_manager=None, **kwargs):
        # ChatOpenAI non-stream path uses _generate; streaming uses _stream.
        seen_stream_flags.append(False)
        return ChatResult(
            generations=[
                ChatGeneration(
                    message=AIMessage(
                        content="",
                        tool_calls=[
                            {
                                "name": "ls",
                                "args": {"path": "/workspace"},
                                "id": "call_ns_1",
                                "type": "tool_call",
                            }
                        ],
                    )
                )
            ]
        )

    def fake_stream(self, messages, stop=None, run_manager=None, **kwargs):
        seen_stream_flags.append(True)
        raise AssertionError("tool_calling must not use streaming against local Ollama facade")

    monkeypatch.setattr(ChatOpenAI, "_generate", fake_generate)
    monkeypatch.setattr(ChatOpenAI, "_stream", fake_stream)

    # Even if caller asks to stream, disable_streaming='tool_calling' forces non-stream
    # when tools are bound (LangChain behavior).
    result = bound.invoke([HumanMessage(content="list /workspace with ls")])
    assert result.tool_calls
    assert seen_stream_flags == [False]
    assert True not in seen_stream_flags


def test_session_model_configuration_ollama_service_tool_supported(tmp_path, monkeypatch):
    from pathlib import Path

    from agent_session.models import AgentSessionCreate
    from agent_session.repository import AgentSessionRepository
    from agent_session.service import AgentSessionService

    from core.config import settings as real_settings

    monkeypatch.setattr(real_settings, "inference_execution_mode", "service", raising=False)
    service = AgentSessionService(AgentSessionRepository(str(tmp_path / "agents.db")))
    session = service.create_session(
        AgentSessionCreate(
            title="phase2 ollama",
            project_path=str(Path.cwd()),
            provider="ollama",
            model="qwen3:8b",
        )
    )
    cfg = session.metadata["model_configuration"]
    assert cfg["tool_calling_supported"] is True
    assert agent_model_tool_calling_status("ollama", real_settings)["supported"] is True
