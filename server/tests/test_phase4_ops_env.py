"""Phase 4: ops/env hygiene — absolute app.db, runtime probes, execution_trace."""

from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from agent_session.deepagents_events import DeepAgentsEventMapper
from agent_session.model_adapter import (
    get_chat_model,
    get_last_chat_model_resolution,
    ProviderAdapterError,
)
from agent_session.models import AgentSessionCreate, AgentPromptRequest
from agent_session.repository import AgentSessionRepository
from agent_session.service import AgentSessionService
from core.config import settings
from core.db_manager import get_db_pool
from core.runtime_env import is_virtualenv, package_available, probe_agent_runtime_environment
from core.storage import APP_DB_PATH, resolve_storage_path


def test_app_db_path_is_absolute_under_server_base_dir():
    app_db = Path(APP_DB_PATH)
    assert app_db.is_absolute()
    # conftest sets FINETUNE_PLATFORM_DB_PATH=data/app_test.db; production default is data/app.db.
    # Both must resolve under server base_dir, never process CWD.
    expected_from_env = Path(
        resolve_storage_path(os.environ.get("FINETUNE_PLATFORM_DB_PATH", "data/app.db"))
    )
    assert app_db == expected_from_env
    assert str(app_db).startswith(str(settings.base_dir.resolve()))
    # Relative inputs resolve against base_dir, not process CWD.
    resolved = Path(resolve_storage_path("data/phase4-relative.db"))
    assert resolved == (settings.base_dir / "data" / "phase4-relative.db").resolve()


def test_get_db_pool_default_uses_absolute_app_db():
    pool = get_db_pool()
    assert Path(pool._db_path).is_absolute()
    assert Path(pool._db_path) == Path(APP_DB_PATH)


def test_probe_agent_runtime_environment_shape():
    payload = probe_agent_runtime_environment()
    assert "in_virtualenv" in payload
    assert "packages" in payload
    assert "langchain_openai" in payload["packages"]
    assert "deepagents" in payload["packages"]
    assert "warnings" in payload
    assert "recommended_command" in payload
    assert "uv run --extra all" in payload["recommended_command"]
    assert payload.get("app_db_path") is None or Path(payload["app_db_path"]).is_absolute()
    # package_available is a real importlib probe
    assert package_available("sys") is True
    assert isinstance(is_virtualenv(), bool)


@pytest.mark.asyncio
async def test_api_info_exposes_storage_and_agent_runtime_env():
    from apps.factory import api_info

    payload = await api_info()
    assert "storage" in payload
    assert Path(payload["storage"]["app_db_path"]).is_absolute()
    assert "agent_runtime_env" in payload
    assert "packages" in payload["agent_runtime_env"]
    assert "recommended_command" in payload["agent_runtime_env"]


def test_get_chat_model_records_last_resolution_for_official_path(monkeypatch):
    captured = {}

    class FakeModel:
        pass

    def fake_init(**kwargs):
        captured.update(kwargs)
        return FakeModel()

    import agent_session.model_adapter as adapter

    monkeypatch.setattr(
        adapter.cloud_provider_repository,
        "get",
        lambda provider_id: {"api_key": "sk-test"} if provider_id == "openai" else {},
    )
    monkeypatch.setattr("langchain.chat_models.init_chat_model", fake_init)

    model = get_chat_model(SimpleNamespace(provider="openai", model="gpt-4o", metadata={}))
    assert isinstance(model, FakeModel)
    resolution = get_last_chat_model_resolution()
    assert resolution is not None
    assert resolution["model_entry"] == "official_init_chat_model"
    assert resolution["path"] == "official"
    assert resolution["fallback_used"] is False
    assert resolution["has_api_key"] is True
    assert "api_key" not in resolution


def test_get_chat_model_records_fallback_resolution(monkeypatch):
    import agent_session.model_adapter as adapter
    from langchain_openai import ChatOpenAI

    monkeypatch.setattr(
        adapter.cloud_provider_repository,
        "get",
        lambda provider_id: {
            "api_key": "sk-fallback",
            "base_url": "https://api.deepseek.com",
        }
        if provider_id == "deepseek"
        else {},
    )
    monkeypatch.setattr(
        "langchain.chat_models.init_chat_model",
        lambda **kwargs: (_ for _ in ()).throw(ImportError("requires the langchain-deepseek package")),
    )

    model = get_chat_model(SimpleNamespace(provider="deepseek", model="deepseek-v4-flash", metadata={}))
    assert isinstance(model, ChatOpenAI)
    resolution = get_last_chat_model_resolution()
    assert resolution["model_entry"] == "openai_compat_fallback"
    assert resolution["path"] == "fallback"
    assert resolution["fallback_used"] is True


def test_record_prompt_failure_writes_execution_trace_errors(tmp_path: Path):
    service = AgentSessionService(AgentSessionRepository(str(tmp_path / "agents.db")))
    session = service.create_session(
        AgentSessionCreate(title="phase4 fail", project_path=str(Path.cwd()), provider="openai", model="gpt-4o")
    )
    # Seed pending trace like prompt() would.
    service.repository.update_session(
        session.id,
        metadata={
            **dict(session.metadata or {}),
            "execution_trace": {
                "provider": "openai",
                "model": "gpt-4o",
                "model_entry": "pending_model_resolution",
            },
        },
    )
    result = service.record_prompt_failure(session.id, RuntimeError("boom-model-failure"))
    trace = (result.get("metadata") or {}).get("execution_trace") or {}
    assert "boom-model-failure" in str(trace.get("last_model_error") or "")
    assert "boom-model-failure" in str(trace.get("last_graph_error") or "")


def test_tool_call_failed_records_last_tool_error():
    class Repo:
        def __init__(self):
            self.parts = []
            self.events = []
            self.session = {"id": "s1", "metadata": {"execution_trace": {}}}

        def add_part(self, *a, **k):
            part = {"id": f"p{len(self.parts)}", "type": a[1], **k, "payload": k.get("payload") or {}}
            self.parts.append(part)
            return part

        def update_part(self, pid, **u):
            for p in self.parts:
                if p["id"] == pid:
                    p.update(u)
                    return p

        def add_event(self, sid, et, msg, payload):
            event = {"event_type": et, "payload": payload}
            self.events.append(event)
            return event

        def get_session(self, _):
            return self.session

        def update_session(self, _sid, **updates):
            if "metadata" in updates:
                self.session["metadata"] = updates["metadata"]
            return self.session

    repo = Repo()
    mapper = DeepAgentsEventMapper(repo, lambda *a: None, "s1")
    mapper.handle({"event": "on_tool_start", "name": "ls", "run_id": "r1", "data": {"input": {}}})
    mapper.handle(
        {
            "event": "on_tool_end",
            "name": "ls",
            "run_id": "r1",
            "data": {"output": "Error: permission denied for read on /workspace"},
        }
    )
    trace = repo.session["metadata"]["execution_trace"]
    assert trace["last_tool_error"]["tool"] == "ls"
    assert "permission denied" in trace["last_tool_error"]["message"]
