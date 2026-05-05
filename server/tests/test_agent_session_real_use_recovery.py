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
    return AgentSessionService(AgentSessionRepository(str(tmp_path / f"agent-real-use-{uuid.uuid4().hex}.db")))


def test_get_session_recovers_completed_diagnostics(tmp_path: Path):
    workspace = Path.cwd()
    run_dir = _workspace_tmp("agent-real-completed")
    target = run_dir / "smoke.py"
    rel = target.relative_to(workspace).as_posix()
    service = _service(tmp_path)
    session = service.create_session(AgentSessionCreate(title="completed", project_path=str(workspace)))
    responses = iter(
        [
            {"tool": "collect_context", "arguments": {"read": [rel]}},
            {"tool": "patch", "arguments": {"payload": {"files": [{"path": rel, "content": "VALUE = 1\n"}]}}},
            {"tool": "bash_command", "arguments": {"payload": {"command": ["python", "-m", "py_compile", rel]}}},
            {"tool": "finalize", "arguments": {"summary": "已创建 smoke 文件并通过 py_compile。"}},
        ]
    )

    async def model_call(_messages):
        return json.dumps(next(responses), ensure_ascii=False)

    service.model_call = model_call
    service.processor.max_iterations = 6
    try:
        result = asyncio.run(service.prompt(session.id, AgentPromptRequest(content="新增 tmp smoke 文件并验证")))
        restored = service.get_session(session.id)
        diagnostics = restored.metadata["diagnostics"]

        assert result.status == "completed"
        assert diagnostics["status"] == "completed"
        assert diagnostics["latest_summary"]["content"] == "已创建 smoke 文件并通过 py_compile。"
        assert diagnostics["latest_action"]["type"] == "command"
        assert diagnostics["latest_command"]["exit_code"] == 0
        assert diagnostics["stop_reason"] == "已创建 smoke 文件并通过 py_compile。"
        assert diagnostics["next_action"] == "可以查看结果，或继续提出下一步需求。"
        assert diagnostics["refresh_safe"] is True
    finally:
        shutil.rmtree(run_dir, ignore_errors=True)


def test_get_session_recovers_waiting_approval_reason(tmp_path: Path):
    workspace = Path.cwd()
    run_dir = _workspace_tmp("agent-real-approval")
    target = run_dir / "manual.py"
    rel = target.relative_to(workspace).as_posix()
    target.write_text("VALUE = 0\n", encoding="utf-8")
    service = _service(tmp_path)
    session = service.create_session(
        AgentSessionCreate(title="approval", project_path=str(workspace), autonomy_mode="confirm_all")
    )
    responses = iter(
        [
            {"tool": "collect_context", "arguments": {"read": [rel]}},
            {"tool": "patch", "arguments": {"payload": {"files": [{"path": rel, "content": "VALUE = 1\n"}]}}},
        ]
    )

    async def model_call(_messages):
        return json.dumps(next(responses), ensure_ascii=False)

    service.model_call = model_call
    service.processor.max_iterations = 4
    try:
        asyncio.run(service.prompt(session.id, AgentPromptRequest(content="确认模式修改文件")))
        restored = service.get_session(session.id)
        diagnostics = restored.metadata["diagnostics"]

        assert restored.status == "waiting_approval"
        assert diagnostics["latest_action"]["type"] == "diff"
        assert diagnostics["latest_action"]["policy_decision"] == "approval_required"
        assert "确认模式" in diagnostics["stop_reason"]
        assert diagnostics["next_action"] == "请确认待处理的修改或验证命令。"
        assert target.read_text(encoding="utf-8") == "VALUE = 0\n"
    finally:
        shutil.rmtree(run_dir, ignore_errors=True)


def test_get_session_recovers_manual_review_reason(tmp_path: Path):
    workspace = Path.cwd()
    run_dir = _workspace_tmp("agent-real-blocked")
    target = run_dir / "readonly.py"
    rel = target.relative_to(workspace).as_posix()
    service = _service(tmp_path)
    session = service.create_session(
        AgentSessionCreate(title="readonly", project_path=str(workspace), autonomy_mode="read_only")
    )
    responses = iter(
        [
            {"tool": "collect_context", "arguments": {"read": [rel]}},
            {"tool": "patch", "arguments": {"payload": {"files": [{"path": rel, "content": "VALUE = 1\n"}]}}},
        ]
    )

    async def model_call(_messages):
        return json.dumps(next(responses), ensure_ascii=False)

    service.model_call = model_call
    service.processor.max_iterations = 4
    try:
        asyncio.run(service.prompt(session.id, AgentPromptRequest(content="只读模式尝试写文件")))
        restored = service.get_session(session.id)
        diagnostics = restored.metadata["diagnostics"]

        assert restored.status == "needs_manual_review"
        assert diagnostics["latest_action"]["type"] == "diff"
        assert diagnostics["latest_action"]["status"] == "blocked"
        assert "只读模式" in diagnostics["stop_reason"]
        assert diagnostics["next_action"] == "请根据上方原因调整需求、手动确认动作，或让 Agent 继续修复。"
        assert not target.exists()
    finally:
        shutil.rmtree(run_dir, ignore_errors=True)


def test_refresh_get_session_does_not_repeat_auto_execution(tmp_path: Path):
    workspace = Path.cwd()
    run_dir = _workspace_tmp("agent-real-refresh")
    target = run_dir / "refresh.py"
    rel = target.relative_to(workspace).as_posix()
    service = _service(tmp_path)
    session = service.create_session(AgentSessionCreate(title="refresh", project_path=str(workspace)))
    responses = iter(
        [
            {"tool": "collect_context", "arguments": {"read": [rel]}},
            {"tool": "patch", "arguments": {"payload": {"files": [{"path": rel, "content": "VALUE = 1\n"}]}}},
            {"tool": "finalize", "arguments": {"summary": "已写入 refresh 文件。"}},
        ]
    )

    async def model_call(_messages):
        return json.dumps(next(responses), ensure_ascii=False)

    service.model_call = model_call
    service.processor.max_iterations = 5
    try:
        result = asyncio.run(service.prompt(session.id, AgentPromptRequest(content="写入 refresh 文件")))
        before_content = target.read_text(encoding="utf-8")
        before_parts = len(result.parts)
        restored_once = service.get_session(session.id)
        restored_twice = service.get_session(session.id)

        assert target.read_text(encoding="utf-8") == before_content
        assert len(restored_once.parts) == before_parts
        assert len(restored_twice.parts) == before_parts
        assert restored_twice.metadata["diagnostics"]["refresh_safe"] is True
        assert restored_twice.metadata["diagnostics"]["latest_action"]["changed_files"] == [rel]
    finally:
        shutil.rmtree(run_dir, ignore_errors=True)

