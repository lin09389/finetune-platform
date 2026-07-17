"""Authoritative v2 event catalog and tolerant projection boundary."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Annotated, Literal, TypeAlias
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, model_validator

from .errors import ErrorPayload

MAX_EVENT_TEXT_CHARS = 16_384
MAX_SUMMARY_CHARS = 1_024
MAX_REFERENCE_COUNT = 32
SafeReference: TypeAlias = Annotated[
    str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
]
Sha256: TypeAlias = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]


class _Event(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class AssistantDeltaEvent(_Event):
    kind: Literal["assistant.delta"]
    delta: str = Field(min_length=1, max_length=MAX_EVENT_TEXT_CHARS)


class AssistantMessageEvent(_Event):
    kind: Literal["assistant.message"]
    message: str = Field(min_length=1, max_length=MAX_EVENT_TEXT_CHARS)


class SessionCreatedEvent(_Event):
    kind: Literal["session.created"]
    runtime_kind: Literal["native"]
    model_ref: SafeReference


class SessionStatusEvent(_Event):
    kind: Literal["session.status"]
    status: Literal["idle", "running", "waiting_approval", "waiting_permission", "cancelling", "recovering"]


class SessionPausedEvent(_Event):
    kind: Literal["session.paused"]
    reason: Literal["approval", "permission", "model_retry", "manual", "recovery"]
    summary: str = Field(min_length=1, max_length=MAX_SUMMARY_CHARS)


class SessionCancelledEvent(_Event):
    kind: Literal["session.cancelled"]
    summary: str = Field(min_length=1, max_length=MAX_SUMMARY_CHARS)


class TurnQueuedEvent(_Event):
    kind: Literal["turn.queued"]
    turn_id: UUID
    queue_position: int = Field(ge=0, le=127)


class TurnStartedEvent(_Event):
    kind: Literal["turn.started"]
    turn_id: UUID


class TurnCompletedEvent(_Event):
    kind: Literal["turn.completed"]
    turn_id: UUID
    summary: str = Field(min_length=1, max_length=MAX_SUMMARY_CHARS)


class TurnFailedEvent(_Event):
    kind: Literal["turn.failed"]
    turn_id: UUID
    error: ErrorPayload


class TurnCancelledEvent(_Event):
    kind: Literal["turn.cancelled"]
    turn_id: UUID
    summary: str = Field(min_length=1, max_length=MAX_SUMMARY_CHARS)


class SteeringRequestedEvent(_Event):
    kind: Literal["steering.requested"]
    steering_id: UUID
    turn_id: UUID
    instruction_ref: SafeReference
    summary: str = Field(min_length=1, max_length=MAX_SUMMARY_CHARS)


class SteeringDeferredEvent(_Event):
    kind: Literal["steering.deferred"]
    steering_id: UUID
    reason: Literal["tool_in_flight", "model_sampling"]


class SteeringAppliedEvent(_Event):
    kind: Literal["steering.applied"]
    steering_id: UUID
    turn_id: UUID


class SteeringRejectedEvent(_Event):
    kind: Literal["steering.rejected"]
    steering_id: UUID
    error: ErrorPayload


class QueueUpdatedEvent(_Event):
    kind: Literal["queue.updated"]
    queued_turn_ids: list[UUID] = Field(max_length=128)


class GoalStep(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    step_id: UUID
    title: str = Field(min_length=1, max_length=256)
    depends_on: list[UUID] = Field(max_length=32)
    state: Literal["pending", "active", "verified", "blocked", "failed"]


class GoalGraphPlannedEvent(_Event):
    kind: Literal["goal.graph_planned"]
    goal_graph_id: UUID
    revision: int = Field(ge=1)
    summary: str = Field(min_length=1, max_length=MAX_SUMMARY_CHARS)
    steps: list[GoalStep] = Field(min_length=1, max_length=128)


class GoalStepStateEvent(_Event):
    kind: Literal["goal.step_state"]
    goal_graph_id: UUID
    revision: int = Field(ge=1)
    step_id: UUID
    state: Literal["pending", "active", "verified", "blocked", "failed"]
    evidence_refs: list[SafeReference] = Field(default_factory=list, max_length=MAX_REFERENCE_COUNT)


class GoalReplannedEvent(_Event):
    kind: Literal["goal.replanned"]
    goal_graph_id: UUID
    from_revision: int = Field(ge=1)
    revision: int = Field(ge=2)
    reason: str = Field(min_length=1, max_length=MAX_SUMMARY_CHARS)
    summary: str = Field(min_length=1, max_length=MAX_SUMMARY_CHARS)

    @model_validator(mode="after")
    def require_later_revision(self) -> GoalReplannedEvent:
        if self.revision <= self.from_revision:
            raise ValueError("replanned revision must be greater than from_revision")
        return self


class GoalVerifiedEvent(_Event):
    kind: Literal["goal.verified"]
    goal_graph_id: UUID
    revision: int = Field(ge=1)
    outcome: Literal["passed", "revise", "blocked", "failed"]
    summary: str = Field(min_length=1, max_length=MAX_SUMMARY_CHARS)
    evidence_refs: list[SafeReference] = Field(default_factory=list, max_length=MAX_REFERENCE_COUNT)


class ModelUsageEvent(_Event):
    kind: Literal["model.usage"]
    usage_id: UUID
    turn_id: UUID
    role: Literal["planner", "implementer", "verifier", "strategist"]
    model_ref: SafeReference
    input_tokens: int = Field(ge=0, le=10_000_000)
    output_tokens: int = Field(ge=0, le=10_000_000)
    total_tokens: int = Field(ge=0, le=20_000_000)
    duration_ms: int = Field(ge=0, le=86_400_000)

    @model_validator(mode="after")
    def validate_total_tokens(self) -> ModelUsageEvent:
        if self.total_tokens != self.input_tokens + self.output_tokens:
            raise ValueError("total_tokens must equal input_tokens plus output_tokens")
        return self


class ToolRequestedEvent(_Event):
    kind: Literal["tool.requested"]
    tool_call_id: UUID
    tool_name: str = Field(pattern=r"^[a-z][a-z0-9_.-]{0,63}$")
    input_ref: SafeReference
    summary: str = Field(min_length=1, max_length=MAX_SUMMARY_CHARS)


class ToolStartedEvent(_Event):
    kind: Literal["tool.started"]
    tool_call_id: UUID


class ToolCompletedEvent(_Event):
    kind: Literal["tool.completed"]
    tool_call_id: UUID
    outcome: Literal["succeeded", "failed", "cancelled"]
    summary: str = Field(min_length=1, max_length=MAX_SUMMARY_CHARS)
    result_ref: SafeReference | None = None
    artifact_ids: list[SafeReference] = Field(default_factory=list, max_length=MAX_REFERENCE_COUNT)


class ApprovalRequestedEvent(_Event):
    kind: Literal["approval.requested"]
    interaction_id: UUID
    request_ref: SafeReference
    summary: str = Field(min_length=1, max_length=MAX_SUMMARY_CHARS)


class ApprovalResolvedEvent(_Event):
    kind: Literal["approval.resolved"]
    interaction_id: UUID
    decision: Literal["approve", "reject"]


class FileMutationRecordedEvent(_Event):
    kind: Literal["file.mutation_recorded"]
    mutation_id: UUID
    operation: Literal["write", "edit", "delete", "rename"]
    path_ref: SafeReference
    new_path_ref: SafeReference | None = None
    before_hash: Sha256 | None = None
    after_hash: Sha256 | None = None
    diff_ref: SafeReference | None = None
    content_bytes: int = Field(default=0, ge=0, le=2 * 1024 * 1024)

    @model_validator(mode="after")
    def validate_mutation_references(self) -> FileMutationRecordedEvent:
        if self.before_hash is None and self.after_hash is None:
            raise ValueError("file mutation requires a before_hash or after_hash")
        if self.operation == "rename" and self.new_path_ref is None:
            raise ValueError("rename mutation requires new_path_ref")
        return self


class VerificationRecordedEvent(_Event):
    kind: Literal["verification.recorded"]
    verification_id: UUID
    checker_ref: SafeReference
    outcome: Literal["passed", "failed", "blocked"]
    summary: str = Field(min_length=1, max_length=MAX_SUMMARY_CHARS)
    evidence_refs: list[SafeReference] = Field(default_factory=list, max_length=MAX_REFERENCE_COUNT)


class CompactionRecordedEvent(_Event):
    kind: Literal["compaction.recorded"]
    compaction_id: UUID
    from_sequence: int = Field(ge=1)
    through_sequence: int = Field(ge=1)
    summary_ref: SafeReference
    omitted_refs: list[SafeReference] = Field(default_factory=list, max_length=MAX_REFERENCE_COUNT)

    @model_validator(mode="after")
    def validate_compaction_range(self) -> CompactionRecordedEvent:
        if self.through_sequence < self.from_sequence:
            raise ValueError("through_sequence must not precede from_sequence")
        return self


class RewindRequestedEvent(_Event):
    kind: Literal["rewind.requested"]
    rewind_id: UUID
    target_sequence: int | None = Field(default=None, ge=0)
    checkpoint_id: UUID | None = None

    @model_validator(mode="after")
    def require_exactly_one_target(self) -> RewindRequestedEvent:
        if (self.target_sequence is None) == (self.checkpoint_id is None):
            raise ValueError("rewind requires exactly one target sequence or checkpoint_id")
        return self


class RewindCompletedEvent(_Event):
    kind: Literal["rewind.completed"]
    rewind_id: UUID
    new_branch_id: UUID
    restored_mutation_ids: list[UUID] = Field(max_length=128)


class RewindConflict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    mutation_id: UUID
    reason: Literal["external_change", "binary_file", "oversized_file", "symlink", "dependency_conflict"]


class RewindConflictEvent(_Event):
    kind: Literal["rewind.conflicted"]
    rewind_id: UUID
    conflicts: list[RewindConflict] = Field(min_length=1, max_length=128)


class SessionCompletedEvent(_Event):
    kind: Literal["session.completed"]
    summary: str = Field(min_length=1, max_length=MAX_SUMMARY_CHARS)


class SessionFailedEvent(_Event):
    kind: Literal["session.failed"]
    error: ErrorPayload


KnownEvent: TypeAlias = Annotated[
    AssistantDeltaEvent
    | AssistantMessageEvent
    | SessionCreatedEvent
    | SessionStatusEvent
    | SessionPausedEvent
    | SessionCancelledEvent
    | TurnQueuedEvent
    | TurnStartedEvent
    | TurnCompletedEvent
    | TurnFailedEvent
    | TurnCancelledEvent
    | SteeringRequestedEvent
    | SteeringDeferredEvent
    | SteeringAppliedEvent
    | SteeringRejectedEvent
    | QueueUpdatedEvent
    | GoalGraphPlannedEvent
    | GoalStepStateEvent
    | GoalReplannedEvent
    | GoalVerifiedEvent
    | ModelUsageEvent
    | ToolRequestedEvent
    | ToolStartedEvent
    | ToolCompletedEvent
    | ApprovalRequestedEvent
    | ApprovalResolvedEvent
    | FileMutationRecordedEvent
    | VerificationRecordedEvent
    | CompactionRecordedEvent
    | RewindRequestedEvent
    | RewindCompletedEvent
    | RewindConflictEvent
    | SessionCompletedEvent
    | SessionFailedEvent,
    Field(discriminator="kind"),
]

_EVENT_ADAPTER = TypeAdapter(KnownEvent)
KNOWN_EVENT_KINDS = frozenset(_EVENT_ADAPTER.json_schema()["discriminator"]["mapping"])


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
