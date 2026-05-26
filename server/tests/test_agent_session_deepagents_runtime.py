from __future__ import annotations

import asyncio
import json
import shutil
import uuid
from pathlib import Path

import pytest

from agent_session.models import AgentPromptRequest, AgentSessionCreate
from agent_session.repository import AgentSessionRepository
from agent_session.service import AgentSessionService
from agent_session.deepagents_runtime import DeepAgentsSessionRunner
from agent_session.runtime import (
    EPHEMERAL_BACKEND_ROUTES,
    FALLBACK_STATE_BACKEND_ROUTE,
    WORKSPACE_BACKEND_ROUTE,
    build_deepagents_backend,
    resolve_interrupt_on,
)


def test_agent_session_deepagents_reads_file_and_completes(tmp_path: Path):
    workspace = Path.cwd() / "tmp" / f"deepagents-runtime-{uuid.uuid4().hex[:8]}"
    workspace.mkdir()
    try:
        target = workspace / "hello.txt"
        target.write_text("hello from deepagents\n", encoding="utf-8")
        service = AgentSessionService(AgentSessionRepository(str(tmp_path / "agents.db")))
        session = service.create_session(AgentSessionCreate(title="deepagents prompt", project_path=str(workspace)))
        responses = iter(
            [
                json.dumps({"tool": "read_file", "arguments": {"file_path": "/workspace/hello.txt"}}, ensure_ascii=False),
                json.dumps({"type": "final", "content": "DeepAgents 已读取 hello.txt。"}, ensure_ascii=False),
            ]
        )

        async def model_call(_messages):
            return next(responses)

        service.model_call = model_call

        result = asyncio.run(service.prompt(session.id, AgentPromptRequest(content="读取 hello.txt 并总结")))
        events = service.list_events(session.id)

        assert result.status == "completed"
        assert result.metadata["runtime"] == "deepagents"
        assert any(part.type == "summary" and "DeepAgents" in (part.content or "") for part in result.parts)
        assert any(event["event_type"] == "session_started" for event in events)
        assert any(event["event_type"] == "tool_call_completed" for event in events)
    finally:
        shutil.rmtree(workspace, ignore_errors=True)


def test_agent_session_deepagents_edit_file_uses_official_hitl(tmp_path: Path):
    workspace = Path.cwd() / "tmp" / f"deepagents-action-{uuid.uuid4().hex[:8]}"
    workspace.mkdir()
    try:
        target = workspace / "hello.txt"
        target.write_text("hello\n", encoding="utf-8")
        service = AgentSessionService(AgentSessionRepository(str(tmp_path / "agents.db")))
        session = service.create_session(AgentSessionCreate(title="deepagents action", project_path=str(workspace)))
        responses = iter(
            [
                json.dumps(
                    {
                        "tool": "edit_file",
                        "arguments": {
                            "file_path": "/workspace/hello.txt",
                            "old_string": "hello\n",
                            "new_string": "hi\n",
                        },
                    },
                    ensure_ascii=False,
                ),
                json.dumps({"type": "final", "content": "已写入 hello.txt。"}, ensure_ascii=False),
            ]
        )

        async def model_call(_messages):
            return next(responses)

        service.model_call = model_call

        result = asyncio.run(service.prompt(session.id, AgentPromptRequest(content="把 hello 改成 hi")))

        assert result.status == "waiting_approval"
        assert target.read_text(encoding="utf-8") == "hello\n"
        assert any(part.type == "permission" and part.status == "pending" for part in result.parts)
    finally:
        shutil.rmtree(workspace, ignore_errors=True)


def test_agent_session_deepagents_execute_uses_official_hitl_without_whitelist(tmp_path: Path):
    workspace = Path.cwd() / "tmp" / f"deepagents-exec-{uuid.uuid4().hex[:8]}"
    workspace.mkdir()
    try:
        target = workspace / "cmd.txt"
        service = AgentSessionService(AgentSessionRepository(str(tmp_path / "agents.db")))
        session = service.create_session(AgentSessionCreate(title="deepagents execute", project_path=str(workspace)))
        responses = iter(
            [
                json.dumps(
                    {
                        "tool": "execute",
                        "arguments": {
                            "command": "python -c \"from pathlib import Path; Path('cmd.txt').write_text('ok', encoding='utf-8')\"",
                        },
                    },
                    ensure_ascii=False,
                ),
                json.dumps({"type": "final", "content": "命令已执行。"}, ensure_ascii=False),
            ]
        )

        async def model_call(_messages):
            return next(responses)

        service.model_call = model_call
        result = asyncio.run(service.prompt(session.id, AgentPromptRequest(content="运行一个命令写入 cmd.txt")))

        assert result.status == "waiting_approval"
        assert not target.exists()
        assert any(part.type == "permission" and part.status == "pending" for part in result.parts)
        assert not any(part.type == "command" for part in result.parts)
    finally:
        shutil.rmtree(workspace, ignore_errors=True)


def test_deepagents_runtime_passes_no_custom_tools(monkeypatch, tmp_path: Path):
    captured: dict[str, object] = {}

    def fake_build_runtime(config):
        captured["tools"] = config.tools
        captured["interrupt_on"] = config.interrupt_on
        captured["project_path"] = config.project_path
        captured["permissions"] = config.permissions
        return object()

    monkeypatch.setattr("agent_session.deepagents_runtime.build_deep_agent_runtime", fake_build_runtime)

    async def model_call(_messages):
        return json.dumps({"type": "final", "content": "ok"}, ensure_ascii=False)

    runner = DeepAgentsSessionRunner(repository=object(), notify_event=lambda *_args: None, model_call=model_call)
    graph = asyncio.run(
        runner._build_graph(
            {
                "id": "session",
                "project_path": str(tmp_path),
                "provider": "",
                "model": None,
                "metadata": {},
            },
            "测试官方内置工具链",
        )
    )

    assert graph is not None
    assert captured["tools"] == []
    assert captured["interrupt_on"] is None
    assert captured["project_path"] == str(tmp_path)
    assert captured["permissions"]


def test_deepagents_backend_routes_internal_files_to_state_backend(tmp_path: Path):
    from deepagents.backends import CompositeBackend, LocalShellBackend, StateBackend

    backend = build_deepagents_backend(str(tmp_path))

    assert isinstance(backend, CompositeBackend)
    assert isinstance(backend.default, LocalShellBackend)
    assert isinstance(backend.routes[WORKSPACE_BACKEND_ROUTE], LocalShellBackend)
    for route in EPHEMERAL_BACKEND_ROUTES:
        assert isinstance(backend.routes[route], StateBackend)
    assert isinstance(backend.routes[FALLBACK_STATE_BACKEND_ROUTE], StateBackend)


def test_deepagents_runtime_resolves_optional_interrupt_config():
    assert resolve_interrupt_on({}) is None
    assert resolve_interrupt_on({"deepagents_interrupt_on": True}) == {"write_file": True, "edit_file": True, "execute": True}
    custom = {"write_file": False, "edit_file": True}
    assert resolve_interrupt_on({"deepagents_interrupt_on": custom}) == custom


def test_agent_session_deepagents_interrupt_creates_permission_card(tmp_path: Path):
    workspace = Path.cwd() / "tmp" / f"deepagents-hitl-{uuid.uuid4().hex[:8]}"
    workspace.mkdir()
    try:
        target = workspace / "hello.txt"
        target.write_text("hello\n", encoding="utf-8")
        service = AgentSessionService(AgentSessionRepository(str(tmp_path / "agents.db")))
        session = service.create_session(AgentSessionCreate(title="deepagents hitl", project_path=str(workspace)))
        responses = iter(
            [
                json.dumps(
                    {
                        "tool": "edit_file",
                        "arguments": {
                            "file_path": "/workspace/hello.txt",
                            "old_string": "hello\n",
                            "new_string": "hi\n",
                        },
                    },
                    ensure_ascii=False,
                ),
                json.dumps({"type": "final", "content": "已完成。"}, ensure_ascii=False),
            ]
        )

        async def model_call(_messages):
            return next(responses)

        service.model_call = model_call
        result = asyncio.run(service.prompt(session.id, AgentPromptRequest(content="把 hello 改成 hi")))

        assert result.status == "waiting_approval"
        permission = next(part for part in result.parts if part.type == "permission")
        assert permission.status == "pending"
        assert permission.payload["official_hitl"] is True
        assert permission.payload["tool"] == "edit_file"
        assert target.read_text(encoding="utf-8") == "hello\n"

        approved = asyncio.run(service.approve_permission_async(permission.id, True))

        assert approved.status == "completed"
        assert target.read_text(encoding="utf-8") == "hi\n"
    finally:
        shutil.rmtree(workspace, ignore_errors=True)


def test_agent_session_hitl_decision_validation_accepts_edit_and_respond(tmp_path: Path):
    service = AgentSessionService(AgentSessionRepository(str(tmp_path / "agents.db")))
    session = service.create_session(AgentSessionCreate(title="hitl decisions", project_path=str(Path.cwd())))
    service.repository.update_session(session.id, provider=None, model=None, metadata={"runtime": "deepagents"})
    part = service.repository.add_part(
        session.id,
        "permission",
        status="pending",
        title="Confirm tools",
        content="Confirm tools",
        payload={
            "official_hitl": True,
            "action_requests": [
                {"name": "edit_file", "args": {"file_path": "/a.py"}},
                {"name": "ask_user", "args": {"question": "Color?"}},
            ],
            "actions": [
                {"name": "edit_file", "args": {"file_path": "/a.py"}, "allowed_decisions": ["approve", "edit", "reject"]},
                {"name": "ask_user", "args": {"question": "Color?"}, "allowed_decisions": ["respond", "reject"]},
            ],
        },
    )

    result = asyncio.run(
        service.decide_permission_async(
            part["id"],
            [
                {"type": "edit", "edited_action": {"name": "edit_file", "args": {"file_path": "/b.py"}}},
                {"type": "respond", "message": "Blue."},
            ],
        )
    )

    updated = next(item for item in result.parts if item.id == part["id"])
    assert updated.status == "approved"
    assert updated.payload["decisions"][0]["edited_action"]["args"]["file_path"] == "/b.py"
    assert updated.payload["decisions"][1]["message"] == "Blue."


def test_agent_session_hitl_decision_validation_rejects_bad_batches(tmp_path: Path):
    service = AgentSessionService(AgentSessionRepository(str(tmp_path / "agents.db")))
    session = service.create_session(AgentSessionCreate(title="hitl decisions", project_path=str(Path.cwd())))
    service.repository.update_session(session.id, provider=None, model=None, metadata={"runtime": "deepagents"})
    part = service.repository.add_part(
        session.id,
        "permission",
        status="pending",
        title="Confirm tools",
        content="Confirm tools",
        payload={
            "official_hitl": True,
            "action_requests": [{"name": "ask_user", "args": {}}],
            "actions": [{"name": "ask_user", "args": {}, "allowed_decisions": ["respond"]}],
        },
    )

    with pytest.raises(ValueError, match="require a message"):
        asyncio.run(service.decide_permission_async(part["id"], [{"type": "respond"}]))

    with pytest.raises(ValueError, match="Expected 1 HITL decision"):
        asyncio.run(service.decide_permission_async(part["id"], [{"type": "respond", "message": "A"}, {"type": "respond", "message": "B"}]))
