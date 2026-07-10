from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
from agent_session.models import AgentSessionCreate
from agent_session.project_chat import DeepAgentsProjectChatRunner, can_use_deepagents_project_chat
from agent_session.repository import AgentSessionRepository
from agent_session.service import AgentSessionService


def test_project_chat_can_read_workspace_files(tmp_path: Path):
    (tmp_path / "app.py").write_text("VALUE = 'project-visible'\n", encoding="utf-8")
    responses = iter(
        [
            json.dumps({"tool": "read_file", "arguments": {"file_path": "/workspace/app.py"}}, ensure_ascii=False),
            json.dumps({"type": "final", "content": "看到了 app.py 里的 project-visible。"}, ensure_ascii=False),
        ]
    )

    async def model_call(_messages):
        return next(responses)

    runner = DeepAgentsProjectChatRunner(
        provider=None,
        model=None,
        project_path=str(tmp_path),
        model_call=model_call,
    )
    result = asyncio.run(runner.run([{"role": "user", "content": "这个项目里 app.py 是什么？"}]))

    assert "project-visible" in result.content
    assert result.metadata["project_chat"] is True
    assert "read_file" in result.metadata["project_chat_tools"]


def test_project_chat_can_list_workspace_root(tmp_path: Path):
    (tmp_path / "visible.py").write_text("VALUE = 1\n", encoding="utf-8")
    calls: list[list[dict[str, str]]] = []
    responses = iter(
        [
            json.dumps({"tool": "ls", "arguments": {"path": "/workspace"}}, ensure_ascii=False),
            json.dumps({"type": "final", "content": "目录读取完成。"}, ensure_ascii=False),
        ]
    )

    async def model_call(messages):
        calls.append(messages)
        return next(responses)

    runner = DeepAgentsProjectChatRunner(
        provider=None,
        model=None,
        project_path=str(tmp_path),
        model_call=model_call,
    )
    result = asyncio.run(runner.run([{"role": "user", "content": "列出项目目录"}]))

    assert "visible.py" in result.content
    assert len(calls) == 2
    assert any("visible.py" in message["content"] for message in calls[-1])
    assert not any("permission denied" in message["content"].lower() for message in calls[-1])


def test_project_chat_denies_workspace_writes(tmp_path: Path):
    target = tmp_path / "app.py"
    target.write_text("original\n", encoding="utf-8")
    responses = iter(
        [
            json.dumps(
                {
                    "tool": "write_file",
                    "arguments": {"file_path": "/workspace/app.py", "content": "changed\n"},
                },
                ensure_ascii=False,
            ),
            json.dumps({"type": "final", "content": "普通聊天不能修改项目，需要升级为 Agent Task。"}, ensure_ascii=False),
        ]
    )

    async def model_call(_messages):
        return next(responses)

    runner = DeepAgentsProjectChatRunner(
        provider=None,
        model=None,
        project_path=str(tmp_path),
        model_call=model_call,
    )
    result = asyncio.run(runner.run([{"role": "user", "content": "改一下 app.py"}]))

    assert target.read_text(encoding="utf-8") == "original\n"
    assert "升级为 Agent Task" in result.content
    assert "write_file" in result.metadata["project_chat_tools"]


def test_project_chat_reads_injected_context_file_data(tmp_path: Path):
    calls: list[list[dict[str, str]]] = []
    responses = iter(
        [
            json.dumps({"tool": "read_file", "arguments": {"file_path": "/context/task.md"}}, ensure_ascii=False),
            json.dumps({"type": "final", "content": "已读取上下文。"}, ensure_ascii=False),
        ]
    )

    async def model_call(messages):
        calls.append(messages)
        return next(responses)

    runner = DeepAgentsProjectChatRunner(
        provider=None,
        model=None,
        project_path=str(tmp_path),
        model_call=model_call,
    )
    result = asyncio.run(
        runner.run(
            [{"role": "user", "content": "读取任务上下文"}],
            context_files={
                "/context/task.md": "SENTINEL_PROJECT_CHAT_CONTEXT",
                "/task.md": "SENTINEL_PROJECT_CHAT_CONTEXT",
            },
        )
    )

    assert "SENTINEL_PROJECT_CHAT_CONTEXT" in result.content
    assert len(calls) == 2
    assert any("SENTINEL_PROJECT_CHAT_CONTEXT" in message["content"] for message in calls[-1])


def test_project_chat_only_auto_enables_for_official_provider_model():
    assert can_use_deepagents_project_chat("deepseek", "deepseek-v4-flash")
    assert can_use_deepagents_project_chat("openrouter", "z-ai/glm-5.1")
    assert not can_use_deepagents_project_chat("minimax", "abab6.5")


def test_agent_task_context_event_keeps_absolute_path_out_of_timeline(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from api import workspace as workspace_api

    server_dir = tmp_path / "server"
    server_dir.mkdir()
    workspace_path = tmp_path / "timeline-visible-label"
    workspace_path.mkdir()
    monkeypatch.setattr(workspace_api.settings, "base_dir", server_dir)
    monkeypatch.setattr(workspace_api.settings, "agent_default_project_path", None)
    monkeypatch.setattr(
        workspace_api,
        "workspaces",
        {"ws_timeline": {"id": "ws_timeline", "name": "Timeline", "local_path": str(workspace_path)}},
    )
    service = AgentSessionService(AgentSessionRepository(str(tmp_path / "agents.db")))

    session = service.create_session(
        AgentSessionCreate(workspace_id="ws_timeline", task_mode="build", project_path=str(tmp_path / "ignored"))
    )
    event = next(item for item in service.list_events(session.id) if item["event_type"] == "task_context_initialized")
    chunk = service.build_stream_chunk(event)

    assert event["message"] == "Task context initialized"
    assert event["payload"]["workspace_id"] == "ws_timeline"
    assert event["payload"]["workspace_label"] == "timeline-visible-label"
    assert event["payload"]["task_mode"] == "build"
    assert str(workspace_path.resolve()) not in json.dumps(event, ensure_ascii=False)
    assert chunk["payload"]["workspace_label"] == "timeline-visible-label"
