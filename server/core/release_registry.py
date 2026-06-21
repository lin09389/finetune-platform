"""Transactional registry for evaluation runs and deployment releases."""

from __future__ import annotations

import json
import os
import socket
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Literal

from core.db_manager import get_db_pool
from core.storage import APP_DB_PATH

ReleaseKind = Literal["evaluation", "deployment"]

_RELEASE_SCHEMA = """
CREATE TABLE IF NOT EXISTS release_runs (
    run_id TEXT PRIMARY KEY,
    kind TEXT NOT NULL CHECK (kind IN ('evaluation', 'deployment')),
    status TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_release_runs_kind_created
    ON release_runs(kind, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_release_runs_kind_status
    ON release_runs(kind, status, updated_at);
CREATE TABLE IF NOT EXISTS release_leases (
    resource_id TEXT PRIMARY KEY,
    lease_kind TEXT NOT NULL,
    owner_id TEXT NOT NULL,
    acquired_at TEXT NOT NULL,
    heartbeat_at TEXT NOT NULL,
    expires_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_release_leases_expires
    ON release_leases(expires_at);
"""


class ConcurrentReleaseUpdate(RuntimeError):
    """Raised when a caller writes an outdated release record version."""


def _now() -> datetime:
    return datetime.now()


def _iso(value: datetime) -> str:
    return value.isoformat()


class ReleaseRegistry:
    def __init__(self, db_path: str = APP_DB_PATH):
        self.db_path = str(Path(db_path))
        self.pool = get_db_pool(self.db_path)

    def ensure_schema(self) -> None:
        self.pool.safe_execute_script(_RELEASE_SCHEMA)

    def upsert(
        self,
        kind: ReleaseKind,
        run_id: str,
        payload: dict[str, Any],
        *,
        expected_version: int | None = None,
    ) -> int:
        now = _iso(_now())
        status = str(payload.get("status") or "unknown")
        created_at = str(payload.get("created_at") or now)
        encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        with self.pool.get_connection() as conn:
            current = conn.execute(
                "SELECT version FROM release_runs WHERE run_id = ?",
                (run_id,),
            ).fetchone()
            if current is None:
                if expected_version not in (None, 0):
                    raise ConcurrentReleaseUpdate(f"{run_id} no longer has version {expected_version}")
                version = 1
                conn.execute(
                    """
                    INSERT INTO release_runs
                        (run_id, kind, status, payload_json, version, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (run_id, kind, status, encoded, version, created_at, now),
                )
                return version

            current_version = int(current["version"])
            if expected_version is not None and current_version != expected_version:
                raise ConcurrentReleaseUpdate(
                    f"{run_id} expected version {expected_version}, found {current_version}"
                )
            version = current_version + 1
            conn.execute(
                """
                UPDATE release_runs
                SET kind = ?, status = ?, payload_json = ?, version = ?, updated_at = ?
                WHERE run_id = ?
                """,
                (kind, status, encoded, version, now, run_id),
            )
            return version

    def get(self, kind: ReleaseKind, run_id: str) -> tuple[dict[str, Any], int] | None:
        with self.pool.get_readonly_connection() as conn:
            row = conn.execute(
                """
                SELECT payload_json, version
                FROM release_runs
                WHERE run_id = ? AND kind = ?
                """,
                (run_id, kind),
            ).fetchone()
        if row is None:
            return None
        payload = json.loads(row["payload_json"])
        return payload, int(row["version"])

    def list(self, kind: ReleaseKind, limit: int = 1000) -> list[dict[str, Any]]:
        with self.pool.get_readonly_connection() as conn:
            rows = conn.execute(
                """
                SELECT payload_json
                FROM release_runs
                WHERE kind = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (kind, max(1, min(limit, 5000))),
            ).fetchall()
        return [json.loads(row["payload_json"]) for row in rows]

    def mutate(
        self,
        kind: ReleaseKind,
        run_id: str,
        mutator,
    ) -> tuple[dict[str, Any], int] | None:
        """Read-modify-write one record inside a single IMMEDIATE transaction."""
        now = _iso(_now())
        with self.pool.get_connection() as conn:
            row = conn.execute(
                """
                SELECT payload_json, version
                FROM release_runs
                WHERE run_id = ? AND kind = ?
                """,
                (run_id, kind),
            ).fetchone()
            if row is None:
                return None
            payload = json.loads(row["payload_json"])
            updated = mutator(payload)
            if updated is not None:
                payload = updated
            version = int(row["version"]) + 1
            conn.execute(
                """
                UPDATE release_runs
                SET status = ?, payload_json = ?, version = ?, updated_at = ?
                WHERE run_id = ? AND kind = ?
                """,
                (
                    str(payload.get("status") or "unknown"),
                    json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
                    version,
                    now,
                    run_id,
                    kind,
                ),
            )
        return payload, version

    def delete(self, kind: ReleaseKind, run_id: str) -> bool:
        with self.pool.get_connection() as conn:
            deleted = conn.execute(
                "DELETE FROM release_runs WHERE run_id = ? AND kind = ?",
                (run_id, kind),
            ).rowcount
            conn.execute("DELETE FROM release_leases WHERE resource_id LIKE ?", (f"{run_id}:%",))
        return bool(deleted)

    def activate_deployment_exclusively(
        self,
        target_payload: dict[str, Any],
        alias: str,
    ) -> list[dict[str, Any]]:
        """Activate one deployment and deactivate every active peer for its alias atomically."""
        now = _iso(_now())
        package_id = str(target_payload["package_id"])
        changed: list[dict[str, Any]] = []
        with self.pool.get_connection() as conn:
            rows = conn.execute(
                "SELECT run_id, payload_json, version FROM release_runs WHERE kind = 'deployment'"
            ).fetchall()
            for row in rows:
                payload = json.loads(row["payload_json"])
                current_alias = (
                    (payload.get("inference_target") or {}).get("model_alias")
                    or (payload.get("env_template") or {}).get("MODEL_NAME")
                )
                if row["run_id"] == package_id or current_alias != alias:
                    continue
                if payload.get("status") != "active":
                    continue
                payload["status"] = "inactive"
                payload["deactivated_at"] = now
                payload.setdefault("audit", []).append({
                    "action": "superseded",
                    "at": now,
                    "replacement_package_id": package_id,
                })
                conn.execute(
                    """
                    UPDATE release_runs
                    SET status = 'inactive', payload_json = ?, version = ?, updated_at = ?
                    WHERE run_id = ? AND kind = 'deployment'
                    """,
                    (
                        json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
                        int(row["version"]) + 1,
                        now,
                        row["run_id"],
                    ),
                )
                changed.append(payload)

            existing = conn.execute(
                "SELECT version FROM release_runs WHERE run_id = ? AND kind = 'deployment'",
                (package_id,),
            ).fetchone()
            version = int(existing["version"]) + 1 if existing is not None else 1
            conn.execute(
                """
                INSERT INTO release_runs
                    (run_id, kind, status, payload_json, version, created_at, updated_at)
                VALUES (?, 'deployment', 'active', ?, ?, ?, ?)
                ON CONFLICT(run_id) DO UPDATE SET
                    status = 'active',
                    payload_json = excluded.payload_json,
                    version = excluded.version,
                    updated_at = excluded.updated_at
                """,
                (
                    package_id,
                    json.dumps(target_payload, ensure_ascii=False, separators=(",", ":")),
                    version,
                    str(target_payload.get("created_at") or now),
                    now,
                ),
            )
            changed.append(target_payload)
        return changed

    def claim(self, resource_id: str, lease_kind: str, owner_id: str, ttl_seconds: int = 120) -> bool:
        now = _now()
        expires = now + timedelta(seconds=max(5, ttl_seconds))
        with self.pool.get_connection() as conn:
            conn.execute("DELETE FROM release_leases WHERE expires_at <= ?", (_iso(now),))
            row = conn.execute(
                "SELECT owner_id FROM release_leases WHERE resource_id = ?",
                (resource_id,),
            ).fetchone()
            if row is not None and row["owner_id"] != owner_id:
                return False
            conn.execute(
                """
                INSERT INTO release_leases
                    (resource_id, lease_kind, owner_id, acquired_at, heartbeat_at, expires_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(resource_id) DO UPDATE SET
                    lease_kind = excluded.lease_kind,
                    owner_id = excluded.owner_id,
                    heartbeat_at = excluded.heartbeat_at,
                    expires_at = excluded.expires_at
                """,
                (resource_id, lease_kind, owner_id, _iso(now), _iso(now), _iso(expires)),
            )
        return True

    def heartbeat(self, resource_id: str, owner_id: str, ttl_seconds: int = 120) -> bool:
        now = _now()
        with self.pool.get_connection() as conn:
            updated = conn.execute(
                """
                UPDATE release_leases
                SET heartbeat_at = ?, expires_at = ?
                WHERE resource_id = ? AND owner_id = ? AND expires_at > ?
                """,
                (
                    _iso(now),
                    _iso(now + timedelta(seconds=max(5, ttl_seconds))),
                    resource_id,
                    owner_id,
                    _iso(now),
                ),
            ).rowcount
        return bool(updated)

    def release(self, resource_id: str, owner_id: str) -> bool:
        with self.pool.get_connection() as conn:
            deleted = conn.execute(
                "DELETE FROM release_leases WHERE resource_id = ? AND owner_id = ?",
                (resource_id, owner_id),
            ).rowcount
        return bool(deleted)

    def migrate_json_directory(self, kind: ReleaseKind, directory: Path, pattern: str) -> int:
        imported = 0
        for path in directory.glob(pattern):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                run_id = str(payload.get("run_id") or payload.get("package_id") or "")
                if not run_id or self.get(kind, run_id) is not None:
                    continue
                self.upsert(kind, run_id, payload, expected_version=0)
                imported += 1
            except (OSError, json.JSONDecodeError, ConcurrentReleaseUpdate):
                continue
        return imported


def make_release_owner_id() -> str:
    return f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex}"


_registries: dict[str, ReleaseRegistry] = {}


def get_release_registry(db_path: str = APP_DB_PATH) -> ReleaseRegistry:
    normalized = str(Path(db_path))
    registry = _registries.get(normalized)
    if registry is None or getattr(registry.pool, "_closed", False):
        registry = ReleaseRegistry(normalized)
        registry.ensure_schema()
        _registries[normalized] = registry
    return registry


def reset_release_registry_for_tests() -> None:
    _registries.clear()
