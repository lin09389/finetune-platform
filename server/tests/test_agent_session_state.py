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
    return AgentSessionService(AgentSessionRepository(str(tmp_path / f"agent-state-{uuid.uuid4().hex}.db")))


def test_state_tracks_context_patch_command_and_summary(tmp_path: Path):
    workspace = Path.cwd()
    run_dir = _workspace_tmp("agent-state")
    target = run_dir / "smoke.py"
    rel = target.relative_to(workspace).as_posix()
    target.write_text("VALUE = 0\n", encoding="utf-8")
    service = _service(tmp_path)
    session = service.create_session(AgentSessionCreate(title="state", project_path=str(workspace)))
    responses = iter(
        [
            {"tool": "collect_context", "arguments": {"read": [rel]}},
            {"tool": "patch", "arguments": {"payload": {"files": [{"path": rel, "content": "VALUE = 1\n"}]}}},
            {"tool": "bash_command", "arguments": {"payload": {"command": ["python", "-m", "py_compile", rel]}}},
            {"tool": "finalize", "arguments": {"summary": "已完成 smoke 修改并验证。"}},
        ]
    )

    async def model_call(_messages):
        return json.dumps(next(responses), ensure_ascii=False)

    service.model_call = model_call
    service.processor.max_iterations = 6
    try:
        result = asyncio.run(service.prompt(session.id, AgentPromptRequest(content="新增 smoke 并验证")))
        restored = service.get_session(session.id)
        state = restored.metadata["state"]
        diff = next(part for part in result.parts if part.type == "diff")
        command = next(part for part in result.parts if part.type == "command")

        assert result.status == "completed"
        assert rel in state["touched_paths"]
        assert rel in state["changed_files"]
        assert state["latest_diff_part_id"] == diff.id
        assert state["latest_command_part_id"] == command.id
        assert state["latest_error"] == ""
        assert state["repair_attempts"] == 0
        assert state["fallback_summary_used"] is False
        assert state["current_phase"] == "completed"
    finally:
        shutil.rmtree(run_dir, ignore_errors=True)


def test_state_tracks_repair_and_latest_error(tmp_path: Path):
    workspace = Path.cwd()
    run_dir = _workspace_tmp("agent-state-repair")
    target = run_dir / "bad.py"
    rel = target.relative_to(workspace).as_posix()
    target.write_text("def broken(:\n", encoding="utf-8")
    service = _service(tmp_path)
    session = service.create_session(AgentSessionCreate(title="repair", project_path=str(workspace)))
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
        result = asyncio.run(service.prompt(session.id, AgentPromptRequest(content="修复 bad.py")))
        state = result.metadata["state"]

        assert result.status == "needs_manual_review"
        assert state["repair_attempts"] == 1
        assert state["current_phase"] == "needs_manual_review"
        assert state["latest_command_part_id"]
        assert state["latest_error"]
    finally:
        shutil.rmtree(run_dir, ignore_errors=True)


def test_fallback_summary_marks_state(tmp_path: Path):
    workspace = Path.cwd()
    service = _service(tmp_path)
    service.processor.max_iterations = 1
    session = service.create_session(AgentSessionCreate(title="fallback", project_path=str(workspace)))

    async def model_call(_messages):
        return "我已经完成了，但是没有按 JSON 输出。"

    service.model_call = model_call
    result = asyncio.run(service.prompt(session.id, AgentPromptRequest(content="触发兜底总结")))
    state = result.metadata["state"]

    assert result.status == "needs_manual_review"
    assert state["fallback_summary_used"] is True
    assert state["current_phase"] == "needs_manual_review"
    assert result.parts[-1].type == "summary"


def test_get_session_recovers_state_without_duplicate_execution(tmp_path: Path):
    workspace = Path.cwd()
    run_dir = _workspace_tmp("agent-state-recover")
    target = run_dir / "recover.py"
    rel = target.relative_to(workspace).as_posix()
    service = _service(tmp_path)
    session = service.create_session(AgentSessionCreate(title="recover", project_path=str(workspace)))
    responses = iter(
        [
            {"tool": "collect_context", "arguments": {"read": [rel]}},
            {"tool": "patch", "arguments": {"payload": {"files": [{"path": rel, "content": "VALUE = 1\n"}]}}},
            {"tool": "finalize", "arguments": {"summary": "已完成。"}},
        ]
    )

    async def model_call(_messages):
        return json.dumps(next(responses), ensure_ascii=False)

    service.model_call = model_call
    service.processor.max_iterations = 5
    try:
        result = asyncio.run(service.prompt(session.id, AgentPromptRequest(content="写入 recover")))
        before_parts = len(result.parts)
        before_content = target.read_text(encoding="utf-8")
        restored = service.get_session(session.id)

        assert len(restored.parts) == before_parts
        assert target.read_text(encoding="utf-8") == before_content
        assert restored.metadata["state"]["latest_diff_part_id"]
        assert restored.metadata["state"]["changed_files"] == [rel]
    finally:
        shutil.rmtree(run_dir, ignore_errors=True)


def test_get_session_includes_recovery_diagnostics_for_completed_run(tmp_path: Path):
    workspace = Path.cwd()
    run_dir = _workspace_tmp("agent-diagnostics")
    target = run_dir / "done.py"
    rel = target.relative_to(workspace).as_posix()
    service = _service(tmp_path)
    session = service.create_session(AgentSessionCreate(title="diagnostics", project_path=str(workspace)))
    responses = iter(
        [
            {"tool": "collect_context", "arguments": {"read": [rel]}},
            {"tool": "patch", "arguments": {"payload": {"files": [{"path": rel, "content": "VALUE = 1\n"}]}}},
            {"tool": "bash_command", "arguments": {"payload": {"command": ["python", "-m", "py_compile", rel]}}},
            {"tool": "finalize", "arguments": {"summary": "已完成诊断 smoke，并通过验证。"}},
        ]
    )

    async def model_call(_messages):
        return json.dumps(next(responses), ensure_ascii=False)

    service.model_call = model_call
    service.processor.max_iterations = 6
    try:
        asyncio.run(service.prompt(session.id, AgentPromptRequest(content="写入并验证")))
        restored = service.get_session(session.id)
        diagnostics = restored.metadata["diagnostics"]

        assert diagnostics["status"] == "completed"
        assert diagnostics["latest_event"]["event_type"] == "summary_completed"
        assert diagnostics["latest_tool_call"]["type"] == "tool_call"
        assert diagnostics["latest_action"]["type"] == "command"
        assert diagnostics["latest_command"]["exit_code"] == 0
        assert diagnostics["latest_summary"]["content"] == "已完成诊断 smoke，并通过验证。"
        assert diagnostics["stop_reason"] == "已完成诊断 smoke，并通过验证。"
        assert diagnostics["next_action"] == "可以查看结果，或继续提出下一步需求。"
        assert diagnostics["refresh_safe"] is True
        assert restored.metadata["latest_event"] == diagnostics["latest_event"]
    finally:
        shutil.rmtree(run_dir, ignore_errors=True)


def test_get_session_explains_waiting_approval_action(tmp_path: Path):
    workspace = Path.cwd()
    run_dir = _workspace_tmp("agent-diagnostics-approval")
    target = run_dir / "confirm.py"
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
        asyncio.run(service.prompt(session.id, AgentPromptRequest(content="确认模式写文件")))
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
