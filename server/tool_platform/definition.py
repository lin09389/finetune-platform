"""Typed, non-wire contracts for canonical tool implementations."""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Generic, Protocol, TypeAlias, TypeVar

from pydantic import BaseModel, ConfigDict, JsonValue, TypeAdapter

from .models import CanonicalToolMeta, ToolAvailability

InputT = TypeVar("InputT", bound=BaseModel)
OutputT = TypeVar("OutputT", bound=BaseModel)


class ToolHandler(Protocol[InputT, OutputT]):
    async def __call__(self, request: InputT) -> OutputT: ...


AvailabilityProbe: TypeAlias = Callable[[], Awaitable[bool | ToolAvailability]]
_FACTS_ADAPTER = TypeAdapter(dict[str, JsonValue], config=ConfigDict(strict=True))


def _is_strict_model(model: type[BaseModel]) -> bool:
    config = model.model_config
    return config.get("extra") == "forbid" and config.get("strict") is True


def _is_async_callable(callback: object) -> bool:
    return inspect.iscoroutinefunction(callback) or inspect.iscoroutinefunction(type(callback).__call__)


@dataclass(frozen=True, slots=True)
class ToolDefinition(Generic[InputT, OutputT]):
    meta: CanonicalToolMeta
    input_model: type[InputT]
    output_model: type[OutputT]
    handler: ToolHandler[InputT, OutputT] | None
    definition_version: int = 1
    aliases: tuple[str, ...] = ()
    availability_probe: AvailabilityProbe | None = None
    runtime_kinds: frozenset[str] = frozenset()
    required_capabilities: frozenset[str] = frozenset()
    agent_ids: frozenset[str] = frozenset()
    required_provider_facts: Mapping[str, JsonValue] = field(default_factory=dict)
    required_model_facts: Mapping[str, JsonValue] = field(default_factory=dict)
    required_platform_facts: Mapping[str, JsonValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.meta, CanonicalToolMeta):
            raise TypeError("meta must be CanonicalToolMeta")
        if isinstance(self.definition_version, bool) or not isinstance(self.definition_version, int) or self.definition_version < 1:
            raise ValueError("definition_version must be at least 1")
        if isinstance(self.aliases, str):
            raise TypeError("aliases must be a sequence of names, not a string")
        object.__setattr__(self, "aliases", tuple(self.aliases))
        for field_name in ("runtime_kinds", "required_capabilities", "agent_ids"):
            raw_values = getattr(self, field_name)
            if isinstance(raw_values, str):
                raise TypeError(f"{field_name} must be a collection of names, not a string")
            values = frozenset(raw_values)
            if any(not isinstance(value, str) or not value or value != value.strip() for value in values):
                raise ValueError(f"{field_name} must contain non-empty normalized strings")
            object.__setattr__(self, field_name, values)
        for model, label in ((self.input_model, "input_model"), (self.output_model, "output_model")):
            if not isinstance(model, type) or not issubclass(model, BaseModel):
                raise TypeError(f"{label} must be a Pydantic BaseModel subclass")
            if not _is_strict_model(model):
                raise TypeError(f"{label} must be a strict Pydantic BaseModel subclass")
        if len(set(self.aliases)) != len(self.aliases):
            raise ValueError("tool aliases must be unique")
        if self.meta.canonical_name in self.aliases:
            raise ValueError("a tool alias cannot equal its canonical name")
        if any(not alias for alias in self.aliases):
            raise ValueError("tool aliases cannot be empty")
        if "@" in self.meta.canonical_name or any("@" in alias for alias in self.aliases):
            raise ValueError("tool names and aliases cannot contain the version separator '@'")
        if any(alias != alias.strip() for alias in self.aliases):
            raise ValueError("tool aliases cannot contain surrounding whitespace")
        if self.handler is not None and not _is_async_callable(self.handler):
            raise TypeError("handler must be an async callable")
        if self.availability_probe is not None and not _is_async_callable(self.availability_probe):
            raise TypeError("availability_probe must be an async callable")
        for field_name in ("required_provider_facts", "required_model_facts", "required_platform_facts"):
            value = _FACTS_ADAPTER.validate_python(dict(getattr(self, field_name)), strict=True)
            object.__setattr__(self, field_name, _freeze_mapping(value))

    def validate_input(self, payload: object) -> InputT:
        return self.input_model.model_validate(payload, strict=True)

    def validate_output(self, payload: object) -> OutputT:
        return self.output_model.model_validate(payload, strict=True)


def _freeze_mapping(value: Mapping[str, JsonValue]) -> Mapping[str, JsonValue]:
    def freeze(item: JsonValue) -> JsonValue:
        if isinstance(item, dict):
            return MappingProxyType({key: freeze(child) for key, child in item.items()})  # type: ignore[return-value]
        if isinstance(item, list):
            return tuple(freeze(child) for child in item)  # type: ignore[return-value]
        return item
    return MappingProxyType({key: freeze(item) for key, item in value.items()})
