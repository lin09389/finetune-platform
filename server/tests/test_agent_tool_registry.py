from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

from agent_runtime.command_policy import command_allowed, normalize_command
from agent_session.tools import AgentToolRegistry


def test_agent_tool_registry_has_core_tools():
    registry = AgentToolRegistry()
    names = {tool.name for tool in registry.list()}

    assert {"read", "search", "find_symbol", "find_references", "glob", "collect_context", "detect_project_commands", "patch", "bash_command", "read_execution", "finalize"} <= names
    assert {"git_status", "git_diff", "list_changed_files", "read_logs", "http_probe", "probe_json_endpoint", "read_local_page", "browser_validate_page", "capture_network_errors", "browser_click", "browser_fill", "browser_wait_for", "run_targeted_test", "summarize_test_results", "collect_test_failures", "run_dev_server", "stop_dev_server", "get_server_status"} <= names
    assert registry.get("read").permission == "read"
    assert registry.get("patch").permission == "patch"
    assert registry.get("bash_command").permission == "command"


def test_unknown_tool_returns_none():
    registry = AgentToolRegistry()

    assert registry.get("unknown_tool") is None


def _workspace_root() -> Path:
    cwd = Path.cwd().resolve()
    return cwd.parent if cwd.name == "server" else cwd


def test_read_tool_accepts_multiple_paths(tmp_path):
    workspace = _workspace_root()
    registry = AgentToolRegistry()
    tool = registry.get("read")

    result = tool.execute({"paths": ["package.json", "server/main.py"]}, {"project_path": str(workspace)})

    assert result.status == "completed"
    assert result.payload["touched_paths"] == ["package.json", "server/main.py"]
    assert [item["path"] for item in result.payload["files"]] == ["package.json", "server/main.py"]


def test_read_tool_blocks_path_escape():
    workspace = Path.cwd()
    registry = AgentToolRegistry()
    tool = registry.get("read")

    try:
        tool.execute({"path": "../outside.txt"}, {"project_path": str(workspace)})
        raised = False
    except ValueError:
        raised = True

    assert raised


def test_precise_project_test_commands_are_allowlisted():
    assert command_allowed(normalize_command(["npm", "run", "test", "--", "src/example.test.ts"]))
    assert command_allowed(normalize_command(["npx", "vitest", "run", "src/example.test.ts"]))
    assert command_allowed(normalize_command(["python", "-m", "pytest", "server/tests/test_agent_tool_registry.py"]))


def test_git_tools_return_structured_payload():
    registry = AgentToolRegistry()
    workspace = Path.cwd()

    status = registry.get("git_status").execute({}, {"project_path": str(workspace)})
    changed = registry.get("list_changed_files").execute({}, {"project_path": str(workspace)})
    diff = registry.get("git_diff").execute({"path": "server/agent_session/tools.py"}, {"project_path": str(workspace)})

    assert status.status in {"completed", "failed"}
    assert "files" in status.payload
    assert changed.payload.get("files") is not None
    assert "stdout" in diff.payload


def test_dev_server_tool_lifecycle(monkeypatch):
    registry = AgentToolRegistry()
    workspace = Path.cwd()

    class FakeProcess:
        def __init__(self, *_args, **_kwargs):
            self.pid = 12345
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

    monkeypatch.setattr("agent_session.tools.subprocess.Popen", FakeProcess)

    context = {"project_path": str(workspace), "session": {"id": "test-dev-server"}}
    payload = {"command": ["npm", "run", "dev"], "server_url": "http://localhost:5173"}
    started = registry.get("run_dev_server").execute({"payload": payload}, context)
    status = registry.get("get_server_status").execute({}, context)
    stopped = registry.get("stop_dev_server").execute({}, context)

    assert started.status == "completed"
    assert started.payload["server_url"] == "http://localhost:5173"
    assert status.payload["running"] is True
    assert stopped.payload["running"] is False


def test_read_execution_returns_latest_part_snapshots(tmp_path):
    from agent_session.repository import AgentSessionRepository

    repository = AgentSessionRepository(str(tmp_path / "agent-read-execution.db"))
    session = repository.create_session({"agent_id": "build", "title": "read execution", "project_path": str(Path.cwd()), "metadata": {}})
    repository.add_part(session["id"], "diff", status="executed", title="补丁", content="patched", payload={"changed_files": ["tmp/demo.ts"]})
    repository.add_part(session["id"], "command", status="failed", title="验证命令", content="failed", payload={"command": ["python", "-m", "pytest"], "failure_summary": "AssertionError"})
    repository.add_part(session["id"], "summary", status="completed", title="最终结果", content="done", payload={"summary": "done"})

    registry = AgentToolRegistry(repository=repository)
    result = registry.get("read_execution").execute({}, {"project_path": str(Path.cwd()), "session": session})

    assert result.status == "completed"
    assert result.payload["latest_command"]["failure_summary"] == "AssertionError"
    assert result.payload["latest_diff"]["changed_files"] == ["tmp/demo.ts"]
    assert result.payload["latest_summary"]["content"] == "done"


def test_find_symbol_and_references_return_matches(tmp_path):
    workspace = Path.cwd()
    run_dir = workspace / "tmp" / "agent-symbol-test"
    run_dir.mkdir(parents=True, exist_ok=True)
    target = run_dir / "sample.ts"
    target.write_text(
        "export function alpha(value: number) {\n"
        "  return value + 1;\n"
        "}\n"
        "const result = alpha(1);\n",
        encoding="utf-8",
    )
    try:
        registry = AgentToolRegistry()
        context = {"project_path": str(workspace)}
        symbol = registry.get("find_symbol").execute({"symbol": "alpha"}, context)
        refs = registry.get("find_references").execute({"symbol": "alpha"}, context)

        assert symbol.status == "completed"
        assert symbol.payload["engine"] == "ast-grep"
        assert symbol.payload["matches"]
        assert symbol.payload["matches"][0]["kind"] == "function"
        assert refs.status == "completed"
        assert refs.payload["engine"] == "ast-grep"
        assert any(not item["is_definition"] for item in refs.payload["matches"])
    finally:
        target.unlink(missing_ok=True)
        run_dir.rmdir()


def test_collect_context_uses_symbol_lookup_to_expand_reads(tmp_path):
    workspace = Path.cwd()
    run_dir = workspace / "tmp" / "agent-collect-symbol-test"
    run_dir.mkdir(parents=True, exist_ok=True)
    target = run_dir / "symbol_feature.ts"
    target.write_text(
        "export function alpha(value: number) {\n"
        "  return value + 1;\n"
        "}\n"
        "const result = alpha(1);\n",
        encoding="utf-8",
    )
    try:
        registry = AgentToolRegistry()
        context = {"project_path": str(workspace), "session": {"title": "修复 alpha 引用"}} 
        result = registry.get("collect_context").execute({"queries": ["alpha"], "symbols": ["alpha"], "read": []}, context)

        assert result.status == "completed"
        assert result.payload["symbols"]
        assert result.payload["symbols"][0]["symbol"] == "alpha"
        assert result.payload["symbols"][0]["engine"] == "ast-grep"
        assert any(item["path"] == "tmp/agent-collect-symbol-test/symbol_feature.ts" for item in result.payload["files"])
    finally:
        target.unlink(missing_ok=True)
        run_dir.rmdir()


def test_collect_context_with_explicit_read_skips_inference(monkeypatch):
    workspace = Path.cwd()
    run_dir = workspace / "tmp" / "agent-collect-explicit-read-test"
    run_dir.mkdir(parents=True, exist_ok=True)
    target = run_dir / "demo_live_patch.txt"
    target.write_text("BEFORE\n", encoding="utf-8")
    registry = AgentToolRegistry()

    def fail_find_symbol(*_args, **_kwargs):
        raise AssertionError("symbol lookup should be skipped for explicit read-only collect_context")

    def fail_find_references(*_args, **_kwargs):
        raise AssertionError("reference lookup should be skipped for explicit read-only collect_context")

    monkeypatch.setattr(registry, "_find_symbol", fail_find_symbol)
    monkeypatch.setattr(registry, "_find_references", fail_find_references)

    try:
        rel = target.relative_to(workspace).as_posix()
        result = registry.get("collect_context").execute(
            {"read": [rel], "queries": [], "symbols": []},
            {"project_path": str(workspace), "session": {"title": f"Patch only this file: {rel}"}},
        )

        assert result.status == "completed"
        assert [item["path"] for item in result.payload["files"]] == [rel]
        assert result.payload["symbols"] == []
    finally:
        target.unlink(missing_ok=True)
        run_dir.rmdir()


def test_http_probe_and_read_local_page_support_local_frontend_validation():
    registry = AgentToolRegistry()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            body = (
                "<html><head><title>Agent Probe</title></head>"
                "<body><h1>Frontend Ready</h1><p>hello probe</p><a href='/next'>Next</a></body></html>"
            ).encode("utf-8")
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
    try:
        probe = registry.get("http_probe").execute({"url": url}, {"project_path": str(Path.cwd())})
        page = registry.get("read_local_page").execute({"url": url}, {"project_path": str(Path.cwd())})

        assert probe.status == "completed"
        assert probe.payload["status_code"] == 200
        assert probe.payload["title"] == "Agent Probe"
        assert page.status == "completed"
        assert page.payload["title"] == "Agent Probe"
        assert page.payload["headings"][0]["text"] == "Frontend Ready"
        assert "/next" in page.payload["links"]
    finally:
        server.shutdown()
        server.server_close()


def test_probe_json_endpoint_reads_local_api_response():
    registry = AgentToolRegistry()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            body = json.dumps({"ok": True, "items": [1, 2, 3]}).encode("utf-8")
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
    try:
        result = registry.get("probe_json_endpoint").execute({"url": url}, {"project_path": str(Path.cwd())})

        assert result.status == "completed"
        assert result.payload["json_type"] == "dict"
        assert result.payload["json_preview"]["ok"] is True
    finally:
        server.shutdown()
        server.server_close()


def test_browser_validate_page_reports_console_and_selector_results(monkeypatch):
    registry = AgentToolRegistry()

    def fake_browser_validation(**kwargs):
        return {
            "url": kwargs["url"],
            "final_url": kwargs["url"],
            "ok": False,
            "status_code": 200,
            "title": "Agent Probe",
            "headings": [{"tag": "h1", "text": "Frontend Ready"}],
            "console_errors": ["boom"],
            "page_errors": [],
            "selector_results": [{"selector": "#app", "found": True, "count": 1}],
            "text_results": [{"text": "Frontend Ready", "found": True}],
            "body_excerpt": "Frontend Ready",
            "engine": "playwright",
            "error": "browser validation failed",
        }

    monkeypatch.setattr(registry, "_run_browser_validation", fake_browser_validation)

    result = registry.get("browser_validate_page").execute(
        {"url": "http://127.0.0.1:5173", "selectors": ["#app"], "required_text": ["Frontend Ready"]},
        {"project_path": str(Path.cwd())},
    )

    assert result.status == "failed"
    assert result.payload["engine"] == "playwright"
    assert result.payload["console_errors"] == ["boom"]
    assert result.payload["selector_results"][0]["found"] is True


def test_capture_network_errors_reports_structured_failures(monkeypatch):
    registry = AgentToolRegistry()

    def fake_network_capture(**kwargs):
        return {
            "url": kwargs["url"],
            "final_url": kwargs["url"],
            "ok": False,
            "status_code": 200,
            "request_failures": [{"url": "http://127.0.0.1:8010/api/demo", "method": "GET", "failure": "net::ERR_CONNECTION_REFUSED"}],
            "error_responses": [{"url": "http://127.0.0.1:8010/api/demo", "method": "GET", "status": 500}],
            "console_errors": ["fetch failed"],
            "page_errors": [],
            "engine": "playwright",
            "error": "network errors detected",
        }

    monkeypatch.setattr(registry, "_run_network_capture", fake_network_capture)
    result = registry.get("capture_network_errors").execute({"url": "http://127.0.0.1:5173"}, {"project_path": str(Path.cwd())})

    assert result.status == "failed"
    assert result.payload["request_failures"][0]["failure"] == "net::ERR_CONNECTION_REFUSED"
    assert result.payload["error_responses"][0]["status"] == 500


def test_browser_interaction_tools_return_structured_results(monkeypatch):
    registry = AgentToolRegistry()

    def fake_browser_action(**kwargs):
        return {
            "url": kwargs["url"],
            "final_url": kwargs["url"] + "/after",
            "ok": True,
            "status_code": 200,
            "title": "After Action",
            "headings": [{"tag": "h1", "text": "Done"}],
            "console_errors": [],
            "page_errors": [],
            "selector_results": ([{"selector": kwargs["selector"], "found": True, "count": 1}] if kwargs["selector"] else []),
            "text_results": [{"text": "Done", "found": True}],
            "body_excerpt": "Done",
            "engine": "playwright",
            "action": kwargs["action"],
        }

    monkeypatch.setattr(registry, "_run_browser_action", fake_browser_action)
    context = {"project_path": str(Path.cwd())}

    click = registry.get("browser_click").execute({"url": "http://127.0.0.1:5173", "selector": "#submit"}, context)
    fill = registry.get("browser_fill").execute({"url": "http://127.0.0.1:5173", "selector": "input[name=q]", "value": "alpha"}, context)
    wait_for = registry.get("browser_wait_for").execute({"url": "http://127.0.0.1:5173", "wait_for": "#done"}, context)

    assert click.status == "completed"
    assert click.payload["action"] == "click"
    assert fill.payload["action"] == "fill"
    assert wait_for.payload["action"] == "wait_for"


def test_collect_test_failures_extracts_failure_blocks():
    registry = AgentToolRegistry()

    result = registry.get("collect_test_failures").execute(
        {
            "stdout": "FAILED server/tests/test_demo.py::test_example - AssertionError: expected 1 == 2\nE AssertionError: expected 1 == 2\n",
            "stderr": "ERROR client/src/test/ui.test.tsx::renders button\nTypeError: boom\n",
            "failure_summary": "2 failures",
        },
        {"project_path": str(Path.cwd())},
    )

    assert result.status == "completed"
    assert result.payload["failure_summary"] == "2 failures"
    assert len(result.payload["failures"]) >= 2


def test_run_targeted_test_builds_framework_specific_commands():
    registry = AgentToolRegistry()
    context = {"project_path": str(Path.cwd())}

    pytest_result = registry.get("run_targeted_test").execute({"framework": "pytest", "target": "server/tests/test_agent_tool_registry.py", "test_name": "collect"}, context)
    vitest_result = registry.get("run_targeted_test").execute({"framework": "vitest", "target": "client/src/test/gaSmokePages.test.tsx", "test_name": "smoke"}, context)

    assert pytest_result.status == "completed"
    assert pytest_result.payload["command"][:3] == ["python", "-m", "pytest"]
    assert "-k" in pytest_result.payload["command"]
    assert vitest_result.status == "completed"
    assert vitest_result.payload["command"][:3] == ["npx", "vitest", "run"]
    assert "-t" in vitest_result.payload["command"]


def test_summarize_test_results_parses_counts():
    registry = AgentToolRegistry()
    result = registry.get("summarize_test_results").execute(
        {
            "framework": "pytest",
            "stdout": "collected 3 items\n\nserver/tests/test_demo.py ..F\n\n=================== 2 passed, 1 failed in 0.45s ===================\n",
            "stderr": "",
            "exit_code": 1,
        },
        {"project_path": str(Path.cwd())},
    )

    assert result.status == "completed"
    assert result.payload["framework"] == "pytest"
    assert result.payload["passed"] == 2
    assert result.payload["failed"] == 1
    assert result.payload["collected"] == 3
