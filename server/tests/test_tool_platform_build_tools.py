"""Platform built-in tool tests (Task 9A/9B): read / search / git-read / write / edit.

Handlers are exercised directly and through the Task-7 Tool Gateway.  Path
isolation is fail-closed: only ``/workspace/`` paths that resolve under the
project root are accepted.  Production runtime is untouched (legacy).
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest
from tool_platform.builtins import (
    PLATFORM_BUILTIN_TOOL_NAMES,
    make_execute_handlers,
    make_filesystem_handlers,
    make_git_handlers,
    make_write_handlers,
    platform_builtin_registry,
    resolve_workspace_path,
)
from tool_platform.builtins.execute import ExecuteInput, RunTestsInput
from tool_platform.builtins.filesystem import (
    EditFileInput,
    GlobInput,
    GrepInput,
    LsInput,
    ReadFileInput,
    WorkspacePathError,
    WriteFileInput,
)
from tool_platform.builtins.git import GitDiffInput, GitLogInput, GitStatusInput
from tool_platform.gateway import ToolGateway
from tool_platform.models import ToolInvocation
from tool_platform.policy import ToolPolicyFacts
from tool_platform.taxonomy import SideEffect, ToolKind


def _read_only_facts() -> ToolPolicyFacts:
    """Facts satisfying the platform builtins' runtime/capability requirements."""
    return ToolPolicyFacts(
        runtime_kind="agent_session",
        enabled_capabilities=frozenset({"deepagents"}),
    )


def _safe_auto_facts() -> ToolPolicyFacts:
    """safe_auto: workspace writes run without approval; sensitive effects ask."""
    return ToolPolicyFacts(
        runtime_kind="agent_session",
        enabled_capabilities=frozenset({"deepagents"}),
        require_approval_for=frozenset(
            {SideEffect.PROCESS, SideEffect.NETWORK, SideEffect.EXTERNAL_WRITE, SideEffect.CREDENTIAL, SideEffect.DESTRUCTIVE}
        ),
    )


def _confirm_all_facts() -> ToolPolicyFacts:
    """confirm_all: every non-NONE side effect (incl. workspace write) asks."""
    return ToolPolicyFacts(
        runtime_kind="agent_session",
        enabled_capabilities=frozenset({"deepagents"}),
        require_approval_for=frozenset(
            {
                SideEffect.WORKSPACE_WRITE,
                SideEffect.PROCESS,
                SideEffect.NETWORK,
                SideEffect.EXTERNAL_WRITE,
                SideEffect.CREDENTIAL,
                SideEffect.DESTRUCTIVE,
            }
        ),
    )


def _read_only_block_facts() -> ToolPolicyFacts:
    """read_only: every non-NONE side effect is hard-denied."""
    return ToolPolicyFacts(
        runtime_kind="agent_session",
        enabled_capabilities=frozenset({"deepagents"}),
        deny_for=frozenset(
            {
                SideEffect.WORKSPACE_WRITE,
                SideEffect.PROCESS,
                SideEffect.NETWORK,
                SideEffect.EXTERNAL_WRITE,
                SideEffect.CREDENTIAL,
                SideEffect.DESTRUCTIVE,
            }
        ),
    )


class _ApprovingAdapter:
    def request_approval(self, invocation, policy_decision):
        from tool_platform.handlers import ApprovalOutcome

        return ApprovalOutcome(granted=True)


# --- path isolation -----------------------------------------------------------


def test_resolve_workspace_path_maps_and_rejects_escape(tmp_path: Path):
    (tmp_path / "app.py").write_text("x = 1\n", encoding="utf-8")

    assert resolve_workspace_path("/workspace/app.py", tmp_path) == tmp_path / "app.py"
    assert resolve_workspace_path("/workspace/", tmp_path) == tmp_path.resolve()

    with pytest.raises(WorkspacePathError):
        resolve_workspace_path("/workspace/../etc/passwd", tmp_path)
    with pytest.raises(WorkspacePathError):
        resolve_workspace_path("/etc/passwd", tmp_path)
    with pytest.raises(WorkspacePathError):
        resolve_workspace_path("/context/task.md", tmp_path)


# --- filesystem handlers ------------------------------------------------------


@pytest.mark.asyncio
async def test_filesystem_handlers_read_list_glob_grep(tmp_path: Path):
    (tmp_path / "app.py").write_text("hello\nworld\nhello again\n", encoding="utf-8")
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "util.py").write_text("value = 42\n", encoding="utf-8")

    handlers = make_filesystem_handlers(tmp_path)

    ls_out = await handlers["workspace.ls"](LsInput(path="/workspace/"))
    assert "app.py" in ls_out.entries and "pkg" in ls_out.entries

    read_out = await handlers["workspace.read_file"](
        ReadFileInput(file_path="/workspace/app.py")
    )
    assert read_out.content.startswith("hello")
    assert read_out.line_count == 3

    glob_out = await handlers["workspace.glob"](GlobInput(pattern="*.py", path="/workspace/"))
    assert "app.py" in glob_out.matches
    assert "pkg/util.py" in glob_out.matches

    grep_files = await handlers["workspace.grep"](
        GrepInput(pattern="hello", path="/workspace/", output_mode="files_with_matches")
    )
    assert "app.py" in grep_files.matches

    grep_count = await handlers["workspace.grep"](
        GrepInput(pattern="hello", path="/workspace/", output_mode="count")
    )
    assert grep_count.count == 2

    grep_content = await handlers["workspace.grep"](
        GrepInput(pattern="hello", path="/workspace/", output_mode="content")
    )
    assert any("app.py:" in line for line in grep_content.matches)


@pytest.mark.asyncio
async def test_filesystem_handler_rejects_path_escape(tmp_path: Path):
    (tmp_path / "app.py").write_text("ok\n", encoding="utf-8")
    handlers = make_filesystem_handlers(tmp_path)

    with pytest.raises(WorkspacePathError):
        await handlers["workspace.read_file"](
            ReadFileInput(file_path="/workspace/../etc/passwd")
        )


@pytest.mark.asyncio
async def test_filesystem_handler_missing_file_raises(tmp_path: Path):
    handlers = make_filesystem_handlers(tmp_path)
    with pytest.raises(FileNotFoundError):
        await handlers["workspace.read_file"](
            ReadFileInput(file_path="/workspace/missing.py")
        )


# --- gateway integration ------------------------------------------------------


@pytest.mark.asyncio
async def test_gateway_dispatches_readonly_filesystem_tool(tmp_path: Path):
    (tmp_path / "app.py").write_text("print('hi')\n", encoding="utf-8")
    registry = platform_builtin_registry()
    handlers = make_filesystem_handlers(tmp_path)
    sink: list = []
    gateway = ToolGateway(registry, sink.append, handlers=handlers)

    invocation = ToolInvocation(
        invocation_id="inv-read",
        tool_name="read_file",
        arguments={"file_path": "/workspace/app.py"},
    )
    outcome = await gateway.invoke(invocation, _read_only_facts())

    assert outcome.status == "success"
    assert outcome.decision == "allow"
    assert outcome.result is not None
    assert "print('hi')" in outcome.result.output["content"]
    assert [event.event_type for event in sink] == ["tool.started", "tool.completed"]


@pytest.mark.asyncio
async def test_gateway_resolves_canonical_and_alias(tmp_path: Path):
    (tmp_path / "app.py").write_text("x\n", encoding="utf-8")
    registry = platform_builtin_registry()
    gateway = ToolGateway(registry, lambda _e: None, handlers=make_filesystem_handlers(tmp_path))

    by_alias = await gateway.invoke(
        ToolInvocation(invocation_id="inv-1", tool_name="read_file", arguments={"file_path": "/workspace/app.py"}),
        _read_only_facts(),
    )
    by_canonical = await gateway.invoke(
        ToolInvocation(invocation_id="inv-2", tool_name="workspace.read_file", arguments={"file_path": "/workspace/app.py"}),
        _read_only_facts(),
    )
    assert by_alias.status == "success" and by_canonical.status == "success"
    assert by_alias.canonical_name == "workspace.read_file"


# --- canonical compliance -----------------------------------------------------


def test_platform_builtins_register_without_conflict():
    registry = platform_builtin_registry()
    assert registry.frozen is True
    assert {
        "workspace.ls",
        "workspace.read_file",
        "workspace.glob",
        "workspace.grep",
        "workspace.write_file",
        "workspace.edit_file",
        "workspace.execute",
        "workspace.run_tests",
        "git.status",
        "git.diff",
        "git.log",
    } == PLATFORM_BUILTIN_TOOL_NAMES


def test_platform_builtins_do_not_collide_with_deepagents_binding_names():
    from tool_platform.adapters.deepagents import builtin_tool_bindings

    deepagents_names = {b.definition.meta.canonical_name for b in builtin_tool_bindings()}
    # Platform canonical names are namespaced; they never equal a DeepAgents
    # builtin canonical name (which is the bare tool name).
    assert PLATFORM_BUILTIN_TOOL_NAMES.isdisjoint(deepagents_names)


def test_read_only_builtins_are_low_risk_and_mutating_builtins_are_medium():
    registry = platform_builtin_registry()
    read_only = {"workspace.ls", "workspace.read_file", "workspace.glob", "workspace.grep", "git.status", "git.diff", "git.log"}
    for name in read_only:
        meta = registry.resolve(name).meta
        assert meta.kind in {ToolKind.READ, ToolKind.LIST_DIR, ToolKind.SEARCH}
        assert meta.risk.value == "low"
        assert meta.side_effects == frozenset({SideEffect.NONE})
    for name in ("workspace.write_file", "workspace.edit_file"):
        meta = registry.resolve(name).meta
        assert meta.kind in {ToolKind.WRITE, ToolKind.EDIT}
        assert meta.risk.value == "medium"
        assert meta.side_effects == frozenset({SideEffect.WORKSPACE_WRITE})
        assert meta.idempotent is False
    for name in ("workspace.execute", "workspace.run_tests"):
        meta = registry.resolve(name).meta
        assert meta.kind is ToolKind.EXECUTE
        assert meta.risk.value == "high"
        assert meta.side_effects == frozenset(
            {SideEffect.PROCESS, SideEffect.WORKSPACE_WRITE, SideEffect.DESTRUCTIVE}
        )
        assert meta.idempotent is False


# --- git handlers -------------------------------------------------------------


def _git(tmp_path: Path, *args: str) -> str:
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
    return subprocess.check_output(["git", *args], cwd=str(tmp_path), env=env, text=True, stderr=subprocess.STDOUT)


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    _git(tmp_path, "init")
    (tmp_path / "a.txt").write_text("first\n", encoding="utf-8")
    _git(tmp_path, "add", "a.txt")
    _git(tmp_path, "commit", "-m", "first")
    (tmp_path / "a.txt").write_text("first\nsecond\n", encoding="utf-8")
    return tmp_path


@pytest.mark.asyncio
async def test_git_handlers_status_diff_log(git_repo: Path):
    handlers = make_git_handlers(git_repo, extra_roots=[git_repo])

    status = await handlers["git.status"](GitStatusInput(path="/workspace/"))
    assert "a.txt" in status.porcelain

    diff = await handlers["git.diff"](GitDiffInput(path="/workspace/", staged=False))
    assert "second" in diff.diff

    log = await handlers["git.log"](GitLogInput(path="/workspace/", limit=5))
    assert "first" in log.log


def test_git_handlers_reject_unvalidated_root(tmp_path: Path):
    # A path outside the allowed workspace roots must fail closed.
    with pytest.raises(ValueError):
        make_git_handlers("/nonexistent/root/xyz")


# --- write / edit handlers (Task 9B) -----------------------------------------


@pytest.mark.asyncio
async def test_write_file_handler_creates_and_overwrites_atomically(tmp_path: Path):
    handlers = make_write_handlers(tmp_path)

    created = await handlers["workspace.write_file"](
        WriteFileInput(file_path="/workspace/app.py", content="first\n")
    )
    assert created.bytes_written == len(b"first\n")
    assert (tmp_path / "app.py").read_text(encoding="utf-8") == "first\n"

    overwritten = await handlers["workspace.write_file"](
        WriteFileInput(file_path="/workspace/app.py", content="second\n")
    )
    assert overwritten.bytes_written == len(b"second\n")
    assert (tmp_path / "app.py").read_text(encoding="utf-8") == "second\n"
    # No leftover tmp file from the atomic write.
    assert not (tmp_path / "app.py.tmp").exists()


@pytest.mark.asyncio
async def test_write_file_handler_creates_parent_dirs(tmp_path: Path):
    handlers = make_write_handlers(tmp_path)
    await handlers["workspace.write_file"](
        WriteFileInput(file_path="/workspace/pkg/mod.py", content="x = 1\n")
    )
    assert (tmp_path / "pkg" / "mod.py").read_text(encoding="utf-8") == "x = 1\n"


@pytest.mark.asyncio
async def test_write_file_handler_rejects_path_escape(tmp_path: Path):
    handlers = make_write_handlers(tmp_path)
    with pytest.raises(WorkspacePathError):
        await handlers["workspace.write_file"](
            WriteFileInput(file_path="/workspace/../etc/evil", content="x")
        )


@pytest.mark.asyncio
async def test_edit_file_handler_unique_replacement(tmp_path: Path):
    (tmp_path / "app.py").write_text("alpha\nbeta\nalpha\n", encoding="utf-8")
    handlers = make_write_handlers(tmp_path)

    out = await handlers["workspace.edit_file"](
        EditFileInput(file_path="/workspace/app.py", old_string="beta", new_string="BETA")
    )
    assert out.replacements == 1
    assert (tmp_path / "app.py").read_text(encoding="utf-8") == "alpha\nBETA\nalpha\n"


@pytest.mark.asyncio
async def test_edit_file_handler_replace_all(tmp_path: Path):
    (tmp_path / "app.py").write_text("alpha\nbeta\nalpha\n", encoding="utf-8")
    handlers = make_write_handlers(tmp_path)

    out = await handlers["workspace.edit_file"](
        EditFileInput(file_path="/workspace/app.py", old_string="alpha", new_string="ALPHA", replace_all=True)
    )
    assert out.replacements == 2
    assert (tmp_path / "app.py").read_text(encoding="utf-8") == "ALPHA\nbeta\nALPHA\n"


@pytest.mark.asyncio
async def test_edit_file_handler_rejects_missing_and_non_unique(tmp_path: Path):
    (tmp_path / "app.py").write_text("a\na\n", encoding="utf-8")
    handlers = make_write_handlers(tmp_path)

    with pytest.raises(ValueError, match="not found"):
        await handlers["workspace.edit_file"](
            EditFileInput(file_path="/workspace/app.py", old_string="missing", new_string="x")
        )
    with pytest.raises(ValueError, match="not unique"):
        await handlers["workspace.edit_file"](
            EditFileInput(file_path="/workspace/app.py", old_string="a", new_string="x")
        )


@pytest.mark.asyncio
async def test_edit_file_handler_rejects_path_escape(tmp_path: Path):
    (tmp_path / "app.py").write_text("x", encoding="utf-8")
    handlers = make_write_handlers(tmp_path)
    with pytest.raises(WorkspacePathError):
        await handlers["workspace.edit_file"](
            EditFileInput(file_path="/workspace/../etc/evil", old_string="x", new_string="y")
        )


# --- gateway integration for write/edit --------------------------------------


@pytest.mark.asyncio
async def test_gateway_write_safe_auto_allows_without_approval(tmp_path: Path):
    registry = platform_builtin_registry()
    gateway = ToolGateway(
        registry,
        lambda _e: None,
        handlers={**make_filesystem_handlers(tmp_path), **make_write_handlers(tmp_path)},
    )
    invocation = ToolInvocation(
        invocation_id="inv-write",
        tool_name="write_file",
        arguments={"file_path": "/workspace/out.py", "content": "print(1)\n"},
    )

    outcome = await gateway.invoke(invocation, _safe_auto_facts())

    assert outcome.status == "success"
    assert outcome.decision == "allow"
    assert (tmp_path / "out.py").read_text(encoding="utf-8") == "print(1)\n"


@pytest.mark.asyncio
async def test_gateway_write_confirm_all_suspends_by_default(tmp_path: Path):
    registry = platform_builtin_registry()
    calls = {"handler": 0}
    handlers = make_write_handlers(tmp_path)
    wrapped = {
        "workspace.write_file": (lambda h: (lambda req: (calls.__setitem__("handler", calls["handler"] + 1), h(req))[1]))(handlers["workspace.write_file"])
    }
    gateway = ToolGateway(registry, lambda _e: None, handlers=wrapped)

    outcome = await gateway.invoke(
        ToolInvocation(invocation_id="inv-w", tool_name="write_file", arguments={"file_path": "/workspace/out.py", "content": "x"}),
        _confirm_all_facts(),
    )

    assert outcome.status == "needs_approval"
    assert outcome.decision == "ask"
    assert calls["handler"] == 0
    assert not (tmp_path / "out.py").exists()


@pytest.mark.asyncio
async def test_gateway_write_confirm_all_dispatches_with_approving_adapter(tmp_path: Path):
    registry = platform_builtin_registry()
    gateway = ToolGateway(
        registry,
        lambda _e: None,
        handlers={**make_filesystem_handlers(tmp_path), **make_write_handlers(tmp_path)},
        approval_adapter=_ApprovingAdapter(),
    )

    outcome = await gateway.invoke(
        ToolInvocation(invocation_id="inv-w2", tool_name="edit_file", arguments={"file_path": "/workspace/app.py", "old_string": "a", "new_string": "b"}),
        _confirm_all_facts(),
    )
    # edit_file on a missing file would fail; seed it first via safe_auto, then edit under confirm_all.
    await gateway.invoke(
        ToolInvocation(invocation_id="inv-seed", tool_name="write_file", arguments={"file_path": "/workspace/app.py", "content": "a"}),
        _safe_auto_facts(),
    )
    outcome = await gateway.invoke(
        ToolInvocation(invocation_id="inv-w3", tool_name="edit_file", arguments={"file_path": "/workspace/app.py", "old_string": "a", "new_string": "b"}),
        _confirm_all_facts(),
    )

    assert outcome.status == "success"
    assert (tmp_path / "app.py").read_text(encoding="utf-8") == "b"


@pytest.mark.asyncio
async def test_gateway_write_read_only_denies(tmp_path: Path):
    registry = platform_builtin_registry()
    gateway = ToolGateway(registry, lambda _e: None, handlers=make_write_handlers(tmp_path))

    outcome = await gateway.invoke(
        ToolInvocation(invocation_id="inv-w4", tool_name="write_file", arguments={"file_path": "/workspace/out.py", "content": "x"}),
        _read_only_block_facts(),
    )

    assert outcome.status == "denied"
    assert outcome.error is not None
    assert outcome.error.code == "denied_side_effect"
    assert not (tmp_path / "out.py").exists()


# --- execute / run_tests handlers (Task 9C) ----------------------------------


@pytest.mark.asyncio
async def test_execute_handler_runs_command_and_captures_output(tmp_path: Path):
    handlers = make_execute_handlers(tmp_path)
    out = await handlers["workspace.execute"](ExecuteInput(command="echo hello"))
    assert out.exit_code == 0
    assert "hello" in out.output


@pytest.mark.asyncio
async def test_execute_handler_reports_nonzero_exit(tmp_path: Path):
    handlers = make_execute_handlers(tmp_path)
    out = await handlers["workspace.execute"](ExecuteInput(command="python -c \"raise SystemExit(3)\""))
    assert out.exit_code == 3


@pytest.mark.asyncio
async def test_run_tests_handler_parses_pass_fail(tmp_path: Path):
    handlers = make_execute_handlers(tmp_path)
    passed = await handlers["workspace.run_tests"](RunTestsInput(command="echo ok"))
    assert passed.passed is True
    assert passed.exit_code == 0

    failed = await handlers["workspace.run_tests"](RunTestsInput(command="python -c \"raise SystemExit(1)\""))
    assert failed.passed is False
    assert failed.exit_code == 1


@pytest.mark.asyncio
async def test_execute_handler_times_out(tmp_path: Path):
    handlers = make_execute_handlers(tmp_path)
    out = await handlers["workspace.execute"](
        ExecuteInput(command="python -c \"import time; time.sleep(5)\"", timeout=1)
    )
    assert out.exit_code == 124
    assert "timed out" in out.output.lower()


@pytest.mark.asyncio
async def test_gateway_execute_safe_auto_asks(tmp_path: Path):
    registry = platform_builtin_registry()
    gateway = ToolGateway(registry, lambda _e: None, handlers=make_execute_handlers(tmp_path))
    outcome = await gateway.invoke(
        ToolInvocation(invocation_id="inv-ex", tool_name="execute", arguments={"command": "echo hi"}),
        _safe_auto_facts(),
    )
    # safe_auto gates process/destructive effects -> ask.
    assert outcome.status == "needs_approval"
    assert outcome.decision == "ask"


@pytest.mark.asyncio
async def test_gateway_execute_approving_adapter_dispatches(tmp_path: Path):
    registry = platform_builtin_registry()
    gateway = ToolGateway(
        registry,
        lambda _e: None,
        handlers=make_execute_handlers(tmp_path),
        approval_adapter=_ApprovingAdapter(),
    )
    outcome = await gateway.invoke(
        ToolInvocation(invocation_id="inv-ex2", tool_name="execute", arguments={"command": "echo hi"}),
        _safe_auto_facts(),
    )
    assert outcome.status == "success"
    assert "hi" in outcome.result.output["output"]


@pytest.mark.asyncio
async def test_gateway_execute_read_only_denies(tmp_path: Path):
    registry = platform_builtin_registry()
    gateway = ToolGateway(registry, lambda _e: None, handlers=make_execute_handlers(tmp_path))
    outcome = await gateway.invoke(
        ToolInvocation(invocation_id="inv-ex3", tool_name="execute", arguments={"command": "echo hi"}),
        _read_only_block_facts(),
    )
    assert outcome.status == "denied"
    assert outcome.error.code == "denied_side_effect"


# --- legacy execute entry blockade (Task 9C core) ----------------------------


def test_controlled_backend_blocks_legacy_execute_without_running(tmp_path: Path):
    from agent_session.platform_shell import PlatformShellBackend

    sentinel = tmp_path / "sentinel.txt"
    backend = PlatformShellBackend(root_dir=str(tmp_path), virtual_mode=True, controlled_execute=True)

    # A command that would create a side-effect file if it actually ran.
    response = backend.execute(
        f'python -c "open(r\'{sentinel}\', \'w\').write(\'x\')"'
    )

    assert response.exit_code == 1
    assert "gated" in response.output.lower()
    # No subprocess ran: the sentinel file was never created.
    assert not sentinel.exists()


def test_legacy_backend_executes_normally(tmp_path: Path):
    from agent_session.platform_shell import PlatformShellBackend

    backend = PlatformShellBackend(root_dir=str(tmp_path), virtual_mode=True, controlled_execute=False)
    response = backend.execute("echo legacy-ok")
    assert response.exit_code == 0
    assert "legacy-ok" in response.output


def test_runtime_factory_passes_controlled_flag_for_controlled_contract(tmp_path: Path):
    from agent_session.runtime_contract import AgentRuntimeContract
    from agent_session.runtime_factory import DeepAgentsRuntimeFactory

    captured: dict[str, object] = {}

    def fake_build(project_path, **kwargs):
        captured.update(kwargs)
        return object()

    import agent_session.runtime as runtime_mod

    original = runtime_mod.build_deepagents_backend
    runtime_mod.build_deepagents_backend = fake_build
    try:
        factory = DeepAgentsRuntimeFactory()
        legacy_contract = AgentRuntimeContract.for_agent_session(
            session={"id": "s", "project_path": str(tmp_path), "agent_id": "build", "metadata": {}},
            goal="g",
            model=object(),
            agent_registry=__import__("agent_session.agent_registry", fromlist=["AgentRegistry"]).AgentRegistry(),
            tools=[],
            middleware=[],
            subagents=[],
            checkpointer=False,
        )
        controlled_contract = AgentRuntimeContract.for_agent_session(
            session={"id": "s", "project_path": str(tmp_path), "agent_id": "build",
                     "metadata": {"orchestration_mode": "controlled"}},
            goal="g",
            model=object(),
            agent_registry=__import__("agent_session.agent_registry", fromlist=["AgentRegistry"]).AgentRegistry(),
            tools=[],
            middleware=[],
            subagents=[],
            checkpointer=False,
        )
        factory._backend_for(legacy_contract)
        assert captured.get("controlled_execute") is False
        factory._backend_for(controlled_contract)
        assert captured.get("controlled_execute") is True
    finally:
        runtime_mod.build_deepagents_backend = original
