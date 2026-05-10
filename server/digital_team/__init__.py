"""Compatibility layer for legacy digital_team imports.

The runtime was migrated to agent_runtime, but several modules and tests
still import the older package path. Keep these shims minimal and
deliberately thin so the new runtime remains the source of truth.
"""

from .models import AgentOutput, TaskStatus
from .prompts import ceo_prompt, developer_prompt, reviewer_prompt
from .repository import DigitalTeamRepository

__all__ = [
    "AgentOutput",
    "TaskStatus",
    "ceo_prompt",
    "developer_prompt",
    "reviewer_prompt",
    "DigitalTeamRepository",
]
