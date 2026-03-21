# -*- coding: utf-8 -*-
"""
会话存储模块 - 统一会话管理
整合原有 session_store 和 conversation_history 功能
"""
from typing import List, Dict, Optional, Any
from datetime import datetime
from dataclasses import dataclass, field
import uuid
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class Message:
    """消息"""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    role: str = ""
    content: str = ""
    created_at: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'role': self.role,
            'content': self.content,
            'created_at': self.created_at.isoformat(),
            'metadata': self.metadata
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Message':
        return cls(
            id=data.get('id', str(uuid.uuid4())),
            role=data.get('role', ''),
            content=data.get('content', ''),
            created_at=datetime.fromisoformat(data['created_at']) if isinstance(data.get('created_at'), str) else data.get('created_at', datetime.now()),
            metadata=data.get('metadata', {})
        )


@dataclass
class Session:
    """会话"""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    title: str = "新对话"
    messages: List[Message] = field(default_factory=list)
    message_count: int = 0
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def add_message(
        self,
        role: str,
        content: str,
        metadata: Dict[str, Any] = None
    ) -> Message:
        """添加消息"""
        message = Message(
            role=role,
            content=content,
            metadata=metadata or {}
        )
        
        self.messages.append(message)
        self.message_count = len(self.messages)
        self.updated_at = datetime.now()
        
        return message
    
    def get_messages(self, limit: int = None) -> List[Message]:
        """获取消息"""
        if limit:
            return self.messages[-limit:]
        return self.messages
    
    def clear_messages(self):
        """清空消息"""
        self.messages.clear()
        self.message_count = 0
        self.updated_at = datetime.now()
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'title': self.title,
            'messages': [m.to_dict() for m in self.messages],
            'message_count': self.message_count,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat(),
            'metadata': self.metadata
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Session':
        session = cls(
            id=data.get('id', str(uuid.uuid4())),
            title=data.get('title', '新对话'),
            message_count=data.get('message_count', 0),
            metadata=data.get('metadata', {})
        )
        
        session.messages = [
            Message.from_dict(m)
            for m in data.get('messages', [])
        ]
        
        if 'created_at' in data:
            session.created_at = datetime.fromisoformat(data['created_at'])
        if 'updated_at' in data:
            session.updated_at = datetime.fromisoformat(data['updated_at'])
        
        return session


class SessionManager:
    """会话管理器，支持容错和重试"""
    
    def __init__(
        self,
        storage_path: str = "data/sessions",
        max_sessions: int = 100,
        auto_save: bool = True,
        max_retries: int = 3,
        retry_delay_ms: int = 100
    ):
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self.max_sessions = max_sessions
        self.auto_save = auto_save
        self.max_retries = max_retries
        self.retry_delay_ms = retry_delay_ms
        
        self._sessions: Dict[str, Session] = {}
        self._memory_cache: Dict[str, Session] = {}
        self._pending_writes: List[Dict[str, Any]] = []
        self._write_errors: int = 0
        
        self._load_sessions()
    
    def _load_sessions(self):
        """加载会话，带重试"""
        for attempt in range(self.max_retries):
            try:
                for file_path in self.storage_path.glob("*.json"):
                    try:
                        with open(file_path, 'r', encoding='utf-8') as f:
                            data = json.load(f)
                        session = Session.from_dict(data)
                        self._sessions[session.id] = session
                        self._memory_cache[session.id] = session
                    except Exception as e:
                        logger.warning(f"加载会话失败 {file_path}: {e}")
                
                logger.info(f"加载了 {len(self._sessions)} 个会话")
                return
            except Exception as e:
                logger.error(f"加载会话失败 (尝试 {attempt + 1}/{self.max_retries}): {e}")
                if attempt < self.max_retries - 1:
                    import time
                    time.sleep(self.retry_delay_ms / 1000)
        
        logger.warning("会话加载失败，使用空会话列表")
    
    def _save_session(self, session: Session, retry: bool = True):
        """保存会话，带重试和降级"""
        if not self.auto_save:
            return
        
        self._memory_cache[session.id] = session
        
        for attempt in range(self.max_retries if retry else 1):
            try:
                file_path = self.storage_path / f"{session.id}.json"
                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump(session.to_dict(), f, ensure_ascii=False, indent=2)
                self._write_errors = 0
                return
            except Exception as e:
                self._write_errors += 1
                logger.warning(f"保存会话失败 (尝试 {attempt + 1}): {e}")
                if attempt < self.max_retries - 1:
                    import time
                    time.sleep(self.retry_delay_ms / 1000)
        
        self._pending_writes.append({
            "session_id": session.id,
            "session": session.to_dict(),
            "timestamp": datetime.now().isoformat()
        })
        logger.warning(f"会话保存失败，已加入待写入队列 (队列长度: {len(self._pending_writes)})")
    
    def _flush_pending_writes(self):
        """刷新待写入队列"""
        if not self._pending_writes:
            return
        
        writes = self._pending_writes.copy()
        self._pending_writes.clear()
        
        for write in writes:
            try:
                session = Session.from_dict(write["session"])
                self._save_session(session, retry=False)
            except Exception as e:
                logger.error(f"待写入会话失败: {e}")
                self._pending_writes.append(write)
    
    def create_session(
        self,
        title: str = "新对话",
        metadata: Dict[str, Any] = None
    ) -> Session:
        """创建会话"""
        if len(self._sessions) >= self.max_sessions:
            self._evict_oldest()
        
        session = Session(
            title=title,
            metadata=metadata or {}
        )
        
        self._sessions[session.id] = session
        self._memory_cache[session.id] = session
        self._save_session(session)
        
        logger.info(f"创建会话: {session.id}")
        return session
    
    def get_session(self, session_id: str) -> Optional[Session]:
        """获取会话，优先从内存缓存获取"""
        if session_id in self._memory_cache:
            return self._memory_cache[session_id]
        return self._sessions.get(session_id)
    
    def delete_session(self, session_id: str) -> bool:
        """删除会话"""
        if session_id not in self._sessions:
            return False
        
        del self._sessions[session_id]
        
        try:
            file_path = self.storage_path / f"{session_id}.json"
            if file_path.exists():
                file_path.unlink()
        except Exception as e:
            logger.warning(f"删除会话文件失败: {e}")
        
        return True
    
    def update_session_title(self, session_id: str, title: str) -> bool:
        """更新会话标题"""
        session = self._sessions.get(session_id)
        if not session:
            return False
        
        session.title = title
        session.updated_at = datetime.now()
        self._save_session(session)
        
        return True
    
    def list_sessions(
        self,
        limit: int = 20,
        offset: int = 0
    ) -> List[Session]:
        """列出会话"""
        sorted_sessions = sorted(
            self._sessions.values(),
            key=lambda s: s.updated_at,
            reverse=True
        )
        
        return sorted_sessions[offset:offset + limit]
    
    def get_session_count(self) -> int:
        """获取会话数量"""
        return len(self._sessions)
    
    def _evict_oldest(self):
        """淘汰最旧的会话"""
        if not self._sessions:
            return
        
        oldest_id = min(
            self._sessions.keys(),
            key=lambda sid: self._sessions[sid].updated_at
        )
        
        self.delete_session(oldest_id)
        logger.info(f"淘汰会话: {oldest_id}")


_session_manager: Optional[SessionManager] = None


def get_session_manager() -> SessionManager:
    """获取会话管理器实例"""
    global _session_manager
    if _session_manager is None:
        _session_manager = SessionManager()
    return _session_manager
