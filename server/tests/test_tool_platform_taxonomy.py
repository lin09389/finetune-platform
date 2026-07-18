from __future__ import annotations

import json

import pytest
from tool_platform.taxonomy import (
    TOOL_KIND_DEFAULTS,
    ExecutionLocation,
    SideEffect,
    ToolKind,
    ToolKindDefaults,
    ToolRisk,
    defaults_for_kind,
)


def test_tool_kind_has_the_complete_stable_canonical_vocabulary() -> None:
    assert {kind.value for kind in ToolKind} == {
        "read", "write", "edit", "list_dir", "search", "lsp", "execute", "web_search", "web_fetch",
        "task", "task_action", "wait_tasks", "schedule", "plan_mode", "todo", "ask_user", "image_gen",
        "video_gen", "training", "mcp_extension",
    }
    assert len(ToolKind) == 20
    for kind in ToolKind:
        assert json.dumps(kind) == json.dumps(kind.value)
        assert ToolKind(kind.value) is kind


@pytest.mark.parametrize(
    ("enum_type", "expected_values"),
    [
        (SideEffect, {"none", "workspace_write", "process", "network", "external_write", "credential", "destructive"}),
        (ToolRisk, {"low", "medium", "high", "critical"}),
        (ExecutionLocation, {"control_plane", "worker", "external"}),
    ],
)
def test_supporting_enums_have_stable_serialized_values(enum_type: type, expected_values: set[str]) -> None:
    assert {member.value for member in enum_type} == expected_values
    for member in enum_type:
        assert json.dumps(member) == json.dumps(member.value)
        assert enum_type(member.value) is member


def test_defaults_are_exhaustive_and_immutable() -> None:
    assert set(TOOL_KIND_DEFAULTS) == set(ToolKind)
    assert all(isinstance(defaults, ToolKindDefaults) for defaults in TOOL_KIND_DEFAULTS.values())
    with pytest.raises(TypeError):
        TOOL_KIND_DEFAULTS[ToolKind.READ] = TOOL_KIND_DEFAULTS[ToolKind.WRITE]  # type: ignore[index]


@pytest.mark.parametrize(
    ("kind", "side_effect", "risk", "location"),
    [
        (ToolKind.READ, SideEffect.NONE, ToolRisk.LOW, ExecutionLocation.CONTROL_PLANE),
        (ToolKind.WRITE, SideEffect.WORKSPACE_WRITE, ToolRisk.MEDIUM, ExecutionLocation.WORKER),
        (ToolKind.EDIT, SideEffect.WORKSPACE_WRITE, ToolRisk.MEDIUM, ExecutionLocation.WORKER),
        (ToolKind.LIST_DIR, SideEffect.NONE, ToolRisk.LOW, ExecutionLocation.CONTROL_PLANE),
        (ToolKind.SEARCH, SideEffect.NONE, ToolRisk.LOW, ExecutionLocation.CONTROL_PLANE),
        (ToolKind.LSP, SideEffect.NONE, ToolRisk.LOW, ExecutionLocation.WORKER),
        (ToolKind.EXECUTE, SideEffect.PROCESS, ToolRisk.HIGH, ExecutionLocation.WORKER),
        (ToolKind.WEB_SEARCH, SideEffect.NETWORK, ToolRisk.MEDIUM, ExecutionLocation.EXTERNAL),
        (ToolKind.WEB_FETCH, SideEffect.NETWORK, ToolRisk.MEDIUM, ExecutionLocation.EXTERNAL),
        (ToolKind.TASK, SideEffect.PROCESS, ToolRisk.HIGH, ExecutionLocation.WORKER),
        (ToolKind.TASK_ACTION, SideEffect.PROCESS, ToolRisk.HIGH, ExecutionLocation.WORKER),
        (ToolKind.WAIT_TASKS, SideEffect.NONE, ToolRisk.LOW, ExecutionLocation.CONTROL_PLANE),
        (ToolKind.SCHEDULE, SideEffect.EXTERNAL_WRITE, ToolRisk.HIGH, ExecutionLocation.WORKER),
        (ToolKind.PLAN_MODE, SideEffect.NONE, ToolRisk.LOW, ExecutionLocation.CONTROL_PLANE),
        (ToolKind.TODO, SideEffect.EXTERNAL_WRITE, ToolRisk.MEDIUM, ExecutionLocation.CONTROL_PLANE),
        (ToolKind.ASK_USER, SideEffect.EXTERNAL_WRITE, ToolRisk.MEDIUM, ExecutionLocation.CONTROL_PLANE),
        (ToolKind.IMAGE_GEN, SideEffect.EXTERNAL_WRITE, ToolRisk.HIGH, ExecutionLocation.EXTERNAL),
        (ToolKind.VIDEO_GEN, SideEffect.EXTERNAL_WRITE, ToolRisk.HIGH, ExecutionLocation.EXTERNAL),
        (ToolKind.TRAINING, SideEffect.PROCESS, ToolRisk.HIGH, ExecutionLocation.WORKER),
        (ToolKind.MCP_EXTENSION, SideEffect.EXTERNAL_WRITE, ToolRisk.HIGH, ExecutionLocation.EXTERNAL),
    ],
)
def test_each_tool_kind_has_explicit_safe_defaults(kind: ToolKind, side_effect: SideEffect, risk: ToolRisk, location: ExecutionLocation) -> None:
    defaults = defaults_for_kind(kind)
    assert side_effect in defaults.side_effects
    assert defaults.risk is risk
    assert defaults.execution_location is location


def test_unclassified_kind_fails_closed() -> None:
    class FutureToolKind:
        value = "future_kind"

    with pytest.raises(ValueError, match="no canonical defaults"):
        defaults_for_kind(FutureToolKind())  # type: ignore[arg-type]


def test_effects_are_composable_and_data_read_only_is_independent() -> None:
    execute = defaults_for_kind(ToolKind.EXECUTE)
    assert execute.side_effects == frozenset({SideEffect.PROCESS, SideEffect.WORKSPACE_WRITE, SideEffect.DESTRUCTIVE})
    assert execute.is_data_read_only is False
    web_fetch = defaults_for_kind(ToolKind.WEB_FETCH)
    assert web_fetch.side_effects == frozenset({SideEffect.NETWORK})
    assert web_fetch.is_data_read_only is True
