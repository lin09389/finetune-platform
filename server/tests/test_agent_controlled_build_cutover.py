"""Controlled tool-platform cutover tests (Task 9D-1).

Controlled mode substitutes the platform-managed tools (routed through the
Tool Gateway) for the legacy DeepAgents built-ins, and the startup gate
verifies every legacy built-in is excluded.  Legacy/shadow behaviour is
unchanged.  Controlled mode is not enabled by default; it requires explicit
``orchestration_mode=controlled`` metadata.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from agent_session.agent_registry import AgentRegistry
from agent_session.runtime_contract import (
    AgentRuntimeContract,
    resolve_orchestration_mode,
)
from tool_platform.adapters.deepagents import (
    CONTROLLED_MODE_EXCLUSION_SET,
    controlled_mode_exclusion_set,
    verify_controlled_mode_exclusion,
)


def _contract(*, metadata: dict, project_path: str):
    return AgentRuntimeContract.for_agent_session(
        session={"id": "ctrl-session", "project_path": str(project_path), "agent_id": "build", "metadata": metadata},
        goal="g",
        model=object(),
        agent_registry=AgentRegistry(),
        tools=[],
        middleware=[],
        subagents=[],
        checkpointer=False,
    )


# --- exclusion helpers --------------------------------------------------------


def test_controlled_exclusion_set_covers_all_builtins_including_unsupported():
    exclusion = controlled_mode_exclusion_set()
    # Every Task-5 builtin is excluded in controlled mode, including the
    # UNSUPPORTED ones (execute / task / write_todos) which controlled mode
    # neither routes through the legacy backend nor exposes to the model.
    assert {"ls", "read_file", "write_file", "edit_file", "glob", "grep", "execute", "task", "write_todos"} <= exclusion


def test_verify_controlled_mode_exclusion_reports_missing():
    full = CONTROLLED_MODE_EXCLUSION_SET
    assert verify_controlled_mode_exclusion(full) == ()
    missing = verify_controlled_mode_exclusion(full - {"write_todos", "execute"})
    assert "write_todos" in missing
    assert "execute" in missing


# --- controlled contract assembly --------------------------------------------


def test_controlled_contract_compiles_projection(tmp_path: Path):
    contract = _contract(metadata={"orchestration_mode": "controlled"}, project_path=str(tmp_path))
    assert contract.orchestration_mode == "controlled"
    assert contract.tool_projection is not None
    assert contract.tool_projection.enforcement_status == "controlled"


def test_controlled_contract_deepagents_surface_unchanged_pre_cutover(tmp_path: Path):
    # Before _apply_controlled_cutover runs, the contract still carries the
    # legacy tool surface (cutover happens in _build_graph). The legacy
    # fields must not drift from a shadow contract of the same metadata.
    controlled = _contract(metadata={"orchestration_mode": "controlled"}, project_path=str(tmp_path))
    shadow = _contract(metadata={"orchestration_mode": "shadow"}, project_path=str(tmp_path))
    assert controlled.interrupt_on == shadow.interrupt_on
    assert controlled.permissions == shadow.permissions
    assert controlled.system_prompt == shadow.system_prompt


def test_apply_controlled_cutover_substitutes_gateway_tools(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """_apply_controlled_cutover adds platform StructuredTools and full exclusion."""
    from agent_session.deepagents_runtime import (
        DeepAgentsSessionRunner,
        _is_tool_exclusion_middleware,
    )

    registry = AgentRegistry()
    runner = DeepAgentsSessionRunner.__new__(DeepAgentsSessionRunner)
    runner.repository = _FakeRepo()
    runner.notify_event = lambda *_a, **_k: None
    runner.agent_registry = registry

    contract = _contract(metadata={"orchestration_mode": "controlled"}, project_path=str(tmp_path))
    # Seed middleware with a legacy exclusion middleware to confirm it's replaced.
    from agent_session.permission import AgentRuntimePermissionPolicy

    legacy_policy = AgentRuntimePermissionPolicy(agent=None, agent_id="build", metadata={})
    contract = contract.__class__(
        **{**contract.__dict__, "middleware": [*legacy_policy.tool_constraint_middleware(frozenset({"execute", "task"}), None)]}
    )

    patched = runner._apply_controlled_cutover(
        contract, "ctrl-session", str(tmp_path), "build", {"autonomy_mode": "safe_auto"}
    )

    # Platform managed tools are now present.
    tool_names = {getattr(t, "name", "") for t in (patched.tools or [])}
    assert {"read_file", "write_file", "edit_file", "execute", "run_tests"} <= tool_names
    # Exactly one exclusion middleware, covering the full controlled set.
    exclusions = [mw for mw in patched.middleware if _is_tool_exclusion_middleware(mw)]
    assert len(exclusions) == 1
    assert exclusions[0]._excluded >= CONTROLLED_MODE_EXCLUSION_SET


def test_apply_controlled_cutover_falls_back_when_exclusion_incomplete(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """If the gate cannot verify full exclusion, controlled falls back to legacy."""
    from agent_session.deepagents_runtime import DeepAgentsSessionRunner

    monkeypatch.setattr(
        "tool_platform.adapters.deepagents.verify_controlled_mode_exclusion",
        lambda _excluded: ("write_todos",),  # simulate mandatory middleware refusing exclusion
    )
    runner = DeepAgentsSessionRunner.__new__(DeepAgentsSessionRunner)
    runner.repository = _FakeRepo()
    runner.notify_event = lambda *_a, **_k: None
    runner.agent_registry = AgentRegistry()

    contract = _contract(metadata={"orchestration_mode": "controlled"}, project_path=str(tmp_path))
    patched = runner._apply_controlled_cutover(
        contract, "ctrl-session", str(tmp_path), "build", {"autonomy_mode": "safe_auto"}
    )
    assert patched.orchestration_mode == "legacy"
    assert patched.tool_projection is None


# --- gateway routing through the StructuredTool wrapper ----------------------


@pytest.mark.asyncio
async def test_gateway_tool_structure_routes_through_gateway(tmp_path: Path):
    (tmp_path / "app.py").write_text("print('hi')\n", encoding="utf-8")
    from tool_platform.builtins import (
        make_filesystem_handlers,
        platform_builtin_registry,
    )
    from tool_platform.builtins.gateway_tools import build_gateway_tool_structures
    from tool_platform.gateway import ToolGateway
    from tool_platform.policy import ToolPolicyFacts

    sink: list = []
    gateway = ToolGateway(
        platform_builtin_registry(),
        sink.append,
        handlers=make_filesystem_handlers(tmp_path),
    )
    tools = build_gateway_tool_structures(
        gateway=gateway,
        registry=platform_builtin_registry(),
        facts=ToolPolicyFacts(
            runtime_kind="agent_session", enabled_capabilities=frozenset({"deepagents"})
        ),
        agent_id="build",
    )
    read_tool = next(t for t in tools if t.name == "read_file")
    import json

    result = await read_tool.ainvoke({"file_path": "/workspace/app.py"})
    payload = json.loads(result)
    assert "print('hi')" in payload["content"]
    # Gateway emitted started + completed canonical events.
    assert [e.event_type for e in sink] == ["tool.started", "tool.completed"]


# --- rollback / default -------------------------------------------------------


def test_default_orchestration_mode_is_legacy():
    assert resolve_orchestration_mode({}) == "legacy"
    assert resolve_orchestration_mode({"orchestration_mode": "legacy"}) == "legacy"


def test_legacy_contract_has_no_cutover(tmp_path: Path):
    contract = _contract(metadata={}, project_path=str(tmp_path))
    assert contract.orchestration_mode == "legacy"
    assert contract.tool_projection is None


class _FakeRepo:
    """Minimal repository stub for cutover assembly (no event projection needed)."""

    def __init__(self):
        self.session = {"id": "ctrl-session", "metadata": {}}

    def get_session(self, _session_id):
        return self.session

    def update_session(self, _session_id, **updates):
        self.session.update(updates)
        return self.session

    def add_event(self, session_id, event_type, message, payload):
        return {"id": "e", "session_id": session_id, "type": event_type, "message": message, "payload": payload}

    def add_part(self, session_id, part_type, *, status=None, title=None, content=None, payload=None):
        return {"id": "p", "session_id": session_id, "type": part_type, "status": status, "payload": payload}

    def update_part(self, part_id, **updates):
        return {"id": part_id, **updates}

    def get_part(self, _part_id):
        return None

    def list_parts(self, _session_id):
        return []
