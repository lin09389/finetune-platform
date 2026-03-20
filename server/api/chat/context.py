"""
对话上下文管理模�?- 整合�?dialog_context.py �?context/manager.py 功能
"""
from typing import Dict, List, Optional, Any
from datetime import datetime
from dataclasses import dataclass, field
from enum import Enum
import logging
import threading

logger = logging.getLogger(__name__)


class MessageRole(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    FUNCTION = "function"


class MessagePriority(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    NORMAL = "normal"
    LOW = "low"


@dataclass
class ContextWindow:
    max_tokens: int = 4096
    reserved_tokens: int = 512
    current_tokens: int = 0
    compression_threshold: float = 0.8
    target_utilization: float = 0.6
    
    @property
    def available_tokens(self) -> int:
        return self.max_tokens - self.reserved_tokens - self.current_tokens
    
    @property
    def utilization(self) -> float:
        return self.current_tokens / (self.max_tokens - self.reserved_tokens)


@dataclass
class ContextMessage:
    id: str
    role: MessageRole
    content: str
    timestamp: datetime
    priority: MessagePriority = MessagePriority.NORMAL
    token_count: int = 0
    importance: float = 0.5
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "role": self.role.value if isinstance(self.role, MessageRole) else self.role,
            "content": self.content,
            "timestamp": self.timestamp.isoformat() if isinstance(self.timestamp, datetime) else self.timestamp,
            "priority": self.priority.value if isinstance(self.priority, MessagePriority) else self.priority,
            "token_count": self.token_count,
            "importance": self.importance,
            "metadata": self.metadata
        }


class ContextManager:
    """对话上下文管理器"""
    
    def __init__(
        self,
        session_id: str = "default",
        max_tokens: int = 4096,
        reserved_tokens: int = 512,
        compression_threshold: float = 0.8,
        target_utilization: float = 0.6
    ):
        self.session_id = session_id
        self.window = ContextWindow(
            max_tokens=max_tokens,
            reserved_tokens=reserved_tokens,
            compression_threshold=compression_threshold,
            target_utilization=target_utilization
        )
        self.messages: List[ContextMessage] = []
        self._lock = threading.RLock()
    
    def add_message(
        self,
        role: MessageRole,
        content: str,
        priority: MessagePriority = MessagePriority.NORMAL,
        importance: Optional[float] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> ContextMessage:
        """添加消息"""
        import uuid
        
        token_count = self._estimate_tokens(content)
        
        if importance is None:
            importance = self._calculate_importance(content, role)
        
        message = ContextMessage(
            id=f"msg_{uuid.uuid4().hex[:8]}",
            role=role,
            content=content,
            timestamp=datetime.now(),
            priority=priority,
            token_count=token_count,
            importance=importance,
            metadata=metadata or {}
        )
        
        with self._lock:
            self.messages.append(message)
            self.window.current_tokens += token_count
            
            if self.window.utilization >= self.window.compression_threshold:
                logger.info(f"上下文利用率 {self.window.utilization:.2%} 超过阈值，建议压缩")
        
        return message
    
    def _estimate_tokens(self, text: str) -> int:
        """估算 Token 数量"""
        chinese_chars = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
        other_chars = len(text) - chinese_chars
        return chinese_chars + other_chars // 4
    
    def _calculate_importance(self, content: str, role: MessageRole) -> float:
        """计算消息重要�?""
        importance = 0.5
        
        if role == MessageRole.SYSTEM:
            importance = 1.0
        elif role == MessageRole.USER:
            importance = 0.7
            if any(kw in content for kw in ["重要", "记住", "注意", "关键"]):
                importance = 0.9
        elif role == MessageRole.ASSISTANT:
            importance = 0.6
            if len(content) > 500:
                importance = 0.7
        
        return importance
    
    def get_context(
        self,
        include_system: bool = True,
        max_messages: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """获取上下文消息列�?""
        with self._lock:
            messages = self.messages
            
            if not include_system:
                messages = [m for m in messages if m.role != MessageRole.SYSTEM]
            
            if max_messages:
                system_messages = [m for m in messages if m.role == MessageRole.SYSTEM]
                other_messages = [m for m in messages if m.role != MessageRole.SYSTEM]
                other_messages = other_messages[-max_messages:]
                messages = system_messages + other_messages
            
            return [m.to_dict() for m in messages]
    
    def get_context_string(
        self,
        format_type: str = "default",
        max_messages: Optional[int] = None
    ) -> str:
        """获取上下文字符串"""
        messages = self.get_context(max_messages=max_messages)
        
        if format_type == "markdown":
            lines = []
            for msg in messages:
                role = msg["role"].upper()
                lines.append(f"## {role}")
                lines.append(msg["content"])
                lines.append("")
            return "\n".join(lines)
        elif format_type == "openai":
            import json
            return json.dumps(messages, ensure_ascii=False, indent=2)
        else:
            lines = []
            for msg in messages:
                role = msg["role"].capitalize()
                lines.append(f"[{role}]: {msg['content']}")
            return "\n".join(lines)
    
    def clear(self, keep_system: bool = True):
        """清空上下�?""
        with self._lock:
            if keep_system:
                self.messages = [m for m in self.messages if m.role == MessageRole.SYSTEM]
            else:
                self.messages = []
            
            self.window.current_tokens = sum(m.token_count for m in self.messages)
    
    def set_max_tokens(self, max_tokens: int):
        """设置最�?Token �?""
        self.window.max_tokens = max_tokens
        
        if self.window.utilization >= self.window.compression_threshold:
            logger.info(f"调整后上下文利用�?{self.window.utilization:.2%} 超过阈�?)
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        with self._lock:
            roles: Dict[str, int] = {}
            for msg in self.messages:
                role = msg.role.value if isinstance(msg.role, MessageRole) else msg.role
                roles[role] = roles.get(role, 0) + 1
            
            return {
                "session_id": self.session_id,
                "message_count": len(self.messages),
                "total_tokens": self.window.current_tokens,
                "max_tokens": self.window.max_tokens,
                "available_tokens": self.window.available_tokens,
                "utilization": round(self.window.utilization, 3),
                "roles": roles
            }
    
    def get_messages_by_role(self, role: MessageRole) -> List[ContextMessage]:
        """按角色获取消�?""
        with self._lock:
            return [m for m in self.messages if m.role == role]
    
    def get_recent_messages(self, count: int) -> List[ContextMessage]:
        """获取最近的消息"""
        with self._lock:
            return self.messages[-count:] if count < len(self.messages) else self.messages.copy()
    
    def find_messages(self, keyword: str) -> List[ContextMessage]:
        """搜索消息"""
        with self._lock:
            return [m for m in self.messages if keyword.lower() in m.content.lower()]


_context_managers: Dict[str, ContextManager] = {}
_managers_lock = threading.Lock()


def get_context_manager(
    session_id: str = "default",
    **kwargs
) -> ContextManager:
    """获取或创建上下文管理�?""
    with _managers_lock:
        if session_id not in _context_managers:
            _context_managers[session_id] = ContextManager(session_id=session_id, **kwargs)
        return _context_managers[session_id]


def remove_context_manager(session_id: str) -> bool:
    """删除上下文管理器"""
    with _managers_lock:
        if session_id in _context_managers:
            del _context_managers[session_id]
            return True
        return False


def list_context_managers() -> List[str]:
    """列出所有上下文管理�?""
    with _managers_lock:
        return list(_context_managers.keys())
