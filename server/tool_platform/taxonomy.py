"""The canonical, fail-closed semantic taxonomy for Agent tools."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType
from typing import Final


class ToolKind(str, Enum):
    READ = "read"
    WRITE = "write"
    EDIT = "edit"
    LIST_DIR = "list_dir"
    SEARCH = "search"
    LSP = "lsp"
    EXECUTE = "execute"
    WEB_SEARCH = "web_search"
    WEB_FETCH = "web_fetch"
    TASK = "task"
    TASK_ACTION = "task_action"
    WAIT_TASKS = "wait_tasks"
    SCHEDULE = "schedule"
    PLAN_MODE = "plan_mode"
    TODO = "todo"
    ASK_USER = "ask_user"
    IMAGE_GEN = "image_gen"
    VIDEO_GEN = "video_gen"
    TRAINING = "training"
    MCP_EXTENSION = "mcp_extension"


class SideEffect(str, Enum):
    NONE = "none"
    WORKSPACE_WRITE = "workspace_write"
    PROCESS = "process"
    NETWORK = "network"
    EXTERNAL_WRITE = "external_write"
    CREDENTIAL = "credential"
    DESTRUCTIVE = "destructive"


class ToolRisk(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ExecutionLocation(str, Enum):
    CONTROL_PLANE = "control_plane"
    WORKER = "worker"
    EXTERNAL = "external"


@dataclass(frozen=True)
class ToolKindDefaults:
    side_effects: frozenset[SideEffect]
    risk: ToolRisk
    execution_location: ExecutionLocation

    @property
    def is_data_read_only(self) -> bool:
        return self.side_effects.isdisjoint(
            {SideEffect.WORKSPACE_WRITE, SideEffect.EXTERNAL_WRITE, SideEffect.DESTRUCTIVE}
        )


def _defaults(
    side_effect: SideEffect | frozenset[SideEffect], risk: ToolRisk, execution_location: ExecutionLocation
) -> ToolKindDefaults:
    effects = side_effect if isinstance(side_effect, frozenset) else frozenset({side_effect})
    return ToolKindDefaults(effects, risk, execution_location)


TOOL_KIND_DEFAULTS: Final[Mapping[ToolKind, ToolKindDefaults]] = MappingProxyType(
    {
        ToolKind.READ: _defaults(SideEffect.NONE, ToolRisk.LOW, ExecutionLocation.CONTROL_PLANE),
        ToolKind.WRITE: _defaults(SideEffect.WORKSPACE_WRITE, ToolRisk.MEDIUM, ExecutionLocation.WORKER),
        ToolKind.EDIT: _defaults(SideEffect.WORKSPACE_WRITE, ToolRisk.MEDIUM, ExecutionLocation.WORKER),
        ToolKind.LIST_DIR: _defaults(SideEffect.NONE, ToolRisk.LOW, ExecutionLocation.CONTROL_PLANE),
        ToolKind.SEARCH: _defaults(SideEffect.NONE, ToolRisk.LOW, ExecutionLocation.CONTROL_PLANE),
        ToolKind.LSP: _defaults(SideEffect.NONE, ToolRisk.LOW, ExecutionLocation.WORKER),
        ToolKind.EXECUTE: _defaults(frozenset({SideEffect.PROCESS, SideEffect.WORKSPACE_WRITE, SideEffect.DESTRUCTIVE}), ToolRisk.HIGH, ExecutionLocation.WORKER),
        ToolKind.WEB_SEARCH: _defaults(SideEffect.NETWORK, ToolRisk.MEDIUM, ExecutionLocation.EXTERNAL),
        ToolKind.WEB_FETCH: _defaults(SideEffect.NETWORK, ToolRisk.MEDIUM, ExecutionLocation.EXTERNAL),
        ToolKind.TASK: _defaults(SideEffect.PROCESS, ToolRisk.HIGH, ExecutionLocation.WORKER),
        ToolKind.TASK_ACTION: _defaults(SideEffect.PROCESS, ToolRisk.HIGH, ExecutionLocation.WORKER),
        ToolKind.WAIT_TASKS: _defaults(SideEffect.NONE, ToolRisk.LOW, ExecutionLocation.CONTROL_PLANE),
        ToolKind.SCHEDULE: _defaults(SideEffect.EXTERNAL_WRITE, ToolRisk.HIGH, ExecutionLocation.WORKER),
        ToolKind.PLAN_MODE: _defaults(SideEffect.NONE, ToolRisk.LOW, ExecutionLocation.CONTROL_PLANE),
        ToolKind.TODO: _defaults(SideEffect.EXTERNAL_WRITE, ToolRisk.MEDIUM, ExecutionLocation.CONTROL_PLANE),
        ToolKind.ASK_USER: _defaults(SideEffect.EXTERNAL_WRITE, ToolRisk.MEDIUM, ExecutionLocation.CONTROL_PLANE),
        ToolKind.IMAGE_GEN: _defaults(SideEffect.EXTERNAL_WRITE, ToolRisk.HIGH, ExecutionLocation.EXTERNAL),
        ToolKind.VIDEO_GEN: _defaults(SideEffect.EXTERNAL_WRITE, ToolRisk.HIGH, ExecutionLocation.EXTERNAL),
        ToolKind.TRAINING: _defaults(frozenset({SideEffect.PROCESS, SideEffect.WORKSPACE_WRITE}), ToolRisk.HIGH, ExecutionLocation.WORKER),
        ToolKind.MCP_EXTENSION: _defaults(frozenset({SideEffect.NETWORK, SideEffect.EXTERNAL_WRITE, SideEffect.CREDENTIAL}), ToolRisk.HIGH, ExecutionLocation.EXTERNAL),
    }
)


def defaults_for_kind(kind: ToolKind) -> ToolKindDefaults:
    try:
        return TOOL_KIND_DEFAULTS[kind]
    except (KeyError, TypeError) as exc:
        value = getattr(kind, "value", repr(kind))
        raise ValueError(f"no canonical defaults for tool kind {value!r}") from exc
