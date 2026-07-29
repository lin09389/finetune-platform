"""Phase B0: task scope + verify recipe."""
from __future__ import annotations

from pathlib import Path

import pytest
from agent_session.task_scope import (
    apply_task_scope_to_metadata,
    build_task_scope,
    discover_verify_recipe,
    format_scope_prompt_section,
    format_verify_recipe_prompt_section,
    normalize_rel_path,
    path_in_scope,
    resolve_scope_paths,
)

from context.deepagents import build_deepagents_context_pack


def test_normalize_and_resolve_scope(tmp_path: Path):
    (tmp_path / "server").mkdir()
    (tmp_path / "client" / "src").mkdir(parents=True)
    paths = resolve_scope_paths(tmp_path, ["server", "/workspace/client/src", "server"])
    assert paths == ["server", "client/src"]

    with pytest.raises(ValueError, match="does not exist"):
        resolve_scope_paths(tmp_path, ["missing-dir"])

    with pytest.raises(ValueError, match="\\.\\."):
        normalize_rel_path("../etc")


def test_path_in_scope():
    scope = {"paths": ["server/agent_session", "client/src/agent"]}
    assert path_in_scope("server/agent_session/foo.py", scope) is True
    assert path_in_scope("/workspace/client/src/agent/x.ts", scope) is True
    assert path_in_scope("server/other/x.py", scope) is False
    assert path_in_scope("anywhere", None) is True
    assert path_in_scope("anywhere", {"paths": []}) is True


def test_apply_task_scope_metadata(tmp_path: Path):
    (tmp_path / "pkg").mkdir()
    meta = apply_task_scope_to_metadata({}, tmp_path, paths=["pkg"], notes="only package")
    assert meta["task_scope"]["paths"] == ["pkg"]
    assert meta["task_scope"]["notes"] == "only package"
    cleared = apply_task_scope_to_metadata(meta, tmp_path, clear=True)
    assert "task_scope" not in cleared


def test_discover_verify_recipe_python_and_docs(tmp_path: Path):
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    (tmp_path / "VERIFY.md").write_text("# Verify\n\nRun pytest.\n", encoding="utf-8")
    (tmp_path / "package.json").write_text(
        '{"scripts":{"typecheck":"tsc -b","test":"vitest"}}',
        encoding="utf-8",
    )
    recipe = discover_verify_recipe(tmp_path)
    assert recipe is not None
    assert "VERIFY.md" in recipe["sources"]
    assert any("pytest" in c for c in recipe["commands"])
    assert any("typecheck" in c for c in recipe["commands"])
    section = format_verify_recipe_prompt_section(recipe)
    assert "验证菜谱" in section
    assert "verify-recipe.md" in section


@pytest.mark.asyncio
async def test_context_pack_includes_scope_and_recipe(tmp_path: Path):
    (tmp_path / "server").mkdir()
    (tmp_path / "VERIFY.md").write_text("## Testing\n\npytest -q\n", encoding="utf-8")
    scope = build_task_scope(tmp_path, paths=["server"])
    recipe = discover_verify_recipe(tmp_path)
    pack = await build_deepagents_context_pack(
        goal="fix a bug in server",
        active_context=None,
        explicit_context=None,
        project_path=str(tmp_path),
        task_scope=scope,
        verify_recipe=recipe,
    )
    assert "【任务范围" in pack.prompt or "Scope" in pack.prompt
    assert "验证菜谱" in pack.prompt
    # files are FileData dicts after normalize
    assert any("verify-recipe" in path for path in pack.files)
    assert any("task-scope" in path for path in pack.files)


def test_scope_prompt_section():
    text = format_scope_prompt_section({"paths": ["server/api"], "notes": "backend only"})
    assert "server/api" in text
    assert "backend only" in text
    assert format_scope_prompt_section(None) == ""


def test_recommend_verify_commands_python_and_client(tmp_path: Path):
    from agent_session.task_scope import (
        format_verify_recommendations_section,
        recommend_verify_commands,
    )

    (tmp_path / "server" / "tests").mkdir(parents=True)
    (tmp_path / "server" / "foo").mkdir(parents=True)
    (tmp_path / "server" / "foo" / "bar.py").write_text("x=1\n", encoding="utf-8")
    (tmp_path / "server" / "tests" / "test_bar.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")
    (tmp_path / "client" / "src").mkdir(parents=True)
    (tmp_path / "client" / "package.json").write_text(
        '{"scripts":{"typecheck":"tsc -b","test":"vitest run"}}',
        encoding="utf-8",
    )

    recipe = {
        "commands": ["python -m pytest -q", "npm run typecheck", "npm run test"],
        "sources": ["package.json"],
    }
    rec = recommend_verify_commands(
        written_paths=["server/foo/bar.py", "client/src/Widget.tsx"],
        recipe=recipe,
        project_path=tmp_path,
    )
    cmds = " ".join(rec["commands"])
    assert "py_compile" in cmds or "pytest" in cmds
    assert "typecheck" in cmds or "vitest" in cmds
    # path-narrowed test when present
    assert any("test_bar" in c for c in rec["commands"]) or "pytest" in cmds

    section = format_verify_recommendations_section(rec)
    assert "相关验证推荐" in section
    assert "`" in section


def test_recommend_verify_commands_docs_only():
    from agent_session.task_scope import recommend_verify_commands

    rec = recommend_verify_commands(written_paths=["docs/guide.md"], recipe=None, project_path=None)
    assert rec["strategy"] == "docs_reread"
    assert rec["commands"] == []


def test_trajectory_blocks_write_outside_scope(tmp_path: Path):
    import asyncio

    from agent_session.repository import AgentSessionRepository
    from agent_session.trajectory import TrajectoryGuardMiddleware, TrajectoryStateStore
    from langchain_core.messages import ToolMessage
    from langgraph.prebuilt.tool_node import ToolCallRequest

    workspace = tmp_path / "ws"
    (workspace / "allowed").mkdir(parents=True)
    (workspace / "denied").mkdir()
    (workspace / "allowed" / "a.py").write_text("x=1\n", encoding="utf-8")
    (workspace / "denied" / "b.py").write_text("y=2\n", encoding="utf-8")

    repository = AgentSessionRepository(str(tmp_path / "agents.db"))
    session = repository.create_session(
        {
            "agent_id": "build",
            "title": "scope",
            "project_path": str(workspace),
            "metadata": apply_task_scope_to_metadata({}, workspace, paths=["allowed"]),
        }
    )
    middleware = TrajectoryGuardMiddleware(
        repository=repository,
        notify_event=lambda *_a, **_k: None,
        session_id=session["id"],
        project_path=str(workspace),
        policy={
            "enabled": True,
            "require_read_before_write": False,
            "require_context_before_create": False,
            "validate_after_write": False,
            "rollback_on_validation_failure": False,
            "require_verification_after_write": False,
            "max_auto_corrections": 0,
        },
    )
    TrajectoryStateStore(repository, lambda *_a, **_k: None, session["id"]).begin_run()

    async def _ok(request: ToolCallRequest) -> ToolMessage:
        return ToolMessage(content="ok", tool_call_id=str(request.tool_call["id"]))

    req = ToolCallRequest(
        tool_call={
            "name": "edit_file",
            "args": {"file_path": "/workspace/denied/b.py", "old_string": "y=2", "new_string": "y=3"},
            "id": "c1",
            "type": "tool_call",
        },
        tool=None,
        state={"messages": []},
        runtime=None,  # type: ignore[arg-type]
    )
    result = asyncio.get_event_loop().run_until_complete(middleware.awrap_tool_call(req, _ok))
    assert isinstance(result, ToolMessage)
    assert "Scope" in str(result.content) or "范围" in str(result.content)
