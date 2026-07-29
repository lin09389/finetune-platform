"""Phase 1: cloud Agent model resolution, credential fail-closed, multi-turn tools."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from agent_session.model_adapter import (
    OPENAI_COMPAT_PROVIDERS,
    ProviderAdapterError,
    describe_cloud_model_resolution,
    get_chat_model,
    init_openai_compat_chat_model,
    normalize_openai_compat_base_url,
    resolve_official_model_spec,
)
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_openai import ChatOpenAI


def _context(provider: str, model: str, metadata: dict | None = None) -> SimpleNamespace:
    return SimpleNamespace(provider=provider, model=model, metadata=metadata or {})


def _patch_cloud_key(monkeypatch, provider: str, payload: dict[str, Any] | None) -> None:
    """Patch CloudProviderRepository.get used by the model adapter."""
    from agent_session import model_adapter as adapter

    original = adapter.cloud_provider_repository.get

    def fake_get(provider_id: str) -> dict[str, Any]:
        if provider_id == provider:
            return dict(payload or {})
        return original(provider_id)

    monkeypatch.setattr(adapter.cloud_provider_repository, "get", fake_get)


def test_normalize_openai_compat_base_url_appends_v1():
    assert normalize_openai_compat_base_url("deepseek", "https://api.deepseek.com") == "https://api.deepseek.com/v1"
    assert normalize_openai_compat_base_url("deepseek", "https://api.deepseek.com/") == "https://api.deepseek.com/v1"
    assert normalize_openai_compat_base_url("deepseek", "https://api.deepseek.com/v1") == "https://api.deepseek.com/v1"
    assert normalize_openai_compat_base_url("deepseek", None) == "https://api.deepseek.com/v1"
    assert normalize_openai_compat_base_url("openrouter", "https://openrouter.ai/api") == "https://openrouter.ai/api/v1"
    assert normalize_openai_compat_base_url("openai", None) is None


def test_openai_without_api_key_fails_closed_before_init(monkeypatch):
    captured: dict[str, Any] = {}

    def boom(**kwargs):
        captured.update(kwargs)
        raise AssertionError("init_chat_model must not run without api_key")

    _patch_cloud_key(monkeypatch, "openai", {})
    monkeypatch.setattr("langchain.chat_models.init_chat_model", boom)

    with pytest.raises(ProviderAdapterError, match="未配置 openai API Key") as exc_info:
        get_chat_model(_context("openai", "gpt-4o"))

    assert "sk-" not in str(exc_info.value)
    assert captured == {}
    plan = describe_cloud_model_resolution(_context("openai", "gpt-4o"))
    assert plan.path == "error"
    assert plan.has_api_key is False
    assert plan.message and "API Key" in plan.message


def test_deepseek_official_init_when_package_available(monkeypatch):
    captured: dict[str, Any] = {}

    class FakeModel:
        def bind_tools(self, tools, **kwargs):
            return self

    def fake_init(**kwargs):
        captured.update(kwargs)
        return FakeModel()

    _patch_cloud_key(
        monkeypatch,
        "deepseek",
        {"api_key": "sk-test-deepseek", "base_url": "https://api.deepseek.com"},
    )
    monkeypatch.setattr("langchain.chat_models.init_chat_model", fake_init)

    model = get_chat_model(_context("deepseek", "deepseek-v4-flash"))
    assert isinstance(model, FakeModel)
    assert captured["model"] == "deepseek-v4-flash"
    assert captured["model_provider"] == "deepseek"
    assert captured["api_key"] == "sk-test-deepseek"
    assert captured["base_url"] == "https://api.deepseek.com/v1"
    plan = describe_cloud_model_resolution(_context("deepseek", "deepseek-v4-flash"))
    assert plan.path == "official"
    assert plan.has_api_key is True
    assert plan.base_url_normalized == "https://api.deepseek.com/v1"


def test_deepseek_falls_back_to_chat_openai_when_official_package_missing(monkeypatch):
    _patch_cloud_key(
        monkeypatch,
        "deepseek",
        {
            "api_key": "sk-test-fallback",
            "base_url": "https://api.deepseek.com",
            "default_model": "deepseek-v4-flash",
        },
    )

    def missing_package(**kwargs):
        raise ImportError(
            "Initializing ChatDeepSeek requires the langchain-deepseek package. "
            "Please install it with `pip install langchain-deepseek`"
        )

    monkeypatch.setattr("langchain.chat_models.init_chat_model", missing_package)

    model = get_chat_model(_context("deepseek", "deepseek-v4-flash"))
    assert isinstance(model, ChatOpenAI)
    assert model.model_name == "deepseek-v4-flash"
    # SecretStr / plain string depending on langchain-openai version
    api_key = model.openai_api_key
    key_text = api_key.get_secret_value() if hasattr(api_key, "get_secret_value") else str(api_key)
    assert key_text == "sk-test-fallback"
    base = str(model.openai_api_base or model.root_client.base_url or "")
    assert base.rstrip("/").endswith("/v1")
    assert "deepseek.com" in base
    assert hasattr(model, "bind_tools")

    plan = describe_cloud_model_resolution(
        _context("deepseek", "deepseek-v4-flash"),
        force_fallback=True,
    )
    assert plan.path == "fallback"
    assert plan.has_api_key is True
    assert plan.base_url_normalized == "https://api.deepseek.com/v1"


def test_openrouter_fallback_normalizes_base_url(monkeypatch):
    _patch_cloud_key(
        monkeypatch,
        "openrouter",
        {"api_key": "sk-or-test", "base_url": "https://openrouter.ai/api"},
    )

    def missing(**kwargs):
        raise ModuleNotFoundError("No module named 'langchain_openrouter'")

    monkeypatch.setattr("langchain.chat_models.init_chat_model", missing)
    model = get_chat_model(_context("openrouter", "z-ai/glm-5.1"))
    assert isinstance(model, ChatOpenAI)
    base = str(model.openai_api_base or "")
    assert base.rstrip("/").endswith("/v1")


def test_init_openai_compat_requires_key(monkeypatch):
    _patch_cloud_key(monkeypatch, "deepseek", {})
    spec = resolve_official_model_spec(_context("deepseek", "deepseek-v4-flash"))
    assert spec is not None
    with pytest.raises(ProviderAdapterError, match="未配置 deepseek API Key"):
        init_openai_compat_chat_model(spec, _context("deepseek", "deepseek-v4-flash"))


def test_multi_turn_tool_loop_on_fallback_client(monkeypatch):
    """Real ChatOpenAI construction (fallback path) + multi-turn tool messages."""
    _patch_cloud_key(
        monkeypatch,
        "deepseek",
        {"api_key": "sk-multi-turn", "base_url": "https://api.deepseek.com/v1"},
    )

    def missing_package(**kwargs):
        raise ImportError("requires the langchain-deepseek package")

    monkeypatch.setattr("langchain.chat_models.init_chat_model", missing_package)
    model = get_chat_model(_context("deepseek", "deepseek-v4-flash"))
    assert isinstance(model, ChatOpenAI)

    turns = {"n": 0}

    def fake_generate(self, messages, stop=None, run_manager=None, **kwargs):
        turns["n"] += 1
        if turns["n"] == 1:
            # First turn: request a tool call (simulates model tool_calls).
            message = AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "ls",
                        "args": {"path": "/workspace"},
                        "id": "call_phase1_1",
                        "type": "tool_call",
                    }
                ],
                additional_kwargs={"reasoning_content": "need to list workspace"},
            )
        else:
            # Second turn: must accept ToolMessage history without protocol error.
            roles = [type(m).__name__ for m in messages]
            assert "ToolMessage" in roles or any(isinstance(m, ToolMessage) for m in messages)
            message = AIMessage(
                content="workspace has a.py",
                additional_kwargs={"reasoning_content": "summarize tool result"},
            )
        return ChatResult(generations=[ChatGeneration(message=message)])

    # Patch generate on this instance's class binding used by invoke.
    monkeypatch.setattr(ChatOpenAI, "_generate", fake_generate)

    def ls(path: str) -> str:
        """List a directory."""
        return "a.py"

    bound = model.bind_tools([ls])
    turn1 = bound.invoke([HumanMessage(content="List /workspace using ls")])
    assert turn1.tool_calls
    assert turn1.tool_calls[0]["name"] == "ls"
    assert turn1.tool_calls[0]["args"].get("path") == "/workspace"

    tool_call_id = turn1.tool_calls[0]["id"]
    turn2 = bound.invoke(
        [
            HumanMessage(content="List /workspace using ls"),
            turn1,
            ToolMessage(content="a.py\nb.py", tool_call_id=tool_call_id),
        ]
    )
    assert turns["n"] == 2
    assert "workspace" in str(turn2.content).lower() or str(turn2.content)


def test_openai_compat_providers_constant_covers_phase1_targets():
    assert {"openai", "deepseek", "openrouter"} <= set(OPENAI_COMPAT_PROVIDERS)


def test_describe_resolution_matrix_rows_have_no_secrets(monkeypatch):
    _patch_cloud_key(monkeypatch, "deepseek", {"api_key": "sk-secret-should-not-leak", "base_url": "https://api.deepseek.com"})
    plan = describe_cloud_model_resolution(_context("deepseek", "deepseek-v4-flash"))
    dumped = str(plan)
    assert "sk-secret" not in dumped
    assert plan.has_api_key is True
