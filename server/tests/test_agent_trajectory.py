from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from agent_session.coding_diff import build_coding_diff_payload
from agent_session.deepagents_events import DeepAgentsEventMapper
from agent_session.deepagents_runtime import DeepAgentsSessionRunner
from agent_session.repository import AgentSessionRepository
from agent_session.trajectory import (
    TrajectoryGuardMiddleware,
    TrajectoryStateStore,
    is_successful_tool_result,
    is_verification_command,
    normalize_workspace_path,
    score_trajectory,
    validate_file_syntax,
)
from langchain_core.messages import ToolMessage
from langgraph.prebuilt.tool_node import ToolCallRequest

POLICY = {
    "enabled": True,
    "require_read_before_write": True,
    "require_context_before_create": True,
    "validate_after_write": True,
    "rollback_on_validation_failure": True,
    "require_verification_after_write": True,
    "max_auto_corrections": 2,
}


def _runtime_request(name: str, args: dict[str, Any], call_id: str = "call-1") -> ToolCallRequest:
    return ToolCallRequest(
        tool_call={"name": name, "args": args, "id": call_id, "type": "tool_call"},
        tool=None,
        state={"messages": []},
        runtime=None,  # type: ignore[arg-type]
    )


def _middleware(tmp_path: Path, workspace: Path):
    repository = AgentSessionRepository(str(tmp_path / "agents.db"))
    session = repository.create_session(
        {"agent_id": "build", "title": "trajectory", "project_path": str(workspace), "metadata": {}}
    )
    emitted: list[dict[str, Any]] = []
    middleware = TrajectoryGuardMiddleware(
        repository=repository,
        notify_event=lambda _session_id, event: emitted.append(event),
        session_id=session["id"],
        project_path=str(workspace),
        policy=POLICY,
    )
    TrajectoryStateStore(repository, lambda *_args: None, session["id"]).begin_run()
    return repository, session["id"], emitted, middleware


async def _success_handler(request: ToolCallRequest) -> ToolMessage:
    return ToolMessage(content="ok", tool_call_id=str(request.tool_call["id"]))


def test_execute_result_uses_deepagents_exit_code_without_misreading_other_tools():
    failed = ToolMessage(content="<no output>\n\nExit code: 1", tool_call_id="execute-1")
    succeeded = ToolMessage(
        content="<no output>\n[Command succeeded with exit code 0]",
        tool_call_id="execute-2",
    )

    assert is_successful_tool_result(failed, tool="execute") is False
    assert is_successful_tool_result(succeeded, tool="execute") is True
    assert is_successful_tool_result(failed, tool="read_file") is True


def test_existing_file_write_is_blocked_until_read(tmp_path: Path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    target = workspace / "app.py"
    target.write_text("print('old')\n", encoding="utf-8")
    repository, session_id, emitted, middleware = _middleware(tmp_path, workspace)
    called = False

    async def edit_handler(request: ToolCallRequest) -> ToolMessage:
        nonlocal called
        called = True
        target.write_text("print('new')\n", encoding="utf-8")
        return await _success_handler(request)

    blocked = asyncio.run(
        middleware.awrap_tool_call(
            _runtime_request("edit_file", {"file_path": "/workspace/app.py"}),
            edit_handler,
        )
    )

    assert isinstance(blocked, ToolMessage)
    assert blocked.status == "error"
    assert called is False
    assert target.read_text(encoding="utf-8") == "print('old')\n"
    assert any(event["event_type"] == "trajectory_guard_blocked" for event in emitted)

    asyncio.run(
        middleware.awrap_tool_call(
            _runtime_request("read_file", {"file_path": "/workspace/app.py"}, "call-read"),
            _success_handler,
        )
    )
    asyncio.run(
        middleware.awrap_tool_call(
            _runtime_request("edit_file", {"file_path": "/workspace/app.py"}, "call-edit"),
            edit_handler,
        )
    )

    state = repository.get_session(session_id)["metadata"]["trajectory_guard"]
    assert called is True
    assert state["writes"]["/workspace/app.py"] > state["reads"]["/workspace/app.py"]


def test_new_file_requires_parent_and_related_file_context(tmp_path: Path):
    workspace = tmp_path / "workspace"
    source_dir = workspace / "pkg"
    source_dir.mkdir(parents=True)
    related = source_dir / "existing.py"
    related.write_text("VALUE = 1\n", encoding="utf-8")
    _, _, _, middleware = _middleware(tmp_path, workspace)
    new_path = "/workspace/pkg/new_file.py"

    blocked_parent = asyncio.run(
        middleware.awrap_tool_call(
            _runtime_request("write_file", {"file_path": new_path}),
            _success_handler,
        )
    )
    assert blocked_parent.status == "error"
    assert "parent_directory_required" in str(blocked_parent.content)

    asyncio.run(
        middleware.awrap_tool_call(
            _runtime_request("ls", {"path": "/workspace/pkg"}, "call-ls"),
            _success_handler,
        )
    )
    blocked_related = asyncio.run(
        middleware.awrap_tool_call(
            _runtime_request("write_file", {"file_path": new_path}, "call-write-1"),
            _success_handler,
        )
    )
    assert blocked_related.status == "error"
    assert "related_file_required" in str(blocked_related.content)

    asyncio.run(
        middleware.awrap_tool_call(
            _runtime_request("read_file", {"file_path": "/workspace/pkg/existing.py"}, "call-read"),
            _success_handler,
        )
    )

    async def valid_write(request: ToolCallRequest) -> ToolMessage:
        (source_dir / "new_file.py").write_text("VALUE = 2\n", encoding="utf-8")
        return await _success_handler(request)

    allowed = asyncio.run(
        middleware.awrap_tool_call(
            _runtime_request("write_file", {"file_path": new_path}, "call-write-2"),
            valid_write,
        )
    )
    assert allowed.status != "error"


def test_failed_verification_requires_reread_before_next_edit(tmp_path: Path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    target = workspace / "app.py"
    target.write_text("print('old')\n", encoding="utf-8")
    repository, session_id, _, middleware = _middleware(tmp_path, workspace)

    asyncio.run(
        middleware.awrap_tool_call(
            _runtime_request("read_file", {"file_path": "/workspace/app.py"}, "read-1"),
            _success_handler,
        )
    )
    asyncio.run(
        middleware.awrap_tool_call(
            _runtime_request("edit_file", {"file_path": "/workspace/app.py"}, "edit-1"),
            _success_handler,
        )
    )

    async def failed_handler(request: ToolCallRequest) -> ToolMessage:
        return ToolMessage(content="tests failed", tool_call_id=str(request.tool_call["id"]), status="error")

    asyncio.run(
        middleware.awrap_tool_call(
            _runtime_request("execute", {"command": "python -m pytest server/tests/test_app.py"}, "verify-1"),
            failed_handler,
        )
    )
    blocked = asyncio.run(
        middleware.awrap_tool_call(
            _runtime_request("edit_file", {"file_path": "/workspace/app.py"}, "edit-2"),
            _success_handler,
        )
    )

    assert blocked.status == "error"
    assert "reread_required" in str(blocked.content)
    state = repository.get_session(session_id)["metadata"]["trajectory_guard"]
    assert state["reread_required"] == ["/workspace/app.py"]


def test_final_write_invalidates_earlier_verification(tmp_path: Path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    target = workspace / "app.py"
    target.write_text("print('old')\n", encoding="utf-8")
    repository, session_id, _, middleware = _middleware(tmp_path, workspace)
    store = TrajectoryStateStore(repository, lambda *_args: None, session_id)

    for name, args, call_id in [
        ("read_file", {"file_path": "/workspace/app.py"}, "read-1"),
        ("edit_file", {"file_path": "/workspace/app.py"}, "edit-1"),
        ("execute", {"command": "python -m pytest -q"}, "verify-1"),
        ("edit_file", {"file_path": "/workspace/app.py"}, "edit-2"),
    ]:
        asyncio.run(middleware.awrap_tool_call(_runtime_request(name, args, call_id), _success_handler))

    issues = store.completion_issues(POLICY)
    assert issues[0]["reason_code"] == "verification_required"


def test_document_reread_satisfies_completion_gate(tmp_path: Path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    target = workspace / "README.md"
    target.write_text("# Old\n", encoding="utf-8")
    repository, session_id, _, middleware = _middleware(tmp_path, workspace)
    store = TrajectoryStateStore(repository, lambda *_args: None, session_id)

    for name, args, call_id in [
        ("read_file", {"file_path": "/workspace/README.md"}, "read-1"),
        ("edit_file", {"file_path": "/workspace/README.md"}, "edit-1"),
        ("read_file", {"file_path": "/workspace/README.md"}, "read-2"),
    ]:
        asyncio.run(middleware.awrap_tool_call(_runtime_request(name, args, call_id), _success_handler))

    assert store.completion_issues(POLICY) == []


def test_verification_classifier_rejects_arbitrary_commands():
    assert is_verification_command("python -m pytest server/tests/test_demo.py -q")
    assert is_verification_command("npm run typecheck")
    assert is_verification_command("npx vitest run")
    assert not is_verification_command("python scripts/update_version.py")
    assert not is_verification_command("echo looks good")


def test_verification_classifier_recognizes_extended_verification_commands():
    assert is_verification_command("python -m unittest discover -s tests")
    assert is_verification_command("make test")
    assert is_verification_command("make check")
    assert is_verification_command("tox")
    assert is_verification_command("nox")
    assert is_verification_command("cmake --build build")
    assert is_verification_command("ctest --test-dir build")
    assert is_verification_command("ruby -c lib/parser.rb")
    assert is_verification_command("php -l src/index.php")
    assert is_verification_command("swift build")
    assert is_verification_command("swift test")
    assert is_verification_command("javac -d out src/Main.java")
    assert is_verification_command("rustc --edition 2021 src/main.rs")
    assert is_verification_command("bash scripts/run_tests.sh")
    assert is_verification_command("./run_tests.sh --check")
    # 自定义脚本只有含 test/check 字样才算验证，纯运行不算
    assert not is_verification_command("bash scripts/deploy.sh")
    assert not is_verification_command("./build.sh")


def test_workspace_path_normalization_rejects_escape():
    assert normalize_workspace_path("/workspace/pkg/../app.py") == "/workspace/app.py"
    assert normalize_workspace_path("../../outside.txt") == ""


def test_invalid_python_edit_is_rolled_back_immediately(tmp_path: Path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    target = workspace / "app.py"
    original = "def greet():\n    return 'hello'\n"
    target.write_text(original, encoding="utf-8")
    repository, session_id, emitted, middleware = _middleware(tmp_path, workspace)

    asyncio.run(
        middleware.awrap_tool_call(
            _runtime_request("read_file", {"file_path": "/workspace/app.py"}, "read"),
            _success_handler,
        )
    )

    async def invalid_edit(request: ToolCallRequest) -> ToolMessage:
        target.write_text("def greet():\nreturn 'broken'\n", encoding="utf-8")
        return await _success_handler(request)

    result = asyncio.run(
        middleware.awrap_tool_call(
            _runtime_request("edit_file", {"file_path": "/workspace/app.py"}, "edit"),
            invalid_edit,
        )
    )

    assert result.status == "error"
    assert "static_validation_failed" in str(result.content)
    assert target.read_text(encoding="utf-8") == original
    state = repository.get_session(session_id)["metadata"]["trajectory_guard"]
    assert state["reread_required"] == ["/workspace/app.py"]
    assert any(event["event_type"] == "trajectory_static_validation_failed" for event in emitted)


def test_invalid_new_json_is_deleted_after_validation_failure(tmp_path: Path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    repository, session_id, _, middleware = _middleware(tmp_path, workspace)
    target = workspace / "config.json"

    asyncio.run(
        middleware.awrap_tool_call(
            _runtime_request("ls", {"path": "/workspace"}, "ls"),
            _success_handler,
        )
    )

    async def invalid_write(request: ToolCallRequest) -> ToolMessage:
        target.write_text('{"enabled": true,,}', encoding="utf-8")
        return await _success_handler(request)

    result = asyncio.run(
        middleware.awrap_tool_call(
            _runtime_request("write_file", {"file_path": "/workspace/config.json"}, "write"),
            invalid_write,
        )
    )

    assert result.status == "error"
    assert not target.exists()
    state = repository.get_session(session_id)["metadata"]["trajectory_guard"]
    assert state["reread_required"] == []


def test_static_validators_cover_structured_and_script_files(tmp_path: Path):
    samples = {
        "good.py": "def value():\n    return 1\n",
        "good.json": '{"value": 1}',
        "good.yaml": "value: 1\n",
        "good.toml": "value = 1\n",
        "good.js": "const value = 1;\n",
        "good.ts": "const value: number = 1;\n",
    }
    for name, content in samples.items():
        path = tmp_path / name
        path.write_text(content, encoding="utf-8")
        result = validate_file_syntax(path, project_root=Path.cwd())
        assert result.valid is True, (name, result)

    invalid = tmp_path / "broken.yaml"
    invalid.write_text("items:\n  - ok\n broken: true\n", encoding="utf-8")
    result = validate_file_syntax(invalid, project_root=Path.cwd())
    assert result.supported is True
    assert result.valid is False
    assert result.line is not None


def test_completion_gate_auto_corrects_with_same_session_state(tmp_path: Path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    repository = AgentSessionRepository(str(tmp_path / "agents.db"))
    session = repository.create_session(
        {"agent_id": "build", "title": "completion", "project_path": str(workspace), "metadata": {}}
    )
    emitted: list[dict[str, Any]] = []
    notify = lambda _session_id, event: emitted.append(event)
    store = TrajectoryStateStore(repository, notify, session["id"])
    store.begin_run()
    store.record_step("read", tool="read_file", path="/workspace/app.py")
    write_state = store.record_step("write", tool="edit_file", path="/workspace/app.py")
    store.persist_coding_diff(
        build_coding_diff_payload(
            path="/workspace/app.py",
            before_existed=True,
            before_content=b"old\n",
            after_existed=True,
            after_content=b"new\n",
            write_sequence=write_state["sequence"],
        )
    )

    class FakeGraph:
        calls = 0

        async def astream_events(self, payload, *, config, version):
            self.calls += 1
            assert "轨迹自动纠正" in str(payload["messages"])
            store.record_step(
                "verification",
                tool="execute",
                command="python -m pytest -q",
                success=True,
            )
            if False:
                yield {}

    runner = DeepAgentsSessionRunner(repository=repository, notify_event=notify, model_call=lambda _: "ok")
    mapper = DeepAgentsEventMapper(repository, notify, session["id"])
    ready, _ = asyncio.run(
        runner._complete_trajectory_requirements(
            FakeGraph(),
            {"configurable": {"thread_id": "test"}},
            mapper,
            session["id"],
            POLICY,
            store,
        )
    )

    assert ready is True
    assert store.load()["auto_corrections"] == 1
    assert any(event["event_type"] == "trajectory_validation_required" for event in emitted)


def test_completion_gate_enters_manual_review_after_budget_exhausted(tmp_path: Path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    repository = AgentSessionRepository(str(tmp_path / "agents.db"))
    session = repository.create_session(
        {"agent_id": "build", "title": "manual", "project_path": str(workspace), "metadata": {}}
    )
    emitted: list[dict[str, Any]] = []
    notify = lambda _session_id, event: emitted.append(event)
    store = TrajectoryStateStore(repository, notify, session["id"])
    store.begin_run()
    store.record_step("read", tool="read_file", path="/workspace/app.py")
    store.record_step("write", tool="edit_file", path="/workspace/app.py")

    class UnusedGraph:
        async def astream_events(self, payload, *, config, version):
            raise AssertionError("correction graph must not run when budget is zero")
            yield {}

    runner = DeepAgentsSessionRunner(repository=repository, notify_event=notify, model_call=lambda _: "ok")
    mapper = DeepAgentsEventMapper(repository, notify, session["id"])
    policy = {**POLICY, "max_auto_corrections": 0}
    ready, _ = asyncio.run(
        runner._complete_trajectory_requirements(
            UnusedGraph(),
            {},
            mapper,
            session["id"],
            policy,
            store,
        )
    )

    updated = repository.get_session(session["id"])
    assert ready is False
    assert updated["status"] == "needs_manual_review"
    assert not any(event["event_type"] == "summary_completed" for event in emitted)


def test_fixed_trajectory_scenarios():
    fixture_path = Path(__file__).parent / "fixtures" / "agent_trajectory_scenarios.json"
    scenarios = json.loads(fixture_path.read_text(encoding="utf-8"))

    for scenario in scenarios:
        result = score_trajectory(scenario["steps"])
        expected = scenario["expected"]
        assert result["read_before_write"] is expected["read_before_write"], scenario["name"]
        assert result["final_verification"] is expected["final_verification"], scenario["name"]
        assert result["failure_recovery"] is expected["failure_recovery"], scenario["name"]
        assert result["score"] == expected["score"], scenario["name"]
