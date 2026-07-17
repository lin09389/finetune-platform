from __future__ import annotations

import json
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from native_agent.commands import CancelTurnCommand, PromptCommand, parse_command
from native_agent.contracts import (
    MAX_PAYLOAD_BYTES,
    AckEnvelope,
    CommandEnvelope,
    Envelope,
    EventEnvelope,
    SequenceCursor,
    SnapshotEnvelope,
)
from native_agent.errors import ErrorPayload, UnknownCommandError, redact_error_message
from native_agent.events import AssistantDeltaEvent, UnknownEvent, project_event
from pydantic import ValidationError


def _base_envelope(**overrides: object) -> dict[str, object]:
    envelope: dict[str, object] = {
        "version": 2,
        "type": "command",
        "id": str(uuid4()),
        "session_id": str(uuid4()),
        "command_id": str(uuid4()),
        "timestamp": datetime.now(UTC).isoformat(),
        "payload": {"kind": "session.prompt", "message": "Implement the change."},
    }
    envelope.update(overrides)
    return envelope


def test_command_envelope_serializes_to_strict_v2_json() -> None:
    envelope = CommandEnvelope.model_validate(_base_envelope())

    encoded = envelope.to_json()
    decoded = json.loads(encoded)

    assert decoded["version"] == 2
    assert decoded["type"] == "command"
    assert "sequence" not in decoded
    assert Envelope.from_json(encoded) == envelope


@pytest.mark.parametrize(
    "field,value",
    [
        ("version", 1),
        ("id", "not-a-uuid"),
        ("session_id", "not-a-uuid"),
        ("timestamp", "2026-07-17T12:00:00"),
    ],
)
def test_envelope_requires_v2_identifiers_and_timezone(field: str, value: object) -> None:
    payload = _base_envelope(**{field: value})

    with pytest.raises(ValidationError):
        CommandEnvelope.model_validate(payload)


def test_command_rejects_server_sequence_and_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        CommandEnvelope.model_validate(_base_envelope(sequence=1))

    with pytest.raises(ValidationError):
        CommandEnvelope.model_validate(_base_envelope(unexpected=True))


def test_event_requires_positive_committed_sequence() -> None:
    payload = _base_envelope(
        type="event",
        command_id=None,
        sequence=4,
        payload={"kind": "assistant.delta", "delta": "Working"},
    )

    event = EventEnvelope.model_validate(payload)

    assert event.sequence == 4
    with pytest.raises(ValidationError):
        EventEnvelope.model_validate({**payload, "sequence": 0})


def test_snapshot_allows_initial_cursor_and_ack_requires_command_id() -> None:
    snapshot_payload = _base_envelope(
        type="snapshot",
        command_id=None,
        sequence=0,
        payload={"projection_version": 2, "state": {}},
    )
    assert SnapshotEnvelope.model_validate(snapshot_payload).sequence == 0

    ack_payload = _base_envelope(type="ack", payload={"status": "accepted"})
    assert AckEnvelope.model_validate(ack_payload).command_id is not None
    with pytest.raises(ValidationError):
        AckEnvelope.model_validate({**ack_payload, "command_id": None})


def test_non_command_frames_have_strict_domain_payloads() -> None:
    ack_payload = _base_envelope(type="ack", payload={"status": "duplicate"})
    snapshot_payload = _base_envelope(
        type="snapshot",
        command_id=None,
        sequence=0,
        payload={"projection_version": 2, "state": {}},
    )

    assert AckEnvelope.model_validate(ack_payload).payload["status"] == "duplicate"
    assert SnapshotEnvelope.model_validate(snapshot_payload).payload["projection_version"] == 2
    with pytest.raises(ValidationError):
        AckEnvelope.model_validate({**ack_payload, "payload": {"status": "not-a-status"}})
    with pytest.raises(ValidationError):
        SnapshotEnvelope.model_validate(
            {**snapshot_payload, "payload": {"projection_version": 1, "state": {}}}
        )


def test_payload_is_bounded_json_and_disallows_non_finite_values() -> None:
    too_large = "x" * (MAX_PAYLOAD_BYTES + 1)

    with pytest.raises(ValidationError, match="payload"):
        CommandEnvelope.model_validate(_base_envelope(payload={"kind": "session.prompt", "message": too_large}))

    with pytest.raises(ValidationError, match="finite"):
        CommandEnvelope.model_validate(
            _base_envelope(payload={"kind": "session.prompt", "message": "ok", "score": float("nan")})
        )


def test_commands_are_discriminated_and_unknown_kinds_are_rejected() -> None:
    command = parse_command({"kind": "session.cancel_turn"})

    assert isinstance(command, CancelTurnCommand)
    assert parse_command({"kind": "session.prompt", "message": "hello"}) == PromptCommand(
        kind="session.prompt", message="hello"
    )
    with pytest.raises(UnknownCommandError):
        parse_command({"kind": "session.erase_history"})


def test_known_events_are_strict_but_unknown_events_are_projection_safe() -> None:
    known = project_event({"kind": "assistant.delta", "delta": "partial"})
    unknown = project_event({"kind": "future.event", "detail": {"safe": True}})

    assert isinstance(known, AssistantDeltaEvent)
    assert isinstance(unknown, UnknownEvent)
    assert unknown.kind == "future.event"
    assert unknown.payload == {"kind": "future.event", "detail": {"safe": True}}


def test_sequence_cursor_rejects_duplicate_gap_and_cross_session_events() -> None:
    session_id = uuid4()
    cursor = SequenceCursor(session_id=session_id)

    first = EventEnvelope.model_validate(
        _base_envelope(
            type="event",
            session_id=str(session_id),
            command_id=None,
            sequence=1,
            payload={"kind": "assistant.delta", "delta": "one"},
        )
    )
    cursor.advance(first)

    with pytest.raises(ValueError, match="expected sequence 2"):
        cursor.advance(first)

    with pytest.raises(ValueError, match="expected sequence 2"):
        cursor.advance(first.model_copy(update={"sequence": 3}))

    with pytest.raises(ValueError, match="session"):
        cursor.advance(first.model_copy(update={"session_id": uuid4(), "sequence": 2}))


def test_error_payload_redacts_paths_and_secret_values() -> None:
    summary = redact_error_message(
        "Failed at C:\\Users\\student\\project\\secret.txt with api_key=super-secret-value"
    )
    error = ErrorPayload(code="internal_error", message=summary)

    assert "C:\\Users" not in error.message
    assert "super-secret-value" not in error.message
    assert "[path]" in error.message
    assert "[redacted]" in error.message
