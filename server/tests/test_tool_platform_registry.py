"""Contract tests for the typed canonical tool registry."""

from __future__ import annotations

import asyncio
import json

import pytest
from pydantic import BaseModel, ConfigDict, ValidationError
from tool_platform.catalog import catalog_json
from tool_platform.definition import ToolDefinition
from tool_platform.models import CanonicalToolMeta, ToolAvailability
from tool_platform.registry import (
    DuplicateToolError,
    RegistryFrozenError,
    ToolProjectionContext,
    ToolRegistry,
)
from tool_platform.taxonomy import (
    ExecutionLocation,
    SideEffect,
    ToolKind,
    ToolRisk,
    defaults_for_kind,
)


class StrictInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    path: str


class StrictOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    content: str


class LooseInput(BaseModel):
    path: str


def make_definition(
    name: str = "workspace.read_file",
    *,
    aliases: tuple[str, ...] = ("read_file",),
    kind: ToolKind = ToolKind.READ,
    risk: ToolRisk = ToolRisk.LOW,
    runtime_kinds: frozenset[str] = frozenset(),
    required_capabilities: frozenset[str] = frozenset(),
    agent_ids: frozenset[str] = frozenset(),
    required_provider_facts: dict[str, object] | None = None,
    required_model_facts: dict[str, object] | None = None,
    required_platform_facts: dict[str, object] | None = None,
    probe=None,
    definition_version: int = 1,
) -> ToolDefinition[StrictInput, StrictOutput]:
    return ToolDefinition(
        meta=CanonicalToolMeta(
            canonical_name=name,
            kind=kind,
            side_effects=defaults_for_kind(kind).side_effects,
            risk=risk,
            execution_location=defaults_for_kind(kind).execution_location,
            display_name=name,
            description="A test tool.",
        ),
        definition_version=definition_version,
        input_model=StrictInput,
        output_model=StrictOutput,
        handler=_handler,
        aliases=aliases,
        runtime_kinds=runtime_kinds,
        required_capabilities=required_capabilities,
        agent_ids=agent_ids,
        required_provider_facts=required_provider_facts or {},
        required_model_facts=required_model_facts or {},
        required_platform_facts=required_platform_facts or {},
        availability_probe=probe,
)


async def _handler(request: StrictInput) -> StrictOutput:
    return StrictOutput(content=request.path)


def test_definition_keeps_implementation_version_separate_from_wire_schema() -> None:
    definition = make_definition(definition_version=7)

    assert definition.definition_version == 7
    assert definition.meta.schema_version == 1


def test_definition_requires_strict_pydantic_models_and_complete_metadata() -> None:
    with pytest.raises(TypeError, match="strict Pydantic"):
        ToolDefinition(
            meta=make_definition().meta,
            input_model=LooseInput,
            output_model=StrictOutput,
            handler=None,
        )

    definition = make_definition()
    assert definition.validate_input({"path": "README.md"}) == StrictInput(path="README.md")
    assert definition.validate_output({"content": "ok"}) == StrictOutput(content="ok")
    with pytest.raises(ValidationError):
        definition.validate_input({"path": 1})
    with pytest.raises(ValidationError):
        definition.validate_output({"content": "ok", "extra": True})
    with pytest.raises(ValidationError):
        make_definition(required_provider_facts={"client": _handler})
    with pytest.raises(ValueError, match="version separator"):
        make_definition(aliases=("read@1",))
    with pytest.raises(TypeError, match="not a string"):
        make_definition(runtime_kinds="agent_session")  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="async"):
        ToolDefinition(
            meta=make_definition().meta,
            input_model=StrictInput,
            output_model=StrictOutput,
            handler=lambda request: StrictOutput(content=request.path),
        )
    with pytest.raises(ValidationError):
        CanonicalToolMeta(
            canonical_name="missing.description",
            kind=ToolKind.READ,
            side_effects=frozenset({SideEffect.NONE}),
            risk=ToolRisk.LOW,
            execution_location=ExecutionLocation.CONTROL_PLANE,
            display_name="Missing",
            description="",
        )


def test_registry_rejects_duplicate_names_aliases_and_versions() -> None:
    registry = ToolRegistry()
    registry.register(make_definition())

    with pytest.raises(DuplicateToolError, match="canonical name"):
        registry.register(make_definition(definition_version=2))
    with pytest.raises(DuplicateToolError, match="alias"):
        registry.register(make_definition("workspace.list_files", aliases=("read_file",)))
    with pytest.raises(DuplicateToolError, match="canonical name"):
        registry.register(make_definition("read_file", aliases=()))


def test_registration_rejects_metadata_that_weakens_kind_defaults() -> None:
    registry = ToolRegistry()
    definition = make_definition("workspace.execute", kind=ToolKind.EXECUTE, risk=ToolRisk.LOW)
    with pytest.raises(ValueError, match="risk"):
        registry.register(definition)


def test_resolve_uses_canonical_name_or_alias_and_unknown_fails_closed() -> None:
    registry = ToolRegistry()
    definition = make_definition()
    registry.register(definition)

    assert registry.resolve("workspace.read_file") is definition
    assert registry.resolve("read_file") is definition
    assert registry.resolve("read_file@1") is definition
    assert registry.resolve("workspace.read_file@1") is definition
    assert registry.resolve("read_file@2") is None
    assert registry.resolve("missing") is None


def test_projection_is_deterministic_and_intersects_normalized_selectors() -> None:
    registry = ToolRegistry()
    registry.register(make_definition("zeta.read", aliases=("z",)))
    registry.register(make_definition("alpha.read", aliases=("a",)))
    registry.register(
        make_definition(
            "beta.execute",
            aliases=("run",),
            kind=ToolKind.EXECUTE,
            risk=ToolRisk.HIGH,
            runtime_kinds=frozenset({"build"}),
            required_capabilities=frozenset({"shell"}),
        )
    )

    unrestricted = registry.project(ToolProjectionContext(agent_id="agent"))
    assert [item.meta.canonical_name for item in unrestricted] == ["alpha.read", "zeta.read"]

    selected = registry.project(
        ToolProjectionContext(
            agent_id="agent",
            allowed_names=frozenset({"a", "run"}),
            denied_names=frozenset({"run"}),
            allowed_kinds=frozenset({ToolKind.READ, ToolKind.EXECUTE}),
            risk_ceiling=ToolRisk.HIGH,
            runtime_kind="build",
            enabled_capabilities=frozenset({"shell"}),
        )
    )
    assert [item.meta.canonical_name for item in selected] == ["alpha.read"]


def test_empty_allowed_names_means_allow_nothing() -> None:
    registry = ToolRegistry()
    registry.register(make_definition())

    assert registry.project(ToolProjectionContext(agent_id="agent", allowed_names=frozenset())) == ()


def test_projection_fails_closed_for_missing_role_runtime_capability_and_facts() -> None:
    registry = ToolRegistry()
    definition = make_definition(
        agent_ids=frozenset({"build"}),
        runtime_kinds=frozenset({"agent_session"}),
        required_capabilities=frozenset({"shell"}),
        required_provider_facts={"tool_calling": True},
        required_model_facts={"family": "gpt"},
        required_platform_facts={"sandbox": "local"},
    )
    registry.register(definition)

    assert registry.project(ToolProjectionContext(agent_id="build")) == ()
    assert registry.project(
        ToolProjectionContext(
            agent_id="build",
            runtime_kind="agent_session",
            enabled_capabilities=frozenset({"shell"}),
            provider_facts={"tool_calling": True},
            model_facts={"family": "gpt"},
            platform_facts={"sandbox": "local"},
        )
    ) == (definition,)
    assert registry.project(
        ToolProjectionContext(
            agent_id="review",
            runtime_kind="agent_session",
            enabled_capabilities=frozenset({"shell"}),
            provider_facts={"tool_calling": True},
            model_facts={"family": "gpt"},
            platform_facts={"sandbox": "local"},
        )
    ) == ()


def test_projection_context_is_strict_frozen_and_json_round_trippable() -> None:
    context = ToolProjectionContext(agent_id="build", provider_facts={"tool_calling": True})
    assert ToolProjectionContext.model_validate_json(context.model_dump_json()) == context
    with pytest.raises(ValidationError):
        ToolProjectionContext(agent_id=1)  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        ToolProjectionContext.model_validate({"agent_id": "build", "unknown": True})


@pytest.mark.asyncio
async def test_runtime_capability_risk_and_dependency_probe_filtering() -> None:
    async def unavailable() -> ToolAvailability:
        return ToolAvailability(canonical_name="gamma.read", available=False, reason_code="dependency_missing")

    registry = ToolRegistry()
    registry.register(make_definition("gamma.read", probe=unavailable))
    registry.register(
        make_definition(
            "delta.execute",
            aliases=("delta",),
            kind=ToolKind.EXECUTE,
            risk=ToolRisk.HIGH,
            runtime_kinds=frozenset({"build"}),
            required_capabilities=frozenset({"shell"}),
        )
    )

    # Projection/catal​og never execute a dependency probe.  Cached status starts
    # fail-closed for probed tools and changes only through the explicit check.
    assert registry.project(ToolProjectionContext(agent_id="agent")) == ()
    checked = await registry.check_availability("gamma.read", timeout_seconds=1)
    assert checked.available is False
    assert registry.project(
        ToolProjectionContext(
            agent_id="agent",
            risk_ceiling=ToolRisk.HIGH,
            runtime_kind="build",
            enabled_capabilities=frozenset({"shell"}),
        )
    ) == (registry.resolve("delta.execute"),)


@pytest.mark.asyncio
async def test_async_availability_probe_is_explicit_and_cached() -> None:
    async def available() -> bool:
        await asyncio.sleep(0)
        return True

    registry = ToolRegistry()
    registry.register(make_definition(probe=available))
    assert registry.project(ToolProjectionContext(agent_id="agent")) == ()
    assert (await registry.check_availability("workspace.read_file", timeout_seconds=1)).available is True
    assert registry.project(ToolProjectionContext(agent_id="agent")) == (registry.resolve("workspace.read_file"),)


def test_catalog_and_snapshot_contain_only_serializable_metadata_and_schemas() -> None:
    registry = ToolRegistry()
    registry.register(make_definition())

    catalog = registry.catalog(ToolProjectionContext(agent_id="agent"))
    snapshot = registry.snapshot(ToolProjectionContext(agent_id="agent"))
    encoded = catalog_json(catalog)
    assert json.loads(encoded) == [item.model_dump(mode="json") for item in catalog]
    assert json.loads(snapshot.model_dump_json()) == snapshot.model_dump(mode="json")
    assert catalog[0].canonical_name == "workspace.read_file"
    assert catalog[0].definition_version == 1
    assert "handler" not in encoded
    assert "availability_probe" not in encoded
    assert "callable" not in encoded
    with pytest.raises(TypeError):
        snapshot.tools[0].input_schema["extra"] = True  # type: ignore[index]


def test_unfiltered_catalog_reports_unchecked_tools_without_running_probes() -> None:
    calls = 0

    async def probe() -> bool:
        nonlocal calls
        calls += 1
        return True

    registry = ToolRegistry()
    registry.register(make_definition(probe=probe))

    catalog = registry.catalog()
    assert calls == 0
    assert catalog[0].availability.available is False
    assert catalog[0].availability.reason_code == "dependency_unchecked"
    assert registry.catalog(ToolProjectionContext(agent_id="agent")) == ()


def test_freeze_rejects_all_future_mutation() -> None:
    registry = ToolRegistry()
    registry.register(make_definition())
    registry.freeze()

    assert registry.frozen is True
    with pytest.raises(RegistryFrozenError):
        registry.register(make_definition("workspace.list_files", aliases=("list_files",)))


@pytest.mark.asyncio
async def test_freeze_keeps_definitions_fixed_but_allows_explicit_health_refresh() -> None:
    async def available() -> bool:
        return True

    registry = ToolRegistry()
    registry.register(make_definition(probe=available))
    registry.freeze()

    assert (await registry.check_availability("workspace.read_file")).available is True
