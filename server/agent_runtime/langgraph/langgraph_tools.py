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


@tool
def list_files(pattern: str = "**/*") -> str:
    """List files in the project directory."""
    return _payload("list_files", pattern=pattern)


@tool
def search_code(query: str, max_results: int = 20) -> str:
    """Search for code matches in the project."""
    return _payload("search_code", query=query, max_results=max_results)


@tool
def read_file(path: str) -> str:
    """Read a file from the project directory."""
    return _payload("read_file", path=path)


@tool
def inspect_project() -> str:
    """Inspect the current project structure."""
    return _payload("inspect_project")


@tool
def detect_project_commands() -> str:
    """Detect useful local project commands."""
    return _payload("detect_project_commands")


@tool
def get_git_status() -> str:
    """Get the current git status."""
    return _payload("get_git_status")


@tool
def get_git_diff(path: str | None = None) -> str:
    """Get the current git diff."""
    return _payload("get_git_diff", path=path)


@tool
def list_changed_files() -> str:
    """List changed files in the repository."""
    return _payload("list_changed_files")


@tool
def propose_patch(files: list[dict[str, Any]], description: str = "") -> str:
    """Propose a patch for approval."""
    return _payload("propose_patch", files=files, description=description)


@tool
def propose_command(command: list[str], description: str = "") -> str:
    """Propose a command for approval."""
    return _payload("propose_command", command=command, description=description)


@tool
def finalize(summary: str) -> str:
    """Signal that the current step is complete."""
    return _payload("finalize", summary=summary)
