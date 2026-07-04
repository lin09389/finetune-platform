from __future__ import annotations

from agent_session.model_adapter import ProviderAdapterError, get_chat_model, resolve_official_model_spec


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


def test_deepseek_defaults_disable_thinking(monkeypatch):
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
    assert captured["extra_body"] == {"thinking": {"type": "disabled"}}


def test_deepseek_model_params_merge_extra_body(monkeypatch):
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
    assert captured["extra_body"] == {"thinking": {"type": "disabled"}, "foo": "bar"}
