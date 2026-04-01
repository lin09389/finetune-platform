import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class MessageRole(str, Enum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    FUNCTION = "function"


class MessagePriority(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    NORMAL = "normal"
    LOW = "low"


@dataclass
class ChatMessage:
    id: str
    role: MessageRole
    content: str
    timestamp: datetime = field(default_factory=datetime.now)
    priority: MessagePriority = MessagePriority.NORMAL
    token_count: int = 0
    importance: float = 0.5
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "role": self.role.value,
            "content": self.content,
            "timestamp": self.timestamp.isoformat(),
            "priority": self.priority.value,
            "token_count": self.token_count,
            "importance": self.importance,
            "metadata": self.metadata,
        }


@dataclass
class ContextWindow:
    max_tokens: int = 4096
    reserved_tokens: int = 512
    system_message_tokens: int = 0
    current_tokens: int = 0

    @property
    def available_tokens(self) -> int:
        return max(0, self.max_tokens - self.reserved_tokens - self.current_tokens)

    @property
    def utilization(self) -> float:
        capacity = max(1, self.max_tokens - self.reserved_tokens)
        return self.current_tokens / capacity


class ContextManager:
    def __init__(
        self,
        session_id: str = "default",
        max_tokens: int = 4096,
        reserved_tokens: int = 512,
        compression_threshold: float = 0.8,
        target_utilization: float = 0.6,
    ):
        self.session_id = session_id
        self.window = ContextWindow(max_tokens=max_tokens, reserved_tokens=reserved_tokens)
        self.compression_threshold = compression_threshold
        self.target_utilization = target_utilization
        self.messages: list[ChatMessage] = []
        self.system_message: ChatMessage | None = None
        self._message_counter = 0

    def _estimate_tokens(self, text: str) -> int:
        if not text:
            return 0
        chinese_chars = len(re.findall(r"[\u4e00-\u9fff]", text))
        english_words = len(re.findall(r"[A-Za-z]+", text))
        other_chars = max(0, len(text) - chinese_chars - sum(len(w) for w in re.findall(r"[A-Za-z]+", text)))
        return max(1, int(chinese_chars * 2 + english_words * 1.3 + other_chars * 0.5))

    def estimate_tokens(self, text: str) -> int:
        return self._estimate_tokens(text)

    def _calculate_importance(self, content: str, role: MessageRole) -> float:
        if role == MessageRole.SYSTEM:
            return 1.0
        importance = 0.5
        keywords = ["important", "error", "bug", "remember", "重要", "记住", "错误", "问题"]
        if any(keyword.lower() in content.lower() for keyword in keywords):
            importance += 0.2
        if len(content) > 200:
            importance += 0.1
        if role == MessageRole.USER:
            importance += 0.1
        return min(1.0, max(0.0, importance))

    def add_message(
        self,
        role: MessageRole | str,
        content: str,
        priority: MessagePriority = MessagePriority.NORMAL,
        importance: float | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ChatMessage:
        role_enum = role if isinstance(role, MessageRole) else MessageRole(str(role))
        self._message_counter += 1
        token_count = self._estimate_tokens(content)
        message = ChatMessage(
            id=f"msg_{self._message_counter}",
            role=role_enum,
            content=content,
            priority=MessagePriority.CRITICAL if role_enum == MessageRole.SYSTEM else priority,
            token_count=token_count,
            importance=1.0 if role_enum == MessageRole.SYSTEM else (importance if importance is not None else self._calculate_importance(content, role_enum)),
            metadata=metadata or {},
        )
        if role_enum == MessageRole.SYSTEM:
            self.system_message = message
            self.window.system_message_tokens = token_count
            return message
        self.messages.append(message)
        self.window.current_tokens += token_count
        return message

    def get_context(self, include_system: bool = False, max_messages: int | None = None) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        if include_system and self.system_message:
            result.append(self.system_message.to_dict())
        messages = self.messages[-max_messages:] if max_messages else self.messages
        result.extend(msg.to_dict() for msg in messages)
        return result

    def get_context_string(self, format_type: str = "default", max_messages: int | None = None) -> str:
        messages = self.messages[-max_messages:] if max_messages else self.messages
        if format_type == "markdown":
            lines: list[str] = []
            if self.system_message:
                lines.extend(["## System", "", self.system_message.content, ""])
            for msg in messages:
                lines.extend([f"## {msg.role.value.title()}", "", msg.content, ""])
            return "\n".join(lines).strip()
        lines = []
        if self.system_message:
            lines.append(f"[System]: {self.system_message.content}")
        for msg in messages:
            lines.append(f"[{msg.role.value.title()}]: {msg.content}")
        return "\n\n".join(lines)

    def clear(self, keep_system: bool = True):
        self.messages = []
        self.window.current_tokens = 0
        if not keep_system:
            self.system_message = None
            self.window.system_message_tokens = 0

    def get_stats(self) -> dict[str, Any]:
        return {
            "message_count": len(self.messages),
            "total_tokens": self.window.current_tokens,
            "max_tokens": self.window.max_tokens,
            "available_tokens": self.window.available_tokens,
            "utilization": self.window.utilization,
        }

    def set_max_tokens(self, max_tokens: int):
        self.window.max_tokens = max_tokens

    def get_messages_by_role(self, role: MessageRole | str) -> list[ChatMessage]:
        role_value = role if isinstance(role, MessageRole) else MessageRole(str(role))
        return [msg for msg in self.messages if msg.role == role_value]

    def get_recent_messages(self, count: int = 5) -> list[ChatMessage]:
        return self.messages[-count:]

    def find_messages(self, keyword: str) -> list[ChatMessage]:
        keyword_lower = keyword.lower()
        return [msg for msg in self.messages if keyword_lower in msg.content.lower()]


_context_managers: dict[str, ContextManager] = {}


def get_context_manager(session_id: str = "default", max_tokens: int = 4096, **kwargs) -> ContextManager:
    if session_id not in _context_managers:
        _context_managers[session_id] = ContextManager(session_id=session_id, max_tokens=max_tokens, **kwargs)
    return _context_managers[session_id]


def remove_context_manager(session_id: str) -> bool:
    return _context_managers.pop(session_id, None) is not None


def list_context_managers() -> list[str]:
    return list(_context_managers.keys())
