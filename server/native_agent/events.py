"""Event catalog and tolerant client projection boundary for v2."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Annotated, Literal, TypeAlias
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from .errors import ErrorPayload

MAX_EVENT_TEXT_CHARS = 16_384


class _Event(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class AssistantDeltaEvent(_Event):
    kind: Literal["assistant.delta"]
    delta: str = Field(min_length=1, max_length=MAX_EVENT_TEXT_CHARS)


class AssistantMessageEvent(_Event):
    kind: Literal["assistant.message"]
    message: str = Field(min_length=1, max_length=MAX_EVENT_TEXT_CHARS)


class ToolRequestedEvent(_Event):
    kind: Literal["tool.requested"]
    tool_call_id: UUID
    tool_name: str = Field(pattern=r"^[a-z][a-z0-9_.-]{0,63}$")
    summary: str = Field(min_length=1, max_length=1_024)


class ToolCompletedEvent(_Event):
    kind: Literal["tool.completed"]
    tool_call_id: UUID
    outcome: Literal["succeeded", "failed", "cancelled"]
    summary: str = Field(min_length=1, max_length=1_024)
    artifact_ids: list[str] = Field(default_factory=list, max_length=32)


class ApprovalRequestedEvent(_Event):
    kind: Literal["approval.requested"]
    interaction_id: UUID
    summary: str = Field(min_length=1, max_length=1_024)


class ApprovalResolvedEvent(_Event):
    kind: Literal["approval.resolved"]
    interaction_id: UUID
    decision: Literal["approve", "reject"]


class QueueUpdatedEvent(_Event):
    kind: Literal["queue.updated"]
    queued_turn_ids: list[UUID] = Field(max_length=128)


class SessionCompletedEvent(_Event):
    kind: Literal["session.completed"]
    summary: str = Field(min_length=1, max_length=1_024)


class SessionFailedEvent(_Event):
    kind: Literal["session.failed"]
    error: ErrorPayload


KnownEvent: TypeAlias = Annotated[
    AssistantDeltaEvent
    | AssistantMessageEvent
    | ToolRequestedEvent
    | ToolCompletedEvent
    | ApprovalRequestedEvent
    | ApprovalResolvedEvent
    | QueueUpdatedEvent
    | SessionCompletedEvent
    | SessionFailedEvent,
    Field(discriminator="kind"),
]

_EVENT_ADAPTER = TypeAdapter(KnownEvent)
KNOWN_EVENT_KINDS = frozenset(
    {
        "assistant.delta",
        "assistant.message",
        "tool.requested",
        "tool.completed",
        "approval.requested",
        "approval.resolved",
        "queue.updated",
        "session.completed",
        "session.failed",
    }
)


@dataclass(frozen=True, slots=True)
class UnknownEvent:
    """Opaque forward-compatible event that only advances a projection cursor."""

    kind: str
    payload: Mapping[str, object]


def parse_event(payload: object) -> KnownEvent:
    """Parse a catalogued server event for producers and known projections."""

    return _EVENT_ADAPTER.validate_python(payload)


def project_event(payload: object) -> KnownEvent | UnknownEvent:
    """Project known events while safely preserving unknown future event kinds.

    Callers must still advance the committed envelope sequence for an
    ``UnknownEvent``; it deliberately has no mutation semantics.
    """

    if not isinstance(payload, dict) or not isinstance(payload.get("kind"), str):
        raise ValueError("event payload requires a string kind")
    if payload["kind"] not in KNOWN_EVENT_KINDS:
        return UnknownEvent(kind=payload["kind"], payload=dict(payload))
    return parse_event(payload)
