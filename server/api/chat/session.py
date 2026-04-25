"""Chat session persistence service."""

import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from threading import RLock
from typing import Any

from core.storage import (
    APP_DB_PATH,
    ChatRepository,
    StorageOutboxRepository,
    dual_write_enabled,
    json_fallback_enabled,
    process_json_outbox,
    storage_read_primary,
)

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
        db_path: str = APP_DB_PATH,
        max_sessions: int = 100,
        auto_save: bool = True,
        max_retries: int = 3,
        retry_delay_ms: int = 100,
    ):
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self.db_path = db_path
        self.repository = ChatRepository(db_path)
        self.outbox = StorageOutboxRepository(db_path)
        self.max_sessions = max_sessions
        self.auto_save = auto_save
        self.max_retries = max_retries
        self.retry_delay_ms = retry_delay_ms
        self._lock = RLock()

        self._sessions: dict[str, Session] = {}
        self._memory_cache: dict[str, Session] = {}
        self._pending_writes: list[dict[str, Any]] = []
        self._write_errors = 0

        self._bootstrap_sessions()

    def _bootstrap_sessions(self) -> None:
        loaded_from_sqlite = self._load_sessions_from_sqlite()
        if loaded_from_sqlite:
            return

        if json_fallback_enabled():
            self._load_sessions_from_json()

    def _load_sessions_from_sqlite(self) -> bool:
        try:
            rows = self.repository.list_sessions(limit=self.max_sessions, offset=0)
            for row in rows:
                payload = self.repository.get_session(row["id"])
                if not payload:
                    continue
                session = Session.from_dict(payload)
                self._sessions[session.id] = session
                self._memory_cache[session.id] = session
            return bool(rows)
        except Exception as e:
            logger.warning("Failed to load sessions from SQLite: %s", e)
            return False

    def _load_sessions_from_json(self) -> None:
        for file_path in self.storage_path.glob("*.json"):
            try:
                with open(file_path, encoding="utf-8") as f:
                    data = json.load(f)
                session = Session.from_dict(data)
                self._sessions[session.id] = session
                self._memory_cache[session.id] = session
                self.repository.save_session(session)
            except Exception as e:
                logger.warning("Failed to load session %s: %s", file_path, e)

    def _atomic_shadow_write(self, session: Session, retry: bool = True) -> bool:
        if not self.auto_save:
            return True

        attempts = self.max_retries if retry else 1
        for attempt in range(attempts):
            try:
                file_path = self.storage_path / f"{session.id}.json"
                tmp_path = file_path.with_suffix(f".json.tmp.{uuid.uuid4().hex}")
                with open(tmp_path, "w", encoding="utf-8") as f:
                    json.dump(session.to_dict(), f, ensure_ascii=False, indent=2)
                    f.flush()
                tmp_path.replace(file_path)
                self._write_errors = 0
                return True
            except Exception as e:
                self._write_errors += 1
                logger.warning("Failed to save session %s (%s/%s): %s", session.id, attempt + 1, attempts, e)

        self._pending_writes.append({"session_id": session.id, "session": session.to_dict(), "ts": datetime.now().isoformat()})
        return False

    def _enqueue_shadow_write(self, session: Session) -> str:
        file_path = self.storage_path / f"{session.id}.json"
        return self.outbox.enqueue(
            task_type="json_shadow_write",
            target=str(file_path),
            payload=session.to_dict(),
            task_id=f"json_session_{session.id}",
        )

    def _shadow_write_with_outbox(self, session: Session, retry: bool = True) -> None:
        task_id = self._enqueue_shadow_write(session)
        if self._atomic_shadow_write(session, retry=retry):
            self.outbox.mark_done(task_id)
        else:
            self.outbox.mark_failed(task_id, f"Failed to shadow-write session {session.id}")

    def replay_pending_writes(self) -> int:
        replayed = 0
        pending = list(self._pending_writes)
        self._pending_writes.clear()
        for item in pending:
            try:
                if self._atomic_shadow_write(Session.from_dict(item["session"]), retry=True):
                    replayed += 1
                else:
                    self._pending_writes.append(item)
            except Exception:
                self._pending_writes.append(item)
        return replayed

    def _save_session(self, session: Session, retry: bool = True) -> None:
        self.repository.save_session(session)
        self._memory_cache[session.id] = session
        if dual_write_enabled():
            self._shadow_write_with_outbox(session, retry=retry)

    def append_message(self, session_id: str, message: Message) -> bool:
        with self._lock:
            session = self.get_session(session_id)
            if not session:
                return False
            if not any(existing.id == message.id for existing in session.messages):
                session.messages.append(message)
            session.message_count = len(session.messages)
            session.updated_at = datetime.now()
            self.repository.append_message(session_id, message)
            self.repository.update_session_header(session, message_count=session.message_count)
            self._memory_cache[session_id] = session
            self._sessions[session_id] = session
            if dual_write_enabled():
                self._shadow_write_with_outbox(session)
            return True

    def clear_session_messages(self, session_id: str) -> bool:
        with self._lock:
            session = self.get_session(session_id)
            if not session:
                return False
            session.clear_messages()
            cleared = self.repository.clear_messages(session_id)
            self.repository.update_session_header(session, message_count=0)
            self._memory_cache[session_id] = session
            self._sessions[session_id] = session
            if dual_write_enabled():
                self._shadow_write_with_outbox(session)
            return cleared

    def replace_session_messages(self, session_id: str, messages: list[dict[str, Any]]) -> bool:
        with self._lock:
            session = self.get_session(session_id)
            if not session:
                return False
            session.messages = [Message.from_dict(message) for message in messages]
            session.message_count = len(session.messages)
            session.updated_at = datetime.now()
            self.repository.replace_messages(session_id, [message.to_dict() for message in session.messages])
            self.repository.update_session_header(session, message_count=session.message_count)
            self._memory_cache[session_id] = session
            self._sessions[session_id] = session
            if dual_write_enabled():
                self._shadow_write_with_outbox(session)
            return True

    def update_message(
        self,
        session_id: str,
        message_id: str,
        *,
        content: str | None = None,
        metadata: dict[str, Any] | None = None,
        role: str | None = None,
    ) -> Message | None:
        with self._lock:
            session = self.get_session(session_id)
            if not session:
                return None
            target = next((message for message in session.messages if message.id == message_id), None)
            if not target:
                return None
            if role is not None:
                target.role = role
            if content is not None:
                target.content = content
            if metadata is not None:
                target.metadata = metadata
            session.updated_at = datetime.now()
            updated = self.repository.update_message(
                session_id,
                message_id,
                content=content,
                metadata=metadata,
                role=role,
            )
            if not updated:
                return None
            self.repository.update_session_header(session, message_count=session.message_count)
            self._memory_cache[session_id] = session
            self._sessions[session_id] = session
            if dual_write_enabled():
                self._shadow_write_with_outbox(session)
            return target

    def delete_message(self, session_id: str, message_id: str) -> bool:
        with self._lock:
            session = self.get_session(session_id)
            if not session:
                return False
            original_count = len(session.messages)
            session.messages = [message for message in session.messages if message.id != message_id]
            if len(session.messages) == original_count:
                return False
            session.message_count = len(session.messages)
            session.updated_at = datetime.now()
            deleted = self.repository.delete_message(session_id, message_id)
            if not deleted:
                return False
            self.repository.update_session_header(session, message_count=session.message_count)
            self._memory_cache[session_id] = session
            self._sessions[session_id] = session
            if dual_write_enabled():
                self._shadow_write_with_outbox(session)
            return True

    def process_shadow_outbox(self, limit: int = 100) -> dict[str, int]:
        return process_json_outbox(self.db_path, limit=limit)

    def create_session(self, title: str = "New Chat", metadata: dict[str, Any] | None = None) -> Session:
        with self._lock:
            if len(self._sessions) >= self.max_sessions:
                self._evict_oldest()

            session = Session(title=title, metadata=metadata or {})
            self._sessions[session.id] = session
            self._memory_cache[session.id] = session
            self._save_session(session)
            return session

    def get_session(self, session_id: str) -> Session | None:
        with self._lock:
            if session_id in self._memory_cache:
                return self._memory_cache[session_id]

            if storage_read_primary() == "sqlite":
                payload = self.repository.get_session(session_id)
                if payload:
                    session = Session.from_dict(payload)
                    self._sessions[session.id] = session
                    self._memory_cache[session.id] = session
                    return session

            session = self._sessions.get(session_id)
            if session:
                return session

            if json_fallback_enabled():
                file_path = self.storage_path / f"{session_id}.json"
                if file_path.exists():
                    try:
                        session = Session.from_dict(json.loads(file_path.read_text(encoding="utf-8")))
                        self._sessions[session.id] = session
                        self._memory_cache[session.id] = session
                        self.repository.save_session(session)
                        return session
                    except Exception as e:
                        logger.warning("Failed to fallback-load session %s: %s", session_id, e)
            return None

    def delete_session(self, session_id: str) -> bool:
        with self._lock:
            deleted = self.repository.delete_session(session_id)
            self._sessions.pop(session_id, None)
            self._memory_cache.pop(session_id, None)

            file_path = self.storage_path / f"{session_id}.json"
            if file_path.exists():
                try:
                    file_path.unlink()
                    deleted = True
                except Exception as e:
                    logger.warning("Failed to delete session file %s: %s", file_path, e)
            return deleted

    def update_session_title(self, session_id: str, title: str) -> bool:
        with self._lock:
            session = self.get_session(session_id)
            if not session:
                return False
            session.title = title
            session.updated_at = datetime.now()
            self._save_session(session)
            return True

    def list_sessions(self, limit: int = 20, offset: int = 0) -> list[Session]:
        with self._lock:
            if storage_read_primary() == "sqlite":
                sessions: list[Session] = []
                for row in self.repository.list_sessions(limit=limit, offset=offset):
                    cached = self._memory_cache.get(row["id"])
                    if cached:
                        sessions.append(cached)
                        continue
                    payload = self.repository.get_session(row["id"]) or row
                    session = Session.from_dict(payload)
                    self._sessions[session.id] = session
                    self._memory_cache[session.id] = session
                    sessions.append(session)
                return sessions

            sorted_sessions = sorted(self._sessions.values(), key=lambda s: s.updated_at, reverse=True)
            return sorted_sessions[offset : offset + limit]

    def get_session_count(self) -> int:
        if storage_read_primary() == "sqlite":
            return self.repository.count_sessions()
        return len(self._sessions)

    def update_session_metadata(self, session_id: str, metadata: dict[str, Any]) -> bool:
        with self._lock:
            session = self.get_session(session_id)
            if not session:
                return False
            session.metadata.update(metadata)
            session.updated_at = datetime.now()
            self._save_session(session)
            return True

    def save_session(self, session_id: str) -> bool:
        with self._lock:
            session = self.get_session(session_id)
            if not session:
                return False
            session.updated_at = datetime.now()
            self._save_session(session)
            return True

    def append_execution_state(self, session_id: str, state: dict[str, Any]) -> bool:
        with self._lock:
            session = self.get_session(session_id)
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
