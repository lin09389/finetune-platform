"""Multi-file HITL fragmentation fix: session-scoped tool trust after approve.

Proves the real permission-decision + interrupt resolution path used when
DeepAgents resume rebuilds interrupt_on from session metadata.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from agent_session.models import AgentSessionCreate
from agent_session.permission import (
    DEFAULT_DEEPAGENTS_INTERRUPT_ON,
    SESSION_TOOL_TRUST_KEY,
    apply_hitl_approve_session_trust,
    grant_session_tool_trust,
    permission_policy_for_agent,
    resolve_deepagents_interrupt_on,
    tools_granted_by_hitl_decisions,
)
from agent_session.repository import AgentSessionRepository
from agent_session.service import AgentSessionService
from fastapi import BackgroundTasks


def _confirm_all_meta(**extra) -> dict:
    return {
        "autonomy_mode": "confirm_all",
        "deepagents_interrupt_on": True,
        "runtime": "deepagents",
        **extra,
    }


def _permission_part(
    *,
    session_id: str,
    tools: list[str],
    part_id: str = "part_perm_1",
) -> dict:
    actions = [{"name": tool, "args": {}, "description": f"approve {tool}"} for tool in tools]
    return {
        "id": part_id,
        "session_id": session_id,
        "type": "permission",
        "status": "pending",
        "payload": {
            "runtime": "deepagents",
            "official_hitl": True,
            "tool": tools[0] if tools else None,
            "action_requests": actions,
            "actions": actions,
        },
    }


# --- pure helpers (round 1) ------------------------------------------------------


def test_confirm_all_initial_interrupt_requires_all_three():
    interrupt = resolve_deepagents_interrupt_on(_confirm_all_meta())
    assert interrupt == DEFAULT_DEEPAGENTS_INTERRUPT_ON
    for tool in ("write_file", "edit_file", "execute"):
        assert interrupt[tool] is True


def test_approve_write_tools_grants_trust_execute_still_gated():
    meta = _confirm_all_meta()
    part = _permission_part(session_id="s1", tools=["edit_file", "write_file"])
    decisions = [{"type": "approve"}, {"type": "approve"}]
    assert tools_granted_by_hitl_decisions(part, decisions) == ["edit_file", "write_file"]
    updated = apply_hitl_approve_session_trust(meta, part, decisions)
    assert set(updated[SESSION_TOOL_TRUST_KEY]) == {"edit_file", "write_file"}
    after = resolve_deepagents_interrupt_on(updated)
    assert after == {"execute": True}
    # Policy surface used by DeepAgents construction agrees.
    assert permission_policy_for_agent(None, "build", updated).interrupt_on() == {"execute": True}


def test_approve_execute_grants_execute_trust_only():
    meta = _confirm_all_meta()
    part = _permission_part(session_id="s1", tools=["execute"])
    updated = apply_hitl_approve_session_trust(meta, part, [{"type": "approve"}])
    after = resolve_deepagents_interrupt_on(updated)
    assert after == {"write_file": True, "edit_file": True}
    assert "execute" not in (after or {})


def test_reject_does_not_grant_trust():
    meta = _confirm_all_meta()
    part = _permission_part(session_id="s1", tools=["edit_file", "execute"])
    updated = apply_hitl_approve_session_trust(
        meta,
        part,
        [{"type": "reject", "message": "no"}, {"type": "reject", "message": "no"}],
    )
    assert SESSION_TOOL_TRUST_KEY not in updated or not updated.get(SESSION_TOOL_TRUST_KEY)
    assert resolve_deepagents_interrupt_on(updated) == DEFAULT_DEEPAGENTS_INTERRUPT_ON


def test_mixed_approve_reject_only_trusts_approved_tools():
    meta = _confirm_all_meta()
    part = _permission_part(session_id="s1", tools=["edit_file", "execute"])
    updated = apply_hitl_approve_session_trust(
        meta,
        part,
        [{"type": "approve"}, {"type": "reject", "message": "later"}],
    )
    assert updated[SESSION_TOOL_TRUST_KEY] == ["edit_file"]
    after = resolve_deepagents_interrupt_on(updated)
    assert after == {"write_file": True, "execute": True}


def test_trust_is_idempotent_and_additive():
    meta = grant_session_tool_trust(_confirm_all_meta(), ["edit_file"])
    meta = grant_session_tool_trust(meta, ["edit_file", "execute"])
    assert set(meta[SESSION_TOOL_TRUST_KEY]) == {"edit_file", "execute"}
    assert resolve_deepagents_interrupt_on(meta) == {"write_file": True}


def test_read_only_never_gains_write_trust():
    meta = {
        "autonomy_mode": "read_only",
        "deepagents_interrupt_on": False,
    }
    updated = grant_session_tool_trust(meta, ["write_file", "execute"])
    assert SESSION_TOOL_TRUST_KEY not in updated or not updated.get(SESSION_TOOL_TRUST_KEY)
    assert resolve_deepagents_interrupt_on(updated) is None


def test_safe_auto_remains_without_interrupt():
    meta = {"autonomy_mode": "safe_auto", "deepagents_interrupt_on": False}
    assert resolve_deepagents_interrupt_on(meta) is None
    # Trust grant is harmless when base interrupt is already empty.
    updated = grant_session_tool_trust(meta, ["edit_file"])
    assert resolve_deepagents_interrupt_on(updated) is None


def test_new_session_metadata_has_no_inherited_trust():
    # Fresh confirm_all defaults never carry session_tool_trust.
    from agent_session.permission import default_deepagents_permission_metadata

    fresh = default_deepagents_permission_metadata("confirm_all")
    assert SESSION_TOOL_TRUST_KEY not in fresh
    assert resolve_deepagents_interrupt_on(fresh) == DEFAULT_DEEPAGENTS_INTERRUPT_ON


# --- production approval path (round 2) ------------------------------------------


@pytest.fixture
def coding_workspace(tmp_path: Path):
    root = Path.cwd() / "tmp" / f"tool-trust-ws-{tmp_path.name}"
    root.mkdir(parents=True, exist_ok=True)
    (root / "a.py").write_text("a=1\n", encoding="utf-8")
    yield root
    import shutil

    shutil.rmtree(root, ignore_errors=True)


def test_approval_service_approve_persists_trust_for_resume(coding_workspace: Path, tmp_path: Path):
    """Real ApprovalService decide path updates session metadata before resume rebuild."""
    service = AgentSessionService(AgentSessionRepository(str(tmp_path / "agents.db")))
    session = service.create_session(
        AgentSessionCreate(
            title="trust-approve",
            project_path=str(coding_workspace),
            autonomy_mode="confirm_all",
            provider="openai",
            model="gpt-test",
        )
    )
    # Before any approve: full HITL.
    assert resolve_deepagents_interrupt_on(session.metadata) == DEFAULT_DEEPAGENTS_INTERRUPT_ON

    # Seed a pending permission part as DeepAgents would.
    part = service.repository.add_part(
        session.id,
        "permission",
        status="pending",
        title="确认 edit_file",
        content="approve edit",
        payload={
            "runtime": "deepagents",
            "official_hitl": True,
            "tool": "edit_file",
            "action_requests": [
                {"name": "edit_file", "args": {"file_path": "/workspace/a.py"}, "description": "edit"}
            ],
            "actions": [
                {"name": "edit_file", "args": {"file_path": "/workspace/a.py"}, "allowed_decisions": ["approve", "reject"]}
            ],
        },
    )
    # Mark runtime deepagents so decide path is taken.
    meta = dict(session.metadata or {})
    meta["runtime"] = "deepagents"
    service.repository.update_session(session.id, metadata=meta)

    bg = BackgroundTasks()
    response = service.start_permission_resume_background(part["id"], [{"type": "approve"}], bg)
    stored = service.repository.get_session(session.id)
    assert stored is not None
    trust = stored["metadata"].get(SESSION_TOOL_TRUST_KEY) or []
    assert "edit_file" in trust
    after = resolve_deepagents_interrupt_on(stored["metadata"])
    # Subsequent multi-file edits: edit_file no longer interrupts; execute still gated.
    assert after is not None
    assert "edit_file" not in after
    assert after.get("write_file") is True
    assert after.get("execute") is True
    # Response reflects same session.
    assert response.id == session.id


def test_approval_service_reject_does_not_persist_trust(coding_workspace: Path, tmp_path: Path):
    service = AgentSessionService(AgentSessionRepository(str(tmp_path / "agents.db")))
    session = service.create_session(
        AgentSessionCreate(
            title="trust-reject",
            project_path=str(coding_workspace),
            autonomy_mode="confirm_all",
            provider="openai",
            model="gpt-test",
        )
    )
    part = service.repository.add_part(
        session.id,
        "permission",
        status="pending",
        title="确认 execute",
        content="reject me",
        payload={
            "runtime": "deepagents",
            "official_hitl": True,
            "tool": "execute",
            "action_requests": [{"name": "execute", "args": {"command": "echo hi"}}],
            "actions": [
                {"name": "execute", "args": {"command": "echo hi"}, "allowed_decisions": ["approve", "reject"]}
            ],
        },
    )
    meta = dict(session.metadata or {})
    meta["runtime"] = "deepagents"
    service.repository.update_session(session.id, metadata=meta)

    bg = BackgroundTasks()
    # reject still goes through decide with reject type
    try:
        service.start_permission_resume_background(
            part["id"],
            [{"type": "reject", "message": "not now"}],
            bg,
        )
    except Exception:
        # Some reject paths may not resume; metadata is what we care about.
        pass
    stored = service.repository.get_session(session.id)
    assert stored is not None
    assert not (stored["metadata"].get(SESSION_TOOL_TRUST_KEY) or [])
    assert resolve_deepagents_interrupt_on(stored["metadata"]) == DEFAULT_DEEPAGENTS_INTERRUPT_ON


def test_second_session_starts_without_first_session_trust(coding_workspace: Path, tmp_path: Path):
    service = AgentSessionService(AgentSessionRepository(str(tmp_path / "agents.db")))
    s1 = service.create_session(
        AgentSessionCreate(
            title="s1",
            project_path=str(coding_workspace),
            autonomy_mode="confirm_all",
            provider="openai",
            model="gpt-test",
        )
    )
    meta = grant_session_tool_trust(dict(s1.metadata), ["edit_file", "execute", "write_file"])
    service.repository.update_session(s1.id, metadata=meta)
    assert resolve_deepagents_interrupt_on(service.repository.get_session(s1.id)["metadata"]) is None

    s2 = service.create_session(
        AgentSessionCreate(
            title="s2",
            project_path=str(coding_workspace),
            autonomy_mode="confirm_all",
            provider="openai",
            model="gpt-test",
        )
    )
    assert SESSION_TOOL_TRUST_KEY not in (s2.metadata or {})
    assert resolve_deepagents_interrupt_on(s2.metadata) == DEFAULT_DEEPAGENTS_INTERRUPT_ON
