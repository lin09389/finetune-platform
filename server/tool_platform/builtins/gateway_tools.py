"""Wrap the Tool Gateway as DeepAgents-visible StructuredTools.

In controlled mode the model is presented with the platform's managed tools
(namespaced canonical definitions exposed under their DeepAgents-compatible
aliases).  Each tool's coroutine routes through :class:`ToolGateway.invoke`,
so policy / approval / dispatch / redaction / canonical events apply before
any side effect.  The legacy DeepAgents built-ins are excluded separately
(see :func:`tool_platform.adapters.deepagents.controlled_mode_exclusion_set`).

This adapter is the controlled-mode execution seam.  It does not persist
approval state and does not alter the DeepAgents model loop beyond
substituting the tool surface.

Invocation identity:
    The LLM-assigned ``tool_call_id`` is the canonical idempotency key for a
    tool invocation.  When the model is resumed after a HITL interrupt, the
    DeepAgents loop replays the *same* ``ToolCall`` — including the same
    ``tool_call_id`` — so the Tool Gateway can match the replay against the
    terminal cache entry it produced earlier.  Using a fresh random UUID here
    would defeat that match, re-triggering an ``ask`` decision forever and
    turning every approval into an infinite loop.
"""

from __future__ import annotations

import inspect
import json
import uuid
from typing import Any

from langchain_core.tools import StructuredTool

from ..adapters.deepagents import DeepAgentsEnforcementCapability
from ..gateway import ToolGateway
from ..models import ToolInvocation, thaw_json_object
from ..policy import ToolPolicyFacts
from ..registry import ToolProjectionContext, ToolRegistry


class _ToolCallIdAwareStructuredTool(StructuredTool):
    """StructuredTool that surfaces the LLM-assigned ``tool_call_id`` to its coroutine.

    The base implementation only forwards ``tool_call_id`` to the coroutine
    when ``args_schema`` declares a field typed with ``InjectedToolCallId``
    (and raises if it is missing).  This adapter reuses the strict platform
    ``args_schema`` untouched and threads the id through afterwards: the id
    is the idempotency key shared between a tool call and its interrupt/resume
    replay, and we cannot afford to lose it from the coroutine's view.
    """

    def _to_args_and_kwargs(
        self, tool_input: Any, tool_call_id: str | None
    ) -> tuple[tuple[Any, ...], dict[str, Any]]:
        args, kwargs = super()._to_args_and_kwargs(tool_input, tool_call_id)
        coroutine = self.coroutine
        if coroutine is not None and "tool_call_id" in inspect.signature(coroutine).parameters:
            kwargs["tool_call_id"] = tool_call_id
        return args, kwargs


def _projection_context(agent_id: str) -> ToolProjectionContext:
    return ToolProjectionContext(
        agent_id=agent_id,
        runtime_kind="agent_session",
        enabled_capabilities=frozenset({"deepagents"}),
    )


def build_gateway_tool_structures(
    *,
    gateway: ToolGateway,
    registry: ToolRegistry,
    facts: ToolPolicyFacts,
    agent_id: str,
    enforcement_capability: DeepAgentsEnforcementCapability = DeepAgentsEnforcementCapability.HIDDEN_AND_ENFORCED,
    allowed_tool_names: frozenset[str] | None = None,
) -> list[Any]:
    """Return DeepAgents ``StructuredTool`` wrappers for every visible platform tool.

    Each tool is exposed under its DeepAgents-compatible alias (e.g.
    ``read_file``) so the model-facing surface is seamless.  Invocations are
    routed through ``gateway.invoke`` with the session's policy facts.

    ``allowed_tool_names``:
    - ``None``: no phase filter (all registry-visible tools).
    - empty frozenset: expose no gateway tools (fail-closed phase surface).
    - non-empty: keep tools whose canonical name or DeepAgents alias is listed.

    The coroutine accepts the LLM-assigned ``tool_call_id`` (forwarded by
    :class:`_ToolCallIdAwareStructuredTool`) so that an interrupt/resume replay
    hits the same gateway ``invocation_id`` as the original tool call.  Without
    this contract the gateway could never match a replay against its terminal
    cache and every approval-bound tool would loop forever.
    """
    visible = registry.project(_projection_context(agent_id))
    if allowed_tool_names is not None and not allowed_tool_names:
        return []
    tools: list[Any] = []

    for definition in visible:
        if allowed_tool_names is not None and not _definition_allowed(definition, allowed_tool_names):
            continue
        meta = definition.meta
        # The StructuredTool is exposed under its namespaced canonical name
        # (e.g. ``workspace.read_file``), NOT its DeepAgents-compatible alias.
        # The controlled-mode exclusion middleware hides the legacy built-ins by
        # their bare alias names (``read_file``); if the platform tool shared
        # that alias, the exclusion middleware would hide it too (it filters all
        # tools by name). Using the canonical name keeps the platform tool
        # model-visible while the legacy built-in is excluded.
        tool_name = meta.canonical_name
        input_model = definition.input_model
        canonical_name = meta.canonical_name

        def _make_handler(name: str) -> Any:
            async def handler(
                *, tool_call_id: str | None = None, **kwargs: Any
            ) -> str:
                invocation_id = tool_call_id or f"gw_{uuid.uuid4().hex}"
                invocation = ToolInvocation(
                    invocation_id=invocation_id,
                    tool_name=name,
                    arguments=kwargs,
                )
                outcome = await gateway.invoke(
                    invocation, facts, enforcement_capability=enforcement_capability
                )
                if outcome.status == "success" and outcome.result is not None:
                    return json.dumps(thaw_json_object(outcome.result.output), ensure_ascii=False)
                error_code = outcome.error.code if outcome.error else outcome.status
                return json.dumps(
                    {"error": error_code, "status": outcome.status},
                    ensure_ascii=False,
                )

            return handler

        tools.append(
            _ToolCallIdAwareStructuredTool.from_function(
                coroutine=_make_handler(canonical_name),
                name=tool_name,
                description=meta.description,
                args_schema=input_model,
            )
        )

    return tools


def _definition_allowed(definition: Any, allowed_tool_names: frozenset[str]) -> bool:
    meta = definition.meta
    if meta.canonical_name in allowed_tool_names:
        return True
    return any(str(alias) in allowed_tool_names for alias in definition.aliases)


__all__ = ["build_gateway_tool_structures"]
