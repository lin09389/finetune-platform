import json
import os
import sys
import time
import asyncio

import pytest
from fastapi.testclient import TestClient

server_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, server_dir)

from api.inference.backends.base import GenerationConfig
from api.inference.backends.ollama import OllamaBackend
from api.inference.backends import ollama as ollama_backend_module
from api.inference import routes as inference_routes
from main import app


class _FakeBackend:
    def __init__(self):
        self.model_name = "default-model"
        self.calls = []

    async def chat_stream(self, messages, config):
        self.calls.append((messages, config))
        yield "hello"
        yield " world"

class _FakeSlowBackend:
    def __init__(self):
        self.model_name = "slow-model"

    async def chat_stream(self, messages, config):
        # 模拟生成第一个字的极速返回
        await asyncio.sleep(0.1)
        yield "hello"
        # 模拟后续生成的缓慢（如果真流式，首字不受这里影响）
        await asyncio.sleep(1.0)
        yield " world"

class _FakeScheduler:
    def __init__(self, backend):
        self.backend = backend

    async def get_backend(self, backend_name):
        return self.backend


def test_chat_stream_returns_sse_events(monkeypatch):
    backend = _FakeBackend()
    scheduler = _FakeScheduler(backend)
    monkeypatch.setattr(inference_routes, "get_scheduler", lambda: scheduler)

    client = TestClient(app)
    response = client.post(
        "/inference/chat/stream",
        json={
            "model": "qwen-test",
            "messages": [{"role": "user", "content": "hi"}],
            "options": {"backend": "ollama", "max_tokens": 32},
        },
    )

    assert response.status_code == 200
    body = response.text
    assert '"type": "metadata"' in body
    assert '"type": "delta"' in body
    assert '"type": "done"' in body
    assert "data: [DONE]" in body

    assert backend.calls, "backend.chat_stream should be called"
    messages, config = backend.calls[0]
    assert isinstance(messages, list)
    assert isinstance(config, GenerationConfig)
    assert messages[0]["role"] == "user"
    assert backend.model_name == "qwen-test"

@pytest.mark.asyncio
async def test_chat_stream_ttft_latency(monkeypatch):
    backend = _FakeSlowBackend()
    scheduler = _FakeScheduler(backend)
    monkeypatch.setattr(inference_routes, "get_scheduler", lambda: scheduler)

    from api.inference.routes import chat_stream
    from api.types import ChatRequest, Message, InferenceOptions
    from core.config import get_settings

    # 直接调用路由函数，绕过 httpx.ASGITransport 的缓冲问题
    request = ChatRequest(
        model="qwen-test",
        messages=[Message(role="user", content="hi")],
        options=InferenceOptions(backend="huggingface", max_tokens=32)
    )
    
    # 模拟环境依赖
    monkeypatch.setattr(inference_routes.settings, "ollama_fast_mode", False)
    
    response = await chat_stream(request)
    # response 此时是一个 StreamingResponse
    
    first_token_time = None
    start_time = time.time()
    
    # 提取内部的 generator
    async for chunk in response.body_iterator:
        if "delta" in chunk:
            if first_token_time is None:
                first_token_time = time.time()
                break # 拿到首字就可以退出了，没必要等完全生成
                
    assert first_token_time is not None
    ttft = first_token_time - start_time
    
    # 断言首字延迟在合理范围内，证明是真正的流式
    # fake backend 需要 0.1s 产出首字，再加上微小的系统开销，0.5s 是合理的上限
    assert ttft < 0.5, f"TTFT was too slow: {ttft}s, possible fake streaming"

@pytest.mark.asyncio
async def test_ollama_chat_stream_auto_load(monkeypatch):
    backend = OllamaBackend({"base_url": "http://test-ollama.local"})
    backend._is_loaded = False

    load_called = False

    async def fake_load_model(model_name, **kwargs):
        nonlocal load_called
        load_called = True
        backend._is_loaded = True
        backend.model_name = model_name
        return True

    class FakeResponse:
        status = 200

        def __init__(self):
            self._lines = [
                json.dumps({"message": {"content": "A"}}).encode("utf-8"),
                json.dumps({"message": {"content": "B"}}).encode("utf-8"),
            ]

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        @property
        def content(self):
            async def _iter():
                for line in self._lines:
                    yield line

            return _iter()

    class FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        def post(self, *args, **kwargs):
            return FakeResponse()

    monkeypatch.setattr(backend, "load_model", fake_load_model)
    monkeypatch.setattr(ollama_backend_module.aiohttp, "ClientSession", FakeSession)

    chunks = []
    async for chunk in backend.chat_stream([{"role": "user", "content": "hi"}], GenerationConfig()):
        chunks.append(chunk)

    assert load_called is True
    assert "".join(chunks) == "AB"
