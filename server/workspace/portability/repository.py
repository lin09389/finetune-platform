"""SQLite persistence for inspected packages and imported read-only contexts."""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any


def _now() -> datetime:
    return datetime.now(UTC)


def _dump(value: Any) -> str:
    return json.dumps(value if value is not None else {}, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _load(value: str | None, default: Any) -> Any:
    try:
        return json.loads(value or "")
    except (TypeError, json.JSONDecodeError):
        return default


class WorkspacePortabilityRepository:
    """A local SQLite repository with owner-bound, expiring inspect tokens."""

    def __init__(self, db_path: str) -> None:
        self.db_path = str(Path(db_path))
        self.ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def ensure_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS workspace_portability_inspections (
                    token TEXT PRIMARY KEY,
                    owner_id TEXT NOT NULL,
                    package_digest TEXT NOT NULL,
                    manifest_json TEXT NOT NULL,
                    preview_json TEXT NOT NULL,
                    archive_path TEXT,
                    expires_at TEXT NOT NULL,
                    committed_import_id TEXT,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS workspace_portability_imports (
                    id TEXT PRIMARY KEY,
                    inspection_token TEXT NOT NULL UNIQUE,
                    owner_id TEXT NOT NULL,
                    workspace_id TEXT NOT NULL,
                    source_portable_id TEXT NOT NULL,
                    package_digest TEXT NOT NULL,
                    resource_bindings_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS workspace_continuation_contexts (
                    id TEXT PRIMARY KEY,
                    import_id TEXT NOT NULL,
                    owner_id TEXT NOT NULL,
                    workspace_id TEXT NOT NULL,
                    source_task_fingerprint TEXT NOT NULL,
                    context_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_workspace_continuation_owner_workspace
                    ON workspace_continuation_contexts(owner_id, workspace_id, created_at DESC);
                """
            )

    def cleanup_expired(self, now: datetime | None = None) -> list[str]:
        cutoff = (now or _now()).isoformat()
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT token, archive_path FROM workspace_portability_inspections "
                "WHERE expires_at <= ? AND committed_import_id IS NULL",
                (cutoff,),
            ).fetchall()
        deleted: list[str] = []
        for row in rows:
            archive_path = row["archive_path"]
            if archive_path:
                try:
                    Path(str(archive_path)).unlink(missing_ok=True)
                except OSError:
                    # Retain the expired record so a later cleanup can retry.
                    continue
                deleted.append(str(archive_path))
            with self._connect() as conn:
                conn.execute(
                    "DELETE FROM workspace_portability_inspections "
                    "WHERE token = ? AND expires_at <= ? AND committed_import_id IS NULL",
                    (row["token"], cutoff),
                )
        return deleted

    def create_inspection(
        self,
        *,
        owner_id: str,
        package_digest: str,
        manifest: dict[str, Any],
        preview: dict[str, Any],
        archive_path: str | None = None,
        ttl_seconds: int = 900,
    ) -> dict[str, Any]:
        self.cleanup_expired()
        created_at = _now()
        record = {
            "token": f"wpi_{uuid.uuid4().hex}",
            "owner_id": owner_id,
            "package_digest": package_digest,
            "manifest": manifest,
            "preview": preview,
            "archive_path": archive_path,
            "expires_at": (created_at + timedelta(seconds=max(0, ttl_seconds))).isoformat(),
            "created_at": created_at.isoformat(),
            "committed_import_id": None,
        }
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO workspace_portability_inspections
                   (token, owner_id, package_digest, manifest_json, preview_json, archive_path, expires_at, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    record["token"], record["owner_id"], record["package_digest"], _dump(manifest), _dump(preview),
                    archive_path, record["expires_at"], record["created_at"],
                ),
            )
        return record

    def get_inspection(self, token: str, owner_id: str, *, include_committed: bool = True) -> dict[str, Any] | None:
        self.cleanup_expired()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM workspace_portability_inspections WHERE token = ? AND owner_id = ?", (token, owner_id)
            ).fetchone()
        if row is None or (not include_committed and row["committed_import_id"]):
            return None
        if not row["committed_import_id"] and row["expires_at"] <= _now().isoformat():
            return None
        return self._inspection_row(row)

    def commit_import(
        self,
        *,
        token: str,
        owner_id: str,
        workspace_id: str,
        source_portable_id: str,
        package_digest: str,
        resource_bindings: dict[str, Any],
        contexts: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Atomically persist an import; replays of an inspect token are stable."""
        now = _now().isoformat()
        with self._connect() as conn:
            inspection = conn.execute(
                "SELECT * FROM workspace_portability_inspections WHERE token = ? AND owner_id = ?", (token, owner_id)
            ).fetchone()
            if inspection is None or (inspection["expires_at"] <= now and not inspection["committed_import_id"]):
                raise LookupError("Import inspection token is missing or expired")
            if inspection["package_digest"] != package_digest:
                raise ValueError("Import package digest does not match inspected package")
            if inspection["committed_import_id"]:
                return self._import_by_id(conn, str(inspection["committed_import_id"]))

            import_id = f"wpi_{uuid.uuid4().hex}"
            conn.execute(
                """INSERT INTO workspace_portability_imports
                   (id, inspection_token, owner_id, workspace_id, source_portable_id, package_digest, resource_bindings_json, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (import_id, token, owner_id, workspace_id, source_portable_id, package_digest, _dump(resource_bindings), now),
            )
            context_ids: list[str] = []
            for context in contexts[:100]:
                context_id = f"wpc_{uuid.uuid4().hex}"
                context_ids.append(context_id)
                conn.execute(
                    """INSERT INTO workspace_continuation_contexts
                       (id, import_id, owner_id, workspace_id, source_task_fingerprint, context_json, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (
                        context_id, import_id, owner_id, workspace_id,
                        str(context.get("source_task_fingerprint") or ""), _dump(context), now,
                    ),
                )
            conn.execute(
                "UPDATE workspace_portability_inspections SET committed_import_id = ?, archive_path = NULL WHERE token = ?",
                (import_id, token),
            )
        return {"import_id": import_id, "workspace_id": workspace_id, "continuation_context_ids": context_ids}

    def list_continuations(self, workspace_id: str, owner_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM workspace_continuation_contexts WHERE workspace_id = ? AND owner_id = ? ORDER BY created_at DESC",
                (workspace_id, owner_id),
            ).fetchall()
        return [self._context_row(row) for row in rows]

    def get_continuation(self, workspace_id: str, context_id: str, owner_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                """SELECT * FROM workspace_continuation_contexts
                   WHERE id = ? AND workspace_id = ? AND owner_id = ?""",
                (context_id, workspace_id, owner_id),
            ).fetchone()
        return self._context_row(row) if row else None

    @staticmethod
    def _inspection_row(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "token": row["token"], "owner_id": row["owner_id"], "package_digest": row["package_digest"],
            "manifest": _load(row["manifest_json"], {}), "preview": _load(row["preview_json"], {}),
            "archive_path": row["archive_path"], "expires_at": row["expires_at"],
            "created_at": row["created_at"], "committed_import_id": row["committed_import_id"],
        }

    @staticmethod
    def _context_row(row: sqlite3.Row) -> dict[str, Any]:
        context = _load(row["context_json"], {})
        return {"id": row["id"], "workspace_id": row["workspace_id"], "import_id": row["import_id"], **context}

    @staticmethod
    def _import_by_id(conn: sqlite3.Connection, import_id: str) -> dict[str, Any]:
        row = conn.execute("SELECT * FROM workspace_portability_imports WHERE id = ?", (import_id,)).fetchone()
        if row is None:
            raise RuntimeError("Committed import is missing")
        context_rows = conn.execute(
            "SELECT id FROM workspace_continuation_contexts WHERE import_id = ? ORDER BY created_at ASC", (import_id,)
        ).fetchall()
        return {"import_id": row["id"], "workspace_id": row["workspace_id"], "continuation_context_ids": [item["id"] for item in context_rows]}


__all__ = ["WorkspacePortabilityRepository"]
