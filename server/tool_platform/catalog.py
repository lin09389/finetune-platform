"""Strict, executable-free catalog projections for canonical tools."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_serializer

from .models import CanonicalToolMeta, FrozenJsonObject, ToolAvailability


class _CatalogModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True, validate_default=True)


class ToolProjectionConstraints(_CatalogModel):
    agent_ids: tuple[str, ...] = ()
    runtime_kinds: tuple[str, ...] = ()
    required_capabilities: tuple[str, ...] = ()
    required_provider_facts: FrozenJsonObject = Field(default_factory=dict)
    required_model_facts: FrozenJsonObject = Field(default_factory=dict)
    required_platform_facts: FrozenJsonObject = Field(default_factory=dict)

    @field_serializer(
        "required_provider_facts",
        "required_model_facts",
        "required_platform_facts",
    )
    def serialize_facts(self, value: FrozenJsonObject) -> JsonValue:
        return _jsonable(value)


class ToolCatalogEntry(_CatalogModel):
    canonical_name: str = Field(min_length=1, max_length=200)
    definition_version: int = Field(ge=1)
    metadata: CanonicalToolMeta
    aliases: tuple[str, ...] = ()
    input_schema: FrozenJsonObject
    output_schema: FrozenJsonObject
    availability: ToolAvailability
    projection: ToolProjectionConstraints = Field(default_factory=ToolProjectionConstraints)

    @field_serializer("input_schema", "output_schema")
    def serialize_schema(self, value: FrozenJsonObject) -> JsonValue:
        return _jsonable(value)


class ToolCatalogSnapshot(_CatalogModel):
    schema_version: Literal[1] = 1
    tools: tuple[ToolCatalogEntry, ...] = ()


def catalog_json(
    catalog: Sequence[ToolCatalogEntry] | ToolCatalogSnapshot,
) -> str:
    """Serialize a strict catalog DTO into deterministic JSON."""

    if isinstance(catalog, ToolCatalogSnapshot):
        payload: JsonValue = catalog.model_dump(mode="json")
    else:
        payload = [item.model_dump(mode="json") for item in catalog]
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def _jsonable(value: object) -> JsonValue:
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_jsonable(item) for item in value]
    return value  # type: ignore[return-value]


__all__ = [
    "ToolCatalogEntry",
    "ToolCatalogSnapshot",
    "ToolProjectionConstraints",
    "catalog_json",
]
