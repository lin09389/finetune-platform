# -*- coding: utf-8 -*-
"""
对话上下文管理模块 - 整合原有 dialog_context 功能
"""
from typing import List, Dict, Optional, Any
from datetime import datetime
from dataclasses import dataclass, field
import json
import logging

logger = logging.getLogger(__name__)


@dataclass
class ContextMessage:
    """上下文消息"""
    role: str
    content: str
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'role': self.role,
            'content': self.content,
            'timestamp': self.timestamp.isoformat(),
            'metadata': self.metadata
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ContextMessage':
        return cls(
            role=data['role'],
            content=data['content'],
            timestamp=datetime.fromisoformat(data['timestamp']) if isinstance(data.get('timestamp'), str) else data.get('timestamp', datetime.now()),
            metadata=data.get('metadata', {})
        )


class ConversationContext:
    """对话上下文管理器"""
    
    def __init__(
        self,
        session_id: str,
        max_messages: int = 50,
        max_tokens: int = 4000
    ):
        self.session_id = session_id
        self.max_messages = max_messages
        self.max_tokens = max_tokens
        
        self.messages: List[ContextMessage] = []
        self.system_prompt: Optional[str] = None
        self.metadata: Dict[str, Any] = {}
        self.created_at = datetime.now()
        self.updated_at = datetime.now()
    
    def add_message(
        self,
        role: str,
        content: str,
        metadata: Dict[str, Any] = None
    ) -> ContextMessage:
        """添加消息"""
        message = ContextMessage(
            role=role,
            content=content,
            metadata=metadata or {}
        )
        
        self.messages.append(message)
        self.updated_at = datetime.now()
        
        if len(self.messages) > self.max_messages:
            self.messages = self.messages[-self.max_messages:]
        
        return message
    
    def get_messages(self, limit: int = None) -> List[ContextMessage]:
        """获取消息列表"""
        if limit:
            return self.messages[-limit:]
        return self.messages
    
    def get_context_for_llm(self) -> List[Dict[str, str]]:
        """获取用于 LLM 的上下文"""
        context = []
        
        if self.system_prompt:
            context.append({
                'role': 'system',
                'content': self.system_prompt
            })
        
        for msg in self.messages:
            context.append({
                'role': msg.role,
                'content': msg.content
            })
        
        return context
    
    def set_system_prompt(self, prompt: str):
        """设置系统提示"""
        self.system_prompt = prompt
        self.updated_at = datetime.now()
    
    def clear(self):
        """清空上下文"""
        self.messages.clear()
        self.updated_at = datetime.now()
    
    def to_dict(self) -> Dict[str, Any]:
        """导出为字典"""
        return {
            'session_id': self.session_id,
            'messages': [m.to_dict() for m in self.messages],
            'system_prompt': self.system_prompt,
            'metadata': self.metadata,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat()
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ConversationContext':
        """从字典导入"""
        context = cls(
            session_id=data['session_id'],
            max_messages=data.get('max_messages', 50),
            max_tokens=data.get('max_tokens', 4000)
        )
        
        context.messages = [
            ContextMessage.from_dict(m)
            for m in data.get('messages', [])
        ]
        context.system_prompt = data.get('system_prompt')
        context.metadata = data.get('metadata', {})
        
        if 'created_at' in data:
            context.created_at = datetime.fromisoformat(data['created_at'])
        if 'updated_at' in data:
            context.updated_at = datetime.fromisoformat(data['updated_at'])
        
        return context


class ContextManager:
    """上下文管理器（多会话）"""
    
    def __init__(self, max_sessions: int = 100):
        self.max_sessions = max_sessions
        self._contexts: Dict[str, ConversationContext] = {}
    
    def get_context(self, session_id: str) -> ConversationContext:
        """获取或创建上下文"""
        if session_id not in self._contexts:
            if len(self._contexts) >= self.max_sessions:
                self._evict_oldest()
            
            self._contexts[session_id] = ConversationContext(session_id)
        
        return self._contexts[session_id]
    
    def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        metadata: Dict[str, Any] = None
    ) -> ContextMessage:
        """添加消息到指定会话"""
        context = self.get_context(session_id)
        return context.add_message(role, content, metadata)
    
    def get_messages(
        self,
        session_id: str,
        limit: int = None
    ) -> List[ContextMessage]:
        """获取指定会话的消息"""
        context = self.get_context(session_id)
        return context.get_messages(limit)
    
    def clear_context(self, session_id: str):
        """清空指定会话的上下文"""
        if session_id in self._contexts:
            self._contexts[session_id].clear()
    
    def remove_context(self, session_id: str):
        """删除指定会话的上下文"""
        if session_id in self._contexts:
            del self._contexts[session_id]
    
    def _evict_oldest(self):
        """淘汰最旧的会话"""
        if not self._contexts:
            return
        
        oldest_id = min(
            self._contexts.keys(),
            key=lambda sid: self._contexts[sid].updated_at
        )
        
        del self._contexts[oldest_id]


_context_manager: Optional[ContextManager] = None


def get_context_manager() -> ContextManager:
    """获取上下文管理器实例"""
    global _context_manager
    if _context_manager is None:
        _context_manager = ContextManager()
    return _context_manager
