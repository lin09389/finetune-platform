from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from enum import Enum


class MCPMessageType(str, Enum):
    REQUEST = "request"
    RESPONSE = "response"
    NOTIFICATION = "notification"


@dataclass
class MCPTool:
    name: str
    description: str
    input_schema: Dict[str, Any]


@dataclass
class MCPToolCall:
    tool_name: str
    arguments: Dict[str, Any]
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
    command: Optional[str] = None
    args: List[str] = field(default_factory=list)
    url: Optional[str] = None
    status: str = "disconnected"
