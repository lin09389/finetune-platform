from __future__ import annotations

from pathlib import Path

from agent_runtime.command_policy import command_allowed, normalize_command
from agent_session.tools import AgentToolRegistry


def test_agent_tool_registry_has_core_tools():
    registry = AgentToolRegistry()
    names = {tool.name for tool in registry.list()}

    assert {"read", "search", "find_symbol", "find_references", "glob", "collect_context", "detect_project_commands", "patch", "bash_command", "read_execution", "finalize"} <= names
    assert {"git_status", "git_diff", "list_changed_files", "read_logs", "run_dev_server", "stop_dev_server", "get_server_status"} <= names
    assert registry.get("read").permission == "read"
    assert registry.get("patch").permission == "patch"
    assert registry.get("bash_command").permission == "command"


def test_unknown_tool_returns_none():
    registry = AgentToolRegistry()

    assert registry.get("unknown_tool") is None


def test_read_tool_accepts_multiple_paths(tmp_path):
    workspace = Path.cwd()
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
