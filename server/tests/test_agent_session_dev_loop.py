from __future__ import annotations

import asyncio
import json
import shutil
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

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


def test_shell_string_command_gets_guidance_and_continues(tmp_path: Path):
    workspace = Path.cwd()
    service = _service(tmp_path)
    session = service.create_session(
        AgentSessionCreate(title="command-guidance", project_path=str(workspace), autonomy_mode="safe_auto")
    )
    responses = iter(
        [
            {"tool": "collect_context", "arguments": {"read": []}},
            {
                "tool": "bash_command",
                "arguments": {
                    "payload": {
                        "command": "mkdir -p tmp && echo 'agent stream smoke ok' > tmp/agent-stream-smoke.txt"
                    }
                },
            },
            {"tool": "finalize", "arguments": {"summary": "已识别命令格式问题，未执行 shell 字符串。"}},
        ]
    )

    async def model_call(_messages):
        return json.dumps(next(responses), ensure_ascii=False)

    service.model_call = model_call
    service.processor.max_iterations = 5
    result = asyncio.run(service.prompt(session.id, AgentPromptRequest(content="测试 shell 字符串命令纠偏")))

    guidance = next(part for part in result.parts if part.type == "tool_result" and "argv 数组" in (part.content or ""))
    commands = [part for part in result.parts if part.type == "command"]

    assert result.status == "completed"
    assert guidance.status == "completed"
    assert commands == []
    assert "未执行 shell 字符串" in result.parts[-1].content


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


def test_http_probe_guides_frontend_validation_flow(tmp_path: Path):
    workspace = Path.cwd()
    service = _service(tmp_path)
    session = service.create_session(
        AgentSessionCreate(title="frontend-guidance", project_path=str(workspace), autonomy_mode="safe_auto")
    )
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            body = b"<html><head><title>Probe</title></head><body><h1>Ready</h1></body></html>"
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format, *args):
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_port}/"
    responses = iter(
        [
            {"tool": "http_probe", "arguments": {"url": url}},
            {"tool": "finalize", "arguments": {"summary": "页面已探测。"}},
        ]
    )
    captured: list[list[dict[str, str]]] = []

    async def model_call(messages):
        captured.append(list(messages))
        return json.dumps(next(responses), ensure_ascii=False)

    service.model_call = model_call
    service.processor.max_iterations = 4
    try:
        result = asyncio.run(service.prompt(session.id, AgentPromptRequest(content="检查前端页面是否正常")))

        assert result.status == "completed"
        assert "read_local_page" in captured[1][-1]["content"]
        assert "browser_validate_page" in captured[1][-1]["content"]
    finally:
        server.shutdown()
        server.server_close()


def test_probe_json_endpoint_guides_api_debug_flow(tmp_path: Path):
    workspace = Path.cwd()
    service = _service(tmp_path)
    session = service.create_session(
        AgentSessionCreate(title="api-guidance", project_path=str(workspace), autonomy_mode="safe_auto")
    )

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            body = json.dumps({"ok": True, "items": [1, 2]}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format, *args):
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_port}/api/status"
    responses = iter(
        [
            {"tool": "probe_json_endpoint", "arguments": {"url": url}},
            {"tool": "finalize", "arguments": {"summary": "接口已探测。"}},
        ]
    )
    captured: list[list[dict[str, str]]] = []

    async def model_call(messages):
        captured.append(list(messages))
        return json.dumps(next(responses), ensure_ascii=False)

    service.model_call = model_call
    service.processor.max_iterations = 4
    try:
        result = asyncio.run(service.prompt(session.id, AgentPromptRequest(content="检查本地 API 是否正常")))

        assert result.status == "completed"
        assert "capture_network_errors" in captured[1][-1]["content"]
    finally:
        server.shutdown()
        server.server_close()


def test_failed_test_command_guides_collect_test_failures(tmp_path: Path):
    workspace = Path.cwd()
    run_dir = _workspace_tmp("agent-test-failure-guidance")
    target = run_dir / "bad.py"
    rel = target.relative_to(workspace).as_posix()
    target.write_text("def broken(:\n", encoding="utf-8")
    service = _service(tmp_path)
    session = service.create_session(
        AgentSessionCreate(title="test-failure-guidance", project_path=str(workspace), autonomy_mode="safe_auto")
    )
    responses = iter(
        [
            {"tool": "collect_context", "arguments": {"read": [rel]}},
            {"tool": "bash_command", "arguments": {"payload": {"command": ["python", "-m", "pytest", "server/tests/does_not_exist.py"]}}},
            {"tool": "finalize", "arguments": {"summary": "测试失败引导已给出。"}},
        ]
    )
    captured: list[list[dict[str, str]]] = []

    async def model_call(messages):
        captured.append(list(messages))
        return json.dumps(next(responses), ensure_ascii=False)

    service.model_call = model_call
    service.processor.max_iterations = 4
    try:
        result = asyncio.run(service.prompt(session.id, AgentPromptRequest(content="运行测试并在失败时给出修复路径")))

        assert result.status in {"completed", "needs_manual_review"}
        assert any("collect_test_failures" in message[-1]["content"] for message in captured[2:])
    finally:
        shutil.rmtree(run_dir, ignore_errors=True)


def test_run_targeted_test_guides_summary_flow(tmp_path: Path):
    workspace = Path.cwd()
    service = _service(tmp_path)
    session = service.create_session(
        AgentSessionCreate(title="targeted-test-guidance", project_path=str(workspace), autonomy_mode="safe_auto")
    )
    responses = iter(
        [
            {"tool": "run_targeted_test", "arguments": {"framework": "pytest", "target": "server/tests/test_agent_tool_registry.py", "test_name": "summarize"}},
            {"tool": "summarize_test_results", "arguments": {"stdout": "=================== 1 passed in 0.20s ===================", "stderr": "", "exit_code": 0, "framework": "pytest"}},
            {"tool": "finalize", "arguments": {"summary": "精准测试链路正常。"}},
        ]
    )
    captured: list[list[dict[str, str]]] = []

    async def model_call(messages):
        captured.append(list(messages))
        return json.dumps(next(responses), ensure_ascii=False)

    service.model_call = model_call
    service.processor.max_iterations = 5
    result = asyncio.run(service.prompt(session.id, AgentPromptRequest(content="运行一个精准测试并总结结果")))

    assert result.status == "completed"
    assert "summarize_test_results" in captured[1][-1]["content"]
