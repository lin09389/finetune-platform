"""SQLite-backed storage repositories for durable application state."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
import sqlite3
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from core.db_manager import get_db_pool

logger = logging.getLogger(__name__)

APP_DB_PATH = "data/app.db"
MIGRATIONS_DIR = Path(__file__).parent / "migrations"
BACKUP_DIR = Path("data/backups")


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


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def _has_table(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type IN ('table', 'virtual table') AND name = ?",
        (table,),
    ).fetchone()
    return row is not None


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    if column not in _table_columns(conn, table):
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def _ensure_migration_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS migration_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            version TEXT NOT NULL,
            source_path TEXT NOT NULL DEFAULT '',
            checksum TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL,
            migrated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(version, source_path, checksum)
        )
        """
    )
    for column, definition in {
        "name": "TEXT",
        "error": "TEXT",
        "duration_ms": "REAL",
        "applied_at": "TEXT",
    }.items():
        _ensure_column(conn, "migration_runs", column, definition)


def run_schema_migrations(db_path: str = APP_DB_PATH) -> dict[str, Any]:
    """Run versioned schema migrations from core/migrations."""
    MIGRATIONS_DIR.mkdir(parents=True, exist_ok=True)
    migration_files = sorted(MIGRATIONS_DIR.glob("*.sql"))
    applied = 0
    skipped = 0
    failed: list[dict[str, Any]] = []

    with get_db_pool(db_path).get_connection() as conn:
        _ensure_migration_table(conn)
        for file_path in migration_files:
            version = file_path.stem.split("_", 1)[0]
            name = file_path.stem
            sql = file_path.read_text(encoding="utf-8")
            checksum = _sha256_text(sql)
            existing = conn.execute(
                """
                SELECT checksum, status FROM migration_runs
                WHERE version = ? AND source_path = ? AND status = 'ok'
                ORDER BY id DESC LIMIT 1
                """,
                (version, str(file_path)),
            ).fetchone()
            if existing:
                if existing["checksum"] != checksum:
                    message = f"Migration checksum mismatch for {file_path}"
                    failed.append({"version": version, "name": name, "error": message})
                    raise RuntimeError(message)
                skipped += 1
                continue

            started = time.perf_counter()
            try:
                conn.executescript(sql)
                duration_ms = round((time.perf_counter() - started) * 1000, 3)
                conn.execute(
                    """
                    INSERT INTO migration_runs
                        (version, name, source_path, checksum, status, error, duration_ms, migrated_at, applied_at)
                    VALUES (?, ?, ?, ?, 'ok', NULL, ?, ?, ?)
                    """,
                    (version, name, str(file_path), checksum, duration_ms, _utcnow(), _utcnow()),
                )
                applied += 1
            except Exception as exc:
                duration_ms = round((time.perf_counter() - started) * 1000, 3)
                conn.execute(
                    """
                    INSERT OR IGNORE INTO migration_runs
                        (version, name, source_path, checksum, status, error, duration_ms, migrated_at, applied_at)
                    VALUES (?, ?, ?, ?, 'failed', ?, ?, ?, ?)
                    """,
                    (version, name, str(file_path), checksum, str(exc), duration_ms, _utcnow(), _utcnow()),
                )
                failed.append({"version": version, "name": name, "error": str(exc)})
                raise

    return {"applied": applied, "skipped": skipped, "failed": failed}


def init_storage(db_path: str = APP_DB_PATH) -> None:
    """Create the canonical SQLite schema and lightweight compatibility columns."""
    pool = get_db_pool(db_path)
    with pool.get_connection() as conn:
        _ensure_migration_table(conn)
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

            CREATE TABLE IF NOT EXISTS storage_outbox (
                id TEXT PRIMARY KEY,
                type TEXT NOT NULL,
                target TEXT NOT NULL,
                payload TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                retry_count INTEGER NOT NULL DEFAULT 0,
                max_retries INTEGER NOT NULL DEFAULT 5,
                next_retry_at TEXT,
                error TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_storage_outbox_status_next
            ON storage_outbox(status, next_retry_at, updated_at);

            CREATE UNIQUE INDEX IF NOT EXISTS idx_chat_messages_session_id
            ON chat_messages(session_id, id);

            CREATE UNIQUE INDEX IF NOT EXISTS idx_chat_messages_session_ordinal_unique
            ON chat_messages(session_id, ordinal);
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
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_chat_sessions_updated ON chat_sessions(updated_at DESC)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_memory_vector_state ON memory_items(vector_state, updated_at)")
        _ensure_memory_fts(conn)

    run_schema_migrations(db_path)


def _ensure_memory_fts(conn: sqlite3.Connection) -> bool:
    try:
        conn.execute(
            """
            CREATE VIRTUAL TABLE IF NOT EXISTS memory_items_fts
            USING fts5(id UNINDEXED, user_id UNINDEXED, content, type, source)
            """
        )
        return True
    except Exception as exc:
        logger.warning("SQLite FTS5 unavailable, memory text search will use LIKE fallback: %s", exc)
        return False


def _memory_fts_available(conn: sqlite3.Connection) -> bool:
    if not _has_table(conn, "memory_items_fts"):
        return _ensure_memory_fts(conn)
    return True


class ChatRepository:
    def __init__(self, db_path: str = APP_DB_PATH):
        self.db_path = db_path
        init_storage(db_path)

    def save_session(self, session: Any) -> None:
        payload = session.to_dict()
        messages = payload.get("messages", [])
        now = _utcnow()
        with get_db_pool(self.db_path).get_connection() as conn:
            self._upsert_session_header(conn, payload, message_count=len(messages), now=now)
            self._replace_messages(conn, payload["id"], messages, now=now)

    def update_session_header(self, session: Any, message_count: int | None = None) -> None:
        payload = session.to_dict() if hasattr(session, "to_dict") else dict(session)
        with get_db_pool(self.db_path).get_connection() as conn:
            self._upsert_session_header(conn, payload, message_count=message_count, now=_utcnow())

    def append_message(self, session_id: str, message: Any) -> int:
        payload = message.to_dict() if hasattr(message, "to_dict") else dict(message)
        now = _utcnow()
        with get_db_pool(self.db_path).get_connection() as conn:
            row = conn.execute(
                "SELECT id FROM chat_sessions WHERE id = ? AND deleted_at IS NULL",
                (session_id,),
            ).fetchone()
            if not row:
                raise KeyError(f"Session not found: {session_id}")

            ordinal_row = conn.execute(
                "SELECT COALESCE(MAX(ordinal), -1) + 1 AS next_ordinal FROM chat_messages WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            ordinal = int(ordinal_row["next_ordinal"] if ordinal_row else 0)
            conn.execute(
                """
                INSERT INTO chat_messages
                    (id, session_id, role, content, metadata, created_at, ordinal)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    payload.get("id"),
                    session_id,
                    payload.get("role", ""),
                    payload.get("content", ""),
                    _json_dumps(payload.get("metadata", {})),
                    payload.get("created_at") or now,
                    ordinal,
                ),
            )
            conn.execute(
                """
                UPDATE chat_sessions
                SET message_count = (SELECT COUNT(*) FROM chat_messages WHERE session_id = ?),
                    updated_at = ?
                WHERE id = ?
                """,
                (session_id, now, session_id),
            )
        return ordinal

    def replace_messages(self, session_id: str, messages: list[dict[str, Any]]) -> None:
        with get_db_pool(self.db_path).get_connection() as conn:
            self._replace_messages(conn, session_id, messages, now=_utcnow())

    def update_message(
        self,
        session_id: str,
        message_id: str,
        *,
        content: str | None = None,
        metadata: dict[str, Any] | None = None,
        role: str | None = None,
    ) -> bool:
        assignments: list[str] = []
        values: list[Any] = []
        if role is not None:
            assignments.append("role = ?")
            values.append(role)
        if content is not None:
            assignments.append("content = ?")
            values.append(content)
        if metadata is not None:
            assignments.append("metadata = ?")
            values.append(_json_dumps(metadata))
        if not assignments:
            return False

        now = _utcnow()
        values.extend([session_id, message_id])
        with get_db_pool(self.db_path).get_connection() as conn:
            cursor = conn.execute(
                f"""
                UPDATE chat_messages
                SET {", ".join(assignments)}
                WHERE session_id = ? AND id = ?
                """,
                tuple(values),
            )
            if cursor.rowcount <= 0:
                return False
            conn.execute(
                "UPDATE chat_sessions SET updated_at = ? WHERE id = ? AND deleted_at IS NULL",
                (now, session_id),
            )
        return True

    def delete_message(self, session_id: str, message_id: str) -> bool:
        now = _utcnow()
        with get_db_pool(self.db_path).get_connection() as conn:
            cursor = conn.execute(
                "DELETE FROM chat_messages WHERE session_id = ? AND id = ?",
                (session_id, message_id),
            )
            if cursor.rowcount <= 0:
                return False
            conn.execute(
                """
                UPDATE chat_sessions
                SET message_count = (SELECT COUNT(*) FROM chat_messages WHERE session_id = ?),
                    updated_at = ?
                WHERE id = ? AND deleted_at IS NULL
                """,
                (session_id, now, session_id),
            )
        return True

    def clear_messages(self, session_id: str) -> bool:
        now = _utcnow()
        with get_db_pool(self.db_path).get_connection() as conn:
            exists = conn.execute(
                "SELECT id FROM chat_sessions WHERE id = ? AND deleted_at IS NULL",
                (session_id,),
            ).fetchone()
            if not exists:
                return False
            conn.execute("DELETE FROM chat_messages WHERE session_id = ?", (session_id,))
            conn.execute(
                "UPDATE chat_sessions SET message_count = 0, updated_at = ? WHERE id = ?",
                (now, session_id),
            )
        return True

    def _upsert_session_header(
        self,
        conn: sqlite3.Connection,
        payload: dict[str, Any],
        message_count: int | None = None,
        now: str | None = None,
    ) -> None:
        now = now or _utcnow()
        resolved_count = int(message_count if message_count is not None else payload.get("message_count", 0) or 0)
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
                resolved_count,
                _json_dumps(payload.get("metadata", {})),
                payload.get("created_at") or now,
                payload.get("updated_at") or now,
            ),
        )

    def _replace_messages(
        self,
        conn: sqlite3.Connection,
        session_id: str,
        messages: list[dict[str, Any]],
        now: str | None = None,
    ) -> None:
        now = now or _utcnow()
        conn.execute("DELETE FROM chat_messages WHERE session_id = ?", (session_id,))
        conn.executemany(
            """
            INSERT INTO chat_messages
                (id, session_id, role, content, metadata, created_at, ordinal)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    msg.get("id") or str(uuid.uuid4()),
                    session_id,
                    msg.get("role", ""),
                    msg.get("content", ""),
                    _json_dumps(msg.get("metadata", {})),
                    msg.get("created_at") or now,
                    index,
                )
                for index, msg in enumerate(messages)
            ],
        )
        conn.execute(
            "UPDATE chat_sessions SET message_count = ?, updated_at = ? WHERE id = ?",
            (len(messages), now, session_id),
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

    def session_exists(self, session_id: str, include_deleted: bool = False) -> bool:
        query = "SELECT 1 FROM chat_sessions WHERE id = ?"
        if not include_deleted:
            query += " AND deleted_at IS NULL"
        query += " LIMIT 1"
        with get_db_pool(self.db_path).get_connection() as conn:
            row = conn.execute(query, (session_id,)).fetchone()
        return row is not None

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


class StorageOutboxRepository:
    def __init__(self, db_path: str = APP_DB_PATH):
        self.db_path = db_path
        init_storage(db_path)

    def enqueue(
        self,
        task_type: str,
        target: str,
        payload: dict[str, Any],
        *,
        task_id: str | None = None,
        max_retries: int = 5,
    ) -> str:
        task_id = task_id or f"outbox_{uuid.uuid4().hex}"
        now = _utcnow()
        with get_db_pool(self.db_path).get_connection() as conn:
            conn.execute(
                """
                INSERT INTO storage_outbox
                    (id, type, target, payload, status, retry_count, max_retries, next_retry_at, error, created_at, updated_at)
                VALUES (?, ?, ?, ?, 'pending', 0, ?, NULL, NULL, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    payload=excluded.payload,
                    status='pending',
                    error=NULL,
                    updated_at=excluded.updated_at
                """,
                (task_id, task_type, target, _json_dumps(payload), max_retries, now, now),
            )
        return task_id

    def list_ready(self, task_type: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        now = _utcnow()
        params: list[Any] = []
        where = "status IN ('pending', 'retry') AND (next_retry_at IS NULL OR next_retry_at <= ?)"
        params.append(now)
        if task_type:
            where += " AND type = ?"
            params.append(task_type)
        params.append(limit)
        with get_db_pool(self.db_path).get_connection() as conn:
            rows = conn.execute(
                f"""
                SELECT * FROM storage_outbox
                WHERE {where}
                ORDER BY created_at ASC
                LIMIT ?
                """,
                tuple(params),
            ).fetchall()
        return [self._row_to_task(row) for row in rows]

    def mark_done(self, task_id: str) -> None:
        with get_db_pool(self.db_path).get_connection() as conn:
            conn.execute(
                "UPDATE storage_outbox SET status = 'done', error = NULL, updated_at = ? WHERE id = ?",
                (_utcnow(), task_id),
            )

    def mark_failed(self, task_id: str, error: str, retry_delay_seconds: int | None = None) -> None:
        now = _utcnow()
        with get_db_pool(self.db_path).get_connection() as conn:
            row = conn.execute(
                "SELECT retry_count, max_retries FROM storage_outbox WHERE id = ?",
                (task_id,),
            ).fetchone()
            if not row:
                return
            retry_count = int(row["retry_count"] or 0) + 1
            max_retries = int(row["max_retries"] or 5)
            status = "failed" if retry_count >= max_retries else "retry"
            if retry_delay_seconds is None:
                retry_delay_seconds = min(3600, 2 ** min(retry_count, 10))
            next_retry_at = None
            if status == "retry":
                next_retry_at = datetime.fromtimestamp(time.time() + retry_delay_seconds).isoformat()
            conn.execute(
                """
                UPDATE storage_outbox
                SET status = ?, retry_count = ?, next_retry_at = ?, error = ?, updated_at = ?
                WHERE id = ?
                """,
                (status, retry_count, next_retry_at, error[:1000], now, task_id),
            )

    def counts(self) -> dict[str, int]:
        with get_db_pool(self.db_path).get_connection() as conn:
            rows = conn.execute(
                "SELECT status, COUNT(*) AS count FROM storage_outbox GROUP BY status"
            ).fetchall()
        return {row["status"]: int(row["count"]) for row in rows}

    def _row_to_task(self, row: Any) -> dict[str, Any]:
        return {
            "id": row["id"],
            "type": row["type"],
            "target": row["target"],
            "payload": _json_loads(row["payload"]),
            "status": row["status"],
            "retry_count": row["retry_count"],
            "max_retries": row["max_retries"],
            "next_retry_at": row["next_retry_at"],
            "error": row["error"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }


def process_json_outbox(db_path: str = APP_DB_PATH, limit: int = 100) -> dict[str, int]:
    outbox = StorageOutboxRepository(db_path)
    tasks = outbox.list_ready(task_type="json_shadow_write", limit=limit)
    result = {"attempted": len(tasks), "done": 0, "failed": 0}
    for task in tasks:
        try:
            target = Path(task["target"])
            target.parent.mkdir(parents=True, exist_ok=True)
            tmp_path = target.with_suffix(f"{target.suffix}.tmp.{uuid.uuid4().hex}")
            tmp_path.write_text(json.dumps(task["payload"], ensure_ascii=False, indent=2), encoding="utf-8")
            tmp_path.replace(target)
            outbox.mark_done(task["id"])
            result["done"] += 1
        except Exception as exc:
            outbox.mark_failed(task["id"], str(exc))
            result["failed"] += 1
    return result


def process_storage_outbox(db_path: str = APP_DB_PATH, limit: int = 100) -> dict[str, Any]:
    """Process all storage outbox task types once."""
    json_result = process_json_outbox(db_path=db_path, limit=limit)
    vector_result = {"enabled": False, "attempted": 0, "ready": 0, "failed": 0, "deleted": 0}
    try:
        from memory.memory_service import get_memory_service

        vector_result = get_memory_service().process_vector_outbox(limit=limit)
    except Exception as exc:
        logger.warning("Vector outbox processing failed: %s", exc)
        vector_result = {
            "enabled": False,
            "attempted": 0,
            "ready": 0,
            "failed": 1,
            "deleted": 0,
            "error": str(exc),
        }
    return {"json": json_result, "vector": vector_result}


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
            self._sync_fts(conn, payload)
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
        query = (query or "").strip()
        if not query:
            return self.list(user_id=user_id, memory_type=memory_type, limit=top_k)

        with get_db_pool(self.db_path).get_connection() as conn:
            if _memory_fts_available(conn):
                try:
                    rows = self._search_text_fts(conn, query, user_id, top_k, memory_type)
                    if rows:
                        return rows
                except Exception as exc:
                    logger.warning("FTS memory search failed, falling back to LIKE: %s", exc)
            return self._search_text_like(conn, query, user_id, top_k, memory_type)

    def _search_text_fts(
        self,
        conn: sqlite3.Connection,
        query: str,
        user_id: str,
        top_k: int,
        memory_type: str | None,
    ) -> list[dict[str, Any]]:
        fts_query = " OR ".join(part.replace('"', '""') for part in query.split()) or query.replace('"', '""')
        params: list[Any] = [fts_query, user_id]
        type_clause = ""
        if memory_type:
            type_clause = "AND m.type = ?"
            params.append(memory_type)
        params.append(top_k)
        rows = conn.execute(
            f"""
            SELECT m.*, bm25(memory_items_fts) AS score
            FROM memory_items_fts
            JOIN memory_items m ON m.id = memory_items_fts.id
            WHERE memory_items_fts MATCH ?
              AND m.user_id = ?
              AND m.deleted_at IS NULL
              {type_clause}
            ORDER BY score ASC, m.importance DESC, m.updated_at DESC
            LIMIT ?
            """,
            tuple(params),
        ).fetchall()
        memories = [self._row_to_memory(row) for row in rows]
        for index, memory in enumerate(memories):
            memory["relevance"] = max(0.0, 1.0 - (index * 0.05))
        return memories

    def _search_text_like(
        self,
        conn: sqlite3.Connection,
        query: str,
        user_id: str,
        top_k: int,
        memory_type: str | None,
    ) -> list[dict[str, Any]]:
        params: list[Any] = [user_id, f"%{query}%"]
        type_clause = ""
        if memory_type:
            type_clause = "AND type = ?"
            params.append(memory_type)
        params.append(top_k)
        rows = conn.execute(
            f"""
            SELECT * FROM memory_items
            WHERE user_id = ?
              AND deleted_at IS NULL
              AND content LIKE ?
              {type_clause}
            ORDER BY importance DESC, updated_at DESC
            LIMIT ?
            """,
            tuple(params),
        ).fetchall()
        memories = [self._row_to_memory(row) for row in rows]
        for memory in memories:
            memory["relevance"] = 1.0 if query.lower() in memory["content"].lower() else 0.5
        return memories

    def delete(self, memory_id: str, user_id: str = "default") -> bool:
        with get_db_pool(self.db_path).get_connection() as conn:
            cursor = conn.execute(
                "UPDATE memory_items SET deleted_at = ?, updated_at = ? WHERE id = ? AND user_id = ? AND deleted_at IS NULL",
                (_utcnow(), _utcnow(), memory_id, user_id),
            )
            self._delete_fts(conn, memory_id)
        return cursor.rowcount > 0

    def clear_user(self, user_id: str = "default") -> int:
        with get_db_pool(self.db_path).get_connection() as conn:
            cursor = conn.execute(
                "UPDATE memory_items SET deleted_at = ?, updated_at = ? WHERE user_id = ? AND deleted_at IS NULL",
                (_utcnow(), _utcnow(), user_id),
            )
            if _memory_fts_available(conn):
                conn.execute("DELETE FROM memory_items_fts WHERE user_id = ?", (user_id,))
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

    def _sync_fts(self, conn: sqlite3.Connection, payload: dict[str, Any]) -> None:
        if not _memory_fts_available(conn):
            return
        self._delete_fts(conn, payload["id"])
        conn.execute(
            """
            INSERT INTO memory_items_fts (id, user_id, content, type, source)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                payload["id"],
                payload["user_id"],
                payload["content"],
                payload["type"],
                payload["source"],
            ),
        )

    def _delete_fts(self, conn: sqlite3.Connection, memory_id: str) -> None:
        if _memory_fts_available(conn):
            conn.execute("DELETE FROM memory_items_fts WHERE id = ?", (memory_id,))


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
            session_id = str(payload.get("id", "")).strip()
            if session_id and chat_repo.session_exists(session_id, include_deleted=True):
                _record_migration("json_sessions_v1", file_path, checksum, "ok", db_path)
                continue
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
    schema_error: str | None = None
    try:
        init_storage(db_path)
    except Exception as exc:
        schema_error = str(exc)
        logger.warning("Storage init failed while collecting status: %s", exc)
    with get_db_pool(db_path).get_connection() as conn:
        migrations = conn.execute(
            "SELECT status, COUNT(*) AS count FROM migration_runs GROUP BY status"
        ).fetchall()
        schema_migrations = conn.execute(
            """
            SELECT version, name, checksum, status, error, duration_ms, applied_at
            FROM migration_runs
            WHERE source_path LIKE '%.sql'
            ORDER BY version ASC, id ASC
            """
        ).fetchall()
        pending = conn.execute(
            """
            SELECT COUNT(*) AS count FROM memory_items
            WHERE deleted_at IS NULL AND vector_state IN ('pending', 'failed')
            """
        ).fetchone()
        table_counts = {}
        for table in ["chat_sessions", "chat_messages", "chat_shares", "memory_items", "audit_logs", "storage_outbox"]:
            try:
                row = conn.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()
                table_counts[table] = int(row["count"] if row else 0)
            except Exception:
                table_counts[table] = 0
        fts_available = _memory_fts_available(conn)
        journal_mode = conn.execute("PRAGMA journal_mode").fetchone()
        foreign_keys = conn.execute("PRAGMA foreign_keys").fetchone()
        failed_schema_rows = conn.execute(
            """
            SELECT version, name, source_path, error
            FROM migration_runs
            WHERE source_path LIKE '%.sql' AND status = 'failed'
            ORDER BY id DESC
            LIMIT 5
            """
        ).fetchall()
        recent_data_migrations = conn.execute(
            """
            SELECT version, source_path, checksum, status, error, migrated_at
            FROM migration_runs
            WHERE source_path NOT LIKE '%.sql'
            ORDER BY id DESC
            LIMIT 10
            """
        ).fetchall()
        outbox_rows = conn.execute(
            "SELECT status, COUNT(*) AS count FROM storage_outbox GROUP BY status"
        ).fetchall()
    db_file = Path(db_path)
    wal_file = Path(f"{db_path}-wal")
    outbox_counts = {row["status"]: int(row["count"]) for row in outbox_rows}
    failed_schema = [
        {
            "version": row["version"],
            "name": row["name"],
            "source_path": row["source_path"],
            "error": row["error"],
        }
        for row in failed_schema_rows
    ]
    schema_health = "ok" if not schema_error and not failed_schema else "failed"
    outbox_failed = int(outbox_counts.get("failed", 0))
    outbox_pending = int(outbox_counts.get("pending", 0)) + int(outbox_counts.get("retry", 0))
    backup_dir = BACKUP_DIR
    backups = sorted(backup_dir.glob("app-*.db")) if backup_dir.exists() else []
    last_backup = str(backups[-1]) if backups else None
    return {
        "db_path": db_path,
        "dual_write_enabled": dual_write_enabled(),
        "read_primary": storage_read_primary(),
        "json_fallback_enabled": json_fallback_enabled(),
        "vector_reconcile_enabled": vector_reconcile_enabled(),
        "json_migrate_on_startup": storage_json_migrate_on_startup(),
        "schema_health": schema_health,
        "schema_error": schema_error,
        "schema_failures": failed_schema,
        "outbox_health": "failed" if outbox_failed else ("pending" if outbox_pending else "ok"),
        "migration_runs": {row["status"]: row["count"] for row in migrations},
        "data_migrations": [
            {
                "version": row["version"],
                "source_path": row["source_path"],
                "checksum": row["checksum"],
                "status": row["status"],
                "error": row["error"],
                "migrated_at": row["migrated_at"],
            }
            for row in recent_data_migrations
        ],
        "schema_migrations": [
            {
                "version": row["version"],
                "name": row["name"],
                "checksum": row["checksum"],
                "status": row["status"],
                "error": row["error"],
                "duration_ms": row["duration_ms"],
                "applied_at": row["applied_at"],
            }
            for row in schema_migrations
        ],
        "outbox": outbox_counts,
        "tables": table_counts,
        "sqlite": {
            "db_size_bytes": db_file.stat().st_size if db_file.exists() else 0,
            "wal_size_bytes": wal_file.stat().st_size if wal_file.exists() else 0,
            "journal_mode": journal_mode[0] if journal_mode else None,
            "foreign_keys": bool(foreign_keys[0]) if foreign_keys else None,
            "fts5_available": fts_available,
        },
        "last_backup": last_backup,
        "pending_vector_items": int(pending["count"] if pending else 0),
    }


def checkpoint_storage(db_path: str = APP_DB_PATH) -> dict[str, Any]:
    init_storage(db_path)
    wal_file = Path(f"{db_path}-wal")
    before_size = wal_file.stat().st_size if wal_file.exists() else 0
    conn = sqlite3.connect(db_path, timeout=5.0, isolation_level=None)
    try:
        rows = conn.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchall()
    finally:
        conn.close()
    after_size = wal_file.stat().st_size if wal_file.exists() else 0
    return {
        "checkpoint": [tuple(row) for row in rows],
        "wal_size_before_bytes": before_size,
        "wal_size_after_bytes": after_size,
    }


def check_storage(db_path: str = APP_DB_PATH, initialize: bool = True) -> dict[str, Any]:
    if initialize:
        init_storage(db_path)
    with get_db_pool(db_path).get_connection() as conn:
        integrity_rows = conn.execute("PRAGMA integrity_check").fetchall()
        foreign_key_rows = conn.execute("PRAGMA foreign_key_check").fetchall()
    integrity = [row[0] for row in integrity_rows]
    foreign_key_errors = [tuple(row) for row in foreign_key_rows]
    ok = integrity == ["ok"] and not foreign_key_errors
    return {
        "status": "ok" if ok else "failed",
        "integrity_check": integrity,
        "foreign_key_check": foreign_key_errors,
    }


def backup_storage(db_path: str = APP_DB_PATH, backup_dir: str | Path = BACKUP_DIR) -> dict[str, Any]:
    init_storage(db_path)
    checkpoint = checkpoint_storage(db_path)
    source = Path(db_path)
    backup_root = Path(backup_dir)
    backup_root.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    destination = backup_root / f"app-{timestamp}.db"
    shutil.copy2(source, destination)
    return {
        "backup_path": str(destination),
        "size_bytes": destination.stat().st_size,
        "checkpoint": checkpoint,
        "integrity": check_storage(str(destination), initialize=False),
    }


def dual_write_enabled() -> bool:
    return _env_bool("STORAGE_DUAL_WRITE_ENABLED", True)


def storage_read_primary() -> str:
    return _env_str("STORAGE_READ_PRIMARY", "sqlite").lower()


def json_fallback_enabled() -> bool:
    return _env_bool("STORAGE_JSON_FALLBACK", True)


def vector_reconcile_enabled() -> bool:
    return _env_bool("VECTOR_RECONCILE_ENABLED", True)


def storage_json_migrate_on_startup() -> bool:
    return _env_bool("STORAGE_JSON_MIGRATE_ON_STARTUP", False)


def storage_outbox_worker_enabled() -> bool:
    return _env_bool("STORAGE_OUTBOX_WORKER_ENABLED", True)


def storage_outbox_worker_interval() -> float:
    try:
        return float(_env_str("STORAGE_OUTBOX_WORKER_INTERVAL", "30"))
    except ValueError:
        return 30.0


def storage_outbox_worker_batch_size() -> int:
    try:
        return int(_env_str("STORAGE_OUTBOX_WORKER_BATCH_SIZE", "100"))
    except ValueError:
        return 100


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
            INSERT OR IGNORE INTO migration_runs (version, name, source_path, checksum, status, error, migrated_at, applied_at)
            VALUES (?, ?, ?, ?, ?, NULL, ?, ?)
            """,
            (version, version, str(path), checksum, status, _utcnow(), _utcnow()),
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
