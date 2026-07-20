"""Canonical, in-process Tool Gateway.

Pipeline::

    idempotency -> resolve -> enforcement -> explicit availability
        -> strict input validation -> policy(allow/ask/deny) -> approval adapter
        -> in-process dispatch(timeout/cancel) -> output validation
        -> redaction -> canonical events

Constraints honored:

* Availability is always fetched explicitly from the registry (never ``None``).
* An ``UNSUPPORTED`` enforcement capability denies before policy runs, so a
  policy ``allow`` can never override it (Task 5 invariant).
* Only platform custom tools are routed; DeepAgents built-ins whose
  enforcement is ``UNSUPPORTED`` (``execute``/``task``/``write_todos``) are
  rejected here.
* No worker process, no database table, no second event log, no second
  approval engine.  Terminal outcomes are cached in-process for idempotent
  replay; canonical events are emitted through an injected sink that wraps the
  existing ``AgentSessionRepository.add_event``.
* ``deepagents_runtime.py`` and ``runtime_factory.py`` are never imported.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections import OrderedDict
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, ValidationError

from .adapters.deepagents import DeepAgentsEnforcementCapability
from .handlers import (
    ApprovalAdapter,
    HandlerMissingError,
    HandlerTimeoutError,
    SuspensionApprovalAdapter,
    ToolEventSink,
    dispatch_handler,
)
from .models import ToolError, ToolEvent, ToolInvocation, ToolResult, redact_json, thaw_json_object
from .policy import ToolPolicyFacts, evaluate_tool_policy
from .taxonomy import ToolRisk

logger = logging.getLogger(__name__)


class ToolGatewayOutcome(BaseModel):
    """The terminal result of one gateway invocation."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    invocation_id: str
    canonical_name: str
    decision: Literal["allow", "ask", "deny"]
    status: Literal["success", "needs_approval", "denied", "error", "cancelled"]
    result: ToolResult | None = None
    error: ToolError | None = None
    events: tuple[ToolEvent, ...] = ()


class ToolGateway:
    """Routes a canonical tool invocation through the full control pipeline."""

    def __init__(
        self,
        registry: Any,
        event_sink: ToolEventSink,
        *,
        handlers: Mapping[str, Any] | None = None,
        approval_adapter: ApprovalAdapter | None = None,
        availability_timeout: float = 5.0,
        handler_timeout: float | None = None,
        terminal_cache_max: int = 1024,
    ) -> None:
        if terminal_cache_max < 1:
            raise ValueError("terminal_cache_max must be >= 1")
        self._registry = registry
        self._sink = event_sink
        self._handlers: dict[str, Any] = dict(handlers) if handlers else {}
        self._approval: ApprovalAdapter = approval_adapter or SuspensionApprovalAdapter()
        self._availability_timeout = availability_timeout
        self._handler_timeout = handler_timeout
        self._terminal_cache_max = terminal_cache_max
        # Bounded FIFO cache of terminal outcomes for in-process idempotency.
        self._terminals: OrderedDict[str, ToolGatewayOutcome] = OrderedDict()

    async def invoke(
        self,
        invocation: ToolInvocation,
        facts: ToolPolicyFacts,
        *,
        enforcement_capability: DeepAgentsEnforcementCapability = DeepAgentsEnforcementCapability.HIDDEN_AND_ENFORCED,
    ) -> ToolGatewayOutcome:
        invocation_id = invocation.invocation_id

        # FIFO lookup only: reads deliberately do not promote an entry, so the
        # cache evicts in the order outcomes were produced. Switching to LRU
        # would require ``move_to_end`` here, but corner cases are negligible
        # at the per-session replay scale (<1024 entries).
        cached = self._terminals.get(invocation_id)
        if cached is not None:
            return cached

        emitted: list[ToolEvent] = []
        sequence = 0

        def emit(event_type: str, payload: dict[str, Any]) -> None:
            nonlocal sequence
            event = ToolEvent(
                event_id=f"tev_{uuid.uuid4().hex}",
                invocation_id=invocation_id,
                sequence=sequence,
                attempt=1,
                event_type=event_type,
                occurred_at=datetime.now(UTC),
                payload=payload,
            )
            self._sink(event)
            emitted.append(event)
            sequence += 1

        def terminal(
            decision: Literal["allow", "ask", "deny"],
            status: Literal["success", "needs_approval", "denied", "error", "cancelled"],
            *,
            canonical_name: str,
            risk: ToolRisk,
            event_type: str,
            reason_code: str,
            error: ToolError | None = None,
            result: ToolResult | None = None,
            payload_extra: Mapping[str, Any] | None = None,
            cache: bool = True,
        ) -> ToolGatewayOutcome:
            payload: dict[str, Any] = {
                "canonical_name": canonical_name,
                "risk": risk.value,
                "reason_code": reason_code,
            }
            if error is not None:
                payload["error"] = error.model_dump(mode="json")
            if payload_extra:
                payload.update(payload_extra)
            emit(event_type, payload)
            outcome = ToolGatewayOutcome(
                invocation_id=invocation_id,
                canonical_name=canonical_name,
                decision=decision,
                status=status,
                result=result,
                error=error,
                events=tuple(emitted),
            )
            if cache:
                self._cache_terminal(invocation_id, outcome)
            return outcome

        # 1. resolve
        definition = self._registry.resolve(invocation.tool_name)
        if definition is None:
            canonical_name = invocation.tool_name
            emit("tool.started", {"tool_name": invocation.tool_name, "canonical_name": None})
            return terminal(
                "deny",
                "denied",
                canonical_name=canonical_name,
                risk=ToolRisk.CRITICAL,
                event_type="tool.failed",
                reason_code="unknown_tool",
                error=ToolError(
                    error_type="policy_denied",
                    code="unknown_tool",
                    message=f"tool {invocation.tool_name!r} is not registered",
                ),
            )

        meta = definition.meta
        canonical_name = meta.canonical_name
        risk = meta.risk
        emit("tool.started", {"tool_name": invocation.tool_name, "canonical_name": canonical_name})

        # 2. explicit availability from the registry (never None, never skipped)
        availability = await self._explicit_availability(invocation.tool_name, canonical_name)

        # 3. enforcement gate (before policy: allow can never override UNSUPPORTED)
        if enforcement_capability is DeepAgentsEnforcementCapability.UNSUPPORTED:
            return terminal(
                "deny",
                "denied",
                canonical_name=canonical_name,
                risk=risk,
                event_type="tool.failed",
                reason_code="unsupported_enforcement",
                error=ToolError(
                    error_type="policy_denied",
                    code="unsupported_enforcement",
                    message=f"tool {canonical_name!r} has no hard enforcement boundary",
                ),
                payload_extra={"enforcement": enforcement_capability.value},
            )

        # 4. strict input validation
        try:
            validated_input = definition.validate_input(thaw_json_object(invocation.arguments))
        except ValidationError:
            return terminal(
                "deny",
                "error",
                canonical_name=canonical_name,
                risk=risk,
                event_type="tool.failed",
                reason_code="input_validation",
                error=ToolError(
                    error_type="validation",
                    code="input_validation",
                    message=f"tool {canonical_name!r} rejected invalid input",
                ),
                payload_extra={"stage": "input_validation"},
            )

        # 5. policy
        policy_decision = evaluate_tool_policy(
            definition, facts, requested_name=invocation.tool_name, availability=availability
        )
        if policy_decision.decision == "deny":
            return terminal(
                "deny",
                "denied",
                canonical_name=canonical_name,
                risk=risk,
                event_type="tool.failed",
                reason_code=policy_decision.reason_code,
                error=ToolError(
                    error_type="policy_denied",
                    code=policy_decision.reason_code,
                    message=f"policy denied tool {canonical_name!r}: {policy_decision.reason_code}",
                ),
                payload_extra={"matched_rules": list(policy_decision.matched_rules)},
            )

        if policy_decision.decision == "ask":
            approval = self._approval.request_approval(invocation, policy_decision)
            if not approval.granted:
                emit(
                    "tool.needs_approval",
                    {
                        "canonical_name": canonical_name,
                        "risk": risk.value,
                        "reason_code": policy_decision.reason_code,
                        "matched_rules": list(policy_decision.matched_rules),
                    },
                )
                return ToolGatewayOutcome(
                    invocation_id=invocation_id,
                    canonical_name=canonical_name,
                    decision="ask",
                    status="needs_approval",
                    events=tuple(emitted),
                )
            # granted: fall through to dispatch (decision=allow).

        # 6. in-process dispatch
        effective_timeout = (
            self._handler_timeout
            if self._handler_timeout is not None
            else meta.timeout_seconds
        )
        handler_override = self._handlers.get(canonical_name)
        try:
            raw_output = await dispatch_handler(
                definition,
                validated_input,
                timeout_seconds=effective_timeout,
                handler=handler_override,
            )
        except asyncio.CancelledError:
            emit(
                "tool.failed",
                {
                    "canonical_name": canonical_name,
                    "risk": risk.value,
                    "reason_code": "cancelled",
                },
            )
            raise
        except HandlerTimeoutError:
            return terminal(
                "allow",
                "error",
                canonical_name=canonical_name,
                risk=risk,
                event_type="tool.failed",
                reason_code="handler_timeout",
                error=ToolError(
                    error_type="timeout",
                    code="handler_timeout",
                    message=f"tool {canonical_name!r} handler timed out",
                    retryable=True,
                ),
            )
        except HandlerMissingError:
            return terminal(
                "allow",
                "error",
                canonical_name=canonical_name,
                risk=risk,
                event_type="tool.failed",
                reason_code="handler_missing",
                error=ToolError(
                    error_type="handler",
                    code="handler_missing",
                    message=f"tool {canonical_name!r} has no in-process handler",
                ),
            )
        except Exception as exc:  # noqa: BLE001 - handler errors are canonical failures
            return terminal(
                "allow",
                "error",
                canonical_name=canonical_name,
                risk=risk,
                event_type="tool.failed",
                reason_code="handler",
                error=ToolError(
                    error_type="handler",
                    code="handler_error",
                    message=str(exc)[:1000] or "handler raised without a message",
                ),
            )

        # 7. output validation
        try:
            validated_output = definition.validate_output(raw_output)
        except ValidationError:
            return terminal(
                "allow",
                "error",
                canonical_name=canonical_name,
                risk=risk,
                event_type="tool.failed",
                reason_code="output_validation",
                error=ToolError(
                    error_type="validation",
                    code="output_validation",
                    message=f"tool {canonical_name!r} returned invalid output",
                ),
                payload_extra={"stage": "output_validation"},
            )

        # 8. redact + terminal success
        redacted_output = redact_json(validated_output.model_dump(mode="json"))
        result = ToolResult(invocation_id=invocation_id, status="success", output=redacted_output)
        return terminal(
            "allow",
            "success",
            canonical_name=canonical_name,
            risk=risk,
            event_type="tool.completed",
            reason_code="success",
            result=result,
            payload_extra={"result": result.model_dump(mode="json")},
        )

    async def _explicit_availability(self, tool_name: str, canonical_name: str):
        """Fetch availability explicitly from the registry; fail closed on error."""
        try:
            return await self._registry.check_availability(
                tool_name, timeout_seconds=self._availability_timeout
            )
        except Exception:  # noqa: BLE001 - fail closed without exposing probe details
            logger.error(
                "availability check failed for tool %s (canonical=%s)",
                tool_name,
                canonical_name,
            )
            from .models import ToolAvailability

            return ToolAvailability(
                canonical_name=canonical_name,
                available=False,
                reason_code="availability_check_failed",
            )

    def _cache_terminal(self, invocation_id: str, outcome: ToolGatewayOutcome) -> None:
        """Store a terminal outcome and evict the oldest entries when full."""
        self._terminals[invocation_id] = outcome
        self._terminals.move_to_end(invocation_id)
        while len(self._terminals) > self._terminal_cache_max:
            self._terminals.popitem(last=False)


__all__ = ["ToolGateway", "ToolGatewayOutcome"]
