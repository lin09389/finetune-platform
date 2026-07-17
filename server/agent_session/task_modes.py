"""Temporary availability policy for Agent task modes during the Native migration."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


BUILD_TASK_MODE = "build"
MIGRATING_TASK_MODES = frozenset({"train", "hybrid"})
# The Native migration keeps ordinary training APIs available, but temporarily
# removes every legacy Agent training tool from all Agent modes.
LEGACY_AGENT_TRAINING_TOOLS_AVAILABLE = False


class AgentCapabilityMigratingError(ValueError):
    """Raised when a legacy Agent mode is unavailable during migration."""

    failure_kind = "capability_migrating"
    next_action = "use_build_agent"

    def __init__(self, task_mode: str) -> None:
        self.task_mode = task_mode
        super().__init__(
            f"Agent {task_mode.title()} mode is temporarily unavailable while it migrates to the Native Agent Loop. "
            "Use Build for Agent work; ordinary training APIs and jobs remain available."
        )


def require_available_agent_task_mode(task_mode: str | None) -> None:
    """Permit Build (and legacy unspecified sessions), reject migrating Agent modes."""
    normalized = str(task_mode or "").strip().lower()
    if normalized in MIGRATING_TASK_MODES:
        raise AgentCapabilityMigratingError(normalized)


def require_available_agent_session_mode(session: Mapping[str, Any]) -> None:
    """Read the persisted mode so legacy sessions cannot launch new Agent work."""
    metadata = session.get("metadata")
    metadata = metadata if isinstance(metadata, Mapping) else {}
    require_available_agent_task_mode(metadata.get("task_mode"))


def legacy_agent_training_tools_available(task_mode: str | None) -> bool:
    """Return whether a legacy Agent session may expose training tools.

    This is deliberately false for Build as well as Train/Hybrid. Build remains
    the only launchable Agent mode, but its native migration does not retain
    the legacy training-tool surface.
    """
    _ = task_mode
    return LEGACY_AGENT_TRAINING_TOOLS_AVAILABLE
