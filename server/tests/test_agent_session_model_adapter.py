from __future__ import annotations

import pytest
from agent_session.model_adapter import (
    ProviderAdapterError,
    get_chat_model,
    resolve_official_model_spec,
)
from agent_session.models import AgentSessionCreate, AgentSessionResponse
from pydantic import ValidationError


def test_agent_session_create_round_trips_workspace_task_context():
    request = AgentSessionCreate(agent_id="build", workspace_id="ws_demo", task_mode="hybrid")

    response = AgentSessionResponse.model_validate(
        {
            "id": "session-demo",
            "agent_id": request.agent_id,
            "status": "idle",
            "title": "Demo",
            "workspace_id": request.workspace_id,
            "task_mode": request.task_mode,
            "created_at": "2026-07-10T00:00:00",
            "updated_at": "2026-07-10T00:00:00",
        }
    )

    assert request.workspace_id == "ws_demo"
    assert request.task_mode == "hybrid"
    assert response.workspace_id == "ws_demo"
    assert response.task_mode == "hybrid"


def test_agent_session_create_rejects_unknown_task_mode():
    with pytest.raises(ValidationError):
        AgentSessionCreate(agent_id="build", task_mode="advise")


def test_agent_session_task_context_is_optional_for_legacy_clients():
    request = AgentSessionCreate(agent_id="build", project_path="C:/legacy-project")
    response = AgentSessionResponse.model_validate(
        {
            "id": "legacy-session",
            "agent_id": request.agent_id,
            "status": "idle",
            "title": "Legacy",
            "project_path": request.project_path,
            "metadata": {},
            "created_at": "2026-07-10T00:00:00",
            "updated_at": "2026-07-10T00:00:00",
        }
    )

    assert request.workspace_id is None
    assert request.task_mode is None
    assert response.workspace_id is None
    assert response.task_mode is None


def test_resolve_official_model_from_provider_model_string():
    context = type("Context", (), {"provider": "", "model": "openrouter:z-ai/glm-5.1"})()

    spec = resolve_official_model_spec(context)

    assert spec is not None
    assert spec.provider == "openrouter"
    assert spec.model == "z-ai/glm-5.1"


def test_resolve_official_model_from_provider_and_model(inference_in_process):
    context = type("Context", (), {"provider": "ollama", "model": "qwen3:8b"})()

    spec = resolve_official_model_spec(context)

    assert spec is not None
    assert spec.provider == "ollama"
    assert spec.model == "qwen3:8b"


def test_get_chat_model_rejects_legacy_platform_provider():
    context = type("Context", (), {"provider": "minimax", "model": "MiniMax-M2.5", "metadata": {}})()

    try:
        get_chat_model(context)
    except ProviderAdapterError as exc:
        assert "provider:model" in str(exc)
    else:
        raise AssertionError("Expected ProviderAdapterError for legacy provider")


def test_get_chat_model_rejects_local_service_before_tool_binding():
    context = type("Context", (), {"provider": "local", "model": "qwen3:8b", "metadata": {}})()

    with pytest.raises(ProviderAdapterError, match="不支持 Agent 所需的工具调用"):
        get_chat_model(context)


def test_get_chat_model_uses_official_init_chat_model(monkeypatch):
    captured = {}

    class FakeModel:
        pass

    def fake_init_chat_model(**kwargs):
        captured.update(kwargs)
        return FakeModel()

    monkeypatch.setattr("agent_session.model_adapter.secure_storage.get", lambda key: {"api_key": "secret"})
    monkeypatch.setattr("langchain.chat_models.init_chat_model", fake_init_chat_model)
    context = type("Context", (), {"provider": "", "model": "openai:gpt-4o", "metadata": {"model_params": {"max_tokens": 1024}}})()

    model = get_chat_model(context)

    assert isinstance(model, FakeModel)
    assert captured["model"] == "gpt-4o"
    assert captured["model_provider"] == "openai"
    assert captured["api_key"] == "secret"
    assert captured["temperature"] == 0
    assert captured["timeout"] == 180
    assert captured["max_retries"] == 2
    assert captured["max_tokens"] == 1024


def test_deepseek_does_not_inject_unsupported_thinking_parameters(monkeypatch):
    captured = {}

    class FakeModel:
        pass

    def fake_init_chat_model(**kwargs):
        captured.update(kwargs)
        return FakeModel()

    monkeypatch.setattr("agent_session.model_adapter.secure_storage.get", lambda key: {"api_key": "secret"})
    monkeypatch.setattr("langchain.chat_models.init_chat_model", fake_init_chat_model)
    context = type("Context", (), {"provider": "deepseek", "model": "deepseek-v4-flash", "metadata": {}})()

    model = get_chat_model(context)

    assert isinstance(model, FakeModel)
    assert captured["model_provider"] == "deepseek"
    assert "extra_body" not in captured


def test_deepseek_model_params_pass_extra_body_through(monkeypatch):
    captured = {}

    class FakeModel:
        pass

    def fake_init_chat_model(**kwargs):
        captured.update(kwargs)
        return FakeModel()

    monkeypatch.setattr("agent_session.model_adapter.secure_storage.get", lambda key: {"api_key": "secret"})
    monkeypatch.setattr("langchain.chat_models.init_chat_model", fake_init_chat_model)
    context = type(
        "Context",
        (),
        {
            "provider": "deepseek",
            "model": "deepseek-v4-flash",
            "metadata": {"model_params": {"extra_body": {"foo": "bar"}}},
        },
    )()

    model = get_chat_model(context)

    assert isinstance(model, FakeModel)
    assert captured["extra_body"] == {"foo": "bar"}
