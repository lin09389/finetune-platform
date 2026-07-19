from __future__ import annotations

import sys
import types
from pathlib import Path
from types import SimpleNamespace

import pytest
from agent_session.permission import AgentRuntimePermissionPolicy, interrupt_on_for_autonomy
from agent_session.runtime_factory import DeepAgentsRuntimeFactory
from pydantic import BaseModel, ConfigDict, ValidationError
from tool_platform.adapters.deepagents import (
    DeepAgentsControlledModeUnsupported,
    DeepAgentsEnforcementCapability,
    DeepAgentsToolSource,
    builtin_tool_bindings,
    controlled_mode_blockers,
    observe_contract_tools,
    require_controlled_mode_support,
)
from tool_platform.taxonomy import ToolKind


class _FakeInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    path: str


def _binding(name: str):
    return next(
        item for item in builtin_tool_bindings() if item.definition.meta.canonical_name == name
    )


def test_builtin_surface_covers_every_installed_injection_source() -> None:
    bindings = builtin_tool_bindings()

    assert {item.definition.meta.canonical_name for item in bindings} == {
        "ls",
        "read_file",
        "write_file",
        "edit_file",
        "glob",
        "grep",
        "execute",
        "task",
        "write_todos",
    }
    assert _binding("execute").source is DeepAgentsToolSource.FILESYSTEM_MIDDLEWARE
    assert _binding("task").source is DeepAgentsToolSource.SUBAGENT_MIDDLEWARE
    assert _binding("write_todos").source is DeepAgentsToolSource.TODO_MIDDLEWARE


def test_installed_filesystem_middleware_surface_matches_the_adapter(tmp_path: Path) -> None:
    from deepagents.backends import LocalShellBackend
    from deepagents.middleware.filesystem import FilesystemMiddleware

    middleware = FilesystemMiddleware(
        backend=LocalShellBackend(root_dir=str(tmp_path), virtual_mode=True)
    )

    assert {tool.name for tool in middleware.tools} == {
        "ls",
        "read_file",
        "write_file",
        "edit_file",
        "glob",
        "grep",
        "execute",
    }


def test_builtin_surface_uses_canonical_kinds_and_strict_schemas() -> None:
    execute = _binding("execute").definition
    read_file = _binding("read_file").definition

    assert execute.meta.kind is ToolKind.EXECUTE
    assert read_file.meta.kind is ToolKind.READ
    assert execute.validate_input({"command": "pytest", "timeout": 30}).command == "pytest"
    with pytest.raises(ValidationError):
        execute.validate_input({"command": "pytest", "timeout": "30"})


def test_filesystem_tools_have_hard_enforcement_but_shell_and_planners_do_not() -> None:
    assert _binding("write_file").enforcement is DeepAgentsEnforcementCapability.HIDDEN_AND_ENFORCED
    assert _binding("edit_file").enforcement is DeepAgentsEnforcementCapability.HIDDEN_AND_ENFORCED
    assert _binding("execute").enforcement is DeepAgentsEnforcementCapability.UNSUPPORTED
    assert _binding("task").enforcement is DeepAgentsEnforcementCapability.UNSUPPORTED
    assert _binding("write_todos").enforcement is DeepAgentsEnforcementCapability.UNSUPPORTED


def test_controlled_mode_fails_closed_for_unknown_or_soft_only_tools() -> None:
    assert controlled_mode_blockers(["read_file", "execute", "unknown", "task"]) == (
        "execute",
        "task",
        "unknown",
    )
    require_controlled_mode_support(["ls", "read_file", "write_file", "edit_file"])

    with pytest.raises(DeepAgentsControlledModeUnsupported) as exc_info:
        require_controlled_mode_support(["read_file", "execute"])
    assert exc_info.value.blockers == ("execute",)


def test_interrupt_metadata_uses_the_actual_deepagents_tool_name() -> None:
    assert all(
        binding.interrupt_name == binding.definition.meta.canonical_name
        for binding in builtin_tool_bindings()
    )
    assert interrupt_on_for_autonomy("safe_auto") is None
    assert interrupt_on_for_autonomy("confirm_all")["execute"] is True


def test_contract_tool_observation_is_sorted_json_safe_and_non_executing() -> None:
    calls = 0

    async def handler() -> None:
        nonlocal calls
        calls += 1

    tools = [
        SimpleNamespace(name="zeta", description="z", args_schema=_FakeInput, coroutine=handler),
        {"name": "alpha", "description": "a", "input_schema": {"type": "object"}},
    ]

    observed = observe_contract_tools(tools)

    assert [item.name for item in observed] == ["alpha", "zeta"]
    assert observed[1].input_schema["properties"]["path"]["type"] == "string"
    assert calls == 0


def test_contract_tool_observation_rejects_ambiguous_names() -> None:
    with pytest.raises(ValueError, match="non-empty name"):
        observe_contract_tools([SimpleNamespace(description="missing")])
    with pytest.raises(ValueError, match="duplicate"):
        observe_contract_tools([{"name": "same"}, {"name": "same"}])


def test_runtime_factory_passes_only_explicit_contract_tools_to_create_deep_agent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def fake_create_deep_agent(**kwargs):
        captured.update(kwargs)
        return object()

    monkeypatch.setitem(
        sys.modules,
        "deepagents",
        types.SimpleNamespace(create_deep_agent=fake_create_deep_agent),
    )
    monkeypatch.setattr(
        DeepAgentsRuntimeFactory,
        "_backend_for",
        lambda *_args: "backend",
    )
    explicit_tools = [SimpleNamespace(name="custom_tool")]
    contract = SimpleNamespace(
        model="model",
        tools=explicit_tools,
        system_prompt="prompt",
        middleware=(),
        memory=None,
        skills=(),
        subagents=(),
        permissions=(),
        interrupt_on=None,
        checkpointer=None,
    )

    DeepAgentsRuntimeFactory().build(contract)

    assert captured["tools"] is explicit_tools
    assert "ls" not in {getattr(tool, "name", "") for tool in explicit_tools}


def test_manifest_filter_hides_builtins_but_does_not_claim_execute_hard_enforcement() -> None:
    agent = SimpleNamespace(tools=["read_file"])
    policy = AgentRuntimePermissionPolicy(agent=agent, agent_id="build", metadata={})

    middleware = policy.tool_constraint_middleware(
        frozenset({"read_file", "write_file", "execute", "task"})
    )

    assert len(middleware) == 1
    assert middleware[0]._excluded == frozenset({"write_file", "execute", "task"})
    assert _binding("execute").enforcement is DeepAgentsEnforcementCapability.UNSUPPORTED
