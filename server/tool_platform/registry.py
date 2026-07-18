"""Fail-closed registration and role-specific projection of tools."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_serializer

from .catalog import ToolCatalogEntry, ToolCatalogSnapshot, ToolProjectionConstraints
from .definition import ToolDefinition
from .models import FrozenJsonObject, ToolAvailability
from .taxonomy import ToolKind, ToolRisk, defaults_for_kind


class ToolRegistryError(ValueError):
    """Base error for invalid registry operations."""


class DuplicateToolError(ToolRegistryError):
    """A canonical name or alias is already occupied."""


class RegistryFrozenError(ToolRegistryError):
    """The registry is immutable after startup has completed."""


_RISK_ORDER = {ToolRisk.LOW: 0, ToolRisk.MEDIUM: 1, ToolRisk.HIGH: 2, ToolRisk.CRITICAL: 3}


class ToolProjectionContext(BaseModel):
    """Non-secret facts used to derive an agent-visible tool set.

    ``allowed_names=None`` means no name allow-list is imposed; an empty set
    explicitly permits no names.  Denies always win after aliases normalize to
    canonical names.
    """

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True, validate_default=True)

    agent_id: str = Field(min_length=1, max_length=200)
    allowed_names: frozenset[str] | None = None
    denied_names: frozenset[str] = frozenset()
    allowed_kinds: frozenset[ToolKind] | None = None
    risk_ceiling: ToolRisk | None = None
    runtime_kind: str | None = None
    enabled_capabilities: frozenset[str] | None = None
    provider_facts: FrozenJsonObject = Field(default_factory=dict)
    model_facts: FrozenJsonObject = Field(default_factory=dict)
    platform_facts: FrozenJsonObject = Field(default_factory=dict)

    @field_serializer("provider_facts", "model_facts", "platform_facts")
    def serialize_facts(self, value: FrozenJsonObject) -> JsonValue:
        return _jsonable(value)


class ToolRegistry:
    """The in-memory source of truth for registered tool definitions."""

    def __init__(self) -> None:
        self._definitions: dict[str, ToolDefinition[Any, Any]] = {}
        self._aliases: dict[str, str] = {}
        self._availability: dict[str, ToolAvailability] = {}
        self._frozen = False

    @property
    def frozen(self) -> bool:
        return self._frozen

    def register(self, definition: ToolDefinition[Any, Any]) -> None:
        if self._frozen:
            raise RegistryFrozenError("tool registry is frozen")
        canonical_name = definition.meta.canonical_name
        if canonical_name in self._definitions or canonical_name in self._aliases:
            raise DuplicateToolError(f"canonical name {canonical_name!r} is already registered")
        for alias in definition.aliases:
            if alias in self._definitions or alias in self._aliases:
                raise DuplicateToolError(f"alias {alias!r} is already registered")
        defaults = defaults_for_kind(definition.meta.kind)
        if not defaults.side_effects.issubset(definition.meta.side_effects):
            raise ValueError("declared side_effects must cover the tool kind defaults")
        if _RISK_ORDER[definition.meta.risk] < _RISK_ORDER[defaults.risk]:
            raise ValueError("declared risk cannot be lower than the tool kind default")
        self._definitions[canonical_name] = definition
        self._aliases.update(dict.fromkeys(definition.aliases, canonical_name))
        self._availability[canonical_name] = ToolAvailability(
            canonical_name=canonical_name,
            available=definition.availability_probe is None,
            reason_code=None if definition.availability_probe is None else "dependency_unchecked",
        )

    def resolve(self, name: str) -> ToolDefinition[Any, Any] | None:
        """Resolve canonical names and aliases; missing names never fall back."""

        reference, separator, raw_version = name.rpartition("@")
        requested_version = int(raw_version) if separator and raw_version.isdigit() else None
        lookup = reference if requested_version is not None else name
        canonical_name = self._aliases.get(lookup, lookup)
        definition = self._definitions.get(canonical_name)
        if definition is not None and requested_version not in {None, definition.definition_version}:
            return None
        return definition

    def freeze(self) -> None:
        self._frozen = True

    async def check_availability(self, name: str, *, timeout_seconds: float = 5) -> ToolAvailability:
        """Refresh one dependency probe under a bounded timeout.

        This is deliberately separate from projection and catalog reads, which
        only consume the cached status and therefore perform no I/O.
        """

        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        definition = self.resolve(name)
        if definition is None:
            raise ToolRegistryError(f"unknown tool {name!r}")
        probe = definition.availability_probe
        if probe is None:
            return self._availability[definition.meta.canonical_name]
        try:
            value = await asyncio.wait_for(probe(), timeout=timeout_seconds)
            if isinstance(value, ToolAvailability):
                if value.canonical_name != definition.meta.canonical_name:
                    raise ValueError("availability probe returned another tool name")
                availability = value
            else:
                availability = ToolAvailability(
                    canonical_name=definition.meta.canonical_name, available=bool(value)
                )
        except TimeoutError:
            availability = ToolAvailability(
                canonical_name=definition.meta.canonical_name,
                available=False,
                reason_code="dependency_probe_timeout",
            )
        except Exception:
            availability = ToolAvailability(
                canonical_name=definition.meta.canonical_name,
                available=False,
                reason_code="dependency_probe_failed",
            )
        self._availability[definition.meta.canonical_name] = availability
        return availability

    def project(self, context: ToolProjectionContext) -> tuple[ToolDefinition[Any, Any], ...]:
        normalized_allowed = self._normalize_names(context.allowed_names, selector_type="allowed")
        normalized_denied = self._normalize_names(context.denied_names, selector_type="denied")
        selected: list[ToolDefinition[Any, Any]] = []
        for name in sorted(self._definitions):
            definition = self._definitions[name]
            if definition.agent_ids and context.agent_id not in definition.agent_ids:
                continue
            if name in normalized_denied:
                continue
            if normalized_allowed is not None and name not in normalized_allowed:
                continue
            if context.allowed_kinds is not None and definition.meta.kind not in context.allowed_kinds:
                continue
            if context.risk_ceiling is not None and _RISK_ORDER[definition.meta.risk] > _RISK_ORDER[context.risk_ceiling]:
                continue
            if definition.runtime_kinds and context.runtime_kind not in definition.runtime_kinds:
                continue
            if definition.required_capabilities and (
                context.enabled_capabilities is None
                or not definition.required_capabilities.issubset(context.enabled_capabilities)
            ):
                continue
            if not self._facts_match(definition.required_provider_facts, context.provider_facts):
                continue
            if not self._facts_match(definition.required_model_facts, context.model_facts):
                continue
            if not self._facts_match(definition.required_platform_facts, context.platform_facts):
                continue
            if not self._availability[definition.meta.canonical_name].available:
                continue
            selected.append(definition)
        return tuple(selected)

    def catalog(self, context: ToolProjectionContext | None = None) -> tuple[ToolCatalogEntry, ...]:
        definitions = self.project(context) if context is not None else self._all_definitions()
        return tuple(self._catalog_item(definition) for definition in definitions)

    def snapshot(self, context: ToolProjectionContext | None = None) -> ToolCatalogSnapshot:
        """Return an executable-free, deterministically ordered registry image."""

        return ToolCatalogSnapshot(tools=self.catalog(context))

    def _all_definitions(self) -> tuple[ToolDefinition[Any, Any], ...]:
        return tuple(definition for _, definition in sorted(self._definitions.items()))

    def _normalize_names(
        self, names: frozenset[str] | None, *, selector_type: str
    ) -> frozenset[str] | None:
        if names is None:
            return None
        normalized: set[str] = set()
        unknown: list[str] = []
        for selector in names:
            definition = self.resolve(selector)
            if definition is None:
                unknown.append(selector)
            else:
                normalized.add(definition.meta.canonical_name)
        if unknown:
            selectors = ", ".join(repr(selector) for selector in sorted(unknown))
            raise ToolRegistryError(f"unknown {selector_type} tool selector(s): {selectors}")
        return frozenset(normalized)

    @staticmethod
    def _facts_match(required: Mapping[str, object], actual: Mapping[str, object]) -> bool:
        return all(key in actual and actual[key] == expected for key, expected in required.items())

    def _catalog_item(self, definition: ToolDefinition[Any, Any]) -> ToolCatalogEntry:
        availability = self._availability[definition.meta.canonical_name]
        return ToolCatalogEntry(
            canonical_name=definition.meta.canonical_name,
            definition_version=definition.definition_version,
            metadata=definition.meta,
            aliases=definition.aliases,
            input_schema=definition.input_model.model_json_schema(),
            output_schema=definition.output_model.model_json_schema(),
            availability=availability,
            projection=ToolProjectionConstraints(
                agent_ids=tuple(sorted(definition.agent_ids)),
                runtime_kinds=tuple(sorted(definition.runtime_kinds)),
                required_capabilities=tuple(sorted(definition.required_capabilities)),
                required_provider_facts=_jsonable(definition.required_provider_facts),  # type: ignore[arg-type]
                required_model_facts=_jsonable(definition.required_model_facts),  # type: ignore[arg-type]
                required_platform_facts=_jsonable(definition.required_platform_facts),  # type: ignore[arg-type]
            ),
        )


def _jsonable(value: object) -> JsonValue:
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_jsonable(item) for item in value]
    return value  # type: ignore[return-value]
