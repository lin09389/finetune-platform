"""P0-1: autonomy_mode wires into real HITL interrupt + tool constraints.

Multi-round matrix against the shipped session create + permission/runtime
resolution path used when DeepAgents is constructed (not a parallel fake policy).

Product mapping locked by these tests:
- confirm_all → interrupt write_file/edit_file/execute (full HITL)
- safe_auto → no interrupt map for those tools (strictly weaker than confirm_all)
- read_only → write/edit/execute excluded; FS profile readonly (mutation fail-closed)
- explicit deepagents_interrupt_on wins over autonomy defaults
"""

from __future__ import annotations

from pathlib import Path

import pytest
from agent_session.execution_context import AgentDefinition
from agent_session.models import AgentSessionCreate
from agent_session.permission import (
    DEFAULT_DEEPAGENTS_INTERRUPT_ON,
    WRITE_EXECUTE_TOOLS,
    default_deepagents_permission_metadata,
    interrupt_on_for_autonomy,
    normalize_autonomy_mode,
    permission_policy_for_agent,
    resolve_deepagents_interrupt_on,
)
from agent_session.repository import AgentSessionRepository
from agent_session.runtime_policy import build_agent_runtime_policy
from agent_session.service import AgentSessionService
from deepagents.middleware.filesystem import _check_fs_permission

# --- pure mapping table (round 1) -------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (None, "safe_auto"),
        ("", "safe_auto"),
        ("safe_auto", "safe_auto"),
        ("confirm_all", "confirm_all"),
        ("manual", "confirm_all"),
        ("read_only", "read_only"),
        ("readonly", "read_only"),
        ("READ-ONLY", "read_only"),
    ],
)
def test_normalize_autonomy_mode(raw, expected):
    assert normalize_autonomy_mode(raw) == expected


def test_interrupt_on_for_autonomy_confirm_stronger_than_safe_auto():
    confirm = interrupt_on_for_autonomy("confirm_all")
    safe = interrupt_on_for_autonomy("safe_auto")
    read_only = interrupt_on_for_autonomy("read_only")
    assert confirm == DEFAULT_DEEPAGENTS_INTERRUPT_ON
    assert safe is None
    assert read_only is None
    # Concrete weaker bar: confirm gates all three; safe gates none.
    for tool in ("write_file", "edit_file", "execute"):
        assert confirm[tool] is True
        assert safe is None or not safe.get(tool)


def test_explicit_deepagents_interrupt_on_wins_over_autonomy():
    # Full HITL even under safe_auto when key is True.
    assert resolve_deepagents_interrupt_on(
        {"autonomy_mode": "safe_auto", "deepagents_interrupt_on": True}
    ) == DEFAULT_DEEPAGENTS_INTERRUPT_ON
    # Disabled HITL even under confirm_all when key is False.
    assert (
        resolve_deepagents_interrupt_on(
            {"autonomy_mode": "confirm_all", "deepagents_interrupt_on": False}
        )
        is None
    )
    custom = {"write_file": False, "edit_file": True, "execute": False}
    assert resolve_deepagents_interrupt_on(
        {"autonomy_mode": "confirm_all", "deepagents_interrupt_on": custom}
    ) == {"edit_file": True}
    # Missing key → derive from autonomy.
    assert resolve_deepagents_interrupt_on({"autonomy_mode": "confirm_all"}) == DEFAULT_DEEPAGENTS_INTERRUPT_ON
    assert resolve_deepagents_interrupt_on({"autonomy_mode": "safe_auto"}) is None


# --- session create path (round 2) -----------------------------------------------


@pytest.fixture
def coding_workspace(tmp_path: Path) -> Path:
    """Workspace under the repo tree so path_policy allowlist accepts it."""
    # Prefer a path under cwd (always an allowed root); fall back to tmp only if needed.
    root = Path.cwd() / "tmp" / f"autonomy-ws-{tmp_path.name}"
    root.mkdir(parents=True, exist_ok=True)
    (root / "app.py").write_text("x = 1\n", encoding="utf-8")
    yield root
    import shutil

    shutil.rmtree(root, ignore_errors=True)


def _create(service: AgentSessionService, workspace: Path, autonomy: str):
    return service.create_session(
        AgentSessionCreate(
            title=f"autonomy-{autonomy}",
            project_path=str(workspace),
            autonomy_mode=autonomy,
            provider="openai",
            model="gpt-test",
        )
    )


def test_session_create_confirm_all_stores_full_hitl(coding_workspace: Path, tmp_path: Path):
    service = AgentSessionService(AgentSessionRepository(str(tmp_path / "agents.db")))
    session = _create(service, coding_workspace, "confirm_all")
    meta = session.metadata
    assert meta["autonomy_mode"] == "confirm_all"
    assert meta["deepagents_interrupt_on"] is True
    policy = permission_policy_for_agent(None, "build", meta)
    interrupt = policy.interrupt_on()
    assert interrupt == DEFAULT_DEEPAGENTS_INTERRUPT_ON
    # Runtime policy used by DeepAgents construction agrees.
    runtime = build_agent_runtime_policy(
        agent=None,
        agent_id="build",
        project_path=str(coding_workspace),
        metadata=meta,
    )
    assert runtime.interrupt_on == DEFAULT_DEEPAGENTS_INTERRUPT_ON


def test_session_create_safe_auto_weaker_than_confirm_all(coding_workspace: Path, tmp_path: Path):
    service = AgentSessionService(AgentSessionRepository(str(tmp_path / "agents.db")))
    safe_session = _create(service, coding_workspace, "safe_auto")
    confirm_session = _create(service, coding_workspace, "confirm_all")
    safe_meta = safe_session.metadata
    confirm_meta = confirm_session.metadata
    assert safe_meta["autonomy_mode"] == "safe_auto"
    assert safe_meta["deepagents_interrupt_on"] is False
    safe_interrupt = permission_policy_for_agent(None, "build", safe_meta).interrupt_on()
    confirm_interrupt = permission_policy_for_agent(None, "build", confirm_meta).interrupt_on()
    assert safe_interrupt is None
    assert confirm_interrupt == DEFAULT_DEEPAGENTS_INTERRUPT_ON
    # safe_auto is strictly weaker: confirm requires approval on tools that safe does not.
    for tool in WRITE_EXECUTE_TOOLS:
        assert confirm_interrupt[tool] is True
        assert safe_interrupt is None or not (safe_interrupt or {}).get(tool)
    # Sensitive .env still denied under safe_auto (not unattended for secrets).
    rules = permission_policy_for_agent(None, "build", safe_meta).filesystem_permissions()
    assert _check_fs_permission(rules, "write", "/workspace/.env") == "deny"
    assert _check_fs_permission(rules, "write", "/workspace/app.py") == "allow"


def test_session_create_read_only_blocks_write_and_execute(coding_workspace: Path, tmp_path: Path):
    """read_only must fail-closed: tools excluded + FS write deny (not interrupt-only)."""
    service = AgentSessionService(AgentSessionRepository(str(tmp_path / "agents.db")))
    session = _create(service, coding_workspace, "read_only")
    meta = session.metadata
    assert meta["autonomy_mode"] == "read_only"
    agent = AgentDefinition(
        id="build",
        name="Build",
        tools=["ls", "read_file", "write_file", "edit_file", "execute", "grep"],
    )
    policy = permission_policy_for_agent(agent, "build", meta)
    allowed = policy.allowed_tools()
    assert allowed is not None
    assert "read_file" in allowed
    assert "ls" in allowed
    for tool in WRITE_EXECUTE_TOOLS:
        assert tool not in allowed
    # Filtered tools list never includes write/execute.
    named = [
        type("T", (), {"name": name})()
        for name in ("read_file", "write_file", "edit_file", "execute", "grep")
    ]
    filtered = [t.name for t in policy.filter_named_tools(named)]
    assert "write_file" not in filtered
    assert "edit_file" not in filtered
    assert "execute" not in filtered
    assert "read_file" in filtered
    # FS profile is readonly even though agent_id is build.
    rules = policy.filesystem_permissions()
    assert _check_fs_permission(rules, "read", "/workspace/app.py") == "allow"
    assert _check_fs_permission(rules, "write", "/workspace/app.py") == "deny"
    runtime = build_agent_runtime_policy(
        agent=agent,
        agent_id="build",
        project_path=str(coding_workspace),
        metadata=meta,
    )
    assert runtime.readonly is True


def test_session_create_default_autonomy_is_safe_auto(coding_workspace: Path, tmp_path: Path):
    service = AgentSessionService(AgentSessionRepository(str(tmp_path / "agents.db")))
    session = service.create_session(
        AgentSessionCreate(title="default-mode", project_path=str(coding_workspace), provider="openai", model="gpt-test")
    )
    assert session.metadata["autonomy_mode"] == "safe_auto"
    assert session.metadata["deepagents_interrupt_on"] is False
    assert permission_policy_for_agent(None, "build", session.metadata).interrupt_on() is None


def test_default_deepagents_permission_metadata_shape():
    assert default_deepagents_permission_metadata("safe_auto") == {
        "autonomy_mode": "safe_auto",
        "deepagents_interrupt_on": False,
    }
    assert default_deepagents_permission_metadata("confirm_all") == {
        "autonomy_mode": "confirm_all",
        "deepagents_interrupt_on": True,
    }
    assert default_deepagents_permission_metadata("read_only")["autonomy_mode"] == "read_only"
    assert default_deepagents_permission_metadata("read_only")["deepagents_interrupt_on"] is False
