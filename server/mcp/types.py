from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class MCPMessageType(str, Enum):
    REQUEST = "request"
    RESPONSE = "response"
    NOTIFICATION = "notification"


@dataclass
class MCPTool:
    name: str
    description: str
    input_schema: dict[str, Any]


@dataclass
class MCPToolCall:
    tool_name: str
    arguments: dict[str, Any]
    call_id: str = ""


@dataclass
class MCPToolResult:
    call_id: str
    content: Any
    is_error: bool = False


@dataclass
class MCPServerInfo:
    name: str
    transport: str
    command: str | None = None
    args: list[str] = field(default_factory=list)
    url: str | None = None
    status: str = "disconnected"
