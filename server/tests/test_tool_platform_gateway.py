"""Pipeline contract tests for the canonical Tool Gateway."""

from __future__ import annotations

import asyncio

import pytest
from pydantic import BaseModel, ConfigDict, ValidationError
from tool_platform.adapters.deepagents import DeepAgentsEnforcementCapability
from tool_platform.gateway import ToolGateway, ToolGatewayOutcome
from tool_platform.handlers import ApprovalOutcome
from tool_platform.models import ToolAvailability, ToolInvocation
from tool_platform.policy import ToolPolicyFacts
from tool_platform.registry import ToolRegistry
from tool_platform.taxonomy import SideEffect, ToolKind, defaults_for_kind


class StrictInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    path: str


class StrictOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    content: str


class StrictOutputWithSecret(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    content: str
    api_key: str = ""


async def _ok_handler(request: StrictInput) -> StrictOutput:
    return StrictOutput(content=request.path)


_UNSET = object()


def make_definition(
    name: str = "test.read",
    *,
    aliases: tuple[str, ...] = (),
    kind: ToolKind = ToolKind.READ,
    handler=_UNSET,
    input_model=StrictInput,
    output_model=StrictOutput,
    probe=None,
):
    from tool_platform.definition import ToolDefinition
    from tool_platform.models import CanonicalToolMeta

    defaults = defaults_for_kind(kind)
    return ToolDefinition(
        meta=CanonicalToolMeta(
            canonical_name=name,
            kind=kind,
            side_effects=defaults.side_effects,
            risk=defaults.risk,
            execution_location=defaults.execution_location,
            display_name=name,
            description="A test tool.",
        ),
        input_model=input_model,
        output_model=output_model,
        handler=_ok_handler if handler is _UNSET else handler,
        aliases=aliases,
        availability_probe=probe,
    )


class SpyRegistry(ToolRegistry):
    """Real registry that records explicit availability lookups."""

    def __init__(self) -> None:
        super().__init__()
        self.availability_calls: list[str] = []

    async def check_availability(self, name: str, *, timeout_seconds: float = 5):
        self.availability_calls.append(name)
        return await super().check_availability(name, timeout_seconds=timeout_seconds)


def _build_registry(*definitions) -> SpyRegistry:
    registry = SpyRegistry()
    for definition in definitions:
        registry.register(definition)
    registry.freeze()
    return registry


def _invocation(name: str, *, arguments=None, invocation_id: str = "inv-1") -> ToolInvocation:
    return ToolInvocation(
        invocation_id=invocation_id,
        tool_name=name,
        arguments=arguments if arguments is not None else {"path": "README.md"},
    )


# --- resolution + enforcement -------------------------------------------------


@pytest.mark.asyncio
async def test_unknown_tool_denies_with_failed_event():
    registry = _build_registry(make_definition())
    sink: list = []
    gateway = ToolGateway(registry, sink.append)

    outcome = await gateway.invoke(
        _invocation("missing.tool"), ToolPolicyFacts()
    )

    assert outcome.status == "denied"
    assert outcome.decision == "deny"
    assert outcome.error is not None
    assert outcome.error.code == "unknown_tool"
    assert [event.event_type for event in sink] == ["tool.started", "tool.failed"]
    assert outcome.events == tuple(sink)


@pytest.mark.asyncio
async def test_unsupported_enforcement_denies_even_when_policy_would_allow():
    # READ tool + permissive facts -> policy would allow; UNSUPPORTED must override.
    registry = _build_registry(make_definition(kind=ToolKind.READ))
    sink: list = []
    gateway = ToolGateway(registry, sink.append)

    outcome = await gateway.invoke(
        _invocation("test.read"),
        ToolPolicyFacts(),
        enforcement_capability=DeepAgentsEnforcementCapability.UNSUPPORTED,
    )

    assert outcome.status == "denied"
    assert outcome.error is not None
    assert outcome.error.code == "unsupported_enforcement"
    # availability is always fetched explicitly, even for an unsupported tool.
    assert registry.availability_calls == ["test.read"]
    assert sink[-1].event_type == "tool.failed"


# --- availability -------------------------------------------------------------


@pytest.mark.asyncio
async def test_availability_is_fetched_explicitly_from_registry():
    registry = _build_registry(make_definition(kind=ToolKind.READ))
    sink: list = []
    gateway = ToolGateway(registry, sink.append)

    outcome = await gateway.invoke(_invocation("test.read"), ToolPolicyFacts())

    assert outcome.status == "success"
    assert registry.availability_calls == ["test.read"]


@pytest.mark.asyncio
async def test_unavailable_tool_denies():
    async def unavailable() -> ToolAvailability:
        return ToolAvailability(
            canonical_name="test.read", available=False, reason_code="dependency_missing"
        )

    registry = _build_registry(make_definition(kind=ToolKind.READ, probe=unavailable))
    # Refresh the cached availability so the gateway sees available=False.
    await registry.check_availability("test.read", timeout_seconds=1)
    sink: list = []
    gateway = ToolGateway(registry, sink.append)

    outcome = await gateway.invoke(_invocation("test.read"), ToolPolicyFacts())

    assert outcome.status == "denied"
    assert outcome.error is not None
    assert outcome.error.code == "unavailable"


@pytest.mark.asyncio
async def test_availability_check_exception_is_fail_closed_and_logged(
    caplog: pytest.LogCaptureFixture,
):
    class BrokenRegistry(SpyRegistry):
        async def check_availability(self, name: str, *, timeout_seconds: float = 5):
            self.availability_calls.append(name)
            raise RuntimeError("registry unavailable")

    registry = BrokenRegistry()
    registry.register(make_definition(kind=ToolKind.READ))
    registry.freeze()
    sink: list = []
    gateway = ToolGateway(registry, sink.append)

    with caplog.at_level("ERROR", logger="tool_platform.gateway"):
        outcome = await gateway.invoke(_invocation("test.read"), ToolPolicyFacts())

    assert outcome.status == "denied"
    assert outcome.error is not None
    assert outcome.error.code == "unavailable"
    assert any("availability check failed" in record.message for record in caplog.records)


# --- input / output validation -----------------------------------------------


@pytest.mark.asyncio
async def test_strict_input_validation_rejects_extra_fields():
    registry = _build_registry(make_definition(kind=ToolKind.READ))
    gateway = ToolGateway(registry, lambda _event: None)

    outcome = await gateway.invoke(
        _invocation("test.read", arguments={"path": "x", "extra": True}),
        ToolPolicyFacts(),
    )

    assert outcome.status == "error"
    assert outcome.error is not None
    assert outcome.error.code == "input_validation"
    assert outcome.error.error_type == "validation"


@pytest.mark.asyncio
async def test_output_validation_failure_fails_closed():
    async def bad_output(request: StrictInput) -> dict:
        return {"content": "ok", "unexpected": True}

    registry = _build_registry(make_definition(kind=ToolKind.READ, handler=bad_output))
    sink: list = []
    gateway = ToolGateway(registry, sink.append)

    outcome = await gateway.invoke(_invocation("test.read"), ToolPolicyFacts())

    assert outcome.status == "error"
    assert outcome.error is not None
    assert outcome.error.code == "output_validation"
    assert outcome.decision == "allow"  # execution was authorized; output failed


# --- policy + approval + dispatch --------------------------------------------


@pytest.mark.asyncio
async def test_policy_allow_dispatches_and_completes():
    registry = _build_registry(make_definition(kind=ToolKind.READ))
    sink: list = []
    gateway = ToolGateway(registry, sink.append)

    outcome = await gateway.invoke(_invocation("test.read"), ToolPolicyFacts())

    assert outcome.status == "success"
    assert outcome.decision == "allow"
    assert outcome.result is not None
    assert outcome.result.status == "success"
    assert outcome.result.output == {"content": "README.md"}
    assert [event.event_type for event in sink] == ["tool.started", "tool.completed"]


@pytest.mark.asyncio
async def test_policy_ask_suspends_by_default_without_dispatch():
    calls = {"handler": 0}

    async def counting_handler(request: StrictInput) -> StrictOutput:
        calls["handler"] += 1
        return StrictOutput(content=request.path)

    registry = _build_registry(
        make_definition(name="test.write", kind=ToolKind.WRITE, handler=counting_handler)
    )
    sink: list = []
    gateway = ToolGateway(registry, sink.append)
    facts = ToolPolicyFacts(require_approval_for=frozenset({SideEffect.WORKSPACE_WRITE}))

    outcome = await gateway.invoke(_invocation("test.write"), facts)

    assert outcome.status == "needs_approval"
    assert outcome.decision == "ask"
    assert calls["handler"] == 0
    assert [event.event_type for event in sink] == ["tool.started", "tool.needs_approval"]


@pytest.mark.asyncio
async def test_policy_ask_with_approving_adapter_proceeds_to_dispatch():
    class AlwaysApprove:
        def request_approval(self, invocation, policy_decision) -> ApprovalOutcome:
            return ApprovalOutcome(granted=True)

    registry = _build_registry(make_definition(name="test.write", kind=ToolKind.WRITE))
    gateway = ToolGateway(registry, lambda _event: None, approval_adapter=AlwaysApprove())
    facts = ToolPolicyFacts(require_approval_for=frozenset({SideEffect.WORKSPACE_WRITE}))

    outcome = await gateway.invoke(_invocation("test.write"), facts)

    assert outcome.status == "success"
    assert outcome.decision == "allow"


@pytest.mark.asyncio
async def test_policy_deny_fails_with_reason_code():
    registry = _build_registry(make_definition(name="test.execute", kind=ToolKind.EXECUTE))
    gateway = ToolGateway(registry, lambda _event: None)
    facts = ToolPolicyFacts(deny_for=frozenset({SideEffect.PROCESS, SideEffect.DESTRUCTIVE}))

    outcome = await gateway.invoke(_invocation("test.execute"), facts)

    assert outcome.status == "denied"
    assert outcome.error is not None
    assert outcome.error.code == "denied_side_effect"


# --- dispatch failure modes ---------------------------------------------------


@pytest.mark.asyncio
async def test_handler_timeout_fails_closed():
    async def slow(request: StrictInput) -> StrictOutput:
        await asyncio.sleep(10)
        return StrictOutput(content=request.path)

    registry = _build_registry(make_definition(kind=ToolKind.READ, handler=slow))
    gateway = ToolGateway(registry, lambda _event: None, handler_timeout=0.05)

    outcome = await gateway.invoke(_invocation("test.read"), ToolPolicyFacts())

    assert outcome.status == "error"
    assert outcome.error is not None
    assert outcome.error.code == "handler_timeout"
    assert outcome.error.error_type == "timeout"


@pytest.mark.asyncio
async def test_handler_exception_fails_closed():
    async def boom(request: StrictInput) -> StrictOutput:
        raise RuntimeError("boom")

    registry = _build_registry(make_definition(kind=ToolKind.READ, handler=boom))
    gateway = ToolGateway(registry, lambda _event: None)

    outcome = await gateway.invoke(_invocation("test.read"), ToolPolicyFacts())

    assert outcome.status == "error"
    assert outcome.error is not None
    assert outcome.error.code == "handler_error"
    assert outcome.error.error_type == "handler"
    assert "boom" in outcome.error.message


@pytest.mark.asyncio
async def test_handler_exception_redacts_credentials_from_error_and_events():
    async def boom(request: StrictInput) -> StrictOutput:
        raise RuntimeError(
            "request failed with Bearer raw-secret-token at "
            "https://example.test/run?api_key=raw-query-secret"
        )

    registry = _build_registry(make_definition(kind=ToolKind.READ, handler=boom))
    sink: list = []
    gateway = ToolGateway(registry, sink.append)

    outcome = await gateway.invoke(_invocation("test.read"), ToolPolicyFacts())

    assert outcome.status == "error"
    assert outcome.error is not None
    serialized = outcome.model_dump_json()
    assert "raw-secret-token" not in serialized
    assert "raw-query-secret" not in serialized
    assert "[REDACTED]" in outcome.error.message
    assert all("raw-secret" not in event.model_dump_json() for event in sink)


@pytest.mark.asyncio
async def test_handler_missing_fails_closed():
    # Definition with handler=None and no injected override.
    registry = _build_registry(make_definition(kind=ToolKind.READ, handler=None))
    gateway = ToolGateway(registry, lambda _event: None)

    outcome = await gateway.invoke(_invocation("test.read"), ToolPolicyFacts())

    assert outcome.status == "error"
    assert outcome.error is not None
    assert outcome.error.code == "handler_missing"


@pytest.mark.asyncio
async def test_injected_handler_override_is_used():
    calls = {"override": 0}

    async def override_handler(request: StrictInput) -> StrictOutput:
        calls["override"] += 1
        return StrictOutput(content="overridden")

    registry = _build_registry(make_definition(name="test.read", kind=ToolKind.READ, handler=None))
    gateway = ToolGateway(registry, lambda _event: None, handlers={"test.read": override_handler})

    outcome = await gateway.invoke(_invocation("test.read"), ToolPolicyFacts())

    assert outcome.status == "success"
    assert calls["override"] == 1
    assert outcome.result is not None
    assert outcome.result.output == {"content": "overridden"}


@pytest.mark.asyncio
async def test_cancellation_emits_failed_and_reraises():
    async def cancelling(request: StrictInput) -> StrictOutput:
        raise asyncio.CancelledError()

    registry = _build_registry(make_definition(kind=ToolKind.READ, handler=cancelling))
    sink: list = []
    gateway = ToolGateway(registry, sink.append)

    with pytest.raises(asyncio.CancelledError):
        await gateway.invoke(_invocation("test.read"), ToolPolicyFacts())

    assert [event.event_type for event in sink] == ["tool.started", "tool.failed"]
    assert sink[-1].payload["reason_code"] == "cancelled"


# --- idempotency + redaction --------------------------------------------------


@pytest.mark.asyncio
async def test_terminal_outcome_is_idempotent():
    calls = {"handler": 0}

    async def counting(request: StrictInput) -> StrictOutput:
        calls["handler"] += 1
        return StrictOutput(content=request.path)

    registry = _build_registry(make_definition(kind=ToolKind.READ, handler=counting))
    sink: list = []
    gateway = ToolGateway(registry, sink.append)
    invocation = _invocation("test.read", invocation_id="repeat-1")

    first = await gateway.invoke(invocation, ToolPolicyFacts())
    second = await gateway.invoke(invocation, ToolPolicyFacts())

    assert first is second
    assert calls["handler"] == 1
    # Second invoke must not re-emit events.
    assert len(sink) == 2


@pytest.mark.asyncio
async def test_terminal_cache_evicts_oldest_entries():
    calls = {"handler": 0}

    async def counting(request: StrictInput) -> StrictOutput:
        calls["handler"] += 1
        return StrictOutput(content=request.path)

    registry = _build_registry(make_definition(kind=ToolKind.READ, handler=counting))
    gateway = ToolGateway(registry, lambda _event: None, terminal_cache_max=2)

    first = await gateway.invoke(
        _invocation("test.read", invocation_id="inv-a"), ToolPolicyFacts()
    )
    second = await gateway.invoke(
        _invocation("test.read", invocation_id="inv-b"), ToolPolicyFacts()
    )
    third = await gateway.invoke(
        _invocation("test.read", invocation_id="inv-c"), ToolPolicyFacts()
    )

    assert calls["handler"] == 3
    assert "inv-a" not in gateway._terminals
    assert set(gateway._terminals) == {"inv-b", "inv-c"}

    # Oldest was evicted: replaying inv-a re-runs the handler.
    replayed = await gateway.invoke(
        _invocation("test.read", invocation_id="inv-a"), ToolPolicyFacts()
    )
    assert calls["handler"] == 4
    assert replayed is not first
    # Recent ids remain cached.
    assert (
        await gateway.invoke(_invocation("test.read", invocation_id="inv-c"), ToolPolicyFacts())
        is third
    )
    assert second.invocation_id == "inv-b"


def test_terminal_cache_max_must_be_positive():
    registry = _build_registry(make_definition())
    with pytest.raises(ValueError, match="terminal_cache_max"):
        ToolGateway(registry, lambda _event: None, terminal_cache_max=0)


@pytest.mark.asyncio
async def test_events_and_result_redact_secrets():
    async def secret_handler(request: StrictInput) -> StrictOutputWithSecret:
        return StrictOutputWithSecret(content=request.path, api_key="sk-super-secret")

    registry = _build_registry(
        make_definition(kind=ToolKind.READ, handler=secret_handler, output_model=StrictOutputWithSecret)
    )
    sink: list = []
    gateway = ToolGateway(registry, sink.append)

    outcome = await gateway.invoke(_invocation("test.read"), ToolPolicyFacts())

    assert outcome.status == "success"
    assert outcome.result is not None
    assert outcome.result.output == {"content": "README.md", "api_key": "[REDACTED]"}
    # No event payload carries the raw secret.
    for event in sink:
        assert "sk-super-secret" not in event.model_dump_json()


def test_outcome_model_is_frozen_and_strict():
    outcome = ToolGatewayOutcome(
        invocation_id="x",
        canonical_name="test.read",
        decision="allow",
        status="success",
    )
    assert outcome.model_config.get("frozen") is True
    with pytest.raises(ValidationError):
        outcome.status = "denied"  # type: ignore[misc]
