import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, AsyncMock, MagicMock

from main import app
from core.inference.engine_base import InferenceResponse, StreamChunk

client = TestClient(app)

@pytest.fixture
def mock_engine_factory():
    with patch("api.inference.openai_routes.get_engine") as mock_get:
        engine_mock = AsyncMock()
        engine_mock.name = "MockEngine"
        
        # get_available_models is a sync method
        engine_mock.get_available_models = MagicMock(return_value=["mock-model-1", "mock-model-2"])
        
        
        # Mock chat response
        engine_mock.chat.return_value = InferenceResponse(
            text="Hello! How can I help you today?",
            tokens_generated=8,
            processing_time_ms=100.0,
            model_id="mock-model",
            backend="mock",
            finish_reason="stop"
        )
        
        # Mock stream response
        async def mock_stream_gen(request):
            yield StreamChunk(content="Hello", done=False, tokens_so_far=1)
            yield StreamChunk(content="!", done=True, tokens_so_far=2, finish_reason="stop")
            
        engine_mock.chat_stream = mock_stream_gen
        
        mock_get.return_value = engine_mock
        yield mock_get


def test_list_models(mock_engine_factory):
    response = client.get("/v1/models")
    assert response.status_code == 200
    data = response.json()
    assert data["object"] == "list"
    assert len(data["data"]) == 2
    assert data["data"][0]["id"] == "mock-model-1"


def test_chat_completions(mock_engine_factory):
    payload = {
        "model": "mock-model-1",
        "messages": [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Hello"}
        ],
        "temperature": 0.5
    }
    
    response = client.post("/v1/chat/completions", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["object"] == "chat.completion"
    assert data["model"] == "mock-model-1"
    assert len(data["choices"]) == 1
    assert data["choices"][0]["message"]["role"] == "assistant"
    assert data["choices"][0]["message"]["content"] == "Hello! How can I help you today?"
    assert data["choices"][0]["finish_reason"] == "stop"
    assert data["usage"]["total_tokens"] == 8


def test_chat_completions_stream(mock_engine_factory):
    payload = {
        "model": "mock-model-1",
        "messages": [
            {"role": "user", "content": "Hello"}
        ],
        "stream": True
    }
    
    response = client.post("/v1/chat/completions", json=payload)
    assert response.status_code == 200
    assert response.headers["content-type"] == "text/event-stream; charset=utf-8"
    
    content = response.content.decode("utf-8")
    assert "data: " in content
    assert "chat.completion.chunk" in content
    assert "Hello" in content
    assert "data: [DONE]" in content
