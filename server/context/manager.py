"""
对话上下文管理器

功能�?- 上下文窗口动态调�?- 基于重要性的消息保留
- 对话历史管理
- Token 计数与限�?"""
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
from dataclasses import dataclass, field
from enum import Enum
import logging
import re

logger = logging.getLogger(__name__)


class MessageRole(str, Enum):
    """消息角色"""
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    FUNCTION = "function"


class MessagePriority(str, Enum):
    """消息优先�?""
    CRITICAL = "critical"      # 系统消息，永不删�?    HIGH = "high"              # 重要消息，尽量保�?    NORMAL = "normal"          # 普通消�?    LOW = "low"                # 低优先级，可优先删除


@dataclass
class ChatMessage:
    """对话消息"""
    id: str
    role: MessageRole
    content: str
    timestamp: datetime = field(default_factory=datetime.now)
    priority: MessagePriority = MessagePriority.NORMAL
    token_count: int = 0
    importance: float = 0.5
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "role": self.role.value,
            "content": self.content,
            "timestamp": self.timestamp.isoformat(),
            "priority": self.priority.value,
            "token_count": self.token_count,
            "importance": self.importance,
            "metadata": self.metadata
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ChatMessage":
        return cls(
            id=data["id"],
            role=MessageRole(data["role"]),
            content=data["content"],
            timestamp=datetime.fromisoformat(data["timestamp"]) if isinstance(data.get("timestamp"), str) else data.get("timestamp", datetime.now()),
            priority=MessagePriority(data.get("priority", "normal")),
            token_count=data.get("token_count", 0),
            importance=data.get("importance", 0.5),
            metadata=data.get("metadata", {})
        )


@dataclass
class ContextWindow:
    """上下文窗口配�?""
    max_tokens: int = 4096
    reserved_tokens: int = 512
    system_message_tokens: int = 0
    current_tokens: int = 0
    
    @property
    def available_tokens(self) -> int:
        return max(0, self.max_tokens - self.reserved_tokens - self.system_message_tokens - self.current_tokens)
    
    @property
    def utilization(self) -> float:
        total = self.max_tokens - self.reserved_tokens - self.system_message_tokens
        if total <= 0:
            return 1.0
        return min(1.0, self.current_tokens / total)


class ContextManager:
    """对话上下文管理器"""
    
    def __init__(
        self,
        max_tokens: int = 4096,
        reserved_tokens: int = 512,
        compression_threshold: float = 0.8,
        target_utilization: float = 0.6
    ):
        self.window = ContextWindow(
            max_tokens=max_tokens,
            reserved_tokens=reserved_tokens
        )
        self.compression_threshold = compression_threshold
        self.target_utilization = target_utilization
        self.messages: List[ChatMessage] = []
        self.system_message: Optional[ChatMessage] = None
        self._message_counter = 0
        
        self.importance_weights = {
            "recency": 0.3,
            "position": 0.2,
            "content_length": 0.2,
            "role_weight": 0.15,
            "custom": 0.15
        }
        
        self.role_weights = {
            MessageRole.SYSTEM: 1.0,
            MessageRole.USER: 0.8,
            MessageRole.ASSISTANT: 0.6,
            MessageRole.FUNCTION: 0.4
        }
        
        logger.info(f"上下文管理器已初始化: max_tokens={max_tokens}")
    
    def estimate_tokens(self, text: str) -> int:
        if not text:
            return 0
        chinese_chars = len(re.findall(r'[\u4e00-\u9fff]', text))
        english_words = len(re.findall(r'[a-zA-Z]+', text))
        other_chars = len(text) - chinese_chars - sum(len(w) for w in re.findall(r'[a-zA-Z]+', text))
        return int(chinese_chars * 1.5 + english_words * 1.3 + other_chars * 0.5) + 1
    
    def add_message(
        self,
        role: MessageRole,
        content: str,
        priority: MessagePriority = MessagePriority.NORMAL,
        importance: Optional[float] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> ChatMessage:
        self._message_counter += 1
        message_id = f"msg_{self._message_counter}_{datetime.now().strftime('%H%M%S')}"
        
        token_count = self.estimate_tokens(content)
        
        if importance is None:
            importance = self._calculate_importance(content, role)
        
        if role == MessageRole.SYSTEM:
            message = ChatMessage(
                id=message_id,
                role=role,
                content=content,
                priority=MessagePriority.CRITICAL,
                token_count=token_count,
                importance=1.0,
                metadata=metadata or {}
            )
            self.system_message = message
            self.window.system_message_tokens = token_count
            logger.debug(f"设置系统消息: {token_count} tokens")
            return message
        
        message = ChatMessage(
            id=message_id,
            role=role,
            content=content,
            priority=priority,
            token_count=token_count,
            importance=importance,
            metadata=metadata or {}
        )
        
        self.messages.append(message)
        self.window.current_tokens += token_count
        
        logger.debug(f"添加消息: role={role.value}, tokens={token_count}, total={self.window.current_tokens}")
        
        if self.window.utilization >= self.compression_threshold:
            logger.info(f"上下文利用率 {self.window.utilization:.1%} 超过阈值，触发压缩")
            self._auto_compress()
        
        return message
    
    def _calculate_importance(self, content: str, role: MessageRole) -> float:
        importance = 0.5
        
        content_length = len(content)
        if content_length > 500:
            importance += 0.1
        elif content_length < 50:
            importance -= 0.1
        
        role_weight = self.role_weights.get(role, 0.5)
        importance = importance * 0.7 + role_weight * 0.3
        
        question_patterns = [
            r'\?', r'为什�?, r'如何', r'怎么', r'什�?, r'怎样',
            r'help', r'问题', r'错误', r'error', r'bug'
        ]
        for pattern in question_patterns:
            if re.search(pattern, content, re.IGNORECASE):
                importance += 0.1
                break
        
        code_patterns = [r'```', r'def ', r'class ', r'function', r'import ']
        for pattern in code_patterns:
            if re.search(pattern, content):
                importance += 0.05
        
        return min(1.0, max(0.0, importance))
    
    def _auto_compress(self) -> Tuple[int, int]:
        if not self.messages:
            return 0, 0
        
        target_tokens = int(
            (self.window.max_tokens - self.window.reserved_tokens - self.window.system_message_tokens)
            * self.target_utilization
        )
        
        tokens_to_remove = self.window.current_tokens - target_tokens
        if tokens_to_remove <= 0:
            return 0, 0
        
        scored_messages = []
        for i, msg in enumerate(self.messages):
            if msg.priority == MessagePriority.CRITICAL:
                continue
            
            recency_score = (i + 1) / len(self.messages)
            position_score = 1.0 - (i / len(self.messages)) if i < 3 else 0.5
            
            score = (
                recency_score * self.importance_weights["recency"] +
                position_score * self.importance_weights["position"] +
                (msg.content and len(msg.content) / 1000 or 0) * self.importance_weights["content_length"] +
                self.role_weights.get(msg.role, 0.5) * self.importance_weights["role_weight"] +
                msg.importance * self.importance_weights["custom"]
            )
            
            scored_messages.append((score, i, msg))
        
        scored_messages.sort(key=lambda x: x[0])
        
        removed_count = 0
        removed_tokens = 0
        indices_to_remove = []
        
        for score, idx, msg in scored_messages:
            if removed_tokens >= tokens_to_remove:
                break
            indices_to_remove.append(idx)
            removed_tokens += msg.token_count
            removed_count += 1
        
        indices_to_remove.sort(reverse=True)
        for idx in indices_to_remove:
            del self.messages[idx]
        
        self.window.current_tokens -= removed_tokens
        
        logger.info(f"自动压缩完成: 移除 {removed_count} 条消�? 释放 {removed_tokens} tokens")
        
        return removed_count, removed_tokens
    
    def compress_messages(
        self,
        messages: Optional[List[ChatMessage]] = None,
        strategy: str = "importance"
    ) -> List[ChatMessage]:
        if messages is None:
            messages = self.messages
        
        if not messages:
            return []
        
        if strategy == "importance":
            return self._compress_by_importance(messages)
        elif strategy == "recency":
            return self._compress_by_recency(messages)
        elif strategy == "hybrid":
            return self._compress_hybrid(messages)
        else:
            return messages
    
    def _compress_by_importance(self, messages: List[ChatMessage]) -> List[ChatMessage]:
        scored = [(msg.importance, msg) for msg in messages]
        scored.sort(key=lambda x: x[0], reverse=True)
        
        target_tokens = int(
            (self.window.max_tokens - self.window.reserved_tokens - self.window.system_message_tokens)
            * self.target_utilization
        )
        
        result = []
        current_tokens = 0
        
        for importance, msg in scored:
            if current_tokens + msg.token_count <= target_tokens:
                result.append(msg)
                current_tokens += msg.token_count
        
        result.sort(key=lambda m: messages.index(m))
        
        return result
    
    def _compress_by_recency(self, messages: List[ChatMessage]) -> List[ChatMessage]:
        target_tokens = int(
            (self.window.max_tokens - self.window.reserved_tokens - self.window.system_message_tokens)
            * self.target_utilization
        )
        
        result = []
        current_tokens = 0
        
        for msg in reversed(messages):
            if current_tokens + msg.token_count <= target_tokens:
                result.insert(0, msg)
                current_tokens += msg.token_count
        
        return result
    
    def _compress_hybrid(self, messages: List[ChatMessage]) -> List[ChatMessage]:
        if len(messages) <= 4:
            return messages
        
        keep_first = 2
        keep_last = 2
        
        first_messages = messages[:keep_first]
        last_messages = messages[-keep_last:]
        middle_messages = messages[keep_first:-keep_last]
        
        if middle_messages:
            compressed_middle = self._compress_by_importance(middle_messages)
            compressed_middle = compressed_middle[:len(middle_messages) // 2]
        else:
            compressed_middle = []
        
        return first_messages + compressed_middle + last_messages
    
    def get_context(
        self,
        include_system: bool = True,
        max_messages: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        result = []
        
        if include_system and self.system_message:
            result.append(self.system_message.to_dict())
        
        messages = self.messages
        if max_messages:
            messages = messages[-max_messages:]
        
        for msg in messages:
            result.append(msg.to_dict())
        
        return result
    
    def get_context_string(
        self,
        format_type: str = "default",
        max_messages: Optional[int] = None
    ) -> str:
        messages = self.messages
        if max_messages:
            messages = messages[-max_messages:]
        
        if format_type == "default":
            lines = []
            if self.system_message:
                lines.append(f"[System]: {self.system_message.content}")
            for msg in messages:
                role_label = {
                    MessageRole.USER: "User",
                    MessageRole.ASSISTANT: "Assistant",
                    MessageRole.FUNCTION: "Function"
                }.get(msg.role, msg.role.value)
                lines.append(f"[{role_label}]: {msg.content}")
            return "\n\n".join(lines)
        
        elif format_type == "markdown":
            lines = []
            if self.system_message:
                lines.append(f"## System\n\n{self.system_message.content}\n")
            for msg in messages:
                role_label = {
                    MessageRole.USER: "User",
                    MessageRole.ASSISTANT: "Assistant",
                    MessageRole.FUNCTION: "Function"
                }.get(msg.role, msg.role.value)
                lines.append(f"## {role_label}\n\n{msg.content}\n")
            return "\n".join(lines)
        
        elif format_type == "openai":
            return str(self.get_context(include_system=True, max_messages=max_messages))
        
        return ""
    
    def clear(self, keep_system: bool = True):
        if keep_system:
            self.messages = []
            self.window.current_tokens = 0
        else:
            self.messages = []
            self.system_message = None
            self.window.current_tokens = 0
            self.window.system_message_tokens = 0
        
        logger.info(f"上下文已清空, keep_system={keep_system}")
    
    def get_stats(self) -> Dict[str, Any]:
        return {
            "total_messages": len(self.messages),
            "total_tokens": self.window.current_tokens,
            "max_tokens": self.window.max_tokens,
            "available_tokens": self.window.available_tokens,
            "utilization": self.window.utilization,
            "has_system_message": self.system_message is not None,
            "compression_threshold": self.compression_threshold,
            "target_utilization": self.target_utilization,
            "message_breakdown": {
                role.value: sum(1 for m in self.messages if m.role == role)
                for role in MessageRole
            }
        }
    
    def set_max_tokens(self, max_tokens: int):
        old_max = self.window.max_tokens
        self.window.max_tokens = max_tokens
        
        if self.window.utilization >= self.compression_threshold:
            logger.info(f"调整 max_tokens 后触发压�? {old_max} -> {max_tokens}")
            self._auto_compress()
        
        logger.info(f"上下文窗口大小已调整: {old_max} -> {max_tokens}")
    
    def get_messages_by_role(self, role: MessageRole) -> List[ChatMessage]:
        return [msg for msg in self.messages if msg.role == role]
    
    def get_recent_messages(self, count: int = 5) -> List[ChatMessage]:
        return self.messages[-count:] if self.messages else []
    
    def find_messages(self, keyword: str) -> List[ChatMessage]:
        keyword_lower = keyword.lower()
        return [
            msg for msg in self.messages
            if keyword_lower in msg.content.lower()
        ]


_context_managers: Dict[str, ContextManager] = {}


def get_context_manager(
    session_id: str = "default",
    max_tokens: int = 4096,
    **kwargs
) -> ContextManager:
    if session_id not in _context_managers:
        _context_managers[session_id] = ContextManager(max_tokens=max_tokens, **kwargs)
    return _context_managers[session_id]


def remove_context_manager(session_id: str) -> bool:
    if session_id in _context_managers:
        del _context_managers[session_id]
        return True
    return False


def list_context_managers() -> List[str]:
    return list(_context_managers.keys())
