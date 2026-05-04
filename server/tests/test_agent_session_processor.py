from __future__ import annotations

import json
import asyncio
import shutil
import uuid
from pathlib import Path

from agent_session.models import AgentPromptRequest, AgentSessionCreate
from agent_session.repository import AgentSessionRepository
from agent_session.service import AgentSessionService


def test_agent_session_runs_read_tool_and_finalizes(tmp_path: Path):
    workspace = Path.cwd()
    run_dir = workspace / "tmp" / f"agent-session-{uuid.uuid4().hex[:8]}"
    run_dir.mkdir(parents=True, exist_ok=True)
    target = run_dir / "hello.txt"
    target.write_text("hello", encoding="utf-8")
    service = AgentSessionService(AgentSessionRepository(str(tmp_path / "agent_sessions.db")))
    session = service.create_session(AgentSessionCreate(title="read", project_path=str(workspace)))
    rel = target.relative_to(workspace).as_posix()
    responses = iter(
        [
            {"tool": "read", "arguments": {"path": rel}},
            {"tool": "finalize", "arguments": {"summary": "已读取文件。"}},
        ]
    )

    async def model_call(_messages):
        return json.dumps(next(responses), ensure_ascii=False)

    service.processor.max_iterations = 4
    service.model_call = model_call
    try:
        result = asyncio.run(service.prompt(session.id, AgentPromptRequest(content="读取 hello.txt")))

        assert result.status == "completed"
        assert [part.type for part in result.parts] == ["text", "tool_call", "tool_result", "tool_call", "summary"]
        assert result.parts[-1].content == "已读取文件。"
        restored = service.get_session(session.id)
        assert restored.parts[-1].type == "summary"
    finally:
        shutil.rmtree(run_dir, ignore_errors=True)


def test_patch_tool_creates_pending_diff_part(tmp_path: Path):
    workspace = Path.cwd()
    run_dir = workspace / "tmp" / f"agent-patch-{uuid.uuid4().hex[:8]}"
    run_dir.mkdir(parents=True, exist_ok=True)
    target = run_dir / "feature.py"
    target.write_text("VALUE = 1\n", encoding="utf-8")
    service = AgentSessionService(AgentSessionRepository(str(tmp_path / "agent_patch.db")))
    session = service.create_session(AgentSessionCreate(title="patch", project_path=str(workspace)))
    rel = target.relative_to(workspace).as_posix()
    responses = iter(
        [
            {"tool": "collect_context", "arguments": {"read": [rel]}},
            {
                "tool": "patch",
                "arguments": {
                    "title": "更新 feature",
                    "payload": {
                        "files": [{"path": rel, "content": "VALUE = 2\n"}],
                    },
                },
            },
            {"tool": "finalize", "arguments": {"summary": "已更新 feature。"}},
        ]
    )

    async def model_call(_messages):
        return json.dumps(next(responses), ensure_ascii=False)

    service.model_call = model_call
    try:
        result = asyncio.run(service.prompt(session.id, AgentPromptRequest(content="修改 feature.py")))
        diff = next(part for part in result.parts if part.type == "diff")

        assert result.status == "completed"
        assert diff.type == "diff"
        assert diff.status == "executed"
        assert target.read_text(encoding="utf-8") == "VALUE = 2\n"
    finally:
        shutil.rmtree(run_dir, ignore_errors=True)


def test_whitelisted_command_executes_and_records_command_part(tmp_path: Path):
    workspace = Path.cwd()
    run_dir = workspace / "tmp" / f"agent-command-{uuid.uuid4().hex[:8]}"
    run_dir.mkdir(parents=True, exist_ok=True)
    target = run_dir / "ok.py"
    target.write_text("VALUE = 1\n", encoding="utf-8")
    service = AgentSessionService(AgentSessionRepository(str(tmp_path / "agent_command.db")))
    session = service.create_session(AgentSessionCreate(title="command", project_path=str(workspace)))
    rel = target.relative_to(workspace).as_posix()
    responses = iter(
        [
            {"tool": "detect_project_commands", "arguments": {}},
            {"tool": "bash_command", "arguments": {"payload": {"command": ["python", "-m", "py_compile", rel]}}},
            {"tool": "finalize", "arguments": {"summary": "验证通过。"}},
        ]
    )

    async def model_call(_messages):
        return json.dumps(next(responses), ensure_ascii=False)

    service.processor.max_iterations = 4
    service.model_call = model_call
    try:
        result = asyncio.run(service.prompt(session.id, AgentPromptRequest(content="运行验证")))
        command = next(part for part in result.parts if part.type == "command")

        assert result.status == "completed"
        assert command.status == "completed"
        assert command.payload["exit_code"] == 0
    finally:
        shutil.rmtree(run_dir, ignore_errors=True)


def test_non_allowlisted_command_is_blocked(tmp_path: Path):
    service = AgentSessionService(AgentSessionRepository(str(tmp_path / "agent_blocked_command.db")))
    session = service.create_session(AgentSessionCreate(title="blocked", project_path=str(Path.cwd())))
    responses = iter(
        [
            {"tool": "bash_command", "arguments": {"payload": {"command": ["git", "commit", "-m", "no"]}}},
        ]
    )

    async def model_call(_messages):
        return json.dumps(next(responses), ensure_ascii=False)

    service.model_call = model_call
    result = asyncio.run(service.prompt(session.id, AgentPromptRequest(content="提交代码")))
    command = result.parts[-1]
    blocked_command = next(part for part in result.parts if part.type == "command")

    assert result.status == "needs_manual_review"
    assert command.type == "summary"
    assert blocked_command.status == "blocked"
    assert "Destructive" in command.content or "白名单" in command.content


def test_command_before_detect_gets_guidance_and_continues(tmp_path: Path):
    workspace = Path.cwd()
    run_dir = workspace / "tmp" / f"agent-command-guidance-{uuid.uuid4().hex[:8]}"
    run_dir.mkdir(parents=True, exist_ok=True)
    target = run_dir / "ok.py"
    target.write_text("VALUE = 1\n", encoding="utf-8")
    service = AgentSessionService(AgentSessionRepository(str(tmp_path / "agent_command_guidance.db")))
    session = service.create_session(AgentSessionCreate(title="command guidance", project_path=str(workspace)))
    rel = target.relative_to(workspace).as_posix()
    responses = iter(
        [
            {"tool": "bash_command", "arguments": {"payload": {"command": ["python", "-m", "py_compile", rel]}}},
            {"tool": "detect_project_commands", "arguments": {}},
            {"tool": "bash_command", "arguments": {"payload": {"command": ["python", "-m", "py_compile", rel]}}},
            {"tool": "finalize", "arguments": {"summary": "验证通过。"}},
        ]
    )

    async def model_call(_messages):
        return json.dumps(next(responses), ensure_ascii=False)

    service.processor.max_iterations = 6
    service.model_call = model_call
    try:
        result = asyncio.run(service.prompt(session.id, AgentPromptRequest(content="运行验证")))
        guidance = next(part for part in result.parts if part.type == "tool_result" and "识别验证命令" in (part.title or ""))
        command = next(part for part in result.parts if part.type == "command")

        assert result.status == "completed"
        assert guidance.status == "completed"
        assert command.status == "completed"
    finally:
        shutil.rmtree(run_dir, ignore_errors=True)


def test_collect_context_infers_source_file_before_patch(tmp_path: Path):
    workspace = Path.cwd()
    run_dir = workspace / "tmp" / f"agent-source-guidance-{uuid.uuid4().hex[:8]}"
    src_dir = run_dir / "src"
    src_dir.mkdir(parents=True, exist_ok=True)
    target = src_dir / "feature.ts"
    target.write_text("export const VALUE = 1;\n", encoding="utf-8")
    service = AgentSessionService(AgentSessionRepository(str(tmp_path / "agent_source_guidance.db")))
    session = service.create_session(AgentSessionCreate(title="source guidance", project_path=str(workspace)))
    rel = target.relative_to(workspace).as_posix()
    responses = iter(
        [
            {"tool": "collect_context", "arguments": {}},
            {"tool": "patch", "arguments": {"payload": {"files": [{"path": rel, "content": "export const VALUE = 2;\n"}]}}},
            {"tool": "finalize", "arguments": {"summary": "源码修改完成。"}},
        ]
    )

    async def model_call(_messages):
        return json.dumps(next(responses), ensure_ascii=False)

    service.processor.max_iterations = 8
    service.model_call = model_call
    try:
        result = asyncio.run(service.prompt(session.id, AgentPromptRequest(content="修改 feature.ts")))
        context = next(part for part in result.parts if part.type == "tool_result" and part.title == "批量收集上下文")
        diff = next(part for part in result.parts if part.type == "diff")

        assert result.status == "completed"
        assert rel in result.metadata["state"]["touched_paths"]
        assert context.payload["files"]
        assert diff.status == "executed"
        assert target.read_text(encoding="utf-8") == "export const VALUE = 2;\n"
    finally:
        shutil.rmtree(run_dir, ignore_errors=True)
