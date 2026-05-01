from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.inference.backends.base import GenerationResult
from api.inference import routes


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
