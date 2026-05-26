from __future__ import annotations

import asyncio
import json
from pathlib import Path

from agent_session.project_chat import DeepAgentsProjectChatRunner, can_use_deepagents_project_chat


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


def test_project_chat_only_auto_enables_for_official_provider_model():
    assert can_use_deepagents_project_chat("deepseek", "deepseek-chat")
    assert can_use_deepagents_project_chat("openrouter", "z-ai/glm-5.1")
    assert not can_use_deepagents_project_chat("minimax", "abab6.5")
