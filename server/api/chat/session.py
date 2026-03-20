"""
会话存储模块 - 统一会话管理
整合�?context/session_store.py 功能
"""
from typing import Dict, List, Optional, Any
from datetime import datetime
from dataclasses import dataclass, field
from enum import Enum
import json
import os
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


class SessionStatus(str, Enum):
    ACTIVE = "active"
    ARCHIVED = "archived"
    DELETED = "deleted"


class MessageRole(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    FUNCTION = "function"
    TOOL = "tool"


@dataclass
class SessionMetadata:
    title: str = ""
    description: str = ""
    model_id: str = ""
    tags: List[str] = field(default_factory=list)
    status: SessionStatus = SessionStatus.ACTIVE
    starred: bool = False
    pinned: bool = False
    custom_data: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SessionMessage:
    id: str
    session_id: str
    role: MessageRole
    content: str
    timestamp: datetime
    token_count: int = 0
    importance: float = 0.5
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "session_id": self.session_id,
            "role": self.role.value if isinstance(self.role, MessageRole) else self.role,
            "content": self.content,
            "timestamp": self.timestamp.isoformat() if isinstance(self.timestamp, datetime) else self.timestamp,
            "token_count": self.token_count,
            "importance": self.importance,
            "metadata": self.metadata
        }


@dataclass
class ChatSession:
    id: str
    metadata: SessionMetadata
    created_at: str
    updated_at: str
    messages: List[SessionMessage] = field(default_factory=list)
    message_count: int = 0
    total_tokens: int = 0


class SessionStore:
    """会话存储管理�?""
    
    def __init__(self, storage_path: Optional[str] = None):
        self.storage_path = Path(storage_path) if storage_path else Path(__file__).parent.parent.parent / "data" / "sessions"
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self._sessions: Dict[str, ChatSession] = {}
        self._load_sessions()
    
    def _load_sessions(self):
        """加载会话数据"""
        sessions_file = self.storage_path / "sessions.json"
        if sessions_file.exists():
            try:
                with open(sessions_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for session_id, session_data in data.items():
                        self._sessions[session_id] = self._deserialize_session(session_data)
                logger.info(f"加载 {len(self._sessions)} 个会�?)
            except Exception as e:
                logger.error(f"加载会话数据失败: {e}")
    
    def _save_sessions(self):
        """保存会话数据"""
        sessions_file = self.storage_path / "sessions.json"
        try:
            data = {}
            for session_id, session in self._sessions.items():
                data[session_id] = self._serialize_session(session)
            with open(sessions_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存会话数据失败: {e}")
    
    def _serialize_session(self, session: ChatSession) -> Dict[str, Any]:
        """序列化会�?""
        return {
            "id": session.id,
            "metadata": {
                "title": session.metadata.title,
                "description": session.metadata.description,
                "model_id": session.metadata.model_id,
                "tags": session.metadata.tags,
                "status": session.metadata.status.value,
                "starred": session.metadata.starred,
                "pinned": session.metadata.pinned,
                "custom_data": session.metadata.custom_data
            },
            "created_at": session.created_at,
            "updated_at": session.updated_at,
            "messages": [m.to_dict() for m in session.messages],
            "message_count": session.message_count,
            "total_tokens": session.total_tokens
        }
    
    def _deserialize_session(self, data: Dict[str, Any]) -> ChatSession:
        """反序列化会话"""
        metadata = SessionMetadata(
            title=data.get("metadata", {}).get("title", ""),
            description=data.get("metadata", {}).get("description", ""),
            model_id=data.get("metadata", {}).get("model_id", ""),
            tags=data.get("metadata", {}).get("tags", []),
            status=SessionStatus(data.get("metadata", {}).get("status", "active")),
            starred=data.get("metadata", {}).get("starred", False),
            pinned=data.get("metadata", {}).get("pinned", False),
            custom_data=data.get("metadata", {}).get("custom_data", {})
        )
        
        messages = []
        for msg_data in data.get("messages", []):
            messages.append(SessionMessage(
                id=msg_data.get("id", ""),
                session_id=msg_data.get("session_id", data.get("id", "")),
                role=MessageRole(msg_data.get("role", "user")),
                content=msg_data.get("content", ""),
                timestamp=datetime.fromisoformat(msg_data["timestamp"]) if isinstance(msg_data.get("timestamp"), str) else datetime.now(),
                token_count=msg_data.get("token_count", 0),
                importance=msg_data.get("importance", 0.5),
                metadata=msg_data.get("metadata", {})
            ))
        
        return ChatSession(
            id=data.get("id", ""),
            metadata=metadata,
            created_at=data.get("created_at", datetime.now().isoformat()),
            updated_at=data.get("updated_at", datetime.now().isoformat()),
            messages=messages,
            message_count=data.get("message_count", len(messages)),
            total_tokens=data.get("total_tokens", 0)
        )
    
    def create_session(
        self,
        title: str = "",
        model_id: str = "",
        description: str = "",
        tags: Optional[List[str]] = None,
        custom_data: Optional[Dict[str, Any]] = None
    ) -> ChatSession:
        """创建新会�?""
        import uuid
        session_id = f"session_{datetime.now().strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:8]}"
        
        session = ChatSession(
            id=session_id,
            metadata=SessionMetadata(
                title=title or f"新对�?{datetime.now().strftime('%m/%d %H:%M')}",
                description=description,
                model_id=model_id,
                tags=tags or [],
                custom_data=custom_data or {}
            ),
            created_at=datetime.now().isoformat(),
            updated_at=datetime.now().isoformat()
        )
        
        self._sessions[session_id] = session
        self._save_sessions()
        
        return session
    
    def get_session(self, session_id: str, include_messages: bool = True) -> Optional[ChatSession]:
        """获取会话"""
        session = self._sessions.get(session_id)
        if session and not include_messages:
            session = ChatSession(
                id=session.id,
                metadata=session.metadata,
                created_at=session.created_at,
                updated_at=session.updated_at,
                messages=[],
                message_count=len(session.messages),
                total_tokens=session.total_tokens
            )
        return session
    
    def update_session(self, session_id: str, **kwargs) -> bool:
        """更新会话"""
        session = self._sessions.get(session_id)
        if not session:
            return False
        
        for key, value in kwargs.items():
            if value is None:
                continue
            if hasattr(session.metadata, key):
                setattr(session.metadata, key, value)
            elif key == "status" and isinstance(value, SessionStatus):
                session.metadata.status = value
        
        session.updated_at = datetime.now().isoformat()
        self._save_sessions()
        return True
    
    def delete_session(self, session_id: str, soft_delete: bool = True) -> bool:
        """删除会话"""
        session = self._sessions.get(session_id)
        if not session:
            return False
        
        if soft_delete:
            session.metadata.status = SessionStatus.DELETED
            session.updated_at = datetime.now().isoformat()
        else:
            del self._sessions[session_id]
        
        self._save_sessions()
        return True
    
    def restore_session(self, session_id: str) -> Optional[ChatSession]:
        """恢复已删除的会话"""
        session = self._sessions.get(session_id)
        if session and session.metadata.status == SessionStatus.DELETED:
            session.metadata.status = SessionStatus.ACTIVE
            session.updated_at = datetime.now().isoformat()
            self._save_sessions()
            return session
        return None
    
    def archive_session(self, session_id: str) -> bool:
        """归档会话"""
        return self.update_session(session_id, status=SessionStatus.ARCHIVED)
    
    def add_message(
        self,
        session_id: str,
        role: MessageRole,
        content: str,
        token_count: int = 0,
        importance: float = 0.5,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Optional[SessionMessage]:
        """添加消息"""
        session = self._sessions.get(session_id)
        if not session:
            return None
        
        import uuid
        message = SessionMessage(
            id=f"msg_{uuid.uuid4().hex[:8]}",
            session_id=session_id,
            role=role,
            content=content,
            timestamp=datetime.now(),
            token_count=token_count,
            importance=importance,
            metadata=metadata or {}
        )
        
        session.messages.append(message)
        session.message_count = len(session.messages)
        session.total_tokens += token_count
        session.updated_at = datetime.now().isoformat()
        
        self._save_sessions()
        return message
    
    def add_messages_batch(self, session_id: str, messages: List[Dict[str, Any]]) -> int:
        """批量添加消息"""
        session = self._sessions.get(session_id)
        if not session:
            return 0
        
        count = 0
        for msg_data in messages:
            try:
                role = MessageRole(msg_data.get("role", "user"))
                self.add_message(
                    session_id=session_id,
                    role=role,
                    content=msg_data.get("content", ""),
                    token_count=msg_data.get("token_count", 0),
                    importance=msg_data.get("importance", 0.5),
                    metadata=msg_data.get("metadata")
                )
                count += 1
            except Exception as e:
                logger.warning(f"添加消息失败: {e}")
        
        return count
    
    def get_messages(
        self,
        session_id: str,
        limit: Optional[int] = None,
        offset: int = 0,
        roles: Optional[List[MessageRole]] = None
    ) -> List[SessionMessage]:
        """获取消息列表"""
        session = self._sessions.get(session_id)
        if not session:
            return []
        
        messages = session.messages
        
        if roles:
            messages = [m for m in messages if m.role in roles]
        
        if offset:
            messages = messages[offset:]
        
        if limit:
            messages = messages[:limit]
        
        return messages
    
    def delete_message(self, session_id: str, message_id: str) -> bool:
        """删除消息"""
        session = self._sessions.get(session_id)
        if not session:
            return False
        
        for i, msg in enumerate(session.messages):
            if msg.id == message_id:
                session.total_tokens -= msg.token_count
                session.messages.pop(i)
                session.message_count = len(session.messages)
                session.updated_at = datetime.now().isoformat()
                self._save_sessions()
                return True
        
        return False
    
    def search_sessions(
        self,
        query: Optional[str] = None,
        tags: Optional[List[str]] = None,
        status: Optional[SessionStatus] = None,
        starred: Optional[bool] = None,
        pinned: Optional[bool] = None,
        model_id: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
        order_by: str = "updated_at",
        order_desc: bool = True
    ) -> tuple:
        """搜索会话"""
        sessions = list(self._sessions.values())
        
        if status:
            sessions = [s for s in sessions if s.metadata.status == status]
        elif status is None:
            sessions = [s for s in sessions if s.metadata.status != SessionStatus.DELETED]
        
        if query:
            query_lower = query.lower()
            sessions = [
                s for s in sessions
                if query_lower in s.metadata.title.lower() or
                   any(query_lower in msg.content.lower() for msg in s.messages)
            ]
        
        if tags:
            sessions = [s for s in sessions if any(t in s.metadata.tags for t in tags)]
        
        if starred is not None:
            sessions = [s for s in sessions if s.metadata.starred == starred]
        
        if pinned is not None:
            sessions = [s for s in sessions if s.metadata.pinned == pinned]
        
        if model_id:
            sessions = [s for s in sessions if s.metadata.model_id == model_id]
        
        if start_date:
            sessions = [s for s in sessions if s.updated_at >= start_date]
        
        if end_date:
            sessions = [s for s in sessions if s.updated_at <= end_date]
        
        reverse = order_desc
        sessions.sort(key=lambda s: getattr(s, order_by, s.updated_at), reverse=reverse)
        
        total = len(sessions)
        sessions = sessions[offset:offset + limit]
        
        return sessions, total
    
    def get_all_tags(self) -> List[Dict[str, Any]]:
        """获取所有标�?""
        tag_counts: Dict[str, int] = {}
        for session in self._sessions.values():
            for tag in session.metadata.tags:
                tag_counts[tag] = tag_counts.get(tag, 0) + 1
        
        return [{"tag": tag, "count": count} for tag, count in sorted(tag_counts.items(), key=lambda x: -x[1])]
    
    def get_statistics(self) -> Dict[str, Any]:
        """获取统计信息"""
        total = len(self._sessions)
        active = sum(1 for s in self._sessions.values() if s.metadata.status == SessionStatus.ACTIVE)
        archived = sum(1 for s in self._sessions.values() if s.metadata.status == SessionStatus.ARCHIVED)
        deleted = sum(1 for s in self._sessions.values() if s.metadata.status == SessionStatus.DELETED)
        
        total_messages = sum(s.message_count for s in self._sessions.values())
        total_tokens = sum(s.total_tokens for s in self._sessions.values())
        
        now = datetime.now()
        seven_days_ago = (now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat())
        thirty_days_ago = seven_days_ago
        
        active_7d = sum(
            1 for s in self._sessions.values()
            if s.metadata.status == SessionStatus.ACTIVE and s.updated_at >= seven_days_ago
        )
        
        return {
            "total_sessions": total,
            "active_sessions": active,
            "archived_sessions": archived,
            "deleted_sessions": deleted,
            "total_messages": total_messages,
            "total_tokens": total_tokens,
            "active_sessions_7d": active_7d,
            "active_sessions_30d": active
        }
    
    def export_session(self, session_id: str, format: str = "json") -> Optional[str]:
        """导出会话"""
        session = self._sessions.get(session_id)
        if not session:
            return None
        
        if format == "json":
            return json.dumps(self._serialize_session(session), ensure_ascii=False, indent=2)
        elif format == "markdown":
            lines = [f"# {session.metadata.title}", ""]
            for msg in session.messages:
                role = msg.role.value if isinstance(msg.role, MessageRole) else msg.role
                lines.append(f"## {role.capitalize()}")
                lines.append(msg.content)
                lines.append("")
            return "\n".join(lines)
        
        return None


_session_store: Optional[SessionStore] = None


def get_session_store() -> SessionStore:
    """获取会话存储单例"""
    global _session_store
    if _session_store is None:
        _session_store = SessionStore()
    return _session_store
