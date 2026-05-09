from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any

from core.db_manager import get_db_pool, validate_column_names
from core.storage import APP_DB_PATH


def _now() -> str:
    return datetime.now().isoformat()


def _json(value: Any) -> str:
    return json.dumps(value if value is not None else {}, ensure_ascii=False)


def _load(value: str | None, default: Any = None) -> Any:
    if not value:
        return {} if default is None else default
    try:
        return json.loads(value)
    except Exception:
        return {} if default is None else default


def _row(row: Any | None) -> dict[str, Any] | None:
    if row is None:
        return None
    data = dict(row)
    for key in ("metadata", "payload"):
        if key in data:
            data[key] = _load(data.get(key))
    return data


class AgentSessionRepository:
    def __init__(self, db_path: str = APP_DB_PATH):
        self.db_path = db_path
        self.ensure_schema()

    def ensure_schema(self) -> None:
        get_db_pool(self.db_path).safe_execute_script(
                """
                CREATE TABLE IF NOT EXISTS agent_sessions (
                    id TEXT PRIMARY KEY,
                    chat_session_id TEXT,
                    agent_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    title TEXT NOT NULL,
                    project_path TEXT,
                    provider TEXT,
                    model TEXT,
                    metadata TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS agent_parts (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    type TEXT NOT NULL,
                    status TEXT,
                    title TEXT,
                    content TEXT,
                    payload TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS agent_events (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    message TEXT NOT NULL,
                    payload TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL
                );
                """
            )

    def create_session(self, data: dict[str, Any]) -> dict[str, Any]:
        now = _now()
        session_id = data.get("id") or f"ags_{uuid.uuid4().hex}"
        with get_db_pool(self.db_path).get_connection() as conn:
            conn.execute(
                """
                INSERT INTO agent_sessions
                    (id, chat_session_id, agent_id, status, title, project_path, provider, model, metadata, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    data.get("chat_session_id"),
                    data.get("agent_id") or "build",
                    data.get("status") or "idle",
                    data.get("title") or "Agent Session",
                    data.get("project_path"),
                    data.get("provider"),
                    data.get("model"),
                    _json(data.get("metadata") or {}),
                    now,
                    now,
                ),
            )
        return self.get_session(session_id) or {}

    def get_session(self, session_id: str) -> dict[str, Any] | None:
        with get_db_pool(self.db_path).get_readonly_connection() as conn:
            row = conn.execute("SELECT * FROM agent_sessions WHERE id = ?", (session_id,)).fetchone()
        return _row(row)

    _SESSION_UPDATABLE = {"status", "title", "project_path", "provider", "model", "metadata", "updated_at"}

    def update_session(self, session_id: str, **updates: Any) -> dict[str, Any]:
        if "metadata" in updates:
            updates["metadata"] = _json(updates["metadata"])
        updates["updated_at"] = _now()
        validate_column_names(list(updates.keys()), self._SESSION_UPDATABLE)
        assignments = ", ".join(f"{key} = ?" for key in updates)
        values = list(updates.values()) + [session_id]
        with get_db_pool(self.db_path).get_connection() as conn:
            conn.execute(f"UPDATE agent_sessions SET {assignments} WHERE id = ?", values)
        return self.get_session(session_id) or {}

    def add_part(
        self,
        session_id: str,
        part_type: str,
        *,
        status: str | None = None,
        title: str | None = None,
        content: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        now = _now()
        part_id = f"agp_{uuid.uuid4().hex}"
        with get_db_pool(self.db_path).get_connection() as conn:
            conn.execute(
                """
                INSERT INTO agent_parts (id, session_id, type, status, title, content, payload, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (part_id, session_id, part_type, status, title, content, _json(payload or {}), now, now),
            )
        return self.get_part(part_id) or {}

    _PART_UPDATABLE = {"status", "title", "content", "payload", "type", "updated_at"}

    def update_part(self, part_id: str, **updates: Any) -> dict[str, Any]:
        if "payload" in updates:
            updates["payload"] = _json(updates["payload"])
        updates["updated_at"] = _now()
        validate_column_names(list(updates.keys()), self._PART_UPDATABLE)
        assignments = ", ".join(f"{key} = ?" for key in updates)
        values = list(updates.values()) + [part_id]
        with get_db_pool(self.db_path).get_connection() as conn:
            conn.execute(f"UPDATE agent_parts SET {assignments} WHERE id = ?", values)
        return self.get_part(part_id) or {}

    def get_part(self, part_id: str) -> dict[str, Any] | None:
        with get_db_pool(self.db_path).get_readonly_connection() as conn:
            row = conn.execute("SELECT * FROM agent_parts WHERE id = ?", (part_id,)).fetchone()
        return _row(row)

    def list_parts(self, session_id: str) -> list[dict[str, Any]]:
        with get_db_pool(self.db_path).get_readonly_connection() as conn:
            rows = conn.execute("SELECT * FROM agent_parts WHERE session_id = ? ORDER BY created_at ASC", (session_id,)).fetchall()
        return [_row(row) or {} for row in rows]

    def add_event(self, session_id: str, event_type: str, message: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        event_id = f"age_{uuid.uuid4().hex}"
        now = _now()
        with get_db_pool(self.db_path).get_connection() as conn:
            conn.execute(
                "INSERT INTO agent_events (id, session_id, event_type, message, payload, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (event_id, session_id, event_type, message, _json(payload or {}), now),
            )
        return self.get_event(event_id) or {}

    def get_event(self, event_id: str) -> dict[str, Any] | None:
        with get_db_pool(self.db_path).get_readonly_connection() as conn:
            row = conn.execute("SELECT * FROM agent_events WHERE id = ?", (event_id,)).fetchone()
        return _row(row)

    def list_events(self, session_id: str) -> list[dict[str, Any]]:
        with get_db_pool(self.db_path).get_readonly_connection() as conn:
            rows = conn.execute("SELECT * FROM agent_events WHERE session_id = ? ORDER BY created_at ASC, rowid ASC", (session_id,)).fetchall()
        return [_row(row) or {} for row in rows]

    def list_events_after(self, session_id: str, event_id: str | None) -> list[dict[str, Any]]:
        events = self.list_events(session_id)
        if not event_id:
            return events
        for index, event in enumerate(events):
            if event.get("id") == event_id:
                return events[index + 1 :]
        return events

