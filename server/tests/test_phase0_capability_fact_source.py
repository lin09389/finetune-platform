"""Phase 0: multi-surface consistency for Agent/local tool-calling facts.

All publishers must consume ``agent_session.model_capabilities`` so Agent
gates, ``GET /api/info``, and inference capability payloads cannot drift.
"""

from __future__ import annotations

import importlib
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from agent_session.model_capabilities import (
    LOCAL_INFERENCE_BACKENDS,
    agent_model_tool_calling_status,
    build_agent_model_runtime_payload,
    build_inference_tool_calling_features,
    build_local_backend_tool_calling_breakdown,
    local_agent_tool_calling_status,
    local_endpoint_backend_tool_calling_status,
)
from agent_session.models import AgentSessionCreate
from agent_session.repository import AgentSessionRepository
from agent_session.service import AgentSessionService


class _Settings:
    def __init__(self, execution_mode: str = "service"):
        self.inference_execution_mode = execution_mode


def _message_category(message: str | None) -> str:
    if not message:
        return "none"
    if "不支持 Agent 所需的工具调用" in message or "仅支持文本聊天" in message:
        return "service_text_only"
    if "请选择 Agent" in message:
        return "select_provider"
    return "other"


@pytest.mark.parametrize("execution_mode", ("service", "in_process"))
def test_local_endpoint_backends_are_fail_closed_for_tools(execution_mode):
    settings = _Settings(execution_mode)
    breakdown = build_local_backend_tool_calling_breakdown(settings)
    features = build_inference_tool_calling_features(settings)

    assert set(breakdown) == set(LOCAL_INFERENCE_BACKENDS)
    assert "llama-cpp" in breakdown
    assert "llamacpp" not in breakdown  # publish BackendType ids only
    # Phase 2: Ollama endpoint tools supported; HF / llama-cpp remain fail-closed.
    assert features["tool_calling"] is True
    assert breakdown["ollama"]["supported"] is True
    assert features["tool_calling_by_backend"]["ollama"] is True
    for backend in ("huggingface", "llama-cpp"):
        assert breakdown[backend]["supported"] is False
        assert features["tool_calling_by_backend"][backend] is False
        assert features["tool_calling_details"][backend]["supported"] is False
        assert _message_category(breakdown[backend]["message"]) == "service_text_only"
    for backend in LOCAL_INFERENCE_BACKENDS:
        endpoint = local_endpoint_backend_tool_calling_status(backend, settings)
        assert endpoint["supported"] is breakdown[backend]["supported"]
        assert endpoint["message"] == breakdown[backend]["message"]
        assert endpoint["backend"] == backend


def test_llama_cpp_canonical_and_alias_agree_and_fail_closed():
    """Regression: BackendType is llama-cpp; helpers must not treat it as cloud."""
    settings = _Settings("service")
    for name in ("llama-cpp", "llamacpp", "llama_cpp"):
        agent = agent_model_tool_calling_status(name, settings)
        local = local_agent_tool_calling_status(name, settings)
        assert agent["supported"] is False
        assert local["supported"] is False
        assert agent["supported"] is local["supported"]
        assert agent.get("backend") == "llama-cpp"
        assert local.get("backend") == "llama-cpp"
        assert _message_category(agent.get("message")) == "service_text_only"

    # Endpoint helper accepts alias and returns canonical backend key.
    endpoint = local_endpoint_backend_tool_calling_status("llamacpp", settings)
    assert endpoint["backend"] == "llama-cpp"
    assert endpoint["supported"] is False
    breakdown = build_local_backend_tool_calling_breakdown(settings)
    assert breakdown["llama-cpp"]["supported"] is False
    features = build_inference_tool_calling_features(settings)
    assert "llama-cpp" in features["tool_calling_by_backend"]
    assert features["tool_calling_by_backend"]["llama-cpp"] is False


@pytest.mark.parametrize(
    ("provider", "execution_mode", "expected_supported", "message_cat"),
    [
        ("local", "service", False, "service_text_only"),
        ("local", "in_process", False, "service_text_only"),
        ("huggingface", "service", False, "service_text_only"),
        ("llama-cpp", "service", False, "service_text_only"),
        ("llama-cpp", "in_process", False, "service_text_only"),
        ("llamacpp", "service", False, "service_text_only"),  # legacy alias
        ("ollama", "service", True, "none"),  # Phase 2: Ollama tools passthrough on service path
        ("ollama", "in_process", True, "none"),
        ("deepseek", "service", True, "none"),
        ("openai", "in_process", True, "none"),
        ("", "service", False, "select_provider"),
        (None, "service", False, "select_provider"),
    ],
)
def test_agent_provider_tool_calling_matrix(provider, execution_mode, expected_supported, message_cat):
    settings = _Settings(execution_mode)
    status = agent_model_tool_calling_status(provider, settings)
    assert status["supported"] is expected_supported
    assert status["execution_mode"] == execution_mode
    assert _message_category(status.get("message")) == message_cat

    local_names = {"local", "ollama", "huggingface", "llama-cpp", "llamacpp"}
    if provider in local_names:
        local = local_agent_tool_calling_status(provider, settings)
        assert local["supported"] is expected_supported
        assert local["supported"] is status["supported"]
        assert _message_category(local.get("message")) == message_cat
        # Canonical backend id for llama-cpp (aliases collapse).
        if provider in {"llama-cpp", "llamacpp"}:
            assert local.get("backend") == "llama-cpp"
            assert status.get("backend") == "llama-cpp"


@pytest.mark.parametrize("execution_mode", ("service", "in_process"))
def test_agent_model_runtime_payload_matches_helpers(execution_mode):
    settings = _Settings(execution_mode)
    local = local_agent_tool_calling_status("local", settings)
    ollama = local_agent_tool_calling_status("ollama", settings)
    payload = build_agent_model_runtime_payload(settings, cloud_model_configured=False)

    assert payload["local_tool_calling_supported"] is local["supported"]
    assert payload["local_tool_calling_message"] == local["message"]
    assert payload["inference_execution_mode"] == execution_mode
    assert payload["providers"]["local"]["tool_calling_supported"] is local["supported"]
    assert payload["providers"]["ollama"]["tool_calling_supported"] is ollama["supported"]
    assert payload["providers"]["ollama"]["message"] == ollama.get("message")

    features = build_inference_tool_calling_features(settings)
    for backend in LOCAL_INFERENCE_BACKENDS:
        assert payload["backends"][backend]["tool_calling"] is features["tool_calling_by_backend"][backend]
        assert payload["backends"][backend]["message"] == features["tool_calling_details"][backend]["message"]

    # Phase 2: Ollama is recommended whenever endpoint/LangChain path supports tools.
    assert ollama["supported"] is True
    assert "ollama" in payload["recommended_agent_providers"]
    for cloud in ("deepseek", "openrouter", "openai"):
        assert cloud in payload["recommended_agent_providers"]


@pytest.mark.asyncio
@pytest.mark.parametrize("module", ("apps.combined", "apps.agent", "apps.finetune"))
async def test_api_info_agent_model_runtime_from_fact_source(module, monkeypatch):
    app_module = __import__(module, fromlist=["app"])
    app = app_module.app
    # Resolve /api/info endpoint without network.
    from apps.factory import api_info

    monkeypatch.setattr(
        "agent_session.model_capabilities.saved_cloud_agent_model_configured",
        lambda _repo: False,
    )
    # Ensure default service-mode fail-closed for local.
    from core.config import settings as real_settings

    monkeypatch.setattr(real_settings, "inference_execution_mode", "service", raising=False)

    payload = await api_info()
    runtime = payload["agent_model_runtime"]
    expected = build_agent_model_runtime_payload(real_settings, cloud_model_configured=False)

    assert runtime["local_tool_calling_supported"] is expected["local_tool_calling_supported"] is False
    assert runtime["local_tool_calling_message"] == expected["local_tool_calling_message"]
    assert runtime["inference_execution_mode"] == expected["inference_execution_mode"]
    assert runtime["backends"] == expected["backends"]
    assert runtime["providers"] == expected["providers"]
    assert runtime["recommended_agent_providers"] == expected["recommended_agent_providers"]
    assert "cloud_model_configured" in runtime
    # Keep profile apps importable (module param documents multi-app surface).
    assert app is not None


def test_inference_capabilities_backend_aware_tool_facts(monkeypatch):
    module = importlib.import_module("inference_server.app")
    monkeypatch.setattr(module.settings, "inference_internal_api_key", "test-internal-key")
    monkeypatch.setattr(module.settings, "inference_execution_mode", "service", raising=False)

    async def fake_backends():
        return {"current": "ollama", "backends": [{"name": "ollama", "available": True}]}

    async def fake_models():
        return SimpleNamespace(model_dump=lambda: {"data": [{"id": "qwen"}]})

    monkeypatch.setattr("api.inference.routes.list_backends", fake_backends)
    monkeypatch.setattr("api.inference.openai_routes.list_models", fake_models)

    response = TestClient(module.app).get(
        "/internal/capabilities",
        headers={"Authorization": "Bearer test-internal-key"},
    )
    assert response.status_code == 200
    payload = response.json()
    features = payload["features"]
    expected = build_inference_tool_calling_features(module.settings)

    assert features["tool_calling"] is expected["tool_calling"] is True
    assert features["tool_calling_by_backend"] == expected["tool_calling_by_backend"]
    assert features["tool_calling_details"] == expected["tool_calling_details"]
    assert features["tool_calling_by_backend"]["ollama"] is True
    assert features["tool_calling_by_backend"]["huggingface"] is False
    assert features["tool_calling_by_backend"]["llama-cpp"] is False


def test_session_model_configuration_matches_fact_source(tmp_path: Path, monkeypatch):
    from core.config import settings as real_settings

    monkeypatch.setattr(real_settings, "inference_execution_mode", "service", raising=False)
    service = AgentSessionService(AgentSessionRepository(str(tmp_path / "agents.db")))
    session = service.create_session(
        AgentSessionCreate(
            title="phase0 local",
            project_path=str(Path.cwd()),
            provider="local",
            model="qwen3:8b",
        )
    )
    status = agent_model_tool_calling_status("local", real_settings)
    cfg = session.metadata["model_configuration"]
    assert cfg["tool_calling_supported"] is status["supported"] is False
    assert cfg["message"] == status["message"]
    assert _message_category(cfg["message"]) == "service_text_only"
    assert session.metadata["model_configured"] is False


def test_session_model_configuration_in_process_ollama_truthful(tmp_path: Path, monkeypatch):
    from core.config import settings as real_settings

    monkeypatch.setattr(real_settings, "inference_execution_mode", "in_process", raising=False)
    service = AgentSessionService(AgentSessionRepository(str(tmp_path / "agents.db")))
    # Ollama needs no cloud API key: provider+model is enough when tools are supported.
    session = service.create_session(
        AgentSessionCreate(
            title="phase0 ollama in_process",
            project_path=str(Path.cwd()),
            provider="ollama",
            model="qwen3:8b",
        )
    )
    status = agent_model_tool_calling_status("ollama", real_settings)
    cfg = session.metadata["model_configuration"]
    assert status["supported"] is True
    assert cfg["tool_calling_supported"] is True
    assert cfg["message"] is None
    assert session.metadata["model_configured"] is True
    assert cfg["tool_calling_supported"] is status["supported"]


def test_session_model_configuration_service_ollama_configured_without_cloud_key(tmp_path: Path, monkeypatch):
    from core.config import settings as real_settings

    monkeypatch.setattr(real_settings, "inference_execution_mode", "service", raising=False)
    service = AgentSessionService(AgentSessionRepository(str(tmp_path / "agents.db")))
    session = service.create_session(
        AgentSessionCreate(
            title="phase0 ollama service",
            project_path=str(Path.cwd()),
            provider="ollama",
            model="qwen2.5:3b",
        )
    )
    cfg = session.metadata["model_configuration"]
    assert cfg["tool_calling_supported"] is True
    assert session.metadata["model_configured"] is True
    assert cfg["configured"] is True
    assert cfg["message"] is None
