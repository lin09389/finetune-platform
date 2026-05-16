"""LangGraph tool wrappers for the workflow runtime.

Phase 1 keeps these wrappers lightweight and structured so the graph can move
onto LangGraph-native tool calls without losing the semantics of the legacy
executor.
"""

from __future__ import annotations

import json
from typing import Any

from langchain_core.tools import tool

from ..tool_models import AgentToolRequest
from ..tools import AgentToolExecutor


def _payload(tool_name: str, **kwargs: Any) -> str:
    return json.dumps({"tool": tool_name, "arguments": kwargs}, ensure_ascii=False)


def parse_tool_payload(content: str) -> AgentToolRequest:
    parsed = json.loads(content)
    if not isinstance(parsed, dict):
        raise ValueError("tool payload must be a JSON object")
    tool_name = parsed.get("tool")
    arguments = parsed.get("arguments") or {}
    if not isinstance(tool_name, str):
        raise ValueError("tool payload missing tool name")
    if not isinstance(arguments, dict):
        raise ValueError("tool payload arguments must be an object")
    return AgentToolRequest(tool=tool_name, arguments=arguments)


def execute_legacy_tool(
    executor: AgentToolExecutor,
    payload: str,
    *,
    workflow_id: str,
    step_id: str | None,
    agent_id: str,
    project: dict[str, Any],
) -> str:
    request = parse_tool_payload(payload)
    result = executor.execute(
        request,
        workflow_id=workflow_id,
        step_id=step_id,
        agent_id=agent_id,
        project=project,
    )
    return result.model_dump_json(ensure_ascii=False)


