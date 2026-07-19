"""Immutable, wire-safe contracts for the canonical tool platform.

The taxonomy deliberately lives in :mod:`tool_platform.taxonomy`; this
module consumes its public enums and does not redefine their semantics.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from datetime import UTC, datetime
from types import MappingProxyType
from typing import Annotated, Literal
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    field_serializer,
    field_validator,
    model_validator,
)

from .taxonomy import ExecutionLocation, SideEffect, ToolKind, ToolRisk

_SENSITIVE_KEY_PARTS = ("authorization", "credential", "password", "secret", "token", "api_key", "apikey")
_BEARER_PATTERN = re.compile(r"(?i)(bearer\s+)[^\s,;]+")
_INLINE_SECRET_PATTERN = re.compile(
    r"(?i)(\b(?:authorization|credential|password|secret|token|api[_-]?key|apikey)=)[^&#\s,;]+"
)


def _freeze_json(value: JsonValue) -> JsonValue:
    if isinstance(value, Mapping):
        return MappingProxyType({key: _freeze_json(item) for key, item in value.items()})  # type: ignore[return-value]
    if isinstance(value, list):
        return tuple(_freeze_json(item) for item in value)  # type: ignore[return-value]
    return value


def freeze_json_object(value: Mapping[str, JsonValue]) -> Mapping[str, JsonValue]:
    return _freeze_json(dict(value))  # type: ignore[return-value]


def thaw_json_object(value: JsonValue) -> JsonValue:
    """Recursively convert frozen JSON (MappingProxyType/tuple) back to mutable dict/list.

    Strict Pydantic models reject ``MappingProxyType`` inputs, so callers that
    validate a frozen :class:`ToolInvocation.arguments` payload thaw it first.
    """
    return _thaw_json(value)


def _thaw_json(value: JsonValue) -> JsonValue:
    if isinstance(value, Mapping):
        return {key: _thaw_json(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw_json(item) for item in value]
    return value


FrozenJsonObject = Annotated[Mapping[str, JsonValue], AfterValidator(freeze_json_object)]


def _is_sensitive_key(key: object) -> bool:
    normalized = str(key).lower().replace("-", "_")
    return any(part in normalized for part in _SENSITIVE_KEY_PARTS)


def redact_json(value: JsonValue) -> JsonValue:
    """Return recursively redacted JSON suitable for persistence or wire payloads."""
    if isinstance(value, Mapping):
        return {
            key: "[REDACTED]" if _is_sensitive_key(key) else redact_json(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact_json(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact_json(item) for item in value)
    if isinstance(value, str):
        redacted = _BEARER_PATTERN.sub(r"\1[REDACTED]", value)
        redacted = _INLINE_SECRET_PATTERN.sub(r"\1[REDACTED]", redacted)
        try:
            parsed = urlsplit(redacted)
            if parsed.scheme and parsed.netloc and parsed.query:
                query = [
                    (key, "[REDACTED]" if _is_sensitive_key(key) else item)
                    for key, item in parse_qsl(parsed.query, keep_blank_values=True)
                ]
                redacted = urlunsplit(parsed._replace(query=urlencode(query)))
        except ValueError:
            pass
        if redacted[:1] in {"{", "["}:
            try:
                return json.dumps(redact_json(json.loads(redacted)), separators=(",", ":"))
            except (json.JSONDecodeError, TypeError):
                pass
        return redacted
    return value


class _CanonicalModel(BaseModel):
    """Base configuration shared by all canonical, externally visible models."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True, validate_default=True)

    def diagnostic_dump(self) -> dict[str, JsonValue]:
        """Return a recursively redacted payload for logs, events, and persistence."""

        return redact_json(self.model_dump(mode="json"))  # type: ignore[return-value]


class CanonicalToolMeta(_CanonicalModel):
    schema_version: Literal[1] = 1
    canonical_name: Annotated[str, Field(min_length=1, max_length=200)]
    kind: ToolKind
    side_effects: frozenset[SideEffect]
    risk: ToolRisk
    execution_location: ExecutionLocation
    display_name: Annotated[str, Field(min_length=1, max_length=200)]
    description: Annotated[str, Field(min_length=1, max_length=10_000)]
    tags: tuple[Annotated[str, Field(min_length=1, max_length=100)], ...] = ()
    timeout_seconds: int = Field(default=30, ge=1, le=3600)
    idempotent: bool = False
    cacheable: bool = False

    @field_validator("side_effects")
    @classmethod
    def validate_side_effects(cls, value: frozenset[SideEffect]) -> frozenset[SideEffect]:
        if not value:
            raise ValueError("at least one side effect classification is required")
        if SideEffect.NONE in value and len(value) != 1:
            raise ValueError("none cannot be combined with another side effect")
        return value

    @property
    def is_data_read_only(self) -> bool:
        mutating = {
            SideEffect.WORKSPACE_WRITE,
            SideEffect.EXTERNAL_WRITE,
            SideEffect.DESTRUCTIVE,
        }
        return self.side_effects.isdisjoint(mutating)

    @property
    def is_read_only(self) -> bool:
        """Compatibility alias for data read-only semantics."""

        return self.is_data_read_only


class ToolInvocation(_CanonicalModel):
    schema_version: Literal[1] = 1
    invocation_id: Annotated[str, Field(min_length=1, max_length=200)]
    tool_name: Annotated[str, Field(min_length=1, max_length=200)]
    arguments: FrozenJsonObject = Field(default_factory=dict, repr=False)
    session_id: Annotated[str, Field(min_length=1, max_length=200)] | None = None
    user_id: Annotated[str, Field(min_length=1, max_length=200)] | None = None
    idempotency_key: Annotated[str, Field(min_length=1, max_length=200)] | None = None
    requested_at: datetime | None = None

    @field_serializer("arguments")
    def serialize_arguments(self, value: FrozenJsonObject) -> JsonValue:
        return _thaw_json(value)  # type: ignore[arg-type]


ToolErrorType = Literal[
    "transport",
    "validation",
    "policy_denied",
    "handler",
    "timeout",
    "cancelled",
    "worker_lost",
]


class ToolError(_CanonicalModel):
    schema_version: Literal[1] = 1
    error_type: ToolErrorType
    code: Annotated[str, Field(min_length=1, max_length=200)]
    message: Annotated[str, Field(min_length=1, max_length=10_000)]
    diagnostic: FrozenJsonObject | None = Field(default=None, repr=False)
    retryable: bool = False
    retry_after_seconds: float | None = Field(default=None, ge=0)
    origin: ExecutionLocation | None = None

    @field_validator("message")
    @classmethod
    def redact_message(cls, value: str) -> str:
        """Keep exception-derived error text safe for API responses and events."""

        redacted = redact_json(value)
        return redacted if isinstance(redacted, str) else value

    @field_validator("diagnostic")
    @classmethod
    def redact_diagnostic(cls, value: FrozenJsonObject | None) -> FrozenJsonObject | None:
        return freeze_json_object(redact_json(value)) if value is not None else None  # type: ignore[arg-type]

    @field_serializer("diagnostic")
    def serialize_diagnostic(self, value: FrozenJsonObject | None) -> JsonValue:
        return redact_json(value) if value is not None else None  # type: ignore[return-value]


class ToolResult(_CanonicalModel):
    schema_version: Literal[1] = 1
    invocation_id: Annotated[str, Field(min_length=1, max_length=200)]
    status: Literal["success", "error", "cancelled"]
    output: FrozenJsonObject | None = Field(default=None, repr=False)
    error: ToolError | None = None

    @field_serializer("output")
    def serialize_output(self, value: FrozenJsonObject | None) -> JsonValue:
        return _thaw_json(value) if value is not None else None  # type: ignore[arg-type]

    @model_validator(mode="after")
    def validate_terminal_payload(self) -> ToolResult:
        if self.status == "success" and self.error is not None:
            raise ValueError("successful tool results cannot contain an error")
        if self.status != "success" and self.error is None:
            raise ValueError("non-successful tool results require an error")
        if self.status == "cancelled" and self.error is not None and self.error.error_type != "cancelled":
            raise ValueError("cancelled tool results require a cancelled error type")
        return self


class ToolEvent(_CanonicalModel):
    schema_version: Literal[1] = 1
    event_id: Annotated[str, Field(min_length=1, max_length=200)]
    invocation_id: Annotated[str, Field(min_length=1, max_length=200)]
    sequence: int = Field(ge=0)
    attempt: int = Field(default=1, ge=1)
    event_type: Annotated[str, Field(min_length=1, max_length=100)]
    occurred_at: datetime
    payload: FrozenJsonObject = Field(default_factory=dict, repr=False)

    @field_validator("payload")
    @classmethod
    def redact_payload(cls, value: FrozenJsonObject) -> FrozenJsonObject:
        return freeze_json_object(redact_json(value))  # type: ignore[arg-type]

    @field_serializer("payload")
    def serialize_payload(self, value: FrozenJsonObject) -> JsonValue:
        return _thaw_json(redact_json(value))  # type: ignore[arg-type]

    @field_validator("occurred_at")
    @classmethod
    def require_utc_timestamp(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("occurred_at must be timezone-aware")
        return value.astimezone(UTC)


class ToolAvailability(_CanonicalModel):
    schema_version: Literal[1] = 1
    canonical_name: Annotated[str, Field(min_length=1, max_length=200)]
    available: bool
    reason_code: Annotated[str, Field(min_length=1, max_length=200)] | None = None
    diagnostic: FrozenJsonObject | None = Field(default=None, repr=False)

    @field_validator("diagnostic")
    @classmethod
    def redact_diagnostic(cls, value: FrozenJsonObject | None) -> FrozenJsonObject | None:
        return freeze_json_object(redact_json(value)) if value is not None else None  # type: ignore[arg-type]

    @field_serializer("diagnostic")
    def serialize_diagnostic(self, value: FrozenJsonObject | None) -> JsonValue:
        return redact_json(value) if value is not None else None  # type: ignore[return-value]
