"""Shadow tool-platform binding regression tests (Task 8).

Legacy sessions bind nothing; shadow sessions compile an immutable snapshot
of the canonical tool projection without running availability probes,
changing the DeepAgents tool list, altering HITL interrupts, or mutating
approval behaviour.  The snapshot records Task-5 enforcement blockers
(execute / task / write_todos as UNSUPPORTED) so the new policy vs legacy
HITL comparison can be computed offline from the bound facts.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from agent_session.agent_registry import AgentRegistry
from agent_session.runtime_contract import (
    AgentRuntimeContract,
    resolve_orchestration_mode,
)
from tool_platform.adapters.deepagents import DeepAgentsEnforcementCapability


def _contract(*, metadata: dict | None = None, project_path: str = ".", agent_id: str = "build"):
    return AgentRuntimeContract.for_agent_session(
        session={
            "id": "shadow-session",
            "project_path": str(project_path),
            "agent_id": agent_id,
            "metadata": metadata or {},
        },
        goal="g",
        model=object(),
        agent_registry=AgentRegistry(),
        tools=[],
        middleware=[],
        subagents=[],
        checkpointer=False,
    )


# --- legacy: zero behaviour change -------------------------------------------


def test_resolve_orchestration_mode_defaults_to_legacy():
    assert resolve_orchestration_mode({}) == "legacy"
    assert resolve_orchestration_mode({"orchestration_mode": "legacy"}) == "legacy"
    assert resolve_orchestration_mode({"orchestration_mode": ""}) == "legacy"
    assert resolve_orchestration_mode({"orchestration_mode": "bogus"}) == "legacy"


def test_resolve_orchestration_mode_accepts_shadow_and_controlled():
    assert resolve_orchestration_mode({"orchestration_mode": "shadow"}) == "shadow"
    assert resolve_orchestration_mode({"orchestration_mode": "CONTROLLED"}) == "controlled"


def test_legacy_contract_binds_no_projection(tmp_path: Path):
    contract = _contract(project_path=str(tmp_path), metadata={})

    assert contract.orchestration_mode == "legacy"
    assert contract.tool_projection is None


def test_legacy_contract_deepagents_surface_unchanged(tmp_path: Path):
    # Same metadata minus orchestration_mode must yield identical legacy fields.
    base_contract = _contract(project_path=str(tmp_path), metadata={"autonomy_mode": "safe_auto"})
    shadow_contract = _contract(
        project_path=str(tmp_path),
        metadata={"autonomy_mode": "safe_auto", "orchestration_mode": "shadow"},
    )

    # The DeepAgents-facing surface is byte-identical across modes — shadow only
    # adds the read-only projection snapshot.
    assert shadow_contract.tools == base_contract.tools
    assert shadow_contract.permissions == base_contract.permissions
    assert shadow_contract.interrupt_on == base_contract.interrupt_on
    assert shadow_contract.middleware == base_contract.middleware
    assert shadow_contract.system_prompt == base_contract.system_prompt


# --- shadow: bind deterministic read-only snapshot ----------------------------


def test_shadow_contract_binds_non_empty_snapshot(tmp_path: Path):
    contract = _contract(
        project_path=str(tmp_path),
        metadata={"autonomy_mode": "safe_auto", "orchestration_mode": "shadow"},
    )

    assert contract.orchestration_mode == "shadow"
    assert contract.tool_projection is not None
    assert contract.tool_projection.orchestration_mode == "shadow"
    assert contract.tool_projection.enforcement_status == "shadow"
    assert contract.tool_projection.agent_id == "build"


def test_shadow_snapshot_marks_unsupported_tools_as_blockers(tmp_path: Path):
    contract = _contract(
        project_path=str(tmp_path),
        metadata={"autonomy_mode": "safe_auto", "orchestration_mode": "shadow"},
    )
    snapshot = contract.tool_projection

    resolved_names = {tool.canonical_name for tool in snapshot.resolved_tools}
    # Build manifest allows the coding builtins (ls/read/grep/glob/write/edit/execute/task).
    assert {"ls", "read_file", "write_file", "edit_file", "execute", "task"} <= resolved_names

    # execute / task have no hard enforcement boundary -> shadow records them as blockers.
    assert "execute" in snapshot.enforcement_blockers
    assert "task" in snapshot.enforcement_blockers
    execute = next(t for t in snapshot.resolved_tools if t.canonical_name == "execute")
    assert execute.enforcement_capability == DeepAgentsEnforcementCapability.UNSUPPORTED.value

    # write_todos is injected by mandatory middleware and not in the manifest allow-list,
    # so it is neither resolved nor a blocker from this snapshot.
    assert "write_todos" not in resolved_names


def test_shadow_snapshot_does_not_recompute_interrupt_on(tmp_path: Path):
    # safe_auto -> legacy interrupt_on is None; shadow must inherit the same gate.
    legacy = _contract(project_path=str(tmp_path), metadata={"autonomy_mode": "safe_auto"})
    shadow = _contract(
        project_path=str(tmp_path),
        metadata={"autonomy_mode": "safe_auto", "orchestration_mode": "shadow"},
    )

    assert shadow.interrupt_on == legacy.interrupt_on
    # confirm_all still drives the full legacy HITL map under both modes.
    legacy_confirm = _contract(project_path=str(tmp_path), metadata={"autonomy_mode": "confirm_all"})
    shadow_confirm = _contract(
        project_path=str(tmp_path),
        metadata={"autonomy_mode": "confirm_all", "orchestration_mode": "shadow"},
    )
    assert shadow_confirm.interrupt_on == legacy_confirm.interrupt_on
    assert shadow_confirm.interrupt_on == {"write_file": True, "edit_file": True, "execute": True}


def test_shadow_snapshot_read_only_carries_autonomy_gates(tmp_path: Path):
    safe = _contract(
        project_path=str(tmp_path),
        metadata={"autonomy_mode": "safe_auto", "orchestration_mode": "shadow"},
    )
    readonly = _contract(
        project_path=str(tmp_path),
        metadata={"autonomy_mode": "read_only", "orchestration_mode": "shadow"},
    )

    from tool_platform.taxonomy import SideEffect

    safe_facts = safe.tool_projection.policy_facts
    readonly_facts = readonly.tool_projection.policy_facts

    assert SideEffect.WORKSPACE_WRITE not in safe_facts.require_approval_for
    assert SideEffect.WORKSPACE_WRITE in readonly_facts.deny_for
    assert SideEffect.PROCESS in readonly_facts.deny_for


def test_shadow_snapshot_json_round_trip_and_redaction(tmp_path: Path):
    contract = _contract(
        project_path=str(tmp_path),
        metadata={"autonomy_mode": "safe_auto", "orchestration_mode": "shadow"},
    )
    snapshot = contract.tool_projection
    dump = snapshot.diagnostic_dump()
    import json

    encoded = json.dumps(dump)
    assert "orchestration_mode" in encoded
    assert "policy_facts" in encoded
    # No handler/probe/callable leaks into the snapshot.
    assert "handler" not in encoded
    assert "probe" not in encoded


def test_shadow_contract_runtime_factory_passes_legacy_fields_only(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    """DeepAgents must receive the same legacy surface regardless of mode."""
    from agent_session.runtime_factory import DeepAgentsRuntimeFactory

    captured: dict[str, object] = {}
    legacy_capture: dict[str, object] = {}

    def make_capture(store):
        def fake_create_deep_agent(**kwargs):
            store.update(kwargs)
            return {"graph": True}
        return fake_create_deep_agent

    fake_module = type(
        "DeepAgentsModule",
        (),
        {
            "create_deep_agent": staticmethod(make_capture(captured)),
            "FilesystemPermission": type(
                "FP",
                (),
                {"__init__": lambda self, **kwargs: setattr(self, "_kwargs", kwargs)},
            ),
        },
    )
    monkeypatch.setitem(__import__("sys").modules, "deepagents", fake_module)
    factory = DeepAgentsRuntimeFactory()
    monkeypatch.setattr(factory, "_backend_for", lambda _contract: object())

    legacy_contract = _contract(project_path=str(tmp_path), metadata={"autonomy_mode": "safe_auto"})
    shadow_contract = _contract(
        project_path=str(tmp_path),
        metadata={"autonomy_mode": "safe_auto", "orchestration_mode": "shadow"},
    )

    # Re-point the fake at a second capture for the legacy build.
    factory.build(legacy_contract)
    legacy_capture.update(captured)
    captured.clear()
    fake_module.create_deep_agent = staticmethod(make_capture(captured))
    factory.build(shadow_contract)

    # The DeepAgents-facing kwargs must not differ by shadow binding.
    for key in ("interrupt_on", "skills", "memory", "checkpointer"):
        assert captured[key] == legacy_capture[key], f"DeepAgents {key} drifted under shadow"
    assert captured["system_prompt"] == legacy_capture["system_prompt"]
    # permissions are freshly-built FilesystemPermission objects per build; compare
    # their declared structure rather than object identity.
    assert len(captured["permissions"]) == len(legacy_capture["permissions"])
    for shadow_perm, legacy_perm in zip(
        captured["permissions"], legacy_capture["permissions"], strict=True
    ):
        assert shadow_perm._kwargs == legacy_perm._kwargs
