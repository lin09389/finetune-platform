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
"""

from __future__ import annotations

import json
import uuid
from typing import Any

from ..adapters.deepagents import DeepAgentsEnforcementCapability
from ..gateway import ToolGateway
from ..models import ToolInvocation, thaw_json_object
from ..policy import ToolPolicyFacts
from ..registry import ToolProjectionContext, ToolRegistry


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
) -> list[Any]:
    """Return DeepAgents ``StructuredTool`` wrappers for every visible platform tool.

    Each tool is exposed under its DeepAgents-compatible alias (e.g.
    ``read_file``) so the model-facing surface is seamless.  Invocations are
    routed through ``gateway.invoke`` with the session's policy facts.
    """
    from langchain_core.tools import StructuredTool

    visible = registry.project(_projection_context(agent_id))
    tools: list[Any] = []

    for definition in visible:
        meta = definition.meta
        alias = definition.aliases[0] if definition.aliases else meta.canonical_name
        input_model = definition.input_model
        canonical_name = meta.canonical_name

        def _make_handler(name: str) -> Any:
            async def handler(**kwargs: Any) -> str:
                invocation = ToolInvocation(
                    invocation_id=f"gw_{uuid.uuid4().hex}",
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
            StructuredTool.from_function(
                coroutine=_make_handler(canonical_name),
                name=alias,
                description=meta.description,
                args_schema=input_model,
            )
        )

    return tools


__all__ = ["build_gateway_tool_structures"]
