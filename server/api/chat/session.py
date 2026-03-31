"""Chat session persistence service."""

import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class Message:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    role: str = ""
    content: str = ""
    created_at: datetime = field(default_factory=datetime.now)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "role": self.role,
            "content": self.content,
            "created_at": self.created_at.isoformat(),
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Message":
        created_at = data.get("created_at")
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at)
        elif created_at is None:
            created_at = datetime.now()
        return cls(
            id=data.get("id", str(uuid.uuid4())),
            role=data.get("role", ""),
            content=data.get("content", ""),
            created_at=created_at,
            metadata=data.get("metadata", {}),
        )


@dataclass
class Session:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    title: str = "New Chat"
    messages: list[Message] = field(default_factory=list)
    message_count: int = 0
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    metadata: dict[str, Any] = field(default_factory=dict)

    def add_message(self, role: str, content: str, metadata: dict[str, Any] | None = None) -> Message:
        message = Message(role=role, content=content, metadata=metadata or {})
        self.messages.append(message)
        self.message_count = len(self.messages)
        self.updated_at = datetime.now()
        return message

    def get_messages(self, limit: int | None = None) -> list[Message]:
        if limit is None:
            return self.messages
        return self.messages[-limit:]

    def clear_messages(self) -> None:
        self.messages.clear()
        self.message_count = 0
        self.updated_at = datetime.now()

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "messages": [m.to_dict() for m in self.messages],
            "message_count": self.message_count,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Session":
        session = cls(
            id=data.get("id", str(uuid.uuid4())),
            title=data.get("title", "New Chat"),
            message_count=data.get("message_count", 0),
            metadata=data.get("metadata", {}),
        )
        session.messages = [Message.from_dict(m) for m in data.get("messages", [])]
        if "created_at" in data and isinstance(data["created_at"], str):
            session.created_at = datetime.fromisoformat(data["created_at"])
        if "updated_at" in data and isinstance(data["updated_at"], str):
            session.updated_at = datetime.fromisoformat(data["updated_at"])
        session.message_count = len(session.messages)
        return session


class SessionManager:
    def __init__(
        self,
        storage_path: str = "data/sessions",
        max_sessions: int = 100,
        auto_save: bool = True,
        max_retries: int = 3,
        retry_delay_ms: int = 100,
    ):
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self.max_sessions = max_sessions
        self.auto_save = auto_save
        self.max_retries = max_retries
        self.retry_delay_ms = retry_delay_ms

        self._sessions: dict[str, Session] = {}
        self._memory_cache: dict[str, Session] = {}
        self._pending_writes: list[dict[str, Any]] = []
        self._write_errors = 0

        self._load_sessions()

    def _load_sessions(self) -> None:
        for file_path in self.storage_path.glob("*.json"):
            try:
                with open(file_path, encoding="utf-8") as f:
                    data = json.load(f)
                session = Session.from_dict(data)
                self._sessions[session.id] = session
                self._memory_cache[session.id] = session
            except Exception as e:
                logger.warning("Failed to load session %s: %s", file_path, e)

    def _save_session(self, session: Session, retry: bool = True) -> None:
        if not self.auto_save:
            return

        self._memory_cache[session.id] = session
        attempts = self.max_retries if retry else 1
        for attempt in range(attempts):
            try:
                file_path = self.storage_path / f"{session.id}.json"
                with open(file_path, "w", encoding="utf-8") as f:
                    json.dump(session.to_dict(), f, ensure_ascii=False, indent=2)
                self._write_errors = 0
                return
            except Exception as e:
                self._write_errors += 1
                logger.warning("Failed to save session %s (%s/%s): %s", session.id, attempt + 1, attempts, e)

        self._pending_writes.append({"session_id": session.id, "session": session.to_dict(), "ts": datetime.now().isoformat()})

    def create_session(self, title: str = "New Chat", metadata: dict[str, Any] | None = None) -> Session:
        if len(self._sessions) >= self.max_sessions:
            self._evict_oldest()

        session = Session(title=title, metadata=metadata or {})
        self._sessions[session.id] = session
        self._memory_cache[session.id] = session
        self._save_session(session)
        return session

    def get_session(self, session_id: str) -> Session | None:
        if session_id in self._memory_cache:
            return self._memory_cache[session_id]
        return self._sessions.get(session_id)

    def delete_session(self, session_id: str) -> bool:
        if session_id not in self._sessions:
            return False
        del self._sessions[session_id]
        self._memory_cache.pop(session_id, None)

        file_path = self.storage_path / f"{session_id}.json"
        if file_path.exists():
            try:
                file_path.unlink()
            except Exception as e:
                logger.warning("Failed to delete session file %s: %s", file_path, e)
        return True

    def update_session_title(self, session_id: str, title: str) -> bool:
        session = self._sessions.get(session_id)
        if not session:
            return False
        session.title = title
        session.updated_at = datetime.now()
        self._save_session(session)
        return True

    def list_sessions(self, limit: int = 20, offset: int = 0) -> list[Session]:
        sorted_sessions = sorted(self._sessions.values(), key=lambda s: s.updated_at, reverse=True)
        return sorted_sessions[offset : offset + limit]

    def get_session_count(self) -> int:
        return len(self._sessions)

    def update_session_metadata(self, session_id: str, metadata: dict[str, Any]) -> bool:
        session = self._sessions.get(session_id)
        if not session:
            return False
        session.metadata.update(metadata)
        session.updated_at = datetime.now()
        self._save_session(session)
        return True

    def append_execution_state(self, session_id: str, state: dict[str, Any]) -> bool:
        session = self._sessions.get(session_id)
        if not session:
            return False

        timeline = session.metadata.get("execution_timeline", [])
        if not isinstance(timeline, list):
            timeline = []
        timeline.append({"timestamp": datetime.now().isoformat(), **state})
        session.metadata["execution_timeline"] = timeline[-200:]
        session.updated_at = datetime.now()
        self._save_session(session)
        return True

    def _evict_oldest(self) -> None:
        if not self._sessions:
            return
        oldest_id = min(self._sessions.keys(), key=lambda sid: self._sessions[sid].updated_at)
        self.delete_session(oldest_id)


_session_manager: SessionManager | None = None


def get_session_manager() -> SessionManager:
    global _session_manager
    if _session_manager is None:
        _session_manager = SessionManager()
    return _session_manager
