"""Test doubles for the default worker + service execution modes.

When tests run with the production default modes
(TRAINING_EXECUTION_MODE=worker, INFERENCE_EXECUTION_MODE=service), these
fixtures provide lightweight stand-ins so that no real GPU worker or 8020 port
is required.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI


@pytest.fixture
def training_job_repo(tmp_path):
    """Return a TrainingJobRepository backed by a temporary SQLite database."""
    from training_worker.repository import TrainingJobRepository

    return TrainingJobRepository(str(tmp_path / "training_jobs.db"))


@pytest.fixture
def fake_inference_service_app():
    """Minimal FastAPI app that acts as the local inference service."""
    app = FastAPI()

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.get("/v1/models")
    def list_models():
        return {"object": "list", "data": []}

    @app.post("/v1/chat/completions")
    def chat_completions(request):
        return {"choices": [{"message": {"content": "fake"}}]}

    @app.get("/internal/capabilities")
    def capabilities():
        return {
            "schema_version": "inference.capabilities.v1",
            "api": {
                "chat_completions": "/v1/chat/completions",
                "models": "/v1/models",
                "streaming": True,
                "batch": True,
            },
            "features": {
                "chat": True,
                "streaming": True,
                "tool_calling": True,
                "tool_calling_by_backend": {
                    "huggingface": False,
                    "ollama": True,
                    "llama-cpp": False,
                },
                "tool_calling_details": {
                    "huggingface": {
                        "supported": False,
                        "via": "local_chat_completions",
                        "message": "当前本地后端不支持 Agent 所需的工具调用。请使用 Ollama（provider=ollama 或 model=ollama/...），或配置支持工具调用的云端 provider:model。",
                    },
                    "ollama": {
                        "supported": True,
                        "via": "local_chat_completions_ollama",
                        "message": None,
                    },
                    "llama-cpp": {
                        "supported": False,
                        "via": "local_chat_completions",
                        "message": "当前本地后端不支持 Agent 所需的工具调用。请使用 Ollama（provider=ollama 或 model=ollama/...），或配置支持工具调用的云端 provider:model。",
                    },
                },
                "vision": False,
                "json_mode": False,
            },
            "limits": {
                "max_read_timeout_seconds": 180.0,
                "network_scope": "loopback_or_private_container_network",
            },
            "backends": {"current": "huggingface", "backends": []},
            "models": [],
        }

    return app


@pytest.fixture
def inference_client_with_fake_service(fake_inference_service_app):
    """Return an InferenceServiceClient pointing at the fake service via ASGI transport."""
    import httpx
    from inference_provider.client import get_inference_service_client

    client = get_inference_service_client()
    client.client = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=fake_inference_service_app),
        base_url="http://testserver",
    )
    return client
