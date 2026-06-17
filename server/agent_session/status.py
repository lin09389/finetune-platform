from __future__ import annotations

from typing import Literal


AgentSessionStatus = Literal[
    "idle",
    "running",
    "waiting_permission",
    "waiting_approval",
    "verifying",
    "repairing",
    "needs_manual_review",
    "interrupted",
    "completed",
    "failed",
]
AgentAsyncTaskStatus = Literal["pending", "running", "completed", "failed", "cancelled"]

SESSION_LIFECYCLE: tuple[AgentSessionStatus, ...] = (
    "idle",
    "running",
    "waiting_permission",
    "waiting_approval",
    "completed",
    "failed",
    "interrupted",
    "needs_manual_review",
)
ACTIVE_SESSION_STATUSES: frozenset[AgentSessionStatus] = frozenset(
    {"running", "verifying", "repairing", "waiting_approval", "waiting_permission"}
)
WAITING_SESSION_STATUSES: frozenset[AgentSessionStatus] = frozenset({"waiting_approval", "waiting_permission"})
TERMINAL_SESSION_STATUSES: frozenset[AgentSessionStatus] = frozenset(
    {"completed", "failed", "interrupted", "needs_manual_review"}
)
FAILED_SESSION_STATUSES: frozenset[AgentSessionStatus] = frozenset(
    {"failed", "interrupted", "needs_manual_review"}
)

ASYNC_SUBTASK_STATUSES: frozenset[AgentAsyncTaskStatus] = frozenset(
    {"pending", "running", "completed", "failed", "cancelled"}
)
ASYNC_SUBTASK_TERMINAL_STATUSES: frozenset[AgentAsyncTaskStatus] = frozenset(
    {"completed", "failed", "cancelled"}
)
