"""Read-only characterization of the installed DeepAgents tool surface.

This adapter deliberately does not execute tools or alter runtime assembly. It
describes tools injected by DeepAgents and records whether the current platform
can both hide and enforce them before side effects occur.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_serializer, field_validator

from ..definition import ToolDefinition
from ..models import CanonicalToolMeta, FrozenJsonObject, freeze_json_object, jsonable, redact_json
from ..taxonomy import ToolKind, defaults_for_kind


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True, validate_default=True)


class LsInput(_StrictModel):
    path: str


class ReadFileInput(_StrictModel):
    file_path: str
    offset: int = 0
    limit: int = 100


class WriteFileInput(_StrictModel):
    file_path: str
    content: str


class EditFileInput(_StrictModel):
    file_path: str
    old_string: str
    new_string: str
    replace_all: bool = False


class GlobInput(_StrictModel):
    pattern: str
    path: str | None = None


class GrepInput(_StrictModel):
    pattern: str
    path: str | None = None
    glob: str | None = None
    output_mode: Literal["files_with_matches", "content", "count"] = "files_with_matches"


class ExecuteInput(_StrictModel):
    command: str
    timeout: int | None = Field(default=None, ge=0)


class TaskInput(_StrictModel):
    description: str
    subagent_type: str


class TodoItem(_StrictModel):
    content: str
    status: Literal["pending", "in_progress", "completed"]


class WriteTodosInput(_StrictModel):
    todos: tuple[TodoItem, ...]


class DeepAgentsToolOutput(_StrictModel):
    """Canonical envelope for an opaque DeepAgents tool result."""

    value: JsonValue | None = None


class DeepAgentsEnforcementCapability(StrEnum):
    """Strength of the current platform boundary for a DeepAgents tool."""

    HIDDEN_AND_ENFORCED = "hidden_and_enforced"
    VISIBLE_BUT_ENFORCED = "visible_but_enforced"
    UNSUPPORTED = "unsupported"


class DeepAgentsToolSource(StrEnum):
    FILESYSTEM_MIDDLEWARE = "filesystem_middleware"
    TODO_MIDDLEWARE = "todo_middleware"
    SUBAGENT_MIDDLEWARE = "subagent_middleware"
    CONTRACT_TOOLS = "contract_tools"


class DeepAgentsContractToolObservation(_StrictModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=10_000)
    input_schema: FrozenJsonObject = Field(default_factory=dict)

    @field_validator("input_schema")
    @classmethod
    def redact_schema(cls, value: FrozenJsonObject) -> FrozenJsonObject:
        return freeze_json_object(redact_json(value))  # type: ignore[arg-type]

    @field_serializer("input_schema")
    def serialize_schema(self, value: FrozenJsonObject) -> JsonValue:
        return jsonable(value)


@dataclass(frozen=True, slots=True)
class DeepAgentsToolBinding:
    definition: ToolDefinition[Any, DeepAgentsToolOutput]
    source: DeepAgentsToolSource
    enforcement: DeepAgentsEnforcementCapability
    interrupt_name: str
    enforcement_reason: str


class DeepAgentsControlledModeUnsupported(RuntimeError):
    """Raised when a requested tool lacks a hard pre-side-effect boundary."""

    def __init__(self, blockers: tuple[str, ...]) -> None:
        self.blockers = blockers
        super().__init__(f"controlled DeepAgents mode cannot enforce tools: {', '.join(blockers)}")


_TOOL_SPECS: tuple[
    tuple[
        str,
        ToolKind,
        type[_StrictModel],
        DeepAgentsToolSource,
        DeepAgentsEnforcementCapability,
        str,
    ],
    ...,
] = (
    (
        "ls",
        ToolKind.LIST_DIR,
        LsInput,
        DeepAgentsToolSource.FILESYSTEM_MIDDLEWARE,
        DeepAgentsEnforcementCapability.HIDDEN_AND_ENFORCED,
        "Model-request exclusion and filesystem permission rules both apply.",
    ),
    (
        "read_file",
        ToolKind.READ,
        ReadFileInput,
        DeepAgentsToolSource.FILESYSTEM_MIDDLEWARE,
        DeepAgentsEnforcementCapability.HIDDEN_AND_ENFORCED,
        "Model-request exclusion and filesystem permission rules both apply.",
    ),
    (
        "write_file",
        ToolKind.WRITE,
        WriteFileInput,
        DeepAgentsToolSource.FILESYSTEM_MIDDLEWARE,
        DeepAgentsEnforcementCapability.HIDDEN_AND_ENFORCED,
        "Model-request exclusion, HITL, trajectory guards, and filesystem rules apply.",
    ),
    (
        "edit_file",
        ToolKind.EDIT,
        EditFileInput,
        DeepAgentsToolSource.FILESYSTEM_MIDDLEWARE,
        DeepAgentsEnforcementCapability.HIDDEN_AND_ENFORCED,
        "Model-request exclusion, HITL, trajectory guards, and filesystem rules apply.",
    ),
    (
        "glob",
        ToolKind.SEARCH,
        GlobInput,
        DeepAgentsToolSource.FILESYSTEM_MIDDLEWARE,
        DeepAgentsEnforcementCapability.HIDDEN_AND_ENFORCED,
        "Model-request exclusion and filesystem permission rules both apply.",
    ),
    (
        "grep",
        ToolKind.SEARCH,
        GrepInput,
        DeepAgentsToolSource.FILESYSTEM_MIDDLEWARE,
        DeepAgentsEnforcementCapability.HIDDEN_AND_ENFORCED,
        "Model-request exclusion and filesystem permission rules both apply.",
    ),
    (
        "execute",
        ToolKind.EXECUTE,
        ExecuteInput,
        DeepAgentsToolSource.FILESYSTEM_MIDDLEWARE,
        DeepAgentsEnforcementCapability.UNSUPPORTED,
        "Visibility can be filtered, but LocalShellBackend has no execution-layer deny.",
    ),
    (
        "task",
        ToolKind.TASK,
        TaskInput,
        DeepAgentsToolSource.SUBAGENT_MIDDLEWARE,
        DeepAgentsEnforcementCapability.UNSUPPORTED,
        "Visibility can be filtered, but the delegated tool has no platform hard-deny boundary.",
    ),
    (
        "write_todos",
        ToolKind.TODO,
        WriteTodosInput,
        DeepAgentsToolSource.TODO_MIDDLEWARE,
        DeepAgentsEnforcementCapability.UNSUPPORTED,
        "The tool is injected by mandatory middleware and is not in the platform exclusion set.",
    ),
)


def _definition(name: str, kind: ToolKind, input_model: type[_StrictModel]) -> ToolDefinition:
    defaults = defaults_for_kind(kind)
    return ToolDefinition(
        meta=CanonicalToolMeta(
            canonical_name=name,
            kind=kind,
            side_effects=defaults.side_effects,
            risk=defaults.risk,
            execution_location=defaults.execution_location,
            display_name=name,
            description=f"DeepAgents built-in {name} tool.",
            idempotent=kind in {ToolKind.READ, ToolKind.LIST_DIR, ToolKind.SEARCH},
        ),
        input_model=input_model,
        output_model=DeepAgentsToolOutput,
        handler=None,
        runtime_kinds=frozenset({"agent_session"}),
        required_capabilities=frozenset({"deepagents"}),
    )


_BUILTIN_BINDINGS = tuple(
    DeepAgentsToolBinding(
        definition=_definition(name, kind, input_model),
        source=source,
        enforcement=enforcement,
        interrupt_name=name,
        enforcement_reason=reason,
    )
    for name, kind, input_model, source, enforcement, reason in _TOOL_SPECS
)


def builtin_tool_bindings() -> tuple[DeepAgentsToolBinding, ...]:
    """Return the immutable, installed-version tool surface characterization."""

    return _BUILTIN_BINDINGS


def controlled_mode_blockers(tool_names: Iterable[str]) -> tuple[str, ...]:
    """Return unknown or non-enforceable tools in stable order."""

    bindings = {item.definition.meta.canonical_name: item for item in _BUILTIN_BINDINGS}
    blockers = {
        name
        for raw_name in tool_names
        if (name := str(raw_name).strip())
        and (
            name not in bindings
            or bindings[name].enforcement is DeepAgentsEnforcementCapability.UNSUPPORTED
        )
    }
    return tuple(sorted(blockers))


def require_controlled_mode_support(tool_names: Iterable[str]) -> None:
    """Fail closed when controlled mode cannot enforce every requested tool."""

    if blockers := controlled_mode_blockers(tool_names):
        raise DeepAgentsControlledModeUnsupported(blockers)


#: Every DeepAgents built-in tool name that must be excluded from the model
#: catalog in controlled mode (the platform substitutes its own managed tools
#: via the Tool Gateway).  Includes the Task-5 UNSUPPORTED tools (execute,
#: task, write_todos) which controlled mode neither routes through the legacy
#: backend nor exposes to the model.
CONTROLLED_MODE_EXCLUSION_SET: frozenset[str] = frozenset(
    {item.definition.meta.canonical_name for item in _BUILTIN_BINDINGS}
)


def controlled_mode_exclusion_set() -> frozenset[str]:
    """Return the built-in tool names controlled mode must exclude."""
    return CONTROLLED_MODE_EXCLUSION_SET


def verify_controlled_mode_exclusion(excluded: Iterable[str]) -> tuple[str, ...]:
    """Return built-in names that controlled mode failed to exclude.

    Used by the 9D startup gate: every name in
    :data:`CONTROLLED_MODE_EXCLUSION_SET` must be present in ``excluded`` (the
    middleware exclusion set actually applied).  Any missing name means the
    legacy entry point remains model-visible and controlled mode must fall
    back to legacy rather than claim enforcement it cannot provide.
    """
    applied = {str(name) for name in excluded}
    missing = CONTROLLED_MODE_EXCLUSION_SET - applied
    return tuple(sorted(missing))


def observe_contract_tools(tools: Iterable[Any]) -> tuple[DeepAgentsContractToolObservation, ...]:
    """Describe explicit ``AgentRuntimeContract.tools`` without invoking them."""

    observations: list[DeepAgentsContractToolObservation] = []
    seen: set[str] = set()
    for tool in tools:
        name = _tool_value(tool, "name")
        if not isinstance(name, str) or not name.strip():
            raise ValueError("DeepAgents contract tools require a non-empty name")
        name = name.strip()
        if name in seen:
            raise ValueError(f"duplicate DeepAgents contract tool: {name}")
        seen.add(name)
        description = _tool_value(tool, "description")
        schema = _input_schema(tool)
        observations.append(
            DeepAgentsContractToolObservation(
                name=name,
                description=description if isinstance(description, str) else "",
                input_schema=schema,
            )
        )
    return tuple(sorted(observations, key=lambda item: item.name))


def _tool_value(tool: Any, key: str) -> Any:
    return tool.get(key) if isinstance(tool, Mapping) else getattr(tool, key, None)


def _input_schema(tool: Any) -> Mapping[str, JsonValue]:
    args_schema = _tool_value(tool, "args_schema")
    if args_schema is not None and callable(getattr(args_schema, "model_json_schema", None)):
        return args_schema.model_json_schema()
    schema = _tool_value(tool, "input_schema")
    if isinstance(schema, Mapping):
        return dict(schema)
    return {}


__all__ = [
    "CONTROLLED_MODE_EXCLUSION_SET",
    "DeepAgentsContractToolObservation",
    "DeepAgentsControlledModeUnsupported",
    "DeepAgentsEnforcementCapability",
    "DeepAgentsToolBinding",
    "DeepAgentsToolSource",
    "builtin_tool_bindings",
    "controlled_mode_blockers",
    "controlled_mode_exclusion_set",
    "observe_contract_tools",
    "require_controlled_mode_support",
    "verify_controlled_mode_exclusion",
]
