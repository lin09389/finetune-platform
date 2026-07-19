"""Platform built-in tool tests (Task 9A): read / search / git-read.

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
    make_filesystem_handlers,
    make_git_handlers,
    platform_builtin_registry,
    resolve_workspace_path,
)
from tool_platform.builtins.filesystem import (
    GlobInput,
    GrepInput,
    LsInput,
    ReadFileInput,
    WorkspacePathError,
)
from tool_platform.builtins.git import GitDiffInput, GitLogInput, GitStatusInput
from tool_platform.gateway import ToolGateway
from tool_platform.models import ToolInvocation
from tool_platform.policy import ToolPolicyFacts
from tool_platform.taxonomy import ToolKind


def _read_only_facts() -> ToolPolicyFacts:
    """Facts satisfying the platform builtins' runtime/capability requirements."""
    return ToolPolicyFacts(
        runtime_kind="agent_session",
        enabled_capabilities=frozenset({"deepagents"}),
    )


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


def test_platform_builtins_are_read_only_low_risk():
    registry = platform_builtin_registry()
    for name in PLATFORM_BUILTIN_TOOL_NAMES:
        meta = registry.resolve(name).meta
        assert meta.kind in {ToolKind.READ, ToolKind.LIST_DIR, ToolKind.SEARCH}
        assert meta.risk.value == "low"
        from tool_platform.taxonomy import SideEffect

        assert meta.side_effects == frozenset({SideEffect.NONE})


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
