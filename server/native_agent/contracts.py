"""Transport-neutral, bounded JSON envelopes for Native Agent Loop v2."""

from __future__ import annotations

import json
import math
from datetime import datetime
from typing import Annotated, Any, Literal, TypeAlias
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, field_validator, model_validator

from .errors import ErrorPayload

SCHEMA_VERSION = 2
MAX_PAYLOAD_BYTES = 64 * 1024
MAX_ENVELOPE_BYTES = 128 * 1024
MAX_PAYLOAD_DEPTH = 12
MAX_COLLECTION_ITEMS = 256
MAX_PAYLOAD_KEY_CHARS = 128


def _validate_json_value(value: object, *, depth: int = 0) -> None:
    if depth > MAX_PAYLOAD_DEPTH:
        raise ValueError("payload nesting exceeds the safe depth")
    if value is None or isinstance(value, str | bool | int):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("payload floats must be finite")
        return
    if isinstance(value, list):
        if len(value) > MAX_COLLECTION_ITEMS:
            raise ValueError("payload list exceeds the item limit")
        for item in value:
            _validate_json_value(item, depth=depth + 1)
        return
    if isinstance(value, dict):
        if len(value) > MAX_COLLECTION_ITEMS:
            raise ValueError("payload object exceeds the item limit")
        for key, item in value.items():
            if not isinstance(key, str) or not key or len(key) > MAX_PAYLOAD_KEY_CHARS:
                raise ValueError("payload object keys must be bounded non-empty strings")
            _validate_json_value(item, depth=depth + 1)
        return
    raise ValueError(f"payload value type is not JSON-safe: {type(value).__name__}")


def _validate_payload(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("payload must be a JSON object")
    _validate_json_value(value)
    encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")
    if len(encoded) > MAX_PAYLOAD_BYTES:
        raise ValueError(f"payload exceeds {MAX_PAYLOAD_BYTES} bytes")
    return value


class _Envelope(BaseModel):
    """Fields shared by every v2 frame, independent of WebSocket/FastAPI."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    version: Literal[SCHEMA_VERSION]
    id: UUID
    session_id: UUID
    sequence: int | None = Field(default=None, ge=0)
    turn_id: UUID | None = None
    command_id: UUID | None = None
    causation_id: UUID | None = None
    timestamp: datetime
    payload: dict[str, Any]

    @field_validator("timestamp")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("timestamp must be RFC3339 with an explicit timezone")
        return value

    @field_validator("payload")
    @classmethod
    def require_safe_payload(cls, value: object) -> dict[str, Any]:
        return _validate_payload(value)

    def to_json(self) -> str:
        """Serialize a strict, compact JSON frame with no null optional fields."""

        return self.model_dump_json(exclude_none=True)


class CommandEnvelope(_Envelope):
    type: Literal["command"]
    sequence: None = None
    command_id: UUID

    @model_validator(mode="after")
    def require_known_command(self) -> CommandEnvelope:
        # Import locally to keep this low-level module acyclic at import time.
        from .commands import parse_command

        parse_command(self.payload)
        return self


class EventEnvelope(_Envelope):
    type: Literal["event"]
    sequence: int = Field(ge=1)


class AckPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: Literal["accepted", "completed", "duplicate", "conflict"]


class AckEnvelope(_Envelope):
    type: Literal["ack"]
    command_id: UUID

    @model_validator(mode="after")
    def require_ack_payload(self) -> AckEnvelope:
        AckPayload.model_validate(self.payload)
        return self


class SnapshotPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    projection_version: Literal[SCHEMA_VERSION]
    state: dict[str, Any]


class ErrorEnvelope(_Envelope):
    type: Literal["error"]

    @model_validator(mode="after")
    def require_error_payload(self) -> ErrorEnvelope:
        ErrorPayload.model_validate(self.payload)
        return self


class SnapshotEnvelope(_Envelope):
    type: Literal["snapshot"]
    sequence: int = Field(ge=0)

    @model_validator(mode="after")
    def require_snapshot_payload(self) -> SnapshotEnvelope:
        SnapshotPayload.model_validate(self.payload)
        return self


class PingPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    nonce: UUID


class PingEnvelope(_Envelope):
    type: Literal["ping"]

    @model_validator(mode="after")
    def require_ping_payload(self) -> PingEnvelope:
        PingPayload.model_validate(self.payload)
        return self


class PongEnvelope(_Envelope):
    type: Literal["pong"]

    @model_validator(mode="after")
    def require_pong_payload(self) -> PongEnvelope:
        PingPayload.model_validate(self.payload)
        return self


EnvelopeFrame: TypeAlias = Annotated[
    CommandEnvelope
    | EventEnvelope
    | AckEnvelope
    | ErrorEnvelope
    | SnapshotEnvelope
    | PingEnvelope
    | PongEnvelope,
    Field(discriminator="type"),
]

_ENVELOPE_ADAPTER = TypeAdapter(EnvelopeFrame)


def _from_json(raw: str | bytes | bytearray) -> EnvelopeFrame:
    raw_bytes = raw.encode("utf-8") if isinstance(raw, str) else bytes(raw)
    if len(raw_bytes) > MAX_ENVELOPE_BYTES:
        raise ValueError(f"envelope exceeds {MAX_ENVELOPE_BYTES} bytes")
    try:
        decoded = json.loads(raw_bytes)
    except (TypeError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("envelope must be valid UTF-8 JSON") from exc
    return _ENVELOPE_ADAPTER.validate_python(decoded)


class Envelope:
    """Namespace for parsing the discriminated v2 envelope union."""

    @staticmethod
    def from_json(raw: str | bytes | bytearray) -> EnvelopeFrame:
        return _from_json(raw)


class SequenceCursor:
    """Strict committed-event cursor used by replay and live projections."""

    def __init__(self, session_id: UUID, after_sequence: int = 0) -> None:
        if after_sequence < 0:
            raise ValueError("after_sequence must be non-negative")
        self.session_id = session_id
        self.sequence = after_sequence

    def advance(self, event: EventEnvelope) -> int:
        if event.session_id != self.session_id:
            raise ValueError("event belongs to a different session")
        expected = self.sequence + 1
        if event.sequence != expected:
            raise ValueError(f"expected sequence {expected}, received {event.sequence}")
        self.sequence = event.sequence
        return self.sequence
