from __future__ import annotations

import asyncio
import json
import shutil
import uuid
from pathlib import Path

import pytest
from agent_session.models import AgentSessionCreate
from agent_session.repository import AgentSessionRepository
from agent_session.runtime import prepare_deepagents_files
from agent_session.service import AgentSessionService

from context.budget import ContextBudget
from context.deepagents import build_deepagents_context_pack
from context.pack import ContextPack, ContextSource


def test_prepare_deepagents_files_repairs_legacy_checkpoint_values():
    class Snapshot:
        values = {
            "files": {
                "/context/legacy.md": "LEGACY_TEXT",
                "/context/typed.md": {"content": "TYPED_TEXT", "encoding": "utf-8"},
            }
        }

    class Graph:
        checkpointer = object()

        async def aget_state(self, _config):
            return Snapshot()

    files = asyncio.run(
        prepare_deepagents_files(
            Graph(),
            {"configurable": {"thread_id": "legacy"}},
            {"/context/task.md": "CURRENT_TEXT"},
        )
    )

    assert files["/context/legacy.md"] == {"content": "LEGACY_TEXT", "encoding": "utf-8"}
    assert files["/context/typed.md"] == {"content": "TYPED_TEXT", "encoding": "utf-8"}
    assert files["/context/task.md"] == {"content": "CURRENT_TEXT", "encoding": "utf-8"}


@pytest.mark.asyncio
async def test_context_pack_offloads_editor_context_to_virtual_files():
    pack = await build_deepagents_context_pack(
        goal="修复当前文件的问题",
        active_context={
            "file_path": "server/example.py",
            "cursor": {"line": 12, "column": 4},
            "selection": {"text": "def broken():\n    pass\n"},
        },
        explicit_context=[{"label": "helper", "path": "server/helper.py", "content": "def helper():\n    return 1\n"}],
        project_path=None,
    )

    assert "/context/task.md" in pack.files
    assert "/task.md" in pack.files
    assert "/context/editor/active-file.md" in pack.files
    assert "/editor/active-file.md" in pack.files
    assert "/active-file.md" in pack.files
    assert any(path.startswith("/context/mentions/") for path in pack.files)
    assert "def broken" not in pack.prompt
    assert "【启动速览】" in pack.prompt
    assert "server/example.py" in pack.prompt
    assert "@helper" in pack.prompt
    assert "server/helper.py" in pack.prompt
    assert "read_file/grep/glob" in pack.prompt
    assert "优先读取 `/context/task.md`" not in pack.prompt
    assert "只有需要完整原文" in pack.prompt
    assert pack.metadata["strategy"] == "deepagents_kickoff_brief_v1"
    assert pack.metadata["kickoff_brief_chars"] > 0
    assert pack.metadata["kickoff_brief_tokens"] > 0
    assert pack.metadata["virtual_file_count"] == len(pack.files)
    assert pack.metadata["virtual_file_tokens"] > 0


@pytest.mark.asyncio
async def test_context_pack_splits_retrieval_context_by_kind(monkeypatch):
    class FakeBuilder:
        async def build(self, **_kwargs):
            return ContextPack(
                query="解释项目",
                sources=[
                    ContextSource(id="memory:1", kind="memory", content="用户偏好：回答要简洁", score=0.9, tokens=12),
                    ContextSource(
                        id="memory:2",
                        kind="memory",
                        content="用户偏好：使用 Windows PowerShell",
                        score=0.85,
                        tokens=12,
                        metadata={
                            "memory_path": "/memories/preferences.md",
                            "path": "/memories/preferences.md",
                            "scope": "user",
                            "namespace": "default",
                            "version": 2,
                        },
                    ),
                    ContextSource(id="project:1", kind="project", content="server/agent_session/service.py 负责会话", score=0.8, tokens=18, metadata={"path": "server/agent_session/service.py"}),
                    ContextSource(id="knowledge:1", kind="knowledge", content="DeepAgents 使用文件系统管理长上下文", score=0.7, tokens=16),
                ],
                context_text="combined",
                budget=ContextBudget(max_tokens=3200, used_tokens=46),
            )

    monkeypatch.setattr("context.deepagents.get_context_builder", lambda: FakeBuilder())

    pack = await build_deepagents_context_pack(
        goal="解释项目",
        active_context=None,
        explicit_context=[],
        project_path="C:/workspace/project",
    )

    assert "/context/retrieval/index.md" in pack.files
    assert "/context/retrieval/memory.md" in pack.files
    assert "/context/retrieval/project.md" in pack.files
    assert "/context/retrieval/knowledge.md" in pack.files
    assert "用户偏好" in pack.files["/context/retrieval/memory.md"]
    assert "/memories/preferences.md" in pack.files["/context/retrieval/memory.md"]
    assert "file-memory snippets" in pack.files["/context/retrieval/memory.md"]
    assert "read full files" in pack.files["/context/retrieval/index.md"]
    assert "server/agent_session/service.py" in pack.files["/context/retrieval/project.md"]
    assert "Retrieved context summary" in pack.prompt
    assert "/memories/preferences.md" in pack.prompt
    assert "server/agent_session/service.py" in pack.prompt
    assert "DeepAgents 使用文件系统管理长上下文" in pack.prompt


@pytest.mark.asyncio
async def test_context_pack_keeps_long_retrieval_content_out_of_prompt(monkeypatch):
    long_project_context = "IMPORTANT_START " + ("implementation detail " * 500) + " IMPORTANT_END"

    class FakeBuilder:
        async def build(self, **_kwargs):
            return ContextPack(
                query="解释长上下文",
                sources=[
                    ContextSource(
                        id="project:long",
                        kind="project",
                        content=long_project_context,
                        score=0.95,
                        tokens=900,
                        metadata={"path": "server/context/deepagents.py"},
                    )
                ],
                context_text="combined",
                budget=ContextBudget(max_tokens=3200, used_tokens=900),
            )

    monkeypatch.setattr("context.deepagents.get_context_builder", lambda: FakeBuilder())

    pack = await build_deepagents_context_pack(
        goal="解释长上下文",
        active_context=None,
        explicit_context=[],
        project_path="C:/workspace/project",
    )

    assert "IMPORTANT_START" in pack.prompt
    assert "IMPORTANT_END" not in pack.prompt
    assert "IMPORTANT_END" in pack.files["/context/retrieval/project.md"]
    assert "server/context/deepagents.py" in pack.prompt
    assert len(pack.metadata["files"]) == pack.metadata["virtual_file_count"]


def test_agent_session_deepagents_reads_offloaded_context_file(tmp_path: Path):
    workspace = Path.cwd() / "tmp" / f"deepagents-context-{uuid.uuid4().hex[:8]}"
    workspace.mkdir()
    try:
        pack = asyncio.run(
            build_deepagents_context_pack(
                goal="根据当前选区说明问题",
                active_context={
                    "file_path": "server/example.py",
                    "cursor": {"line": 1, "column": 1},
                    "selection": {"text": "SENTINEL_ACTIVE_CONTEXT"},
                },
                explicit_context=[],
                project_path=None,
            )
        )
        responses = iter(
            [
                json.dumps({"tool": "read_file", "arguments": {"file_path": "/context/editor/active-file.md"}}, ensure_ascii=False),
                json.dumps({"type": "final", "content": "已读取 active context。"}, ensure_ascii=False),
            ]
        )

        async def model_call(_messages):
            return next(responses)

        service = AgentSessionService(AgentSessionRepository(str(tmp_path / "agents.db")), model_call=model_call)
        session = service.create_session(AgentSessionCreate(title="context engineering", project_path=str(workspace)))
        result = asyncio.run(service.deepagents_runner.run_prompt(session.id, pack.prompt, context_files=pack.files))

        assert result["status"] == "completed"
        tool_parts = [part for part in result["parts"] if part["type"] == "tool_call"]
        assert any(part["status"] == "completed" for part in tool_parts)
        assert any("SENTINEL_ACTIVE_CONTEXT" in (part.get("content") or "") for part in tool_parts)
        assert any(part["type"] == "summary" and "active context" in (part.get("content") or "") for part in result["parts"])
    finally:
        shutil.rmtree(workspace, ignore_errors=True)
