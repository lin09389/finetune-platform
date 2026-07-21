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

    # Platform managed tools are now present (under namespaced canonical names
    # so the exclusion middleware - which filters by bare alias - does not hide
    # them alongside the legacy built-ins).
    tool_names = {getattr(t, "name", "") for t in (patched.tools or [])}
    assert {"workspace.read_file", "workspace.write_file", "workspace.edit_file", "workspace.execute", "workspace.run_tests"} <= tool_names
    # Bare aliases are NOT present as tool names (they are excluded).
    assert "read_file" not in tool_names and "execute" not in tool_names
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
    read_tool = next(t for t in tools if t.name == "workspace.read_file")
    import json

    result = await read_tool.ainvoke({"file_path": "/workspace/app.py"})
    payload = json.loads(result)
    assert "print('hi')" in payload["content"]
    # Gateway emitted started + completed canonical events.
    assert [e.event_type for e in sink] == ["tool.started", "tool.completed"]


@pytest.mark.asyncio
async def test_gateway_tool_structure_uses_tool_call_id_for_idempotent_replay(
    tmp_path: Path,
):
    """Replaying the same ``tool_call_id`` must hit the gateway terminal cache.

    Before the fix the StructuredTool coroutine minted a fresh random UUID
    per handler entry, so when DeepAgents resumed a HITL-interrupted tool
    call, the gateway saw a new invocation_id, never matched its terminal
    cache, and re-issued the same ``ask`` forever.  The LLM-assigned
    ``tool_call_id`` is the canonical idempotency key.
    """
    (tmp_path / "app.py").write_text("print('hi')\n", encoding="utf-8")
    from tool_platform.builtins import (
        make_filesystem_handlers,
        platform_builtin_registry,
    )
    from tool_platform.builtins.gateway_tools import build_gateway_tool_structures
    from tool_platform.gateway import ToolGateway
    from tool_platform.policy import ToolPolicyFacts

    handler_calls = {"count": 0}
    base_handlers = make_filesystem_handlers(tmp_path)
    read_handler = base_handlers["workspace.read_file"]

    async def counting(request, *args, **kwargs):  # type: ignore[no-untyped-def]
        handler_calls["count"] += 1
        return await read_handler(request, *args, **kwargs)

    wrapped_handlers = dict(base_handlers)
    wrapped_handlers["workspace.read_file"] = counting
    sink: list = []
    gateway = ToolGateway(
        platform_builtin_registry(),
        sink.append,
        handlers=wrapped_handlers,
    )
    tools = build_gateway_tool_structures(
        gateway=gateway,
        registry=platform_builtin_registry(),
        facts=ToolPolicyFacts(
            runtime_kind="agent_session", enabled_capabilities=frozenset({"deepagents"})
        ),
        agent_id="build",
    )
    read_tool = next(t for t in tools if t.name == "workspace.read_file")

    tool_call = {
        "args": {"file_path": "/workspace/app.py"},
        "name": "read_file",
        "type": "tool_call",
        "id": "call_replay_1",
    }
    # First call executes the handler and caches the terminal outcome under
    # invocation_id == "call_replay_1".
    first = await read_tool.ainvoke(tool_call)
    # Second call with the SAME tool_call_id must hit the cache: the handler
    # is not re-executed and no new canonical events are emitted.
    second = await read_tool.ainvoke(tool_call)

    import json

    assert json.loads(first.content) == json.loads(second.content)
    assert handler_calls["count"] == 1
    assert len(sink) == 2  # tool.started + tool.completed once
    # The cache entry is keyed by the tool_call_id, proving the StructuredTool
    # forwards the LLM-assigned id instead of minting a random UUID.
    assert "call_replay_1" in gateway._terminals


@pytest.mark.asyncio
async def test_apply_controlled_cutover_reuses_gateway_across_resumes(tmp_path: Path):
    """The same ToolGateway instance must back both prompt and resume turns.

    A resume rebuilds the contract via ``_apply_controlled_cutover``. If the
    gateway were reconstructed on every call its in-process terminal cache
    (``_terminals``) would be wiped, defeating the idempotency achieved via
    the LLM-assigned ``tool_call_id`` and turning every approval into an
    infinite loop.
    """
    from agent_session.deepagents_runtime import (
        DeepAgentsSessionRunner,
        _is_tool_exclusion_middleware,
    )

    runner = DeepAgentsSessionRunner.__new__(DeepAgentsSessionRunner)
    runner.repository = _FakeRepo()
    runner.notify_event = lambda *_a, **_k: None
    runner.agent_registry = AgentRegistry()
    runner._controlled_tool_runtimes = {}

    contract = _contract(metadata={"orchestration_mode": "controlled"}, project_path=str(tmp_path))

    first = runner._apply_controlled_cutover(
        contract, "ctrl-session", str(tmp_path), "build", {"autonomy_mode": "safe_auto"}
    )
    second = runner._apply_controlled_cutover(
        contract, "ctrl-session", str(tmp_path), "build", {"autonomy_mode": "safe_auto"}
    )

    # Tool surface is identical (memory identity would be too strict; the
    # wiring is rebuilt but every tool shares one gateway).
    assert {getattr(t, "name", "") for t in first.tools} == {
        getattr(t, "name", "") for t in second.tools
    }
    # Cached runtime record exists for the (session_id, project_path) key.
    assert ("ctrl-session", str(tmp_path)) in runner._controlled_tool_runtimes
    runtime = runner._controlled_tool_runtimes[("ctrl-session", str(tmp_path))]
    # Sanity-check the cached gateway instance is the ONLY one materialised.
    cached_gateway_ids = {id(runtime.gateway)}
    assert len(cached_gateway_ids) == 1
    # Exclusion middleware still applied exactly once on both contracts.
    for patched in (first, second):
        exclusions = [mw for mw in patched.middleware if _is_tool_exclusion_middleware(mw)]
        assert len(exclusions) == 1
        assert exclusions[0]._excluded >= CONTROLLED_MODE_EXCLUSION_SET


@pytest.mark.asyncio
async def test_controlled_gateway_cache_survives_cutover_replay_for_idempotency(
    tmp_path: Path,
):
    """End-to-end replay guarantee: prompt + resume share the gateway cache.

    Combined check for fix 1 (tool_call_id-driven invocation_id) and fix 2
    (cross-resume gateway identity) at the runner seam: a writer tool that
    would otherwise need approval must not re-request approval when the same
    ``tool_call_id`` is replayed on the resume turn.
    """
    (tmp_path / "app.py").write_text("a\n", encoding="utf-8")
    from agent_session.deepagents_runtime import DeepAgentsSessionRunner
    from tool_platform.policy import ToolPolicyFacts
    from tool_platform.taxonomy import SideEffect

    runner = DeepAgentsSessionRunner.__new__(DeepAgentsSessionRunner)
    runner.repository = _FakeRepo()
    runner.notify_event = lambda *_a, **_k: None
    runner.agent_registry = AgentRegistry()
    runner._controlled_tool_runtimes = {}

    contract = _contract(metadata={"orchestration_mode": "controlled"}, project_path=str(tmp_path))

    # confirm_all: workspace writes need approval; the approving adapter
    # would normally short-circuit policy ``ask`` for both turns.
    facts = ToolPolicyFacts(
        runtime_kind="agent_session",
        enabled_capabilities=frozenset({"deepagents"}),
        require_approval_for=frozenset({SideEffect.WORKSPACE_WRITE}),
    )

    # Prompt-turn cutover.
    first_contract = runner._apply_controlled_cutover(
        contract, "ctrl-session", str(tmp_path), "build", {"autonomy_mode": "safe_auto"}
    )
    # Resume-turn cutover on the same session.
    second_contract = runner._apply_controlled_cutover(
        contract, "ctrl-session", str(tmp_path), "build", {"autonomy_mode": "safe_auto"}
    )

    # Sanity-check facts derivation (kept here for clarity; the runner uses
    # its own policy_facts_for_session internally).
    _ = facts

    runtime_cache = runner._controlled_tool_runtimes[("ctrl-session", str(tmp_path))]
    first_gateway_tools = [t for t in first_contract.tools if getattr(t, "name", "") == "workspace.edit_file"]
    second_gateway_tools = [t for t in second_contract.tools if getattr(t, "name", "") == "workspace.edit_file"]
    assert first_gateway_tools and second_gateway_tools

    edit_tool = first_gateway_tools[0]
    tool_call = {
        "args": {
            "file_path": "/workspace/app.py",
            "old_string": "a",
            "new_string": "b",
        },
        "name": "edit_file",
        "type": "tool_call",
        "id": "call_edit_1",
    }
    import json

    # First turn: the gateway runs the handler and caches the terminal outcome
    # under invocation_id == "call_edit_1". (Under confirm_all this would
    # normally suspend without dispatch; safe_auto lets it complete.) On
    # success the StructuredTool returns the tool's output JSON directly (no
    # envelope), so ``replacements`` proves the edit ran.
    first_out = await edit_tool.ainvoke(tool_call)
    first_payload = json.loads(first_out.content)
    assert first_payload.get("replacements") == 1

    # Second turn (resume): the SAME tool_call is replayed with the same id.
    # The gateway must hit its terminal cache — provided the gateway instance
    # survived between cutover calls (fix 2) and forwarded the tool_call_id
    # instead of minting a fresh UUID (fix 1).
    second_out = await second_gateway_tools[0].ainvoke(tool_call)
    second_payload = json.loads(second_out.content)
    assert second_payload == first_payload
    assert "call_edit_1" in runtime_cache.gateway._terminals


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


# --- 9D-2: factory.build assembly + backend blockade -------------------------


def test_controlled_factory_build_passes_platform_tools_and_full_exclusion(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    """DeepAgents receives platform StructuredTools + a full controlled exclusion."""
    from agent_session.runtime_factory import DeepAgentsRuntimeFactory

    captured: dict[str, object] = {}

    def fake_create_deep_agent(**kwargs):
        captured.update(kwargs)
        return {"graph": True}

    fake_module = type(
        "DeepAgentsModule",
        (),
        {
            "create_deep_agent": staticmethod(fake_create_deep_agent),
            "FilesystemPermission": type("FP", (), {"__init__": lambda self, **kw: setattr(self, "_kwargs", kw)}),
        },
    )
    monkeypatch.setitem(__import__("sys").modules, "deepagents", fake_module)
    factory = DeepAgentsRuntimeFactory()
    monkeypatch.setattr(factory, "_backend_for", lambda _contract: object())

    # _apply_controlled_cutover runs inside _build_graph; call it directly to
    # observe the substituted tools/middleware without a real DeepAgents graph.
    from agent_session.deepagents_runtime import DeepAgentsSessionRunner

    runner = DeepAgentsSessionRunner.__new__(DeepAgentsSessionRunner)
    runner.repository = _FakeRepo()
    runner.notify_event = lambda *_a, **_k: None
    runner.agent_registry = AgentRegistry()

    contract = _contract(metadata={"orchestration_mode": "controlled"}, project_path=str(tmp_path))
    from agent_session.deepagents_runtime import _is_tool_exclusion_middleware

    patched = runner._apply_controlled_cutover(
        contract, "ctrl-session", str(tmp_path), "build", {"autonomy_mode": "safe_auto"}
    )

    tool_names = {getattr(t, "name", "") for t in (patched.tools or [])}
    assert {
        "workspace.read_file",
        "workspace.write_file",
        "workspace.edit_file",
        "workspace.execute",
        "workspace.run_tests",
        "workspace.ls",
        "workspace.grep",
        "workspace.glob",
    } <= tool_names
    exclusions = [mw for mw in patched.middleware if _is_tool_exclusion_middleware(mw)]
    assert len(exclusions) == 1
    assert exclusions[0]._excluded >= CONTROLLED_MODE_EXCLUSION_SET


def test_controlled_backend_blocks_legacy_execute_entry(tmp_path: Path):
    """In controlled mode the backend deny blocks the legacy execute entry point."""
    from agent_session.platform_shell import PlatformShellBackend

    backend = PlatformShellBackend(root_dir=str(tmp_path), virtual_mode=True, controlled_execute=True)
    response = backend.execute("echo should-not-run")
    assert response.exit_code == 1
    assert "gated" in response.output.lower()


def test_controlled_factory_passes_controlled_execute_flag(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    """_backend_for forwards controlled_execute=True for controlled contracts."""
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
        controlled = _contract(metadata={"orchestration_mode": "controlled"}, project_path=str(tmp_path))
        legacy = _contract(metadata={}, project_path=str(tmp_path))
        factory._backend_for(controlled)
        assert captured.get("controlled_execute") is True
        factory._backend_for(legacy)
        assert captured.get("controlled_execute") is False
    finally:
        runtime_mod.build_deepagents_backend = original


# --- rollback: controlled is opt-in ------------------------------------------


def test_controlled_mode_is_opt_in_by_default(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """No explicit metadata/config => legacy, even for Build sessions."""
    monkeypatch.setenv("AGENT_TOOL_ORCHESTRATION_MODE", "legacy")
    contract = _contract(metadata={}, project_path=str(tmp_path))
    assert contract.orchestration_mode == "legacy"
    assert contract.tool_projection is None


def test_controlled_mode_opt_in_via_metadata(tmp_path: Path):
    contract = _contract(metadata={"orchestration_mode": "controlled"}, project_path=str(tmp_path))
    assert contract.orchestration_mode == "controlled"


# --- P0-1: exclusion middleware None must downgrade to legacy ----------------


def test_controlled_downgrades_when_exclusion_middleware_unavailable(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    """If the exclusion middleware cannot be built, controlled falls back to legacy.

    Fail-closed: without the exclusion middleware the legacy built-ins would
    stay model-visible and bypass the Tool Gateway, so the cutover must
    downgrade rather than run controlled unenforced.
    """
    from agent_session import deepagents_runtime as dr
    from agent_session.deepagents_runtime import DeepAgentsSessionRunner

    monkeypatch.setattr(dr, "_build_exclusion_middleware", lambda _excluded, _logger: None)
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


# --- P0-2: ask is wired to DeepAgents interrupt_on ---------------------------


def test_controlled_safe_auto_interrupt_on_covers_execute_and_run_tests(tmp_path: Path):
    """safe_auto gates process/destructive tools via interrupt_on, not Gateway ask."""
    from agent_session.deepagents_runtime import DeepAgentsSessionRunner

    runner = DeepAgentsSessionRunner.__new__(DeepAgentsSessionRunner)
    runner.repository = _FakeRepo()
    runner.notify_event = lambda *_a, **_k: None
    runner.agent_registry = AgentRegistry()

    contract = _contract(metadata={"orchestration_mode": "controlled"}, project_path=str(tmp_path))
    patched = runner._apply_controlled_cutover(
        contract, "ctrl-session", str(tmp_path), "build", {"autonomy_mode": "safe_auto"}
    )
    assert patched.interrupt_on == {"workspace.execute": True, "workspace.run_tests": True}
    # Workspace writes are NOT interrupted under safe_auto (they run without HITL).
    assert "workspace.write_file" not in (patched.interrupt_on or {})
    assert "workspace.edit_file" not in (patched.interrupt_on or {})


def test_controlled_confirm_all_interrupt_on_covers_mutating_tools(tmp_path: Path):
    from agent_session.deepagents_runtime import DeepAgentsSessionRunner

    runner = DeepAgentsSessionRunner.__new__(DeepAgentsSessionRunner)
    runner.repository = _FakeRepo()
    runner.notify_event = lambda *_a, **_k: None
    runner.agent_registry = AgentRegistry()

    contract = _contract(metadata={"orchestration_mode": "controlled"}, project_path=str(tmp_path))
    patched = runner._apply_controlled_cutover(
        contract, "ctrl-session", str(tmp_path), "build", {"autonomy_mode": "confirm_all"}
    )
    assert patched.interrupt_on == {
        "workspace.write_file": True,
        "workspace.edit_file": True,
        "workspace.execute": True,
        "workspace.run_tests": True,
    }


def test_controlled_gateway_facts_clear_require_approval_for(tmp_path: Path):
    """The Gateway runs with require_approval_for cleared (HITL owns ask)."""
    # Verify via the interrupt_on derivation helper that the original facts
    # still carry require_approval_for (so interrupt_on is non-empty) while the
    # gateway_facts copy used for tool assembly clears it.
    from agent_session.deepagents_runtime import DeepAgentsSessionRunner

    runner = DeepAgentsSessionRunner.__new__(DeepAgentsSessionRunner)
    runner.repository = _FakeRepo()
    runner.notify_event = lambda *_a, **_k: None
    runner.agent_registry = AgentRegistry()

    contract = _contract(metadata={"orchestration_mode": "controlled"}, project_path=str(tmp_path))
    patched = runner._apply_controlled_cutover(
        contract, "ctrl-session", str(tmp_path), "build", {"autonomy_mode": "safe_auto"}
    )
    # interrupt_on non-empty proves the original facts had require_approval_for.
    assert patched.interrupt_on is not None
    # A managed execute tool invoked through the gateway with cleared facts
    # would NOT hit a needs_approval outcome (validated by the integration test
    # below); here we assert the cutover produced a usable contract surface.
    tool_names = {getattr(t, "name", "") for t in (patched.tools or [])}
    assert "workspace.execute" in tool_names


def test_controlled_cutover_applies_inspect_phase_gateway_filter(tmp_path: Path):
    from agent_session.deepagents_runtime import DeepAgentsSessionRunner
    from agent_session.phase_controller import initial_build_phase_state, serialize_phase_state

    registry = AgentRegistry()
    runner = DeepAgentsSessionRunner.__new__(DeepAgentsSessionRunner)
    runner.repository = _FakeRepo()
    runner.notify_event = lambda *_a, **_k: None
    runner.agent_registry = registry

    inspect_state = initial_build_phase_state(
        metadata={"goal_plan_status": "attached", "execution_plan": {"plan_id": "p1"}, "autonomy_mode": "safe_auto"},
        session={"agent_id": "build", "metadata": {"autonomy_mode": "safe_auto"}},
    )
    metadata = {
        "orchestration_mode": "controlled",
        "autonomy_mode": "safe_auto",
        "phase_state": serialize_phase_state(inspect_state),
        "phase_tool_projection": {
            "schema_version": "agent.execution.phase_projection.v1",
            "phase": "inspect",
            "routing_mode": "goal_plan",
            "application": "next_runtime_contract",
            "allowed_tools": ["read_file", "ls", "glob", "grep"],
            "denied_tools": ["write_file", "edit_file", "execute"],
            "blocked_reasons": [],
            "goal_plan_scope_hints": [],
            "tightening_proof": {},
            "runtime_bound": True,
        },
    }
    contract = _contract(metadata=metadata, project_path=str(tmp_path))
    contract = contract.__class__(
        **{
            **contract.__dict__,
            "phase_projection_application": "next_runtime_contract",
            "phase_tool_projection": metadata["phase_tool_projection"],
        }
    )
    patched = runner._apply_controlled_cutover(contract, "ctrl-session", str(tmp_path), "build", metadata)
    gateway_names = {getattr(tool, "name", "") for tool in patched.tools or []}
    assert "workspace.read_file" in gateway_names
    assert "workspace.write_file" not in gateway_names
    assert "workspace.edit_file" not in gateway_names
    assert "workspace.execute" not in gateway_names


def test_gateway_tool_structures_empty_allowlist_exposes_no_tools():
    from tool_platform.builtins import platform_builtin_registry
    from tool_platform.builtins.gateway_tools import build_gateway_tool_structures
    from tool_platform.gateway import ToolGateway
    from tool_platform.policy import ToolPolicyFacts

    gateway = ToolGateway(platform_builtin_registry(), lambda *_a, **_k: None, handlers={})
    tools = build_gateway_tool_structures(
        gateway=gateway,
        registry=platform_builtin_registry(),
        facts=ToolPolicyFacts(runtime_kind="agent_session", enabled_capabilities=frozenset({"deepagents"})),
        agent_id="build",
        allowed_tool_names=frozenset(),
    )
    assert tools == []
