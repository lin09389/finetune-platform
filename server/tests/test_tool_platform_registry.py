"""Contract tests for the typed canonical tool registry."""
from __future__ import annotations
import asyncio
import json
import pytest
from pydantic import BaseModel, ConfigDict, ValidationError
from tool_platform.catalog import catalog_json
from tool_platform.definition import ToolDefinition
from tool_platform.models import CanonicalToolMeta, ToolAvailability
from tool_platform.registry import DuplicateToolError, RegistryFrozenError, ToolProjectionContext, ToolRegistry
from tool_platform.taxonomy import ToolKind, ToolRisk, defaults_for_kind

class StrictInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    path: str
class StrictOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    content: str
class LooseInput(BaseModel): path: str
async def _handler(request: StrictInput) -> StrictOutput: return StrictOutput(content=request.path)
def make_definition(name="workspace.read_file", *, aliases=("read_file",), kind=ToolKind.READ, risk=ToolRisk.LOW, probe=None, **kwargs):
    return ToolDefinition(meta=CanonicalToolMeta(canonical_name=name, kind=kind, side_effects=defaults_for_kind(kind).side_effects, risk=risk, execution_location=defaults_for_kind(kind).execution_location, display_name=name, description="A test tool."), input_model=StrictInput, output_model=StrictOutput, handler=_handler, aliases=aliases, availability_probe=probe, **kwargs)

def test_definition_requires_strict_models_async_callbacks_and_json_facts():
    with pytest.raises(TypeError, match="strict Pydantic"): ToolDefinition(meta=make_definition().meta, input_model=LooseInput, output_model=StrictOutput, handler=None)
    with pytest.raises(TypeError, match="async"): ToolDefinition(meta=make_definition().meta, input_model=StrictInput, output_model=StrictOutput, handler=lambda _: StrictOutput(content="x"))
    definition = make_definition(required_provider_facts={"nested": {"x": True}})
    assert definition.validate_input({"path": "x"}).path == "x"
    with pytest.raises(ValidationError): definition.validate_input({"path": 1})

def test_registration_alias_and_version_resolution_fail_closed():
    registry = ToolRegistry(); definition = make_definition(definition_version=2); registry.register(definition)
    assert registry.resolve("read_file@2") is definition and registry.resolve("read_file@1") is None
    with pytest.raises(DuplicateToolError): registry.register(make_definition("read_file", aliases=()))
    with pytest.raises(DuplicateToolError): registry.register(make_definition("other", aliases=("read_file",)))

def test_projection_fails_closed_for_selectors_and_required_facts():
    registry = ToolRegistry(); definition = make_definition(agent_ids=frozenset({"build"}), runtime_kinds=frozenset({"runtime"}), required_capabilities=frozenset({"shell"}), required_provider_facts={"calls": True}) ; registry.register(definition)
    assert registry.project(ToolProjectionContext(agent_id="build")) == ()
    context = ToolProjectionContext(agent_id="build", runtime_kind="runtime", enabled_capabilities=frozenset({"shell"}), provider_facts={"calls": True})
    assert registry.project(context) == (definition,)
    assert registry.project(ToolProjectionContext(agent_id="build", allowed_names=frozenset())) == ()

def test_catalog_is_immutable_json_only_and_never_runs_probe():
    calls = 0
    async def probe():
        nonlocal calls; calls += 1; return True
    registry = ToolRegistry(); registry.register(make_definition(probe=probe))
    catalog = registry.catalog(); assert calls == 0 and catalog[0].availability.reason_code == "dependency_unchecked"
    assert registry.catalog(ToolProjectionContext(agent_id="x")) == ()
    encoded = catalog_json(catalog); assert "handler" not in encoded and json.loads(encoded)[0]["canonical_name"] == "workspace.read_file"
    with pytest.raises(TypeError): catalog[0].input_schema["x"] = True  # type: ignore[index]

@pytest.mark.asyncio
async def test_explicit_health_refresh_is_bounded_and_survives_freeze():
    async def probe() -> bool: await asyncio.sleep(0); return True
    registry = ToolRegistry(); registry.register(make_definition(probe=probe)); registry.freeze()
    assert registry.frozen and (await registry.check_availability("read_file", timeout_seconds=1)).available
    with pytest.raises(RegistryFrozenError): registry.register(make_definition("other", aliases=("other",)))

def test_context_is_strict_frozen_and_json_round_trippable():
    context = ToolProjectionContext(agent_id="build", provider_facts={"calls": True})
    assert ToolProjectionContext.model_validate_json(context.model_dump_json()) == context
    with pytest.raises(ValidationError): ToolProjectionContext.model_validate({"agent_id": "build", "other": True})
