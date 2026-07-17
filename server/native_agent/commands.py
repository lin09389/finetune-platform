"""Strict command catalog for Native Agent Loop v2."""

from __future__ import annotations

from typing import Annotated, Literal, TypeAlias
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from .errors import UnknownCommandError

MAX_MESSAGE_CHARS = 16_384


class _Command(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class PromptCommand(_Command):
    kind: Literal["session.prompt"]
    message: str = Field(min_length=1, max_length=MAX_MESSAGE_CHARS)


class FollowUpCommand(_Command):
    kind: Literal["session.follow_up"]
    message: str = Field(min_length=1, max_length=MAX_MESSAGE_CHARS)


class SteerCommand(_Command):
    kind: Literal["session.steer"]
    instruction: str = Field(min_length=1, max_length=MAX_MESSAGE_CHARS)


class SendNowCommand(_Command):
    kind: Literal["session.send_now"]
    message: str = Field(min_length=1, max_length=MAX_MESSAGE_CHARS)


class CancelTurnCommand(_Command):
    kind: Literal["session.cancel_turn"]


class ApprovalResolveCommand(_Command):
    kind: Literal["approval.resolve"]
    interaction_id: UUID
    decision: Literal["approve", "reject"]


class RewindRequestCommand(_Command):
    kind: Literal["rewind.request"]
    branch_id: UUID | None = None


class SubscribeCommand(_Command):
    kind: Literal["session.subscribe"]
    after_sequence: int = Field(ge=0)
    projection_version: int = Field(default=2, ge=1, le=2)


Command: TypeAlias = Annotated[
    PromptCommand
    | FollowUpCommand
    | SteerCommand
    | SendNowCommand
    | CancelTurnCommand
    | ApprovalResolveCommand
    | RewindRequestCommand
    | SubscribeCommand,
    Field(discriminator="kind"),
]

_COMMAND_ADAPTER = TypeAdapter(Command)
COMMAND_KINDS = frozenset(
    {
        "session.prompt",
        "session.follow_up",
        "session.steer",
        "session.send_now",
        "session.cancel_turn",
        "approval.resolve",
        "rewind.request",
        "session.subscribe",
    }
)


def parse_command(payload: object) -> Command:
    """Parse a known command, rejecting forward command kinds by design."""

    if not isinstance(payload, dict) or not isinstance(payload.get("kind"), str):
        raise UnknownCommandError("command payload requires a known string kind")
    if payload["kind"] not in COMMAND_KINDS:
        raise UnknownCommandError(f"unknown command kind: {payload['kind']}")
    return _COMMAND_ADAPTER.validate_python(payload)
