from __future__ import annotations

import json
import logging
import sqlite3
import time
import uuid
from datetime import datetime
from typing import Any

from tool_platform.models import jsonable, redact_json

from agent_session.work_unit import (
    WORK_UNIT_TERMINAL_STATUSES,
    WorkUnit,
    WorkUnitResult,
    parse_work_unit,
    require_work_unit_status_transition,
    serialize_work_unit,
    serialize_work_unit_result,
)
from core.db_manager import dynamic_update, get_db_pool, validate_column_names
from core.storage import APP_DB_PATH

logger = logging.getLogger(__name__)

LEGACY_SUBTASK_RECORD_KIND = "legacy_async_subtask"
WORK_UNIT_RECORD_KIND = "typed_work_unit"
WORK_UNIT_ENVELOPE_SCHEMA_VERSION = 1


class WorkUnitRepositoryError(ValueError):
    """Base class for fail-closed typed WorkUnit persistence errors."""


class WorkUnitIdentityConflict(WorkUnitRepositoryError):
    """Raised when a stable WorkUnit ID is reused for different content."""


class WorkUnitStateConflict(WorkUnitRepositoryError):
    """Raised when an attempt, child revision, or status CAS fails."""


class WorkUnitEventConflict(WorkUnitRepositoryError):
    """Raised when a durable event ID is reused for different content."""


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


def _work_unit_envelope(work_unit: WorkUnit) -> dict[str, Any]:
    return {
        "schema_version": WORK_UNIT_ENVELOPE_SCHEMA_VERSION,
        "type": WORK_UNIT_RECORD_KIND,
        "work_unit": serialize_work_unit(work_unit),
    }


def _parse_work_unit_envelope(raw: object) -> WorkUnit:
    if (
        not isinstance(raw, dict)
        or raw.get("schema_version") != WORK_UNIT_ENVELOPE_SCHEMA_VERSION
        or raw.get("type") != WORK_UNIT_RECORD_KIND
    ):
        raise WorkUnitIdentityConflict("invalid typed WorkUnit envelope")
    try:
        return parse_work_unit(raw.get("work_unit"))
    except Exception as exc:
        raise WorkUnitIdentityConflict("invalid typed WorkUnit payload") from exc


def _validate_work_unit_record(data: dict[str, Any] | None) -> WorkUnit:
    if data is None or data.get("record_kind") != WORK_UNIT_RECORD_KIND:
        raise WorkUnitIdentityConflict("typed WorkUnit record is missing")
    work_unit = _parse_work_unit_envelope(data.get("input_json"))
    if (
        data.get("id") != work_unit.work_unit_id
        or data.get("parent_session_id") != work_unit.parent_session_id
        or data.get("plan_fingerprint") != work_unit.plan_fingerprint
    ):
        raise WorkUnitIdentityConflict("typed WorkUnit row binding is invalid")
    return work_unit


def _safe_work_unit_event_payload(
    *,
    work_unit_id: str,
    attempt: int,
    payload: dict[str, Any] | None,
) -> dict[str, Any]:
    safe_payload = jsonable(redact_json(payload or {}))
    return {
        "schema_version": 1,
        "work_unit_id": work_unit_id,
        "attempt": attempt,
        "data": safe_payload,
    }


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
                    record_kind TEXT NOT NULL DEFAULT 'legacy_async_subtask',
                    plan_fingerprint TEXT,
                    work_unit_attempt INTEGER NOT NULL DEFAULT 0,
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

                CREATE TABLE IF NOT EXISTS agent_training_links (
                    task_id TEXT PRIMARY KEY,
                    proposal_id TEXT NOT NULL UNIQUE,
                    session_id TEXT NOT NULL,
                    owner_id TEXT,
                    part_id TEXT NOT NULL UNIQUE,
                    last_event_sequence INTEGER NOT NULL DEFAULT 0,
                    status TEXT NOT NULL DEFAULT 'queued',
                    sync_failures INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_agent_training_links_active
                    ON agent_training_links(status, updated_at);
                CREATE INDEX IF NOT EXISTS idx_agent_training_links_session
                    ON agent_training_links(session_id);
                """
            )
        self._ensure_subtask_columns()
        self._ensure_subtask_event_columns()
        self._ensure_training_link_columns()

    def _ensure_training_link_columns(self) -> None:
        with get_db_pool(self.db_path).get_connection() as conn:
            rows = conn.execute("PRAGMA table_info(agent_training_links)").fetchall()
            existing = {row["name"] for row in rows}
            if "sync_failures" not in existing:
                conn.execute(
                    "ALTER TABLE agent_training_links ADD COLUMN sync_failures INTEGER NOT NULL DEFAULT 0"
                )

    def _ensure_subtask_columns(self) -> None:
        expected = {
            "started_at": "TEXT",
            "completed_at": "TEXT",
            "cancelled_at": "TEXT",
            "restart_count": "INTEGER NOT NULL DEFAULT 0",
            "previous_child_session_ids": "TEXT NOT NULL DEFAULT '[]'",
            "record_kind": "TEXT NOT NULL DEFAULT 'legacy_async_subtask'",
            "plan_fingerprint": "TEXT",
            "work_unit_attempt": "INTEGER NOT NULL DEFAULT 0",
        }
        with get_db_pool(self.db_path).get_connection() as conn:
            rows = conn.execute("PRAGMA table_info(agent_subtasks)").fetchall()
            existing = {row["name"] for row in rows}
            for column, definition in expected.items():
                if column not in existing:
                    validate_column_names([column])
                    conn.execute(f"ALTER TABLE agent_subtasks ADD COLUMN {column} {definition}")
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_agent_subtasks_work_unit_plan
                ON agent_subtasks(
                    record_kind,
                    parent_session_id,
                    plan_fingerprint,
                    created_at
                )
                """
            )

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

    def run_write_with_retry(self, operation, *, attempts: int = 5, base_delay: float = 0.05) -> Any:
        last_exc: Exception | None = None
        for attempt in range(max(1, attempts)):
            try:
                return operation()
            except sqlite3.OperationalError as exc:
                last_exc = exc
                if "locked" not in str(exc).lower() or attempt >= attempts - 1:
                    raise
                delay = base_delay * (2 ** attempt)
                logger.warning("SQLite write locked; retrying AgentSessionRepository write in %.2fs", delay)
                time.sleep(delay)
        if last_exc:
            raise last_exc
        return operation()

    def list_sessions_by_status(self, statuses: set[str]) -> list[dict[str, Any]]:
        if not statuses:
            return []
        placeholders = ", ".join("?" for _ in statuses)
        with get_db_pool(self.db_path).get_readonly_connection() as conn:
            rows = conn.execute(
                f"SELECT * FROM agent_sessions WHERE status IN ({placeholders}) ORDER BY updated_at ASC",
                tuple(sorted(statuses)),
            ).fetchall()
        return [_row(row) or {} for row in rows]

    def list_sessions(self, limit: int = 100) -> list[dict[str, Any]]:
        with get_db_pool(self.db_path).get_readonly_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM agent_sessions ORDER BY updated_at DESC LIMIT ?",
                (max(1, min(int(limit), 500)),),
            ).fetchall()
        return [_row(row) or {} for row in rows]

    def list_sessions_for_workspace(self, workspace_id: str, owner_id: str, limit: int = 100) -> list[dict[str, Any]]:
        """Return only sessions owned by ``owner_id`` for a single Workspace.

        Workspace and owner live in JSON metadata for backwards compatibility,
        so this method applies the authorization predicate before exposing any
        row to callers.
        """
        bounded_limit = max(1, min(int(limit), 100))
        with get_db_pool(self.db_path).get_readonly_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM agent_sessions ORDER BY updated_at DESC",
            ).fetchall()
        matches: list[dict[str, Any]] = []
        for row in rows:
            session = _row(row) or {}
            metadata = session.get("metadata") if isinstance(session.get("metadata"), dict) else {}
            workspace = metadata.get("workspace") if isinstance(metadata.get("workspace"), dict) else {}
            if str(workspace.get("id") or "") != workspace_id:
                continue
            if str(metadata.get("user_id") or "") != owner_id:
                continue
            matches.append(session)
            if len(matches) >= bounded_limit:
                break
        return matches

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

    def update_part_if_status(self, part_id: str, expected_status: str, **updates: Any) -> dict[str, Any] | None:
        if "payload" in updates:
            updates["payload"] = _json(updates["payload"])
        updates["updated_at"] = _now()
        validate_column_names(updates.keys(), self._PART_UPDATABLE)
        assignments = ", ".join(f"{key} = ?" for key in updates)
        values = list(updates.values()) + [part_id, expected_status]
        with get_db_pool(self.db_path).get_connection() as conn:
            changed = conn.execute(
                f"UPDATE agent_parts SET {assignments} WHERE id = ? AND status = ?",
                values,
            ).rowcount
        return self.get_part(part_id) if changed else None

    def get_part(self, part_id: str) -> dict[str, Any] | None:
        with get_db_pool(self.db_path).get_readonly_connection() as conn:
            row = conn.execute("SELECT * FROM agent_parts WHERE id = ?", (part_id,)).fetchone()
        return _row(row)

    def list_parts(self, session_id: str) -> list[dict[str, Any]]:
        with get_db_pool(self.db_path).get_readonly_connection() as conn:
            rows = conn.execute("SELECT * FROM agent_parts WHERE session_id = ? ORDER BY created_at ASC", (session_id,)).fetchall()
        return [_row(row) or {} for row in rows]

    def create_training_link(
        self,
        *,
        session_id: str,
        owner_id: str | None,
        proposal_id: str,
        task_id: str,
    ) -> dict[str, Any]:
        """Atomically create the one timeline card bound to an approved task.

        The Worker never calls this method.  Repeating the identical request is
        safe; attempting to rebind either task or proposal is rejected.
        """
        session_id, proposal_id, task_id = (str(value or "").strip() for value in (session_id, proposal_id, task_id))
        owner_id = str(owner_id or "").strip() or None
        if not session_id or not proposal_id or not task_id:
            raise ValueError("Training links require session, proposal, and task identifiers")
        now = _now()

        def operation() -> dict[str, Any]:
            with get_db_pool(self.db_path).get_connection() as conn:
                session = conn.execute("SELECT metadata FROM agent_sessions WHERE id = ?", (session_id,)).fetchone()
                if session is None:
                    raise ValueError("Agent session not found")
                metadata = _load(session["metadata"], {})
                session_owner = str(metadata.get("user_id") or "").strip() or None
                if session_owner != owner_id:
                    raise PermissionError("Training link owner does not match Agent session owner")
                if metadata.get("task_mode") not in {"train", "hybrid"}:
                    raise ValueError("Only Train or Hybrid Agent sessions can link training tasks")
                existing = conn.execute(
                    "SELECT * FROM agent_training_links WHERE task_id = ? OR proposal_id = ?",
                    (task_id, proposal_id),
                ).fetchone()
                if existing is not None:
                    link = dict(existing)
                    if (link["task_id"], link["proposal_id"], link["session_id"], link["owner_id"]) != (
                        task_id, proposal_id, session_id, owner_id,
                    ):
                        raise ValueError("Training task or proposal is already bound to another Agent session")
                    return _row(existing) or {}
                part_id = f"agp_{uuid.uuid4().hex}"
                activity = {
                    "kind": "submission",
                    "source_tool": "submit_training",
                    "proposal_id": proposal_id,
                    "task_id": task_id,
                    "status": "queued",
                    "summary": "Training task queued.",
                }
                conn.execute(
                    """INSERT INTO agent_parts (id, session_id, type, status, title, content, payload, created_at, updated_at)
                       VALUES (?, ?, 'tool_result', 'running', ?, ?, ?, ?, ?)""",
                    (part_id, session_id, "训练运行", "Training task queued.", _json({"tool": "submit_training", "training_activity": activity}), now, now),
                )
                conn.execute(
                    """INSERT INTO agent_training_links
                       (task_id, proposal_id, session_id, owner_id, part_id, last_event_sequence, status, created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, 0, 'queued', ?, ?)""",
                    (task_id, proposal_id, session_id, owner_id, part_id, now, now),
                )
            return self.get_training_link(task_id) or {}

        return self.run_write_with_retry(operation)

    @staticmethod
    def _training_link_row(row: Any | None) -> dict[str, Any] | None:
        return dict(row) if row is not None else None

    def get_training_link(self, task_id: str) -> dict[str, Any] | None:
        with get_db_pool(self.db_path).get_readonly_connection() as conn:
            row = conn.execute("SELECT * FROM agent_training_links WHERE task_id = ?", (task_id,)).fetchone()
        return self._training_link_row(row)

    def get_terminal_training_link(self, task_id: str) -> dict[str, Any] | None:
        with get_db_pool(self.db_path).get_readonly_connection() as conn:
            row = conn.execute(
                "SELECT * FROM agent_training_links WHERE task_id = ? AND status IN ('completed', 'failed', 'cancelled', 'stopped', 'interrupted', 'missing')",
                (task_id,),
            ).fetchone()
        return self._training_link_row(row)

    def list_training_links_for_reconciliation(self, *, limit: int = 100) -> list[dict[str, Any]]:
        with get_db_pool(self.db_path).get_readonly_connection() as conn:
            rows = conn.execute(
                """SELECT * FROM agent_training_links
                   WHERE status NOT IN ('completed', 'failed', 'cancelled', 'stopped', 'interrupted', 'missing')
                   ORDER BY updated_at ASC LIMIT ?""",
                (max(1, min(int(limit), 500)),),
            ).fetchall()
        return [self._training_link_row(row) or {} for row in rows]

    def advance_training_link(
        self,
        task_id: str,
        *,
        sequence: int,
        status: str,
        activity: dict[str, Any] | None = None,
    ) -> bool:
        """CAS-advance a cursor and its one part in the same SQLite transaction."""
        sequence = int(sequence)
        if sequence < 0:
            raise ValueError("Training event sequence must be non-negative")
        now = _now()

        def operation() -> bool:
            with get_db_pool(self.db_path).get_connection() as conn:
                link = conn.execute("SELECT * FROM agent_training_links WHERE task_id = ?", (task_id,)).fetchone()
                if link is None:
                    return False
                if sequence <= int(link["last_event_sequence"]):
                    return False
                current_status = str(link["status"] or "queued")
                effective_status = current_status if current_status in {"completed", "failed", "cancelled", "stopped", "interrupted", "missing"} else status
                existing_part = conn.execute("SELECT payload FROM agent_parts WHERE id = ?", (link["part_id"],)).fetchone()
                if existing_part is None:
                    raise ValueError("Training link timeline part is missing")
                payload = _load(existing_part["payload"], {})
                if activity is not None:
                    payload["training_activity"] = activity
                terminal = effective_status in {"completed", "failed", "cancelled", "stopped", "interrupted", "missing"}
                conn.execute(
                    "UPDATE agent_parts SET status = ?, title = ?, content = ?, payload = ?, updated_at = ? WHERE id = ?",
                    ("completed" if terminal else "running", "训练运行", str((activity or payload.get("training_activity") or {}).get("summary") or "Training run updated."), _json(payload), now, link["part_id"]),
                )
                changed = conn.execute(
                    """UPDATE agent_training_links
                       SET last_event_sequence = ?, status = ?, sync_failures = 0, updated_at = ?
                       WHERE task_id = ? AND last_event_sequence < ?""",
                    (sequence, effective_status, now, task_id, sequence),
                ).rowcount
                if changed != 1:
                    raise RuntimeError("Training link cursor compare-and-advance lost its write race")
            return True

        return bool(self.run_write_with_retry(operation))

    def record_training_sync_issue(
        self,
        task_id: str,
        *,
        missing: bool,
        missing_after: int = 5,
    ) -> str | None:
        """Persist a safe degraded/missing projection without inventing an event cursor."""
        now = _now()
        threshold = max(1, int(missing_after))

        def operation() -> str | None:
            with get_db_pool(self.db_path).get_connection() as conn:
                link = conn.execute(
                    "SELECT * FROM agent_training_links WHERE task_id = ?", (task_id,)
                ).fetchone()
                if link is None:
                    return None
                current = str(link["status"] or "queued")
                if current in {"completed", "failed", "cancelled", "stopped", "interrupted", "missing"}:
                    return current
                failures = int(link["sync_failures"] or 0) + 1
                next_status = "missing" if missing and failures >= threshold else "degraded"
                part = conn.execute(
                    "SELECT payload FROM agent_parts WHERE id = ?", (link["part_id"],)
                ).fetchone()
                if part is None:
                    raise ValueError("Training link timeline part is missing")
                payload = _load(part["payload"], {})
                activity = payload.get("training_activity")
                if not isinstance(activity, dict):
                    activity = {}
                activity = dict(activity)
                activity["status"] = next_status
                activity["summary"] = (
                    "Training task record is unavailable and needs review."
                    if next_status == "missing"
                    else "Live training progress is temporarily unavailable."
                )
                payload["training_activity"] = activity
                conn.execute(
                    "UPDATE agent_parts SET status = ?, content = ?, payload = ?, updated_at = ? WHERE id = ?",
                    (
                        "completed" if next_status == "missing" else "running",
                        activity["summary"],
                        _json(payload),
                        now,
                        link["part_id"],
                    ),
                )
                conn.execute(
                    "UPDATE agent_training_links SET status = ?, sync_failures = ?, updated_at = ? WHERE task_id = ?",
                    (next_status, failures, now, task_id),
                )
                return next_status

        return self.run_write_with_retry(operation)

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

    @staticmethod
    def _work_unit_row_in_transaction(
        conn: sqlite3.Connection,
        work_unit_id: str,
    ) -> dict[str, Any] | None:
        row = conn.execute(
            """
            SELECT * FROM agent_subtasks
            WHERE id = ? AND record_kind = ?
            """,
            (work_unit_id, WORK_UNIT_RECORD_KIND),
        ).fetchone()
        return _subtask_row(row)

    @staticmethod
    def _ensure_work_unit_event_once(
        conn: sqlite3.Connection,
        *,
        event_id: str,
        work_unit_id: str,
        parent_session_id: str,
        child_session_id: str | None,
        attempt: int,
        event_type: str,
        status: str | None,
        payload: dict[str, Any] | None,
    ) -> bool:
        safe_payload = _safe_work_unit_event_payload(
            work_unit_id=work_unit_id,
            attempt=attempt,
            payload=payload,
        )
        message = event_type
        existing_row = conn.execute(
            "SELECT * FROM agent_subtask_events WHERE id = ?",
            (event_id,),
        ).fetchone()
        existing = _subtask_event_row(existing_row)
        if existing is not None:
            expected = {
                "task_id": work_unit_id,
                "parent_session_id": parent_session_id,
                "child_session_id": child_session_id,
                "event_type": event_type,
                "status": status,
                "message": message,
                "payload": safe_payload,
            }
            if any(existing.get(key) != value for key, value in expected.items()):
                raise WorkUnitEventConflict(
                    f"event ID {event_id} is already bound to different content"
                )
            return False
        conn.execute(
            """
            INSERT INTO agent_subtask_events
                (
                    id, task_id, parent_session_id, child_session_id,
                    event_type, status, message, payload_json, created_at
                )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event_id,
                work_unit_id,
                parent_session_id,
                child_session_id,
                event_type,
                status,
                message,
                _json(safe_payload),
                _now(),
            ),
        )
        return True

    def create_work_unit_if_absent(self, work_unit: WorkUnit) -> dict[str, Any]:
        if not isinstance(work_unit, WorkUnit):
            raise TypeError("work_unit must be a validated WorkUnit")
        envelope = _work_unit_envelope(work_unit)
        now = _now()

        def operation() -> dict[str, Any]:
            with get_db_pool(self.db_path).get_connection() as conn:
                parent = conn.execute(
                    "SELECT id, agent_id FROM agent_sessions WHERE id = ?",
                    (work_unit.parent_session_id,),
                ).fetchone()
                if parent is None or str(parent["agent_id"]) != "build":
                    raise WorkUnitIdentityConflict(
                        "typed WorkUnit parent must be an existing Build session"
                    )
                existing_row = conn.execute(
                    "SELECT * FROM agent_subtasks WHERE id = ?",
                    (work_unit.work_unit_id,),
                ).fetchone()
                existing = _subtask_row(existing_row)
                if existing is not None:
                    existing_unit = _validate_work_unit_record(existing)
                    if existing_unit != work_unit:
                        raise WorkUnitIdentityConflict(
                            f"WorkUnit ID {work_unit.work_unit_id} has different content"
                        )
                    return existing
                conn.execute(
                    """
                    INSERT INTO agent_subtasks
                        (
                            id, parent_session_id, child_session_id, agent_name,
                            status, record_kind, plan_fingerprint,
                            work_unit_attempt, input_json, result_json, error,
                            created_at, updated_at, last_checked_at, started_at,
                            completed_at, cancelled_at, restart_count,
                            previous_child_session_ids
                        )
                    VALUES (?, ?, NULL, ?, ?, ?, ?, 0, ?, '{}', NULL, ?, ?, NULL,
                            NULL, NULL, NULL, 0, '[]')
                    """,
                    (
                        work_unit.work_unit_id,
                        work_unit.parent_session_id,
                        work_unit.owner,
                        "planned",
                        WORK_UNIT_RECORD_KIND,
                        work_unit.plan_fingerprint,
                        _json(envelope),
                        now,
                        now,
                    ),
                )
                created_row = conn.execute(
                    "SELECT * FROM agent_subtasks WHERE id = ?",
                    (work_unit.work_unit_id,),
                ).fetchone()
                return _subtask_row(created_row) or {}

        return self.run_write_with_retry(operation)

    def get_work_unit_record(self, work_unit_id: str) -> dict[str, Any] | None:
        with get_db_pool(self.db_path).get_readonly_connection() as conn:
            row = conn.execute(
                """
                SELECT * FROM agent_subtasks
                WHERE id = ? AND record_kind = ?
                """,
                (work_unit_id, WORK_UNIT_RECORD_KIND),
            ).fetchone()
        data = _subtask_row(row)
        if data is not None:
            _validate_work_unit_record(data)
        return data

    def list_work_unit_records(
        self,
        parent_session_id: str,
        *,
        plan_fingerprint: str | None = None,
    ) -> list[dict[str, Any]]:
        query = """
            SELECT * FROM agent_subtasks
            WHERE parent_session_id = ? AND record_kind = ?
        """
        params: tuple[Any, ...] = (
            parent_session_id,
            WORK_UNIT_RECORD_KIND,
        )
        if plan_fingerprint is not None:
            query += " AND plan_fingerprint = ?"
            params = (*params, plan_fingerprint)
        query += " ORDER BY created_at ASC, rowid ASC"
        with get_db_pool(self.db_path).get_readonly_connection() as conn:
            rows = conn.execute(query, params).fetchall()
        records = [_subtask_row(row) or {} for row in rows]
        for record in records:
            _validate_work_unit_record(record)
        return records

    def advance_work_unit_attempt(
        self,
        work_unit_id: str,
        *,
        expected_attempt: int,
        event_id: str,
    ) -> dict[str, Any]:
        def operation() -> dict[str, Any]:
            with get_db_pool(self.db_path).get_connection() as conn:
                record = self._work_unit_row_in_transaction(conn, work_unit_id)
                work_unit = _validate_work_unit_record(record)
                next_attempt = expected_attempt + 1
                event_payload = {
                    "previous_attempt": expected_attempt,
                    "attempt": next_attempt,
                }
                inserted = self._ensure_work_unit_event_once(
                    conn,
                    event_id=event_id,
                    work_unit_id=work_unit_id,
                    parent_session_id=work_unit.parent_session_id,
                    child_session_id=None,
                    attempt=next_attempt,
                    event_type="work_unit_attempt_advanced",
                    status=None,
                    payload=event_payload,
                )
                if not inserted:
                    return record or {}
                current_attempt = int(record["work_unit_attempt"])
                if current_attempt != expected_attempt:
                    raise WorkUnitStateConflict(
                        "WorkUnit attempt compare-and-swap failed"
                    )
                if str(record["status"]) in WORK_UNIT_TERMINAL_STATUSES:
                    raise WorkUnitStateConflict(
                        "terminal WorkUnit attempts cannot advance"
                    )
                if next_attempt > work_unit.budget.max_attempts:
                    raise WorkUnitStateConflict(
                        "WorkUnit attempt budget is exhausted"
                    )
                previous_child_ids = list(
                    record.get("previous_child_session_ids") or []
                )
                current_child_id = record.get("child_session_id")
                if current_child_id and current_child_id not in previous_child_ids:
                    previous_child_ids.append(current_child_id)
                conn.execute(
                    """
                    UPDATE agent_subtasks
                    SET work_unit_attempt = ?,
                        child_session_id = NULL,
                        previous_child_session_ids = ?,
                        updated_at = ?
                    WHERE id = ? AND record_kind = ? AND work_unit_attempt = ?
                    """,
                    (
                        next_attempt,
                        _json(previous_child_ids),
                        _now(),
                        work_unit_id,
                        WORK_UNIT_RECORD_KIND,
                        expected_attempt,
                    ),
                )
                updated = self._work_unit_row_in_transaction(conn, work_unit_id)
                return updated or {}

        return self.run_write_with_retry(operation)

    def bind_work_unit_child_once(
        self,
        work_unit_id: str,
        *,
        attempt: int,
        child_session_id: str,
        event_id: str,
    ) -> dict[str, Any]:
        if not child_session_id.strip():
            raise WorkUnitStateConflict("child_session_id is required")

        def operation() -> dict[str, Any]:
            with get_db_pool(self.db_path).get_connection() as conn:
                record = self._work_unit_row_in_transaction(conn, work_unit_id)
                work_unit = _validate_work_unit_record(record)
                inserted = self._ensure_work_unit_event_once(
                    conn,
                    event_id=event_id,
                    work_unit_id=work_unit_id,
                    parent_session_id=work_unit.parent_session_id,
                    child_session_id=child_session_id,
                    attempt=attempt,
                    event_type="work_unit_child_bound",
                    status=None,
                    payload={"child_session_id": child_session_id},
                )
                if not inserted:
                    return record or {}
                if int(record["work_unit_attempt"]) != attempt:
                    raise WorkUnitStateConflict(
                        "child revision attempt does not match current WorkUnit"
                    )
                current_child_id = record.get("child_session_id")
                if current_child_id not in {None, child_session_id}:
                    raise WorkUnitStateConflict(
                        "a different child revision is already active"
                    )
                if current_child_id is None:
                    conn.execute(
                        """
                        UPDATE agent_subtasks
                        SET child_session_id = ?, updated_at = ?
                        WHERE id = ? AND record_kind = ?
                          AND work_unit_attempt = ?
                          AND child_session_id IS NULL
                        """,
                        (
                            child_session_id,
                            _now(),
                            work_unit_id,
                            WORK_UNIT_RECORD_KIND,
                            attempt,
                        ),
                    )
                updated = self._work_unit_row_in_transaction(conn, work_unit_id)
                return updated or {}

        return self.run_write_with_retry(operation)

    def transition_work_unit(
        self,
        work_unit_id: str,
        *,
        expected_attempt: int,
        target_status: str,
        event_id: str,
        event_type: str,
        payload: dict[str, Any] | None,
        result: WorkUnitResult | None = None,
        expected_child_session_id: str | None = None,
    ) -> dict[str, Any]:
        def operation() -> dict[str, Any]:
            with get_db_pool(self.db_path).get_connection() as conn:
                record = self._work_unit_row_in_transaction(conn, work_unit_id)
                work_unit = _validate_work_unit_record(record)
                inserted = self._ensure_work_unit_event_once(
                    conn,
                    event_id=event_id,
                    work_unit_id=work_unit_id,
                    parent_session_id=work_unit.parent_session_id,
                    child_session_id=expected_child_session_id,
                    attempt=expected_attempt,
                    event_type=event_type,
                    status=target_status,
                    payload=payload,
                )
                if not inserted:
                    return record or {}
                if int(record["work_unit_attempt"]) != expected_attempt:
                    raise WorkUnitStateConflict(
                        "WorkUnit transition attempt is stale"
                    )
                if (
                    expected_child_session_id is not None
                    and record.get("child_session_id")
                    != expected_child_session_id
                ):
                    raise WorkUnitStateConflict(
                        "WorkUnit transition child revision is stale"
                    )
                current_status = str(record["status"])
                try:
                    require_work_unit_status_transition(
                        current_status,
                        target_status,
                    )
                except ValueError as exc:
                    raise WorkUnitStateConflict(str(exc)) from exc
                result_json: dict[str, Any] = (
                    record.get("result_json") or {}
                )
                if result is not None:
                    if (
                        result.work_unit_id != work_unit_id
                        or result.attempt != expected_attempt
                    ):
                        raise WorkUnitStateConflict(
                            "WorkUnit result identity or attempt is stale"
                        )
                    result_json = serialize_work_unit_result(result)
                elif target_status in {"completed", "degraded"}:
                    raise WorkUnitStateConflict(
                        "terminal WorkUnit transitions require a typed result"
                    )
                now = _now()
                completed_at = (
                    now
                    if target_status in {"completed", "degraded"}
                    else record.get("completed_at")
                )
                cancelled_at = (
                    now
                    if target_status == "cancelled"
                    else record.get("cancelled_at")
                )
                conn.execute(
                    """
                    UPDATE agent_subtasks
                    SET status = ?, result_json = ?, updated_at = ?,
                        completed_at = ?, cancelled_at = ?
                    WHERE id = ? AND record_kind = ? AND work_unit_attempt = ?
                    """,
                    (
                        target_status,
                        _json(result_json),
                        now,
                        completed_at,
                        cancelled_at,
                        work_unit_id,
                        WORK_UNIT_RECORD_KIND,
                        expected_attempt,
                    ),
                )
                updated = self._work_unit_row_in_transaction(conn, work_unit_id)
                return updated or {}

        return self.run_write_with_retry(operation)

    def add_work_unit_event_once(
        self,
        *,
        event_id: str,
        work_unit_id: str,
        attempt: int,
        event_type: str,
        payload: dict[str, Any] | None,
    ) -> dict[str, Any]:
        def operation() -> dict[str, Any]:
            with get_db_pool(self.db_path).get_connection() as conn:
                record = self._work_unit_row_in_transaction(conn, work_unit_id)
                work_unit = _validate_work_unit_record(record)
                current_attempt = int(record["work_unit_attempt"])
                if attempt < 0 or attempt > current_attempt:
                    raise WorkUnitStateConflict(
                        "WorkUnit event attempt is ahead of durable state"
                    )
                self._ensure_work_unit_event_once(
                    conn,
                    event_id=event_id,
                    work_unit_id=work_unit_id,
                    parent_session_id=work_unit.parent_session_id,
                    child_session_id=record.get("child_session_id"),
                    attempt=attempt,
                    event_type=event_type,
                    status=None,
                    payload=payload,
                )
                event_row = conn.execute(
                    "SELECT * FROM agent_subtask_events WHERE id = ?",
                    (event_id,),
                ).fetchone()
                return _subtask_event_row(event_row) or {}

        return self.run_write_with_retry(operation)

    def list_work_unit_events(
        self,
        work_unit_id: str,
    ) -> list[dict[str, Any]]:
        with get_db_pool(self.db_path).get_readonly_connection() as conn:
            typed = conn.execute(
                """
                SELECT id FROM agent_subtasks
                WHERE id = ? AND record_kind = ?
                """,
                (work_unit_id, WORK_UNIT_RECORD_KIND),
            ).fetchone()
            if typed is None:
                return []
            rows = conn.execute(
                """
                SELECT * FROM agent_subtask_events
                WHERE task_id = ?
                ORDER BY created_at ASC, rowid ASC
                """,
                (work_unit_id,),
            ).fetchall()
        return [_subtask_event_row(row) or {} for row in rows]

    def create_subtask(self, data: dict[str, Any]) -> dict[str, Any]:
        now = _now()
        task_id = data.get("id") or f"agt_{uuid.uuid4().hex}"
        if str(task_id).startswith("wu_"):
            raise WorkUnitIdentityConflict(
                "the wu_ ID prefix is reserved for typed WorkUnits"
            )
        with get_db_pool(self.db_path).get_connection() as conn:
            conn.execute(
                """
                INSERT INTO agent_subtasks
                    (
                        id, parent_session_id, child_session_id, agent_name, status,
                        record_kind, plan_fingerprint, work_unit_attempt,
                        input_json, result_json, error, created_at, updated_at, last_checked_at,
                        started_at, completed_at, cancelled_at, restart_count, previous_child_session_ids
                    )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    task_id,
                    data.get("parent_session_id"),
                    data.get("child_session_id"),
                    data.get("agent_name"),
                    data.get("status") or "pending",
                    LEGACY_SUBTASK_RECORD_KIND,
                    None,
                    0,
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
            current = conn.execute(
                "SELECT record_kind FROM agent_subtasks WHERE id = ?",
                (task_id,),
            ).fetchone()
            if current is not None and current["record_kind"] != LEGACY_SUBTASK_RECORD_KIND:
                raise WorkUnitStateConflict(
                    "typed WorkUnits require the dedicated CAS update methods"
                )
            dynamic_update(conn, "agent_subtasks", "id", task_id, updates, self._SUBTASK_UPDATABLE)
            row = conn.execute(
                """
                SELECT * FROM agent_subtasks
                WHERE id = ? AND record_kind = ?
                """,
                (task_id, LEGACY_SUBTASK_RECORD_KIND),
            ).fetchone()
        return _subtask_row(row) or {}

    def get_subtask(self, task_id: str) -> dict[str, Any] | None:
        with get_db_pool(self.db_path).get_readonly_connection() as conn:
            row = conn.execute(
                """
                SELECT * FROM agent_subtasks
                WHERE id = ? AND record_kind = ?
                """,
                (task_id, LEGACY_SUBTASK_RECORD_KIND),
            ).fetchone()
        return _subtask_row(row)

    def list_subtasks(self, parent_session_id: str, status_filter: str | None = None) -> list[dict[str, Any]]:
        query = """
            SELECT * FROM agent_subtasks
            WHERE parent_session_id = ? AND record_kind = ?
        """
        params: tuple[Any, ...] = (
            parent_session_id,
            LEGACY_SUBTASK_RECORD_KIND,
        )
        if status_filter and status_filter != "all":
            query += " AND status = ?"
            params = (
                parent_session_id,
                LEGACY_SUBTASK_RECORD_KIND,
                status_filter,
            )
        query += " ORDER BY created_at ASC, rowid ASC"
        with get_db_pool(self.db_path).get_readonly_connection() as conn:
            rows = conn.execute(query, params).fetchall()
        return [_subtask_row(row) or {} for row in rows]

    def list_all_subtasks(self, statuses: set[str] | None = None) -> list[dict[str, Any]]:
        query = "SELECT * FROM agent_subtasks WHERE record_kind = ?"
        params: tuple[Any, ...] = (LEGACY_SUBTASK_RECORD_KIND,)
        if statuses:
            placeholders = ", ".join("?" for _ in statuses)
            query += f" AND status IN ({placeholders})"
            params = (LEGACY_SUBTASK_RECORD_KIND, *tuple(sorted(statuses)))
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
            task_row = conn.execute(
                "SELECT record_kind FROM agent_subtasks WHERE id = ?",
                (task_id,),
            ).fetchone()
            if task_row is not None and task_row["record_kind"] != LEGACY_SUBTASK_RECORD_KIND:
                raise WorkUnitStateConflict(
                    "typed WorkUnit events require add_work_unit_event_once"
                )
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
            row = conn.execute(
                """
                SELECT event.*
                FROM agent_subtask_events AS event
                JOIN agent_subtasks AS task ON task.id = event.task_id
                WHERE event.id = ? AND task.record_kind = ?
                """,
                (event_id, LEGACY_SUBTASK_RECORD_KIND),
            ).fetchone()
        return _subtask_event_row(row)

    def list_subtask_events(self, task_id: str, limit: int | None = None) -> list[dict[str, Any]]:
        query = """
            SELECT event.*
            FROM agent_subtask_events AS event
            JOIN agent_subtasks AS task ON task.id = event.task_id
            WHERE event.task_id = ? AND task.record_kind = ?
            ORDER BY event.created_at ASC, event.rowid ASC
        """
        params: tuple[Any, ...] = (task_id, LEGACY_SUBTASK_RECORD_KIND)
        if limit is not None:
            query += " LIMIT ?"
            params = (
                task_id,
                LEGACY_SUBTASK_RECORD_KIND,
                max(1, int(limit)),
            )
        with get_db_pool(self.db_path).get_readonly_connection() as conn:
            rows = conn.execute(query, params).fetchall()
        return [_subtask_event_row(row) or {} for row in rows]

    def list_parent_subtask_events(self, parent_session_id: str, limit: int | None = None) -> list[dict[str, Any]]:
        query = """
            SELECT event.*
            FROM agent_subtask_events AS event
            JOIN agent_subtasks AS task ON task.id = event.task_id
            WHERE event.parent_session_id = ? AND task.record_kind = ?
            ORDER BY event.created_at ASC, event.rowid ASC
        """
        params: tuple[Any, ...] = (
            parent_session_id,
            LEGACY_SUBTASK_RECORD_KIND,
        )
        if limit is not None:
            query += " LIMIT ?"
            params = (
                parent_session_id,
                LEGACY_SUBTASK_RECORD_KIND,
                max(1, int(limit)),
            )
        with get_db_pool(self.db_path).get_readonly_connection() as conn:
            rows = conn.execute(query, params).fetchall()
        return [_subtask_event_row(row) or {} for row in rows]

    def summarize_subtask_metrics(self, parent_session_id: str) -> dict[str, Any]:
        with get_db_pool(self.db_path).get_readonly_connection() as conn:
            status_rows = conn.execute(
                """
                SELECT status, COUNT(*) AS count
                FROM agent_subtasks
                WHERE parent_session_id = ? AND record_kind = ?
                GROUP BY status
                """,
                (parent_session_id, LEGACY_SUBTASK_RECORD_KIND),
            ).fetchall()
            event_row = conn.execute(
                """
                SELECT COUNT(*) AS count
                FROM agent_subtask_events AS event
                JOIN agent_subtasks AS task ON task.id = event.task_id
                WHERE event.parent_session_id = ? AND task.record_kind = ?
                """,
                (parent_session_id, LEGACY_SUBTASK_RECORD_KIND),
            ).fetchone()
            recovery_row = conn.execute(
                """
                SELECT COUNT(*) AS count
                FROM agent_subtask_events AS event
                JOIN agent_subtasks AS task ON task.id = event.task_id
                WHERE event.parent_session_id = ?
                  AND task.record_kind = ?
                  AND event.event_type = 'recovered'
                """,
                (parent_session_id, LEGACY_SUBTASK_RECORD_KIND),
            ).fetchone()
            last_event_row = conn.execute(
                """
                SELECT event.*
                FROM agent_subtask_events AS event
                JOIN agent_subtasks AS task ON task.id = event.task_id
                WHERE event.parent_session_id = ? AND task.record_kind = ?
                ORDER BY event.created_at DESC, event.rowid DESC
                LIMIT 1
                """,
                (parent_session_id, LEGACY_SUBTASK_RECORD_KIND),
            ).fetchone()
        by_status = {str(row["status"] or "unknown"): int(row["count"] or 0) for row in status_rows}
        total = sum(by_status.values())
        attention = by_status.get("failed", 0)
        event_count = int(event_row["count"] if event_row else 0)
        recovery_count = int(recovery_row["count"] if recovery_row else 0)
        return {
            "total": total,
            "by_status": by_status,
            "running": by_status.get("running", 0),
            "failed": by_status.get("failed", 0),
            "cancelled": by_status.get("cancelled", 0),
            "completed": by_status.get("completed", 0),
            "attention": attention,
            "recovery_count": recovery_count,
            "event_count": event_count,
            "last_event": _subtask_event_row(last_event_row),
        }
