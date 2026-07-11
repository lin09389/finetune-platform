"""Pydantic DTOs forming the stable agent-training tool contract."""

from __future__ import annotations

from datetime import datetime, timezone
import math
import re
from typing import Annotated, Any, Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, field_validator, model_validator

from training_engine.schemas import TrainingConfigInput


class TrainingProposalRequest(BaseModel):
    """A read-only request to diagnose a potential training run."""

    model_config = ConfigDict(protected_namespaces=())

    config: TrainingConfigInput
    use_queue: bool = False
    priority: Literal["urgent", "high", "normal", "low"] = "normal"


class TrainingProposal(BaseModel):
    """Stored diagnostic result that must be explicitly approved before submission."""

    model_config = ConfigDict(protected_namespaces=())

    proposal_id: str
    config: TrainingConfigInput
    owner_id: str | None = None
    session_id: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    use_queue: bool = False
    priority: Literal["urgent", "high", "normal", "low"] = "normal"
    status: Literal["ready", "warning", "blocked"]
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)
    required_vram_gb: float | None = None


class ApprovedTrainingAction(BaseModel):
    """Explicit human/tool approval for a previously issued proposal."""

    proposal_id: str
    approved: bool = False


class TrainingSubmission(BaseModel):
    """The task created after an approved proposal reaches the orchestrator."""

    proposal_id: str
    task_id: str
    status: str


class TrainingRunSummary(BaseModel):
    """Read-only projection of an authoritative training record."""

    task_id: str
    status: str
    model_id: str
    dataset_id: str
    method: str
    task_goal: str | None = None
    started_at: str
    completed_at: str | None = None
    output_path: str
    adapter_path: str | None = None
    checkpoint_path: str | None = None
    final_loss: float | None = None
    elapsed_time: float | None = None
    phase: str | None = None
    step: int | None = Field(default=None, ge=0)
    total_steps: int | None = Field(default=None, gt=0)
    epoch: float | None = Field(default=None, ge=0)
    loss: float | None = Field(default=None, ge=0)
    eta: float | None = Field(default=None, ge=0)
    updated_at: str | None = None
    artifact_available: bool | None = None

    @field_validator("final_loss", "elapsed_time", "epoch", "loss", "eta")
    @classmethod
    def _finite_non_negative_metric(cls, value: float | None) -> float | None:
        if value is not None and (not math.isfinite(value) or value < 0):
            raise ValueError("Training metrics must be finite and non-negative")
        return value


_ABSOLUTE_PATH_RE = re.compile(r"(?<!\w)(?:[A-Za-z]:[\\/]|/)[^\s,;\]\)}]+")
_SECRET_ASSIGNMENT_RE = re.compile(
    r"\b((?:api[_-]?key|access[_-]?token|token|secret|password|passwd|authorization)\s*[=:]\s*)([^\s,;]+)",
    re.IGNORECASE,
)
_BEARER_TOKEN_RE = re.compile(r"\b(Bearer\s+)[^\s,;]+", re.IGNORECASE)


def _safe_display_value(value: Any) -> Any:
    """Redact strings that are unsafe to persist in a timeline activity."""

    if isinstance(value, str):
        value = _ABSOLUTE_PATH_RE.sub("[redacted path]", value)
        value = _SECRET_ASSIGNMENT_RE.sub(r"\1[redacted secret]", value)
        return _BEARER_TOKEN_RE.sub(r"\1[redacted secret]", value)
    if isinstance(value, list):
        return [_safe_display_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _safe_display_value(item) for key, item in value.items()}
    return value


class _TrainingActivityBase(BaseModel):
    """Allowlisted, display-safe data persisted with an Agent timeline part."""

    model_config = ConfigDict(extra="forbid")

    kind: str
    source_tool: str
    status: str = Field(min_length=1)
    summary: str = Field(min_length=1)

    @model_validator(mode="before")
    @classmethod
    def _redact_display_values(cls, value: Any) -> Any:
        return _safe_display_value(value)


class TrainingProposalActivity(_TrainingActivityBase):
    kind: Literal["proposal"] = "proposal"
    source_tool: Literal["propose_training"] = "propose_training"
    proposal_id: str = Field(min_length=1)
    model_id: str = Field(min_length=1)
    dataset_id: str = Field(min_length=1)
    method: str = Field(min_length=1)
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)
    required_vram_gb: float | None = None


class TrainingSubmissionActivity(_TrainingActivityBase):
    kind: Literal["submission"] = "submission"
    source_tool: Literal["submit_training"] = "submit_training"
    proposal_id: str = Field(min_length=1)
    task_id: str = Field(min_length=1)


class TrainingRunSummaryActivity(_TrainingActivityBase):
    kind: Literal["run_summary"] = "run_summary"
    source_tool: Literal["get_training_summary"] = "get_training_summary"
    task_id: str = Field(min_length=1)
    model_id: str = Field(min_length=1)
    dataset_id: str = Field(min_length=1)
    method: str = Field(min_length=1)
    task_goal: str | None = None
    started_at: str = Field(min_length=1)
    completed_at: str | None = None
    final_loss: float | None = None
    elapsed_time: float | None = None
    phase: str | None = None
    step: int | None = Field(default=None, ge=0)
    total_steps: int | None = Field(default=None, gt=0)
    epoch: float | None = Field(default=None, ge=0)
    loss: float | None = Field(default=None, ge=0)
    eta: float | None = Field(default=None, ge=0)
    updated_at: str | None = None
    artifact_available: bool | None = None


TrainingActivity: TypeAlias = Annotated[
    TrainingProposalActivity | TrainingSubmissionActivity | TrainingRunSummaryActivity,
    Field(discriminator="kind"),
]
_TRAINING_ACTIVITY_ADAPTER = TypeAdapter(TrainingActivity)


def _proposal_summary(status: str) -> str:
    return {
        "ready": "Training proposal is ready for approval.",
        "warning": "Training proposal needs review.",
        "blocked": "Training proposal is blocked.",
    }.get(status, "Training proposal updated.")


def _submission_summary(status: str) -> str:
    return {
        "queued": "Training task queued.",
        "duplicate": "Existing training task reused.",
    }.get(status, "Training submission updated.")


def _run_summary(status: str) -> str:
    return {
        "queued": "Training task is queued.",
        "running": "Training run is in progress.",
        "completed": "Training run completed.",
        "failed": "Training run failed.",
        "cancelled": "Training run was cancelled.",
    }.get(status, "Training run updated.")


def training_activity_for(
    value: TrainingProposal | TrainingSubmission | TrainingRunSummary,
) -> TrainingActivity:
    """Serialize authoritative training state into the persisted timeline contract."""

    if isinstance(value, TrainingProposal):
        return TrainingProposalActivity(
            proposal_id=value.proposal_id,
            status=value.status,
            summary=_proposal_summary(value.status),
            model_id=value.config.model_id,
            dataset_id=value.config.dataset_id,
            method=value.config.method,
            blockers=value.blockers,
            warnings=value.warnings,
            suggestions=value.suggestions,
            required_vram_gb=value.required_vram_gb,
        )
    if isinstance(value, TrainingSubmission):
        return TrainingSubmissionActivity(
            proposal_id=value.proposal_id,
            task_id=value.task_id,
            status=value.status,
            summary=_submission_summary(value.status),
        )
    return TrainingRunSummaryActivity(
        task_id=value.task_id,
        status=value.status,
        summary=_run_summary(value.status),
        model_id=value.model_id,
        dataset_id=value.dataset_id,
        method=value.method,
        task_goal=value.task_goal,
        started_at=value.started_at,
        completed_at=value.completed_at,
        final_loss=value.final_loss,
        elapsed_time=value.elapsed_time,
        phase=value.phase,
        step=value.step,
        total_steps=value.total_steps,
        epoch=value.epoch,
        loss=value.loss,
        eta=value.eta,
        updated_at=value.updated_at,
        artifact_available=value.artifact_available,
    )


def training_activity_from_tool_result(tool_name: str, value: Any) -> TrainingActivity | None:
    """Recover a strict activity only from a successful, known training tool result."""

    if not isinstance(value, dict):
        return None
    try:
        if tool_name == "propose_training":
            return TrainingProposalActivity.model_validate(
                {"kind": "proposal", "source_tool": tool_name, "summary": _proposal_summary(str(value.get("status") or "")), **value}
            )
        if tool_name == "submit_training":
            return TrainingSubmissionActivity.model_validate(
                {"kind": "submission", "source_tool": tool_name, "summary": _submission_summary(str(value.get("status") or "")), **value}
            )
        if tool_name == "get_training_summary":
            return TrainingRunSummaryActivity.model_validate(
                {"kind": "run_summary", "source_tool": tool_name, "summary": _run_summary(str(value.get("status") or "")), **value}
            )
    except (TypeError, ValueError):
        return None
    return None


def parse_training_activity(value: Any) -> TrainingActivity | None:
    """Validate a persisted projection while preserving generic fallback on old data."""

    try:
        return _TRAINING_ACTIVITY_ADAPTER.validate_python(value)
    except (TypeError, ValueError):
        return None
