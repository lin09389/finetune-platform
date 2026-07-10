"""Pydantic DTOs forming the stable agent-training tool contract."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

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
