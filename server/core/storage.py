"""SQLite-backed storage repositories for durable application state."""

from __future__ import annotations

import hashlib
import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any

from core.db_manager import get_db_pool

logger = logging.getLogger(__name__)

APP_DB_PATH = "data/app.db"


def _json_dumps(value: Any) -> str:
    return json.dumps(value if value is not None else {}, ensure_ascii=False)


def _json_loads(value: str | bytes | None, default: Any = None) -> Any:
    if value in (None, ""):
        return {} if default is None else default
    try:
        return json.loads(value)
    except Exception:
        return {} if default is None else default


def _string_or_json(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False)


def _utcnow() -> str:
    return datetime.now().isoformat()


def _file_checksum(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def init_storage(db_path: str = APP_DB_PATH) -> None:
    """Create the canonical SQLite schema and lightweight compatibility columns."""
    pool = get_db_pool(db_path)
    with pool.get_connection() as conn:
        cursor = conn.cursor()
        cursor.executescript(
            """
            CREATE TABLE IF NOT EXISTS chat_sessions (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                message_count INTEGER DEFAULT 0,
                metadata TEXT DEFAULT '{}',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                deleted_at TEXT
            );

            CREATE TABLE IF NOT EXISTS chat_messages (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                metadata TEXT DEFAULT '{}',
                created_at TEXT NOT NULL,
                ordinal INTEGER NOT NULL,
                FOREIGN KEY (session_id) REFERENCES chat_sessions(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_chat_messages_session_ordinal
            ON chat_messages(session_id, ordinal);

            CREATE TABLE IF NOT EXISTS chat_branches (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                parent_message_id TEXT,
                title TEXT,
                metadata TEXT DEFAULT '{}',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (session_id) REFERENCES chat_sessions(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_chat_branches_session
            ON chat_branches(session_id);

            CREATE TABLE IF NOT EXISTS chat_shares (
                share_id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                title TEXT NOT NULL,
                messages TEXT NOT NULL,
                created_at TEXT NOT NULL,
                expires_at TEXT,
                view_count INTEGER DEFAULT 0,
                is_public INTEGER DEFAULT 1,
                FOREIGN KEY (session_id) REFERENCES chat_sessions(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_chat_shares_session
            ON chat_shares(session_id);

            CREATE TABLE IF NOT EXISTS memory_items (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL DEFAULT 'default',
                content TEXT NOT NULL,
                type TEXT NOT NULL DEFAULT 'knowledge',
                importance REAL DEFAULT 0.5,
                source TEXT DEFAULT 'unknown',
                metadata TEXT DEFAULT '{}',
                vector_state TEXT DEFAULT 'pending',
                access_count INTEGER DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                deleted_at TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_memory_items_user_type
            ON memory_items(user_id, type, deleted_at);

            CREATE INDEX IF NOT EXISTS idx_memory_items_content
            ON memory_items(content);

            CREATE TABLE IF NOT EXISTS audit_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id TEXT UNIQUE,
                trace_id TEXT,
                user_id TEXT,
                session_id TEXT,
                agent_id TEXT,
                source_ip TEXT,
                event_type TEXT,
                severity TEXT,
                resource_type TEXT,
                resource_id TEXT,
                action TEXT,
                details TEXT DEFAULT '{}',
                params TEXT,
                status TEXT,
                result TEXT,
                latency REAL,
                error TEXT,
                metadata TEXT DEFAULT '{}',
                timestamp TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS migration_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                version TEXT NOT NULL,
                source_path TEXT NOT NULL,
                checksum TEXT NOT NULL,
                status TEXT NOT NULL,
                migrated_at TEXT NOT NULL,
                UNIQUE(version, source_path, checksum)
            );
            """
        )

        existing_cols = {row[1] for row in cursor.execute("PRAGMA table_info(audit_logs)").fetchall()}
        for col_name, col_def in {
            "event_id": "TEXT",
            "session_id": "TEXT",
            "agent_id": "TEXT",
            "source_ip": "TEXT",
            "event_type": "TEXT",
            "severity": "TEXT",
            "resource_type": "TEXT",
            "resource_id": "TEXT",
            "details": "TEXT DEFAULT '{}'",
            "result": "TEXT",
            "error_message": "TEXT",
            "duration_ms": "REAL",
            "metadata": "TEXT DEFAULT '{}'",
        }.items():
            if col_name not in existing_cols:
                cursor.execute(f"ALTER TABLE audit_logs ADD COLUMN {col_name} {col_def}")
        cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_audit_logs_event_id ON audit_logs(event_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_audit_logs_event_type ON audit_logs(event_type)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_audit_logs_user_id ON audit_logs(user_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_audit_logs_timestamp ON audit_logs(timestamp)")


class ChatRepository:
    def __init__(self, db_path: str = APP_DB_PATH):
        self.db_path = db_path
        init_storage(db_path)

    def save_session(self, session: Any) -> None:
        payload = session.to_dict()
        messages = payload.get("messages", [])
        now = _utcnow()
        with get_db_pool(self.db_path).get_connection() as conn:
            conn.execute(
                """
                INSERT INTO chat_sessions (id, title, message_count, metadata, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    title=excluded.title,
                    message_count=excluded.message_count,
                    metadata=excluded.metadata,
                    updated_at=excluded.updated_at,
                    deleted_at=NULL
                """,
                (
                    payload["id"],
                    payload.get("title") or "New Chat",
                    len(messages),
                    _json_dumps(payload.get("metadata", {})),
                    payload.get("created_at") or now,
                    payload.get("updated_at") or now,
                ),
            )
            conn.execute("DELETE FROM chat_messages WHERE session_id = ?", (payload["id"],))
            conn.executemany(
                """
                INSERT INTO chat_messages
                    (id, session_id, role, content, metadata, created_at, ordinal)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        msg.get("id"),
                        payload["id"],
                        msg.get("role", ""),
                        msg.get("content", ""),
                        _json_dumps(msg.get("metadata", {})),
                        msg.get("created_at") or now,
                        index,
                    )
                    for index, msg in enumerate(messages)
                ],
            )

    def get_session(self, session_id: str) -> dict[str, Any] | None:
        with get_db_pool(self.db_path).get_connection() as conn:
            row = conn.execute(
                """
                SELECT id, title, message_count, metadata, created_at, updated_at
                FROM chat_sessions
                WHERE id = ? AND deleted_at IS NULL
                """,
                (session_id,),
            ).fetchone()
            if not row:
                return None
            messages = conn.execute(
                """
                SELECT id, role, content, metadata, created_at
                FROM chat_messages
                WHERE session_id = ?
                ORDER BY ordinal ASC, created_at ASC
                """,
                (session_id,),
            ).fetchall()

        return {
            "id": row["id"],
            "title": row["title"],
            "message_count": row["message_count"],
            "metadata": _json_loads(row["metadata"]),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "messages": [
                {
                    "id": msg["id"],
                    "role": msg["role"],
                    "content": msg["content"],
                    "metadata": _json_loads(msg["metadata"]),
                    "created_at": msg["created_at"],
                }
                for msg in messages
            ],
        }

    def list_sessions(self, limit: int = 20, offset: int = 0) -> list[dict[str, Any]]:
        with get_db_pool(self.db_path).get_connection() as conn:
            rows = conn.execute(
                """
                SELECT id, title, message_count, metadata, created_at, updated_at
                FROM chat_sessions
                WHERE deleted_at IS NULL
                ORDER BY updated_at DESC
                LIMIT ? OFFSET ?
                """,
                (limit, offset),
            ).fetchall()
        return [
            {
                "id": row["id"],
                "title": row["title"],
                "message_count": row["message_count"],
                "metadata": _json_loads(row["metadata"]),
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
                "messages": [],
            }
            for row in rows
        ]

    def count_sessions(self) -> int:
        with get_db_pool(self.db_path).get_connection() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS count FROM chat_sessions WHERE deleted_at IS NULL"
            ).fetchone()
        return int(row["count"] if row else 0)

    def delete_session(self, session_id: str) -> bool:
        with get_db_pool(self.db_path).get_connection() as conn:
            cursor = conn.execute(
                "UPDATE chat_sessions SET deleted_at = ? WHERE id = ? AND deleted_at IS NULL",
                (_utcnow(), session_id),
            )
        return cursor.rowcount > 0


class ShareRepository:
    def __init__(self, db_path: str = APP_DB_PATH):
        self.db_path = db_path
        init_storage(db_path)

    def save_share(self, share: dict[str, Any]) -> None:
        with get_db_pool(self.db_path).get_connection() as conn:
            conn.execute(
                """
                INSERT INTO chat_shares
                    (share_id, session_id, title, messages, created_at, expires_at, view_count, is_public)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(share_id) DO UPDATE SET
                    title=excluded.title,
                    messages=excluded.messages,
                    expires_at=excluded.expires_at,
                    view_count=excluded.view_count,
                    is_public=excluded.is_public
                """,
                (
                    share["share_id"],
                    share["session_id"],
                    share.get("title") or "Shared Chat",
                    _json_dumps(share.get("messages", [])),
                    share.get("created_at") or _utcnow(),
                    share.get("expires_at"),
                    int(share.get("view_count", 0)),
                    1 if share.get("is_public", True) else 0,
                ),
            )

    def get_share(self, share_id: str) -> dict[str, Any] | None:
        with get_db_pool(self.db_path).get_connection() as conn:
            row = conn.execute(
                """
                SELECT share_id, session_id, title, messages, created_at, expires_at, view_count, is_public
                FROM chat_shares WHERE share_id = ?
                """,
                (share_id,),
            ).fetchone()
        if not row:
            return None
        return {
            "share_id": row["share_id"],
            "session_id": row["session_id"],
            "title": row["title"],
            "messages": _json_loads(row["messages"], []),
            "created_at": row["created_at"],
            "expires_at": row["expires_at"],
            "view_count": row["view_count"],
            "is_public": bool(row["is_public"]),
        }

    def delete_share(self, share_id: str) -> bool:
        with get_db_pool(self.db_path).get_connection() as conn:
            cursor = conn.execute("DELETE FROM chat_shares WHERE share_id = ?", (share_id,))
        return cursor.rowcount > 0

    def increment_view_count(self, share_id: str) -> int:
        with get_db_pool(self.db_path).get_connection() as conn:
            conn.execute(
                "UPDATE chat_shares SET view_count = view_count + 1 WHERE share_id = ?",
                (share_id,),
            )
            row = conn.execute(
                "SELECT view_count FROM chat_shares WHERE share_id = ?",
                (share_id,),
            ).fetchone()
        return int(row["view_count"] if row else 0)

    def count(self) -> int:
        with get_db_pool(self.db_path).get_connection() as conn:
            row = conn.execute("SELECT COUNT(*) AS count FROM chat_shares").fetchone()
        return int(row["count"] if row else 0)


class MemoryRepository:
    def __init__(self, db_path: str = APP_DB_PATH):
        self.db_path = db_path
        init_storage(db_path)

    def create(self, item: dict[str, Any]) -> dict[str, Any]:
        now = item.get("created_at") or _utcnow()
        payload = {
            "id": item["id"],
            "user_id": item.get("user_id", "default"),
            "content": item.get("content", ""),
            "type": item.get("type", "knowledge"),
            "importance": float(item.get("importance", 0.5) or 0.5),
            "source": item.get("source", "unknown"),
            "metadata": item.get("metadata", {}),
            "vector_state": item.get("vector_state", "pending"),
            "access_count": int(item.get("access_count", 0) or 0),
            "created_at": now,
            "updated_at": item.get("updated_at") or now,
        }
        with get_db_pool(self.db_path).get_connection() as conn:
            conn.execute(
                """
                INSERT INTO memory_items
                    (id, user_id, content, type, importance, source, metadata,
                     vector_state, access_count, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    content=excluded.content,
                    type=excluded.type,
                    importance=excluded.importance,
                    source=excluded.source,
                    metadata=excluded.metadata,
                    vector_state=excluded.vector_state,
                    access_count=excluded.access_count,
                    updated_at=excluded.updated_at,
                    deleted_at=NULL
                """,
                (
                    payload["id"],
                    payload["user_id"],
                    payload["content"],
                    payload["type"],
                    payload["importance"],
                    payload["source"],
                    _json_dumps(payload["metadata"]),
                    payload["vector_state"],
                    payload["access_count"],
                    payload["created_at"],
                    payload["updated_at"],
                ),
            )
        return payload

    def update(self, memory_id: str, user_id: str, **updates: Any) -> dict[str, Any] | None:
        item = self.get(memory_id, user_id=user_id, increment_access=False)
        if not item:
            return None
        item.update({key: value for key, value in updates.items() if value is not None})
        item["updated_at"] = _utcnow()
        return self.create(item)

    def update_vector_state(self, memory_id: str, state: str) -> None:
        with get_db_pool(self.db_path).get_connection() as conn:
            conn.execute(
                "UPDATE memory_items SET vector_state = ?, updated_at = ? WHERE id = ?",
                (state, _utcnow(), memory_id),
            )

    def get(self, memory_id: str, user_id: str = "default", increment_access: bool = True) -> dict[str, Any] | None:
        with get_db_pool(self.db_path).get_connection() as conn:
            row = conn.execute(
                """
                SELECT * FROM memory_items
                WHERE id = ? AND user_id = ? AND deleted_at IS NULL
                """,
                (memory_id, user_id),
            ).fetchone()
            if row and increment_access:
                conn.execute(
                    "UPDATE memory_items SET access_count = access_count + 1, updated_at = ? WHERE id = ?",
                    (_utcnow(), memory_id),
                )
        return self._row_to_memory(row) if row else None

    def get_many(self, ids: list[str], user_id: str = "default") -> list[dict[str, Any]]:
        if not ids:
            return []
        placeholders = ",".join("?" for _ in ids)
        with get_db_pool(self.db_path).get_connection() as conn:
            rows = conn.execute(
                f"""
                SELECT * FROM memory_items
                WHERE user_id = ? AND deleted_at IS NULL AND id IN ({placeholders})
                """,
                (user_id, *ids),
            ).fetchall()
        by_id = {row["id"]: self._row_to_memory(row) for row in rows}
        return [by_id[memory_id] for memory_id in ids if memory_id in by_id]

    def list(self, user_id: str = "default", memory_type: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        params: list[Any] = [user_id]
        where = "user_id = ? AND deleted_at IS NULL"
        if memory_type:
            where += " AND type = ?"
            params.append(memory_type)
        params.append(limit)
        with get_db_pool(self.db_path).get_connection() as conn:
            rows = conn.execute(
                f"""
                SELECT * FROM memory_items
                WHERE {where}
                ORDER BY importance DESC, updated_at DESC
                LIMIT ?
                """,
                tuple(params),
            ).fetchall()
        return [self._row_to_memory(row) for row in rows]

    def search_text(self, query: str, user_id: str = "default", top_k: int = 5, memory_type: str | None = None) -> list[dict[str, Any]]:
        query_lower = query.lower()
        memories = self.list(user_id=user_id, memory_type=memory_type, limit=1000)
        query_words = set(query_lower.split())
        for memory in memories:
            content_lower = memory["content"].lower()
            content_words = set(content_lower.split())
            if query_lower and query_lower in content_lower:
                memory["relevance"] = 1.0
            elif query_words:
                memory["relevance"] = len(query_words & content_words) / len(query_words)
            else:
                memory["relevance"] = 0.0
        memories.sort(key=lambda item: (item.get("relevance", 0), item.get("importance", 0)), reverse=True)
        return memories[:top_k]

    def delete(self, memory_id: str, user_id: str = "default") -> bool:
        with get_db_pool(self.db_path).get_connection() as conn:
            cursor = conn.execute(
                "UPDATE memory_items SET deleted_at = ?, updated_at = ? WHERE id = ? AND user_id = ? AND deleted_at IS NULL",
                (_utcnow(), _utcnow(), memory_id, user_id),
            )
        return cursor.rowcount > 0

    def clear_user(self, user_id: str = "default") -> int:
        with get_db_pool(self.db_path).get_connection() as conn:
            cursor = conn.execute(
                "UPDATE memory_items SET deleted_at = ?, updated_at = ? WHERE user_id = ? AND deleted_at IS NULL",
                (_utcnow(), _utcnow(), user_id),
            )
        return cursor.rowcount

    def pending_vectors(self, limit: int = 100) -> list[dict[str, Any]]:
        with get_db_pool(self.db_path).get_connection() as conn:
            rows = conn.execute(
                """
                SELECT * FROM memory_items
                WHERE deleted_at IS NULL AND vector_state IN ('pending', 'failed')
                ORDER BY updated_at ASC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [self._row_to_memory(row) for row in rows]

    def pending_vector_count(self) -> int:
        with get_db_pool(self.db_path).get_connection() as conn:
            row = conn.execute(
                """
                SELECT COUNT(*) AS count FROM memory_items
                WHERE deleted_at IS NULL AND vector_state IN ('pending', 'failed')
                """
            ).fetchone()
        return int(row["count"] if row else 0)

    def stats(self, user_id: str = "default") -> dict[str, Any]:
        with get_db_pool(self.db_path).get_connection() as conn:
            total = conn.execute(
                "SELECT COUNT(*) AS count FROM memory_items WHERE user_id = ? AND deleted_at IS NULL",
                (user_id,),
            ).fetchone()
            pending = conn.execute(
                """
                SELECT COUNT(*) AS count FROM memory_items
                WHERE user_id = ? AND deleted_at IS NULL AND vector_state IN ('pending', 'failed')
                """,
                (user_id,),
            ).fetchone()
        return {
            "total_memories": int(total["count"] if total else 0),
            "pending_vectors": int(pending["count"] if pending else 0),
        }

    def _row_to_memory(self, row: Any) -> dict[str, Any]:
        return {
            "id": row["id"],
            "user_id": row["user_id"],
            "content": row["content"],
            "type": row["type"],
            "importance": row["importance"],
            "source": row["source"],
            "metadata": _json_loads(row["metadata"]),
            "vector_state": row["vector_state"],
            "storage_mode": "vector" if row["vector_state"] == "ready" else "text_only",
            "access_count": row["access_count"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }


class AuditRepository:
    def __init__(self, db_path: str = APP_DB_PATH):
        self.db_path = db_path
        init_storage(db_path)

    def save_event(self, event: Any) -> None:
        payload = event.to_dict() if hasattr(event, "to_dict") else dict(event)
        details = payload.get("details") or payload.get("params") or {}
        result = _string_or_json(payload.get("result") or payload.get("status"))
        duration_ms = payload.get("duration_ms")
        if duration_ms is None:
            duration_ms = payload.get("latency")
        error_message = _string_or_json(payload.get("error_message") or payload.get("error"))
        with get_db_pool(self.db_path).get_connection() as conn:
            conn.execute(
                """
                INSERT INTO audit_logs
                    (event_id, user_id, session_id, agent_id, source_ip, event_type,
                     severity, resource_type, resource_id, action, details, params,
                     status, result, latency, error, metadata, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(event_id) DO NOTHING
                """,
                (
                    payload.get("id"),
                    payload.get("user_id"),
                    payload.get("session_id"),
                    payload.get("agent_id"),
                    payload.get("source_ip"),
                    payload.get("event_type"),
                    payload.get("severity"),
                    payload.get("resource_type"),
                    payload.get("resource_id"),
                    payload.get("action"),
                    _json_dumps(details),
                    _json_dumps(details),
                    result,
                    result,
                    duration_ms,
                    error_message,
                    _json_dumps(payload.get("metadata", {})),
                    payload.get("timestamp") or _utcnow(),
                ),
            )

    def query_events(self, **filters: Any) -> list[dict[str, Any]]:
        params: list[Any] = []
        where: list[str] = []
        for key, column in {
            "user_id": "user_id",
            "event_type": "event_type",
            "severity": "severity",
            "resource_type": "resource_type",
        }.items():
            value = filters.get(key)
            if value:
                where.append(f"{column} = ?")
                params.append(value.value if hasattr(value, "value") else value)
        if filters.get("start_time"):
            where.append("timestamp >= ?")
            params.append(filters["start_time"].isoformat())
        if filters.get("end_time"):
            where.append("timestamp <= ?")
            params.append(filters["end_time"].isoformat())
        limit = int(filters.get("limit") or 100)
        params.append(limit)
        where_sql = "WHERE " + " AND ".join(where) if where else ""
        with get_db_pool(self.db_path).get_connection() as conn:
            rows = conn.execute(
                f"""
                SELECT * FROM audit_logs
                {where_sql}
                ORDER BY timestamp DESC, id DESC
                LIMIT ?
                """,
                tuple(params),
            ).fetchall()
        return [self._row_to_event_dict(row) for row in rows]

    def stats(self) -> dict[str, Any]:
        with get_db_pool(self.db_path).get_connection() as conn:
            total = conn.execute("SELECT COUNT(*) AS count FROM audit_logs").fetchone()
            severity_rows = conn.execute(
                "SELECT severity, COUNT(*) AS count FROM audit_logs GROUP BY severity"
            ).fetchall()
            bounds = conn.execute(
                "SELECT MIN(timestamp) AS oldest, MAX(timestamp) AS newest FROM audit_logs"
            ).fetchone()
        return {
            "total_events": int(total["count"] if total else 0),
            "severity_distribution": {row["severity"] or "unknown": row["count"] for row in severity_rows},
            "oldest_event": bounds["oldest"] if bounds else None,
            "newest_event": bounds["newest"] if bounds else None,
        }

    def _row_to_event_dict(self, row: Any) -> dict[str, Any]:
        return {
            "id": row["event_id"] or str(row["id"]),
            "event_type": row["event_type"] or "api_call",
            "severity": row["severity"] or "info",
            "timestamp": row["timestamp"],
            "user_id": row["user_id"],
            "session_id": row["session_id"],
            "agent_id": row["agent_id"],
            "source_ip": row["source_ip"],
            "resource_type": row["resource_type"],
            "resource_id": row["resource_id"],
            "action": row["action"],
            "details": _json_loads(row["details"]),
            "result": row["result"] or row["status"],
            "error_message": row["error_message"] or row["error"],
            "duration_ms": row["duration_ms"] if row["duration_ms"] is not None else row["latency"],
            "metadata": _json_loads(row["metadata"]),
        }


def migrate_json_state(db_path: str = APP_DB_PATH, base_dir: str | Path = "data") -> dict[str, int]:
    """Import legacy JSON sessions and shares into SQLite. Safe to rerun."""
    init_storage(db_path)
    base = Path(base_dir)
    migrated = {"sessions": 0, "shares": 0}
    chat_repo = ChatRepository(db_path)
    share_repo = ShareRepository(db_path)

    for file_path in (base / "sessions").glob("*.json"):
        checksum = _file_checksum(file_path)
        if _migration_seen("json_sessions_v1", file_path, checksum, db_path):
            continue
        try:
            payload = json.loads(file_path.read_text(encoding="utf-8"))
            chat_repo.save_session(_DictSession(payload))
            _record_migration("json_sessions_v1", file_path, checksum, "ok", db_path)
            migrated["sessions"] += 1
        except Exception as exc:
            logger.warning("Failed to migrate session %s: %s", file_path, exc)
            _record_migration("json_sessions_v1", file_path, checksum, "failed", db_path)

    for file_path in (base / "share").glob("share_*.json"):
        checksum = _file_checksum(file_path)
        if _migration_seen("json_shares_v1", file_path, checksum, db_path):
            continue
        try:
            payload = json.loads(file_path.read_text(encoding="utf-8"))
            share_repo.save_share(payload)
            _record_migration("json_shares_v1", file_path, checksum, "ok", db_path)
            migrated["shares"] += 1
        except Exception as exc:
            logger.warning("Failed to migrate share %s: %s", file_path, exc)
            _record_migration("json_shares_v1", file_path, checksum, "failed", db_path)

    return migrated


def storage_status(db_path: str = APP_DB_PATH) -> dict[str, Any]:
    init_storage(db_path)
    with get_db_pool(db_path).get_connection() as conn:
        migrations = conn.execute(
            "SELECT status, COUNT(*) AS count FROM migration_runs GROUP BY status"
        ).fetchall()
        pending = conn.execute(
            """
            SELECT COUNT(*) AS count FROM memory_items
            WHERE deleted_at IS NULL AND vector_state IN ('pending', 'failed')
            """
        ).fetchone()
    return {
        "db_path": db_path,
        "dual_write_enabled": dual_write_enabled(),
        "read_primary": storage_read_primary(),
        "json_fallback_enabled": json_fallback_enabled(),
        "vector_reconcile_enabled": vector_reconcile_enabled(),
        "migration_runs": {row["status"]: row["count"] for row in migrations},
        "pending_vector_items": int(pending["count"] if pending else 0),
    }


def dual_write_enabled() -> bool:
    return _env_bool("STORAGE_DUAL_WRITE_ENABLED", True)


def storage_read_primary() -> str:
    return _env_str("STORAGE_READ_PRIMARY", "sqlite").lower()


def json_fallback_enabled() -> bool:
    return _env_bool("STORAGE_JSON_FALLBACK", True)


def vector_reconcile_enabled() -> bool:
    return _env_bool("VECTOR_RECONCILE_ENABLED", True)


def get_storage_status(db_path: str = APP_DB_PATH) -> dict[str, Any]:
    return storage_status(db_path)


ChatShareRepository = ShareRepository


def _migration_seen(version: str, path: Path, checksum: str, db_path: str) -> bool:
    with get_db_pool(db_path).get_connection() as conn:
        row = conn.execute(
            """
            SELECT id FROM migration_runs
            WHERE version = ? AND source_path = ? AND checksum = ? AND status = 'ok'
            """,
            (version, str(path), checksum),
        ).fetchone()
    return row is not None


def _record_migration(version: str, path: Path, checksum: str, status: str, db_path: str) -> None:
    with get_db_pool(db_path).get_connection() as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO migration_runs (version, source_path, checksum, status, migrated_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (version, str(path), checksum, status, _utcnow()),
        )


def _env_bool(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).lower() in {"1", "true", "yes", "on"}


def _env_str(name: str, default: str) -> str:
    return os.getenv(name, default)


class _DictSession:
    def __init__(self, payload: dict[str, Any]):
        self.payload = payload

    def to_dict(self) -> dict[str, Any]:
        return self.payload
