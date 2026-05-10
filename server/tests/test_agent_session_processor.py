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


def test_run_dev_server_requires_approval(tmp_path: Path):
    service = AgentSessionService(AgentSessionRepository(str(tmp_path / "agent_dev_server.db")))
    session = service.create_session(AgentSessionCreate(title="dev server", project_path=str(Path.cwd())))
    responses = iter(
        [
            {"tool": "run_dev_server", "arguments": {"payload": {"command": ["npm", "run", "dev"], "server_url": "http://localhost:5173"}}},
        ]
    )

    async def model_call(_messages):
        return json.dumps(next(responses), ensure_ascii=False)

    service.model_call = model_call
    result = asyncio.run(service.prompt(session.id, AgentPromptRequest(content="启动前端开发服务器")))
    command = next(part for part in result.parts if part.type == "command")

    assert result.status == "waiting_approval"
    assert command.status == "pending"
    assert command.payload["tool"] == "run_dev_server"
    assert command.payload["server_url"] == "http://localhost:5173"
    assert command.payload["execution_mode"] == "approval_required"


def test_stop_dev_server_auto_executes_without_manual_approval(tmp_path: Path, monkeypatch):
    service = AgentSessionService(AgentSessionRepository(str(tmp_path / "agent_stop_dev_server.db")))
    session = service.create_session(AgentSessionCreate(title="stop dev server", project_path=str(Path.cwd())))

    class FakeProcess:
        def __init__(self):
            self.pid = 123
            self._returncode = None

        def poll(self):
            return self._returncode

        def terminate(self):
            self._returncode = 0

        def wait(self, timeout=None):
            self._returncode = 0
            return 0

        def kill(self):
            self._returncode = -9

    log_path = Path.cwd() / "tmp" / "agent-dev-servers" / "test.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_file = log_path.open("a", encoding="utf-8")
    fake_process = FakeProcess()
    monkeypatch.setitem(
        __import__("agent_session.tools", fromlist=["DEV_SERVER_PROCESSES"]).DEV_SERVER_PROCESSES,
        f"{session.id}:dev",
        {
            "name": "dev",
            "command": ["npm", "run", "dev"],
            "cwd": str(Path.cwd()),
            "pid": fake_process.pid,
            "server_url": "http://localhost:5173",
            "log_path": log_path.relative_to(Path.cwd()).as_posix(),
            "process": fake_process,
            "log_file": log_file,
        },
    )
    responses = iter(
        [
            {"tool": "stop_dev_server", "arguments": {"payload": {"name": "dev"}}},
            {"tool": "finalize", "arguments": {"summary": "开发服务器已停止。"}},
        ]
    )

    async def model_call(_messages):
        return json.dumps(next(responses), ensure_ascii=False)

    service.processor.max_iterations = 4
    service.model_call = model_call
    try:
        result = asyncio.run(service.prompt(session.id, AgentPromptRequest(content="停止开发服务器并总结状态")))
        command = next(part for part in result.parts if part.type == "command")
        assert result.status == "completed"
        assert command.status == "completed"
        assert command.payload["running"] is False
    finally:
        try:
            log_file.close()
        except Exception:
            pass


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


def test_local_fallback_summary_mentions_written_files_after_action():
    service = AgentSessionService(AgentSessionRepository(":memory:"))
    observation = {
        "tool": "patch",
        "status": "completed",
        "changed_files": ["tmp/demo_live_patch.txt"],
    }
    messages = [
        {
            "role": "user",
            "content": "工具结果：\n" + json.dumps(observation, ensure_ascii=False),
        }
    ]

    raw = service._local_fallback_model_response(messages, "没有选择云端模型")

    parsed = json.loads(raw)
    assert parsed["tool"] == "finalize"
    assert "补丁已执行并写入文件" in parsed["arguments"]["summary"]
    assert "tmp/demo_live_patch.txt" in parsed["arguments"]["summary"]


def test_frontend_validation_tools_add_next_step_guidance(tmp_path: Path):
    service = AgentSessionService(AgentSessionRepository(str(tmp_path / "agent_frontend_guidance.db")))
    guidance = service.processor._next_tool_guidance(
        "browser_validate_page",
        "completed",
        {"ok": True, "status_code": 200},
    )

    assert guidance is not None
    assert "browser_click" in guidance["recommended_tools"]
    assert "finalize" in guidance["recommended_tools"]


def test_collect_test_failures_adds_repair_guidance(tmp_path: Path):
    service = AgentSessionService(AgentSessionRepository(str(tmp_path / "agent_failure_guidance.db")))
    guidance = service.processor._next_tool_guidance(
        "collect_test_failures",
        "completed",
        {"failures": [{"headline": "FAILED test_demo"}], "failure_summary": "1 failure"},
    )

    assert guidance is not None
    assert "read_execution" in guidance["recommended_tools"]
    assert "patch" in guidance["recommended_tools"]


def test_summarize_test_results_guidance_branches_on_failures(tmp_path: Path):
    service = AgentSessionService(AgentSessionRepository(str(tmp_path / "agent_summary_guidance.db")))
    failing = service.processor._next_tool_guidance(
        "summarize_test_results",
        "completed",
        {"failed": 1, "exit_code": 1},
    )
    passing = service.processor._next_tool_guidance(
        "summarize_test_results",
        "completed",
        {"failed": 0, "exit_code": 0},
    )

    assert failing is not None
    assert "collect_test_failures" in failing["recommended_tools"]
    assert passing is not None
    assert "finalize" in passing["recommended_tools"]


def test_api_and_network_guidance_suggests_next_steps(tmp_path: Path):
    service = AgentSessionService(AgentSessionRepository(str(tmp_path / "agent_api_guidance.db")))
    api = service.processor._next_tool_guidance(
        "probe_json_endpoint",
        "completed",
        {"ok": True, "json_type": "dict"},
    )
    network = service.processor._next_tool_guidance(
        "capture_network_errors",
        "completed",
        {"ok": False, "request_failures": [{"url": "x"}]},
    )

    assert api is not None
    assert "capture_network_errors" in api["recommended_tools"]
    assert network is not None
    assert "read_logs" in network["recommended_tools"]


def test_model_call_failure_returns_summary_instead_of_raising(tmp_path: Path):
    service = AgentSessionService(AgentSessionRepository(str(tmp_path / "agent_model_failure.db")))
    session = service.create_session(AgentSessionCreate(title="model failure", project_path=str(Path.cwd())))

    async def model_call(_messages):
        raise RuntimeError("provider exploded")

    service.model_call = model_call
    result = asyncio.run(service.prompt(session.id, AgentPromptRequest(content="触发模型失败")))

    assert result.status == "needs_manual_review"
    assert result.parts[-1].type == "summary"
    assert "provider exploded" in result.parts[-1].content


def test_processor_internal_failure_returns_recoverable_summary(tmp_path: Path):
    service = AgentSessionService(AgentSessionRepository(str(tmp_path / "agent_processor_failure.db")))
    session = service.create_session(AgentSessionCreate(title="processor failure", project_path=str(Path.cwd())))

    async def broken_prompt(*_args, **_kwargs):
        raise RuntimeError("processor exploded")

    service.processor.prompt = broken_prompt  # type: ignore[method-assign]
    result = asyncio.run(service.prompt(session.id, AgentPromptRequest(content="触发 processor 失败")))

    assert result.status == "needs_manual_review"
    assert result.parts[-1].type == "summary"
    assert "processor exploded" in result.parts[-1].content
    assert result.metadata["diagnostics"]["stop_reason"]


def test_missing_provider_can_still_run_explicit_read_only_task(tmp_path: Path):
    workspace = Path.cwd()
    service = AgentSessionService(AgentSessionRepository(str(tmp_path / "agent_local_read_fallback.db")))
    session = service.create_session(AgentSessionCreate(title="local read fallback", project_path=str(workspace)))
    service.processor.max_iterations = 4

    result = asyncio.run(
        service.prompt(
            session.id,
            AgentPromptRequest(
                content="先简单说明你要做什么，然后读取当前项目的 package.json 和 server/main.py，最后总结你看到了什么。不要写文件。"
            ),
        )
    )

    read_paths = [part.payload.get("path") for part in result.parts if part.type == "tool_result"]
    assert result.status == "completed"
    assert "package.json" in read_paths
    assert "server/main.py" in read_paths
    assert result.parts[-1].type == "summary"
