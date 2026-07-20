"""Contract tests for canonical tool models.

Taxonomy is implemented by the paired Task 1 subtask.  These tests skip with
an explicit reason until its public enum module is available.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

pytest.importorskip("tool_platform.taxonomy", reason="depends on the Task 1 taxonomy public enums")

from tool_platform.models import (  # noqa: E402
    CanonicalToolMeta,
    ToolAvailability,
    ToolError,
    ToolEvent,
    ToolInvocation,
    ToolResult,
    freeze_json_object,
    jsonable,
)
from tool_platform.taxonomy import (  # noqa: E402
    ExecutionLocation,
    SideEffect,
    ToolKind,
    ToolRisk,
)


def tool_meta() -> CanonicalToolMeta:
    return CanonicalToolMeta(
        canonical_name="workspace.read_file",
        kind=ToolKind.READ,
        side_effects=frozenset({SideEffect.NONE}),
        risk=ToolRisk.LOW,
        execution_location=ExecutionLocation.CONTROL_PLANE,
        display_name="Read file",
        description="Read a file from the active workspace.",
    )


def test_models_share_the_canonical_top_level_taxonomy_identity() -> None:
    assert CanonicalToolMeta.model_fields["kind"].annotation is ToolKind


def test_schema_version_is_fixed_at_one_and_meta_is_read_only() -> None:
    assert tool_meta().schema_version == 1
    assert tool_meta().is_read_only is True
    with pytest.raises(ValidationError):
        CanonicalToolMeta.model_validate({**tool_meta().model_dump(), "schema_version": 2})


@pytest.mark.parametrize(
    ("factory", "unexpected"),
    [
        (tool_meta, {"unknown": "field"}),
        (lambda: ToolInvocation(invocation_id="call-1", tool_name="workspace.read_file"), {"unknown": "field"}),
        (lambda: ToolError(error_type="handler", code="handler_failed", message="failed"), {"unknown": "field"}),
        (
            lambda: ToolEvent(event_id="event-1", invocation_id="call-1", sequence=0, event_type="started", occurred_at=datetime.now(UTC)),
            {"unknown": "field"},
        ),
        (lambda: ToolAvailability(canonical_name="workspace.read_file", available=True), {"unknown": "field"}),
    ],
)
def test_unknown_fields_are_rejected(factory, unexpected) -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        factory().model_validate({**factory().model_dump(), **unexpected})


def test_ranges_and_result_state_are_validated() -> None:
    with pytest.raises(ValidationError):
        CanonicalToolMeta.model_validate({**tool_meta().model_dump(), "timeout_seconds": 0})
    with pytest.raises(ValidationError):
        ToolEvent(event_id="event-1", invocation_id="call-1", sequence=-1, event_type="started", occurred_at=datetime.now(UTC))
    with pytest.raises(ValidationError, match="require an error"):
        ToolResult(invocation_id="call-1", status="error")
    with pytest.raises(ValidationError, match="cancelled error type"):
        ToolResult(
            invocation_id="call-1",
            status="cancelled",
            error=ToolError(error_type="handler", code="failed", message="failed"),
        )


def test_models_are_immutable() -> None:
    invocation = ToolInvocation(
        invocation_id="call-1",
        tool_name="workspace.read_file",
        arguments={"nested": {"values": [1, 2]}},
    )
    with pytest.raises(ValidationError, match="frozen"):
        invocation.tool_name = "workspace.write_file"  # type: ignore[misc]
    with pytest.raises(TypeError):
        invocation.arguments["new"] = True  # type: ignore[index]
    nested = invocation.arguments["nested"]
    assert isinstance(nested, dict | Mapping)
    with pytest.raises(TypeError):
        nested["new"] = True  # type: ignore[index]


def test_json_round_trip_preserves_contracts() -> None:
    original = ToolResult(
        invocation_id="call-1",
        status="error",
        error=ToolError(
            error_type="transport",
            code="connection_refused",
            message="The remote service refused the connection.",
            diagnostic={"retry_after_seconds": 1},
            retryable=True,
        ),
    )
    assert ToolResult.model_validate_json(original.model_dump_json()) == original
    assert CanonicalToolMeta.model_validate_json(tool_meta().model_dump_json()) == tool_meta()


def test_jsonable_unfreezes_maps_tuples_and_set_likes() -> None:
    frozen = freeze_json_object({"nested": {"values": [1, 2]}, "flag": True})
    assert jsonable(frozen) == {"nested": {"values": [1, 2]}, "flag": True}
    assert jsonable(("a", "b")) == ["a", "b"]
    assert jsonable(["a", "b"]) == ["a", "b"]
    assert sorted(jsonable({"z", "a"})) == ["a", "z"]  # type: ignore[arg-type]
    assert sorted(jsonable(frozenset({"b", "a"}))) == ["a", "b"]  # type: ignore[arg-type]
    assert jsonable({"z", "a"}) == ["a", "z"]  # type: ignore[arg-type]
    assert jsonable(frozenset({"b", "a"})) == ["a", "b"]  # type: ignore[arg-type]
    assert jsonable("plain") == "plain"
    assert jsonable(3) == 3


@pytest.mark.parametrize(
    "error_type",
    ["transport", "validation", "policy_denied", "handler", "timeout", "cancelled", "worker_lost"],
)
def test_all_canonical_error_types_are_accepted(error_type: str) -> None:
    assert ToolError(error_type=error_type, code="stable_code", message="message").error_type == error_type


def test_sensitive_values_are_hidden_from_repr_and_diagnostics() -> None:
    invocation = ToolInvocation(
        invocation_id="call-1",
        tool_name="remote.call",
        arguments={"access_token": "top-secret"},
    )
    error = ToolError(
        error_type="transport",
        code="connection_refused",
        message="failed",
        diagnostic={"nested": {"api_key": "top-secret"}, "safe": "value"},
    )
    availability = ToolAvailability(
        canonical_name="remote.call", available=False, diagnostic={"password": "top-secret"}
    )

    assert "top-secret" not in repr(invocation)
    assert "top-secret" not in repr(error)
    assert error.model_dump()["diagnostic"] == {"nested": {"api_key": "[REDACTED]"}, "safe": "value"}
    assert availability.model_dump()["diagnostic"] == {"password": "[REDACTED]"}


def test_composable_effects_separate_data_mutation_from_network_access() -> None:
    web_meta = CanonicalToolMeta(
        canonical_name="web.fetch",
        kind=ToolKind.WEB_FETCH,
        side_effects=frozenset({SideEffect.NETWORK}),
        risk=ToolRisk.MEDIUM,
        execution_location=ExecutionLocation.EXTERNAL,
        display_name="Fetch URL",
        description="Fetch a public URL.",
    )
    assert web_meta.is_data_read_only is True
    with pytest.raises(ValidationError, match="none cannot be combined"):
        CanonicalToolMeta.model_validate(
            {
                **web_meta.model_dump(),
                "side_effects": frozenset({SideEffect.NONE, SideEffect.NETWORK}),
            }
        )


def test_diagnostic_dump_redacts_nested_url_bearer_and_json_secrets() -> None:
    invocation = ToolInvocation(
        invocation_id="call-1",
        tool_name="remote.call",
        arguments={
            "url": "https://example.test/path?token=secret&safe=yes",
            "header": "Bearer secret-token",
            "json": '{"nested":{"api_key":"secret"}}',
        },
    )
    public = invocation.diagnostic_dump()
    serialized = json.dumps(public)
    assert "secret-token" not in serialized
    assert '"secret"' not in serialized
    assert "%5BREDACTED%5D" in serialized


def test_redaction_covers_hyphenated_api_key_headers_and_query_parameters() -> None:
    invocation = ToolInvocation(
        invocation_id="call-1",
        tool_name="remote.call",
        arguments={
            "headers": {"X-API-Key": "header-secret"},
            "url": "https://example.test/path?api-key=query-secret",
        },
    )

    serialized = json.dumps(invocation.diagnostic_dump())
    assert "header-secret" not in serialized
    assert "query-secret" not in serialized


def test_event_payload_is_redacted_before_persistence_or_serialization() -> None:
    event = ToolEvent(
        event_id="event-1",
        invocation_id="call-1",
        sequence=0,
        event_type="progress",
        occurred_at=datetime.now(UTC),
        payload={"headers": {"x-api-key": "event-secret"}},
    )

    assert event.model_dump()["payload"] == {"headers": {"x-api-key": "[REDACTED]"}}
    assert "event-secret" not in event.model_dump_json()


def test_events_require_stable_identity_attempt_and_aware_utc_time() -> None:
    event = ToolEvent(
        event_id="event-1",
        invocation_id="call-1",
        sequence=0,
        attempt=2,
        event_type="started",
        occurred_at=datetime.now(UTC),
    )
    assert event.attempt == 2
    assert event.occurred_at.tzinfo is UTC
    with pytest.raises(ValidationError, match="timezone-aware"):
        ToolEvent(
            event_id="event-2",
            invocation_id="call-1",
            sequence=1,
            event_type="progress",
            occurred_at=datetime.now(),
        )
