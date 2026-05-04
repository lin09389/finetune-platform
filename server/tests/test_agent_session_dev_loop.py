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
    return AgentSessionService(AgentSessionRepository(str(tmp_path / f"agent-{uuid.uuid4().hex}.db")))


def test_safe_auto_patch_command_finalize_loop(tmp_path: Path):
    workspace = Path.cwd()
    run_dir = _workspace_tmp("agent-loop")
    target = run_dir / "smoke.py"
    rel = target.relative_to(workspace).as_posix()
    service = _service(tmp_path)
    session = service.create_session(
        AgentSessionCreate(title="loop", project_path=str(workspace), autonomy_mode="safe_auto")
    )
    responses = iter(
        [
            {"tool": "collect_context", "arguments": {"read": []}},
            {"tool": "patch", "arguments": {"payload": {"files": [{"path": rel, "content": "VALUE = 1\n"}]}}},
            {"tool": "bash_command", "arguments": {"payload": {"command": ["python", "-m", "py_compile", rel]}}},
            {"tool": "finalize", "arguments": {"summary": "smoke 文件已创建并通过 py_compile。"}},
        ]
    )

    async def model_call(_messages):
        return json.dumps(next(responses), ensure_ascii=False)

    service.model_call = model_call
    service.processor.max_iterations = 6
    try:
        result = asyncio.run(service.prompt(session.id, AgentPromptRequest(content="新增 smoke 文件并验证")))
        diff = next(part for part in result.parts if part.type == "diff")
        command = next(part for part in result.parts if part.type == "command")

        assert result.status == "completed"
        assert diff.status == "executed"
        assert diff.payload["execution_mode"] == "auto"
        assert diff.payload["changed_files"] == [rel]
        assert command.status == "completed"
        assert command.payload["exit_code"] == 0
        assert result.parts[-1].type == "summary"
        assert target.read_text(encoding="utf-8") == "VALUE = 1\n"
    finally:
        shutil.rmtree(run_dir, ignore_errors=True)


def test_confirm_all_patch_waits_for_approval(tmp_path: Path):
    workspace = Path.cwd()
    run_dir = _workspace_tmp("agent-confirm")
    target = run_dir / "smoke.py"
    rel = target.relative_to(workspace).as_posix()
    service = _service(tmp_path)
    session = service.create_session(
        AgentSessionCreate(title="confirm", project_path=str(workspace), autonomy_mode="confirm_all")
    )
    responses = iter(
        [
            {"tool": "collect_context", "arguments": {"read": []}},
            {"tool": "patch", "arguments": {"payload": {"files": [{"path": rel, "content": "VALUE = 1\n"}]}}},
        ]
    )

    async def model_call(_messages):
        return json.dumps(next(responses), ensure_ascii=False)

    service.model_call = model_call
    result = asyncio.run(service.prompt(session.id, AgentPromptRequest(content="新增 smoke 文件")))
    diff = result.parts[-1]

    assert result.status == "waiting_approval"
    assert diff.type == "diff"
    assert diff.status == "pending"
    assert diff.payload["execution_mode"] == "approval_required"
    assert not target.exists()
    shutil.rmtree(run_dir, ignore_errors=True)


def test_read_only_blocks_patch_with_error_summary(tmp_path: Path):
    workspace = Path.cwd()
    run_dir = _workspace_tmp("agent-readonly")
    target = run_dir / "smoke.py"
    rel = target.relative_to(workspace).as_posix()
    service = _service(tmp_path)
    session = service.create_session(
        AgentSessionCreate(title="readonly", project_path=str(workspace), autonomy_mode="read_only")
    )
    responses = iter(
        [
            {"tool": "collect_context", "arguments": {"read": []}},
            {"tool": "patch", "arguments": {"payload": {"files": [{"path": rel, "content": "VALUE = 1\n"}]}}},
        ]
    )

    async def model_call(_messages):
        return json.dumps(next(responses), ensure_ascii=False)

    service.model_call = model_call
    result = asyncio.run(service.prompt(session.id, AgentPromptRequest(content="只读模式尝试写文件")))

    assert result.status == "needs_manual_review"
    assert result.parts[-1].type == "summary"
    assert "只读模式" in result.parts[-1].content
    assert not target.exists()
    shutil.rmtree(run_dir, ignore_errors=True)


def test_patch_before_context_gets_guidance_and_continues(tmp_path: Path):
    workspace = Path.cwd()
    run_dir = _workspace_tmp("agent-guidance")
    target = run_dir / "guided.py"
    rel = target.relative_to(workspace).as_posix()
    target.write_text("VALUE = 1\n", encoding="utf-8")
    service = _service(tmp_path)
    session = service.create_session(
        AgentSessionCreate(title="guidance", project_path=str(workspace), autonomy_mode="safe_auto")
    )
    responses = iter(
        [
            {"tool": "patch", "arguments": {"payload": {"files": [{"path": rel, "content": "VALUE = 2\n"}]}}},
            {"tool": "read", "arguments": {"path": rel}},
            {"tool": "patch", "arguments": {"payload": {"files": [{"path": rel, "content": "VALUE = 2\n"}]}}},
            {"tool": "finalize", "arguments": {"summary": "已根据读取结果完成修改。"}},
        ]
    )

    async def model_call(_messages):
        return json.dumps(next(responses), ensure_ascii=False)

    service.model_call = model_call
    service.processor.max_iterations = 6
    try:
        result = asyncio.run(service.prompt(session.id, AgentPromptRequest(content="修改 guided.py")))
        guidance = next(part for part in result.parts if part.type == "tool_result" and "先读取" in (part.content or ""))
        diff = next(part for part in result.parts if part.type == "diff")

        assert guidance.status == "completed"
        assert result.status == "completed"
        assert diff.status == "executed"
        assert target.read_text(encoding="utf-8") == "VALUE = 2\n"
    finally:
        shutil.rmtree(run_dir, ignore_errors=True)


def test_command_failure_repairs_once_then_needs_manual_review(tmp_path: Path):
    workspace = Path.cwd()
    run_dir = _workspace_tmp("agent-repair")
    target = run_dir / "bad.py"
    rel = target.relative_to(workspace).as_posix()
    target.write_text("def broken(:\n", encoding="utf-8")
    service = _service(tmp_path)
    session = service.create_session(
        AgentSessionCreate(title="repair", project_path=str(workspace), autonomy_mode="safe_auto")
    )
    responses = iter(
        [
            {"tool": "collect_context", "arguments": {"read": [rel]}},
            {"tool": "bash_command", "arguments": {"payload": {"command": ["python", "-m", "py_compile", rel]}}},
            {"tool": "read_execution", "arguments": {}},
            {"tool": "patch", "arguments": {"payload": {"files": [{"path": rel, "content": "def broken(:\n"}]}}},
            {"tool": "bash_command", "arguments": {"payload": {"command": ["python", "-m", "py_compile", rel]}}},
        ]
    )

    async def model_call(_messages):
        return json.dumps(next(responses), ensure_ascii=False)

    service.model_call = model_call
    service.processor.max_iterations = 8
    try:
        result = asyncio.run(service.prompt(session.id, AgentPromptRequest(content="修复 bad.py 并验证")))
        commands = [part for part in result.parts if part.type == "command"]

        assert result.status == "needs_manual_review"
        assert result.metadata["repair_attempts"] == 1
        assert len(commands) == 2
        assert commands[-1].status == "failed"
        assert result.parts[-1].type == "summary"
        assert "验证失败" in result.parts[-1].content
    finally:
        shutil.rmtree(run_dir, ignore_errors=True)

