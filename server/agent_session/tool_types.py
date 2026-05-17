"""Shared dataclasses for the agent_session tool registry and its mixins.

Extracted from ``tools.py`` so that mixin modules (``web_tools``, etc.)
can import ``ToolResult`` / ``ToolDefinition`` without creating a
circular dependency back to ``tools``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


@dataclass
class ToolResult:
    status: str
    summary: str
    payload: dict[str, Any]
    error: str | None = None


@dataclass
class ToolDefinition:
    name: str
    description: str
    permission: str
    input_schema: dict[str, Any]
    execute: Callable[[dict[str, Any], dict[str, Any]], ToolResult]
