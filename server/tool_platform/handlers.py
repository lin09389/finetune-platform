"""In-process handler dispatch and Tool Gateway seams.

The gateway dispatches handlers in-process only: there is no worker process,
no database table, and no second approval engine.  The approval adapter is a
seam consulted when the policy returns ``ask``; the default
:class:`SuspensionApprovalAdapter` never grants, so the gateway suspends
(emits ``needs_approval`` and does not execute).  An injected adapter may
grant to exercise the dispatch path under an ``ask`` decision.  Approval
persistence stays owned by the existing DeepAgents/session HITL integration.
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol

from .definition import ToolDefinition
from .models import ToolEvent, ToolInvocation
from .policy import ToolPolicyDecision


class ToolEventSink(Protocol):
    """Synchronous receiver for canonical tool events.

    Wraps ``AgentSessionRepository.add_event`` (+ notify) when projected
    through :class:`~agent_session.deepagents_events.DeepAgentsEventMapper`.
    """

    def __call__(self, event: ToolEvent) -> None: ...


@dataclass(frozen=True, slots=True)
class ApprovalOutcome:
    """Result of consulting the approval adapter for an ``ask`` decision."""

    granted: bool


class ApprovalAdapter(Protocol):
    """Seam consulted when policy returns ``ask``.

    Must not persist approval state; persistence is owned by the existing
    DeepAgents/session HITL integration.  Returning ``granted=False`` suspends
    the invocation (no execution); ``granted=True`` proceeds to dispatch.
    """

    def request_approval(
        self,
        invocation: ToolInvocation,
        policy_decision: ToolPolicyDecision,
    ) -> ApprovalOutcome: ...


class SuspensionApprovalAdapter:
    """Default adapter: ``ask`` always suspends (no execution, no persistence)."""

    def request_approval(
        self,
        invocation: ToolInvocation,
        policy_decision: ToolPolicyDecision,
    ) -> ApprovalOutcome:
        return ApprovalOutcome(granted=False)


class HandlerMissingError(Exception):
    """A tool definition has no handler and no override was provided."""

    def __init__(self, name: str) -> None:
        self.name = name
        super().__init__(f"tool {name!r} has no in-process handler")


class HandlerTimeoutError(Exception):
    """An in-process handler exceeded its bounded timeout."""

    def __init__(self, name: str) -> None:
        self.name = name
        super().__init__(f"tool {name!r} handler timed out")


async def dispatch_handler(
    definition: ToolDefinition,
    request: Any,
    *,
    timeout_seconds: float | None,
    handler: Any = None,
) -> Any:
    """Invoke a tool handler in-process under a bounded timeout.

    ``handler`` overrides ``definition.handler`` when supplied (test seam).
    ``handler is None`` (after override resolution) raises
    :class:`HandlerMissingError`.  ``TimeoutError`` is normalized to
    :class:`HandlerTimeoutError`; ``asyncio.CancelledError`` propagates so the
    caller can record a cancelled terminal event before re-raising.
    """
    effective = handler if handler is not None else definition.handler
    if effective is None:
        raise HandlerMissingError(definition.meta.canonical_name)
    if timeout_seconds is None:
        return await effective(request)
    try:
        return await asyncio.wait_for(effective(request), timeout=timeout_seconds)
    except TimeoutError as exc:
        raise HandlerTimeoutError(definition.meta.canonical_name) from exc


HandlerProvider = Mapping[str, Any]


__all__ = [
    "ApprovalAdapter",
    "ApprovalOutcome",
    "HandlerMissingError",
    "HandlerProvider",
    "HandlerTimeoutError",
    "SuspensionApprovalAdapter",
    "ToolEventSink",
    "dispatch_handler",
]
