from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any

from core.db_manager import get_db_pool, validate_column_names, dynamic_update
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


def _subtask_row(row: Any | None) -> dict[str, Any] | None:
    data = _row(row)
    if data is None:
        return None
    for key in ("input_json", "result_json", "previous_child_session_ids"):
        if key in data:
            data[key] = _load(data.get(key))
    return data


def _subtask_event_row(row: Any | None) -> dict[str, Any] | None:
    data = _row(row)
    if data is None:
        return None
    if "payload_json" in data:
        data["payload"] = _load(data.pop("payload_json"))
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

                CREATE TABLE IF NOT EXISTS agent_subtasks (
                    id TEXT PRIMARY KEY,
                    parent_session_id TEXT NOT NULL,
                    child_session_id TEXT,
                    agent_name TEXT NOT NULL,
                    status TEXT NOT NULL,
                    input_json TEXT NOT NULL DEFAULT '{}',
                    result_json TEXT NOT NULL DEFAULT '{}',
                    error TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    last_checked_at TEXT,
                    started_at TEXT,
                    completed_at TEXT,
                    cancelled_at TEXT,
                    restart_count INTEGER NOT NULL DEFAULT 0,
                    previous_child_session_ids TEXT NOT NULL DEFAULT '[]'
                );

                CREATE TABLE IF NOT EXISTS agent_subtask_events (
                    id TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL,
                    parent_session_id TEXT NOT NULL,
                    child_session_id TEXT,
                    event_type TEXT NOT NULL,
                    status TEXT,
                    message TEXT NOT NULL,
                    payload_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_agent_subtask_events_task_created
                    ON agent_subtask_events(task_id, created_at);
                CREATE INDEX IF NOT EXISTS idx_agent_subtask_events_parent_created
                    ON agent_subtask_events(parent_session_id, created_at);
                CREATE INDEX IF NOT EXISTS idx_agent_subtask_events_type
                    ON agent_subtask_events(event_type);
                """
            )
        self._ensure_subtask_columns()
        self._ensure_subtask_event_columns()

    def _ensure_subtask_columns(self) -> None:
        expected = {
            "started_at": "TEXT",
            "completed_at": "TEXT",
            "cancelled_at": "TEXT",
            "restart_count": "INTEGER NOT NULL DEFAULT 0",
            "previous_child_session_ids": "TEXT NOT NULL DEFAULT '[]'",
        }
        with get_db_pool(self.db_path).get_connection() as conn:
            rows = conn.execute("PRAGMA table_info(agent_subtasks)").fetchall()
            existing = {row["name"] for row in rows}
            for column, definition in expected.items():
                if column not in existing:
                    validate_column_names([column])
                    conn.execute(f"ALTER TABLE agent_subtasks ADD COLUMN {column} {definition}")

    def _ensure_subtask_event_columns(self) -> None:
        expected = {
            "child_session_id": "TEXT",
            "status": "TEXT",
            "payload_json": "TEXT NOT NULL DEFAULT '{}'",
        }
        with get_db_pool(self.db_path).get_connection() as conn:
            rows = conn.execute("PRAGMA table_info(agent_subtask_events)").fetchall()
            existing = {row["name"] for row in rows}
            for column, definition in expected.items():
                if column not in existing:
                    validate_column_names([column])
                    conn.execute(f"ALTER TABLE agent_subtask_events ADD COLUMN {column} {definition}")
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_agent_subtask_events_task_created ON agent_subtask_events(task_id, created_at)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_agent_subtask_events_parent_created ON agent_subtask_events(parent_session_id, created_at)"
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_agent_subtask_events_type ON agent_subtask_events(event_type)")

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
        with get_db_pool(self.db_path).get_connection() as conn:
            dynamic_update(conn, "agent_sessions", "id", session_id, updates, self._SESSION_UPDATABLE)
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
        with get_db_pool(self.db_path).get_connection() as conn:
            dynamic_update(conn, "agent_parts", "id", part_id, updates, self._PART_UPDATABLE)
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

    def create_subtask(self, data: dict[str, Any]) -> dict[str, Any]:
        now = _now()
        task_id = data.get("id") or f"agt_{uuid.uuid4().hex}"
        with get_db_pool(self.db_path).get_connection() as conn:
            conn.execute(
                """
                INSERT INTO agent_subtasks
                    (
                        id, parent_session_id, child_session_id, agent_name, status,
                        input_json, result_json, error, created_at, updated_at, last_checked_at,
                        started_at, completed_at, cancelled_at, restart_count, previous_child_session_ids
                    )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    task_id,
                    data.get("parent_session_id"),
                    data.get("child_session_id"),
                    data.get("agent_name"),
                    data.get("status") or "pending",
                    _json(data.get("input_json") or {}),
                    _json(data.get("result_json") or {}),
                    data.get("error"),
                    now,
                    now,
                    data.get("last_checked_at"),
                    data.get("started_at"),
                    data.get("completed_at"),
                    data.get("cancelled_at"),
                    int(data.get("restart_count") or 0),
                    _json(data.get("previous_child_session_ids") or []),
                ),
            )
        return self.get_subtask(task_id) or {}

    _SUBTASK_UPDATABLE = {
        "child_session_id",
        "status",
        "input_json",
        "result_json",
        "error",
        "updated_at",
        "last_checked_at",
        "started_at",
        "completed_at",
        "cancelled_at",
        "restart_count",
        "previous_child_session_ids",
    }

    def update_subtask(self, task_id: str, **updates: Any) -> dict[str, Any]:
        if "input_json" in updates:
            updates["input_json"] = _json(updates["input_json"])
        if "result_json" in updates:
            updates["result_json"] = _json(updates["result_json"])
        if "previous_child_session_ids" in updates:
            updates["previous_child_session_ids"] = _json(updates["previous_child_session_ids"])
        updates["updated_at"] = _now()
        with get_db_pool(self.db_path).get_connection() as conn:
            dynamic_update(conn, "agent_subtasks", "id", task_id, updates, self._SUBTASK_UPDATABLE)
        return self.get_subtask(task_id) or {}

    def get_subtask(self, task_id: str) -> dict[str, Any] | None:
        with get_db_pool(self.db_path).get_readonly_connection() as conn:
            row = conn.execute("SELECT * FROM agent_subtasks WHERE id = ?", (task_id,)).fetchone()
        return _subtask_row(row)

    def list_subtasks(self, parent_session_id: str, status_filter: str | None = None) -> list[dict[str, Any]]:
        query = "SELECT * FROM agent_subtasks WHERE parent_session_id = ?"
        params: tuple[Any, ...] = (parent_session_id,)
        if status_filter and status_filter != "all":
            query += " AND status = ?"
            params = (parent_session_id, status_filter)
        query += " ORDER BY created_at ASC, rowid ASC"
        with get_db_pool(self.db_path).get_readonly_connection() as conn:
            rows = conn.execute(query, params).fetchall()
        return [_subtask_row(row) or {} for row in rows]

    def list_all_subtasks(self, statuses: set[str] | None = None) -> list[dict[str, Any]]:
        query = "SELECT * FROM agent_subtasks"
        params: tuple[Any, ...] = ()
        if statuses:
            placeholders = ", ".join("?" for _ in statuses)
            query += f" WHERE status IN ({placeholders})"
            params = tuple(sorted(statuses))
        query += " ORDER BY created_at ASC, rowid ASC"
        with get_db_pool(self.db_path).get_readonly_connection() as conn:
            rows = conn.execute(query, params).fetchall()
        return [_subtask_row(row) or {} for row in rows]

    def add_subtask_event(
        self,
        task_id: str,
        parent_session_id: str,
        event_type: str,
        message: str,
        *,
        child_session_id: str | None = None,
        status: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        event_id = f"aste_{uuid.uuid4().hex}"
        now = _now()
        with get_db_pool(self.db_path).get_connection() as conn:
            conn.execute(
                """
                INSERT INTO agent_subtask_events
                    (id, task_id, parent_session_id, child_session_id, event_type, status, message, payload_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (event_id, task_id, parent_session_id, child_session_id, event_type, status, message, _json(payload or {}), now),
            )
        return self.get_subtask_event(event_id) or {}

    def get_subtask_event(self, event_id: str) -> dict[str, Any] | None:
        with get_db_pool(self.db_path).get_readonly_connection() as conn:
            row = conn.execute("SELECT * FROM agent_subtask_events WHERE id = ?", (event_id,)).fetchone()
        return _subtask_event_row(row)

    def list_subtask_events(self, task_id: str, limit: int | None = None) -> list[dict[str, Any]]:
        query = "SELECT * FROM agent_subtask_events WHERE task_id = ? ORDER BY created_at ASC, rowid ASC"
        params: tuple[Any, ...] = (task_id,)
        if limit is not None:
            query += " LIMIT ?"
            params = (task_id, max(1, int(limit)))
        with get_db_pool(self.db_path).get_readonly_connection() as conn:
            rows = conn.execute(query, params).fetchall()
        return [_subtask_event_row(row) or {} for row in rows]

    def list_parent_subtask_events(self, parent_session_id: str, limit: int | None = None) -> list[dict[str, Any]]:
        query = "SELECT * FROM agent_subtask_events WHERE parent_session_id = ? ORDER BY created_at ASC, rowid ASC"
        params: tuple[Any, ...] = (parent_session_id,)
        if limit is not None:
            query += " LIMIT ?"
            params = (parent_session_id, max(1, int(limit)))
        with get_db_pool(self.db_path).get_readonly_connection() as conn:
            rows = conn.execute(query, params).fetchall()
        return [_subtask_event_row(row) or {} for row in rows]

    def summarize_subtask_metrics(self, parent_session_id: str) -> dict[str, Any]:
        tasks = self.list_subtasks(parent_session_id)
        events = self.list_parent_subtask_events(parent_session_id)
        by_status: dict[str, int] = {}
        for task in tasks:
            status = str(task.get("status") or "unknown")
            by_status[status] = by_status.get(status, 0) + 1
        attention = sum(1 for task in tasks if str(task.get("status") or "") in {"failed"})
        recovery_count = sum(1 for event in events if str(event.get("event_type") or "") == "recovered")
        return {
            "total": len(tasks),
            "by_status": by_status,
            "running": by_status.get("running", 0),
            "failed": by_status.get("failed", 0),
            "cancelled": by_status.get("cancelled", 0),
            "completed": by_status.get("completed", 0),
            "attention": attention,
            "recovery_count": recovery_count,
            "event_count": len(events),
            "last_event": events[-1] if events else None,
        }
