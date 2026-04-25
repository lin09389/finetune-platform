"""Models for the Digital Team MVP."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class ProjectStatus(str, Enum):
    DRAFT = "draft"
    PLANNING = "planning"
    AWAITING_APPROVAL = "awaiting_approval"
    IMPLEMENTING = "implementing"
    REVIEWING = "reviewing"
    COMPLETED = "completed"
    FAILED = "failed"


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    AWAITING_APPROVAL = "awaiting_approval"
    APPROVED = "approved"
    COMPLETED = "completed"
    FAILED = "failed"
    NEEDS_MANUAL_REVIEW = "needs_manual_review"


class AgentOutput(BaseModel):
    summary: str = ""
    tasks: list[dict[str, Any]] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    artifacts: list[dict[str, Any]] = Field(default_factory=list)
    next_action: str = ""
    requires_approval: bool = True
    raw_output: str | None = None
    needs_manual_review: bool = False


class TeamTemplate(BaseModel):
    id: str
    name: str
    description: str
    roles: list[dict[str, Any]]
    default_provider: str = "minimax"
    default_approval_mode: str = "manual"


class ProjectCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=120)
    goal: str = Field(..., min_length=1)
    template_id: str = "software_dev_team"
    project_path: str | None = None
    provider: str = "minimax"
    model: str | None = None
    approval_mode: str = "manual"


class ProjectResponse(BaseModel):
    id: str
    team_id: str
    title: str
    goal: str
    template_id: str
    project_path: str | None = None
    provider: str
    model: str | None = None
    approval_mode: str
    status: str
    current_stage: str | None = None
    created_at: str
    updated_at: str
    completed_at: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    tasks: list[dict[str, Any]] = Field(default_factory=list)


class TaskResponse(BaseModel):
    id: str
    project_id: str
    role: str
    title: str
    description: str
    status: str
    requires_approval: bool
    output: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    created_at: str
    updated_at: str
    completed_at: str | None = None


class ApprovalRequest(BaseModel):
    approved: bool = True
    comment: str | None = None

