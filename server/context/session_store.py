"""
项目上下文会话存储 — JSON 文件持久化

职责：管理项目上下文理解的聊天会话（技术栈检测、代码符号提取、
语义搜索结果的对话历史）。

存储方式：JSON 文件（data/context_sessions/），每个会话一个文件。
生命周期：跨会话持久化，用户可手动归档/删除。

注意：此模块与 API 层的 SessionManager（SQLite 持久化）和
Gateway 的 GatewaySessionManager（纯内存）是独立系统。
此模块专注于项目上下文相关的对话，而非通用聊天。
"""
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Any


class SessionStatus(StrEnum):
    ACTIVE = "active"
    ARCHIVED = "archived"
    DELETED = "deleted"


@dataclass
class SessionMetadata:
    title: str = ""
    description: str = ""
    model_id: str = ""
    tags: list[str] = field(default_factory=list)
    status: SessionStatus = SessionStatus.ACTIVE
    starred: bool = False
    pinned: bool = False
    custom_data: dict[str, Any] = field(default_factory=dict)


@dataclass
class SessionMessage:
    id: str = ""
    session_id: str = ""
    role: str = "user"
    content: str = ""
    timestamp: datetime | str = field(default_factory=datetime.now)
    token_count: int = 0
    importance: float = 0.5
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        ts = self.timestamp.isoformat() if isinstance(self.timestamp, datetime) else self.timestamp
        return {
            "id": self.id,
            "session_id": self.session_id,
            "role": self.role,
            "content": self.content,
            "timestamp": ts,
            "token_count": self.token_count,
            "importance": self.importance,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SessionMessage":
        return cls(
            id=data.get("id", ""),
            session_id=data.get("session_id", ""),
            role=data.get("role", "user"),
            content=data.get("content", ""),
            timestamp=data.get("timestamp", datetime.now().isoformat()),
            token_count=data.get("token_count", 0),
            importance=data.get("importance", 0.5),
            metadata=data.get("metadata", {}),
        )


@dataclass
class ChatSession:
    id: str = ""
    metadata: SessionMetadata = field(default_factory=SessionMetadata)
    messages: list[SessionMessage] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    message_count: int = 0
    total_tokens: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "metadata": {
                "title": self.metadata.title,
                "description": self.metadata.description,
                "model_id": self.metadata.model_id,
                "tags": self.metadata.tags,
                "status": self.metadata.status.value,
                "starred": self.metadata.starred,
                "pinned": self.metadata.pinned,
                "custom_data": self.metadata.custom_data,
            },
            "messages": [m.to_dict() for m in self.messages],
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "message_count": self.message_count,
            "total_tokens": self.total_tokens,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ChatSession":
        metadata = data.get("metadata", {})
        return cls(
            id=data.get("id", ""),
            metadata=SessionMetadata(
                title=metadata.get("title", ""),
                description=metadata.get("description", ""),
                model_id=metadata.get("model_id", ""),
                tags=metadata.get("tags", []),
                status=SessionStatus(metadata.get("status", SessionStatus.ACTIVE.value)),
                starred=metadata.get("starred", False),
                pinned=metadata.get("pinned", False),
                custom_data=metadata.get("custom_data", {}),
            ),
            messages=[SessionMessage.from_dict(m) for m in data.get("messages", [])],
            created_at=data.get("created_at", datetime.now().isoformat()),
            updated_at=data.get("updated_at", datetime.now().isoformat()),
            message_count=data.get("message_count", len(data.get("messages", []))),
            total_tokens=data.get("total_tokens", 0),
        )


class SessionStore:
    def __init__(self, storage_path: str | Path = "data/session_store"):
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self._sessions: dict[str, ChatSession] = {}
        self._load()

    def _session_file(self, session_id: str) -> Path:
        return self.storage_path / f"{session_id}.json"

    def _load(self):
        for file_path in self.storage_path.glob("*.json"):
            try:
                self._sessions[file_path.stem] = ChatSession.from_dict(json.loads(file_path.read_text(encoding="utf-8")))
            except Exception:
                continue

    def _save(self, session: ChatSession):
        session.updated_at = datetime.now().isoformat()
        session.message_count = len(session.messages)
        session.total_tokens = sum(msg.token_count for msg in session.messages)
        self._session_file(session.id).write_text(json.dumps(session.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")

    def create_session(self, title: str = "", model_id: str = "", description: str = "", tags: list[str] | None = None, custom_data: dict[str, Any] | None = None) -> ChatSession:
        session_id = f"session_{datetime.now().strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:8]}"
        session = ChatSession(
            id=session_id,
            metadata=SessionMetadata(
                title=title or f"New Chat {datetime.now().strftime('%Y-%m-%d %H:%M')}",
                description=description,
                model_id=model_id,
                tags=tags or [],
                custom_data=custom_data or {},
            ),
        )
        self._sessions[session.id] = session
        self._save(session)
        return session

    def get_session(self, session_id: str, include_messages: bool = True) -> ChatSession | None:
        session = self._sessions.get(session_id)
        if session is None or include_messages:
            return session
        return ChatSession(
            id=session.id,
            metadata=session.metadata,
            messages=[],
            created_at=session.created_at,
            updated_at=session.updated_at,
            message_count=session.message_count,
            total_tokens=session.total_tokens,
        )

    def update_session(self, session_id: str, **updates) -> bool:
        session = self._sessions.get(session_id)
        if not session:
            return False
        for key, value in updates.items():
            if value is None:
                continue
            if hasattr(session.metadata, key):
                setattr(session.metadata, key, value)
        self._save(session)
        return True

    def delete_session(self, session_id: str, soft_delete: bool = True) -> bool:
        session = self._sessions.get(session_id)
        if not session:
            return False
        if soft_delete:
            session.metadata.status = SessionStatus.DELETED
            self._save(session)
        else:
            self._sessions.pop(session_id, None)
            file_path = self._session_file(session_id)
            if file_path.exists():
                file_path.unlink()
        return True

    def restore_session(self, session_id: str) -> ChatSession | None:
        session = self._sessions.get(session_id)
        if not session:
            return None
        session.metadata.status = SessionStatus.ACTIVE
        self._save(session)
        return session

    def archive_session(self, session_id: str) -> bool:
        session = self._sessions.get(session_id)
        if not session:
            return False
        session.metadata.status = SessionStatus.ARCHIVED
        self._save(session)
        return True

    def add_message(self, session_id: str, role: str, content: str, token_count: int = 0, importance: float = 0.5, metadata: dict[str, Any] | None = None) -> SessionMessage | None:
        session = self._sessions.get(session_id)
        if not session:
            return None
        msg = SessionMessage(
            id=f"msg_{uuid.uuid4().hex[:8]}",
            session_id=session_id,
            role=str(role),
            content=content,
            timestamp=datetime.now(),
            token_count=token_count,
            importance=importance,
            metadata=metadata or {},
        )
        session.messages.append(msg)
        self._save(session)
        return msg

    def add_messages_batch(self, session_id: str, messages: list[dict[str, Any]]) -> int:
        count = 0
        for message in messages:
            if self.add_message(
                session_id,
                message.get("role", "user"),
                message.get("content", ""),
                token_count=message.get("token_count", 0),
                importance=message.get("importance", 0.5),
                metadata=message.get("metadata", {}),
            ):
                count += 1
        return count

    def get_messages(self, session_id: str, limit: int | None = None, offset: int = 0, roles: list[str] | None = None) -> list[SessionMessage]:
        session = self._sessions.get(session_id)
        if not session:
            return []
        messages = session.messages
        if roles:
            role_values = {str(role) for role in roles}
            messages = [msg for msg in messages if msg.role in role_values]
        if offset:
            messages = messages[offset:]
        if limit is not None:
            messages = messages[:limit]
        return messages

    def delete_message(self, session_id: str, message_id: str) -> bool:
        session = self._sessions.get(session_id)
        if not session:
            return False
        before = len(session.messages)
        session.messages = [msg for msg in session.messages if msg.id != message_id]
        changed = len(session.messages) != before
        if changed:
            self._save(session)
        return changed

    def search_sessions(self, query: str | None = None, tags: list[str] | None = None, status: SessionStatus | None = None, **_) -> tuple[list[ChatSession], int]:
        sessions = list(self._sessions.values())
        sessions = [s for s in sessions if s.metadata.status != SessionStatus.DELETED]
        if query:
            query_lower = query.lower()
            sessions = [s for s in sessions if query_lower in s.metadata.title.lower() or query_lower in s.metadata.description.lower()]
        if tags:
            sessions = [s for s in sessions if all(tag in s.metadata.tags for tag in tags)]
        if status:
            sessions = [s for s in sessions if s.metadata.status == status]
        return sessions, len(sessions)

    def get_statistics(self) -> dict[str, Any]:
        sessions = list(self._sessions.values())
        return {
            "total_sessions": len(sessions),
            "active_sessions": sum(1 for s in sessions if s.metadata.status == SessionStatus.ACTIVE),
            "archived_sessions": sum(1 for s in sessions if s.metadata.status == SessionStatus.ARCHIVED),
            "deleted_sessions": sum(1 for s in sessions if s.metadata.status == SessionStatus.DELETED),
            "total_messages": sum(len(s.messages) for s in sessions),
            "total_tokens": sum(sum(m.token_count for m in s.messages) for s in sessions),
        }

    def export_session(self, session_id: str, format: str = "json") -> str | None:
        session = self._sessions.get(session_id)
        if not session:
            return None
        if format == "json":
            return json.dumps({"id": session.id, **session.to_dict()}, ensure_ascii=False, indent=2)
        if format == "markdown":
            lines = [f"# {session.metadata.title}", ""]
            for msg in session.messages:
                lines.extend([f"## {msg.role.title()}", "", msg.content, ""])
            return "\n".join(lines)
        return None

    def get_all_tags(self) -> list[dict[str, Any]]:
        counts: dict[str, int] = {}
        for session in self._sessions.values():
            if session.metadata.status == SessionStatus.DELETED:
                continue
            for tag in session.metadata.tags:
                counts[tag] = counts.get(tag, 0) + 1
        return [{"tag": tag, "count": count} for tag, count in sorted(counts.items())]


_session_store: SessionStore | None = None


def get_session_store(storage_path: str | Path = "data/session_store") -> SessionStore:
    global _session_store
    if _session_store is None:
        _session_store = SessionStore(storage_path=storage_path)
    return _session_store


def init_session_store(storage_path: str | Path) -> SessionStore:
    global _session_store
    _session_store = SessionStore(storage_path=storage_path)
    return _session_store
