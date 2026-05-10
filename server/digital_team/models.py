from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


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
    requires_approval: bool = False
    needs_manual_review: bool = False
    raw_output: str = ""
