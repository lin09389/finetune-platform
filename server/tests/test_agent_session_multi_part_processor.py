from __future__ import annotations

import asyncio
import json
import shutil
import uuid
from pathlib import Path

from agent_session.models import AgentPromptRequest, AgentSessionCreate
from agent_session.repository import AgentSessionRepository
from agent_session.service import AgentSessionService


def _workspace_tmp(name: str) -> Path:
    path = Path.cwd() / "tmp" / f"{name}-{uuid.uuid4().hex[:8]}"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _service(tmp_path: Path) -> AgentSessionService:
    return AgentSessionService(AgentSessionRepository(str(tmp_path / f"agent-multipart-{uuid.uuid4().hex}.db")))


def test_text_and_multiple_read_tools_are_recorded_in_order(tmp_path: Path):
    workspace = Path.cwd()
    run_dir = _workspace_tmp("agent-multipart-read")
    first = run_dir / "a.txt"
    second = run_dir / "b.txt"
    first.write_text("a", encoding="utf-8")
    second.write_text("b", encoding="utf-8")
    first_rel = first.relative_to(workspace).as_posix()
    second_rel = second.relative_to(workspace).as_posix()
    service = _service(tmp_path)
    session = service.create_session(AgentSessionCreate(title="multi read", project_path=str(workspace)))
    responses = iter(
        [
            "我先读取两个文件。\n"
            + json.dumps(
                [
                    {"tool": "read", "arguments": {"path": first_rel}},
                    {"tool": "read", "arguments": {"path": second_rel}},
                ],
                ensure_ascii=False,
            ),
            {"tool": "finalize", "arguments": {"summary": "两个文件都已读取。"}},
        ]
    )

    async def model_call(_messages):
        item = next(responses)
        return item if isinstance(item, str) else json.dumps(item, ensure_ascii=False)

    service.model_call = model_call
    service.processor.max_iterations = 4
    try:
        result = asyncio.run(service.prompt(session.id, AgentPromptRequest(content="读取两个文件")))

        visible_parts = [part for part in result.parts if not (part.type == "text" and part.title == "请求")]
        assert [part.type for part in visible_parts[:5]] == ["text", "tool_call", "tool_result", "tool_call", "tool_result"]
        assert result.status == "completed"
        assert result.parts[-1].type == "summary"
    finally:
        shutil.rmtree(run_dir, ignore_errors=True)


def test_content_block_tool_use_response_executes_like_transcript_parts(tmp_path: Path):
    workspace = Path.cwd()
    run_dir = _workspace_tmp("agent-content-blocks")
    target = run_dir / "block.txt"
    target.write_text("content block", encoding="utf-8")
    rel = target.relative_to(workspace).as_posix()
    service = _service(tmp_path)
    session = service.create_session(AgentSessionCreate(title="content blocks", project_path=str(workspace)))
    responses = iter(
        [
            {
                "content": [
                    {"type": "text", "text": "我先读一下目标文件。"},
                    {"type": "tool_use", "name": "read", "input": {"path": rel}},
                ]
            },
            {"tool": "finalize", "arguments": {"summary": "目标文件已读取。"}},
        ]
    )

    async def model_call(_messages):
        return json.dumps(next(responses), ensure_ascii=False)

    service.model_call = model_call
    service.processor.max_iterations = 4
    try:
        result = asyncio.run(service.prompt(session.id, AgentPromptRequest(content="读取文件")))
        visible_parts = [part for part in result.parts if not (part.type == "text" and part.title == "请求")]

        assert [part.type for part in visible_parts[:3]] == ["text", "tool_call", "tool_result"]
        assert visible_parts[0].content == "我先读一下目标文件。"
        assert result.status == "completed"
    finally:
        shutil.rmtree(run_dir, ignore_errors=True)


def test_pending_patch_stops_later_command_in_same_response(tmp_path: Path):
    workspace = Path.cwd()
    run_dir = _workspace_tmp("agent-multipart-approval")
    target = run_dir / "manual.py"
    target.write_text("VALUE = 0\n", encoding="utf-8")
    rel = target.relative_to(workspace).as_posix()
    service = _service(tmp_path)
    session = service.create_session(
        AgentSessionCreate(title="approval", project_path=str(workspace), autonomy_mode="confirm_all")
    )
    raw = json.dumps(
        [
            {"tool": "collect_context", "arguments": {"read": [rel]}},
            {"tool": "patch", "arguments": {"payload": {"files": [{"path": rel, "content": "VALUE = 1\n"}]}}},
            {"tool": "bash_command", "arguments": {"payload": {"command": ["python", "-m", "py_compile", rel]}}},
        ],
        ensure_ascii=False,
    )

    async def model_call(_messages):
        return raw

    service.model_call = model_call
    service.processor.max_iterations = 2
    try:
        result = asyncio.run(service.prompt(session.id, AgentPromptRequest(content="确认模式修改并验证")))

        assert result.status == "waiting_approval"
        assert next(part for part in result.parts if part.type == "diff").status == "pending"
        assert not any(part.type == "command" for part in result.parts)
        assert target.read_text(encoding="utf-8") == "VALUE = 0\n"
    finally:
        shutil.rmtree(run_dir, ignore_errors=True)


def test_auto_patch_then_command_can_execute_in_same_response(tmp_path: Path):
    workspace = Path.cwd()
    run_dir = _workspace_tmp("agent-multipart-auto")
    target = run_dir / "auto.py"
    rel = target.relative_to(workspace).as_posix()
    service = _service(tmp_path)
    session = service.create_session(AgentSessionCreate(title="auto", project_path=str(workspace)))
    responses = iter(
        [
            json.dumps(
                [
                    {"tool": "collect_context", "arguments": {"read": [rel]}},
                    {"tool": "patch", "arguments": {"payload": {"files": [{"path": rel, "content": "VALUE = 1\n"}]}}},
                    {"tool": "bash_command", "arguments": {"payload": {"command": ["python", "-m", "py_compile", rel]}}},
                ],
                ensure_ascii=False,
            ),
            {"tool": "finalize", "arguments": {"summary": "补丁和验证都完成。"}},
        ]
    )

    async def model_call(_messages):
        item = next(responses)
        return item if isinstance(item, str) else json.dumps(item, ensure_ascii=False)

    service.model_call = model_call
    service.processor.max_iterations = 4
    try:
        result = asyncio.run(service.prompt(session.id, AgentPromptRequest(content="写入并验证")))
        diff = next(part for part in result.parts if part.type == "diff")
        command = next(part for part in result.parts if part.type == "command")

        assert result.status == "completed"
        assert diff.status == "executed"
        assert command.status == "completed"
        assert command.payload["exit_code"] == 0
        assert target.read_text(encoding="utf-8") == "VALUE = 1\n"
    finally:
        shutil.rmtree(run_dir, ignore_errors=True)


def test_finalize_ignores_later_tool_requests(tmp_path: Path):
    workspace = Path.cwd()
    run_dir = _workspace_tmp("agent-multipart-finalize")
    target = run_dir / "ignored.py"
    rel = target.relative_to(workspace).as_posix()
    service = _service(tmp_path)
    session = service.create_session(AgentSessionCreate(title="finalize", project_path=str(workspace)))
    raw = json.dumps(
        [
            {"tool": "finalize", "arguments": {"summary": "无需修改。"}},
            {"tool": "patch", "arguments": {"payload": {"files": [{"path": rel, "content": "VALUE = 1\n"}]}}},
        ],
        ensure_ascii=False,
    )

    async def model_call(_messages):
        return raw

    service.model_call = model_call
    result = asyncio.run(service.prompt(session.id, AgentPromptRequest(content="只总结")))
    events = service.list_events(session.id)

    assert result.status == "completed"
    assert result.parts[-1].type == "summary"
    assert not target.exists()
    assert any(event["event_type"] == "tool_call_ignored" for event in events)
