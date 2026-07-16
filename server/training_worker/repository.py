"""SQLite coordination primitives for isolated training workers."""

from __future__ import annotations

import json
import os
import socket
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from core.db_manager import get_db_pool
from core.storage import APP_DB_PATH
from core.training_events_v2 import TrainingEventV2

TERMINAL_JOB_STATUSES = frozenset({"completed", "failed", "stopped", "cancelled", "interrupted"})
ACTIVE_JOB_STATUSES = frozenset({"leased", "running", "cancellation_requested"})
JOB_STATUS_TO_RECORD_STATUS: dict[str, str] = {
    "queued": "queued",
    "leased": "loading",
    "running": "running",
    "cancellation_requested": "stopping",
    "completed": "completed",
    "failed": "failed",
    "stopped": "stopped",
    "cancelled": "cancelled",
    "interrupted": "interrupted",
}


def record_status_for_job_status(job_status: str) -> str:
    return JOB_STATUS_TO_RECORD_STATUS.get(job_status, job_status)


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _iso(value: datetime | None = None) -> str:
    return (value or _utcnow()).astimezone(UTC).isoformat()


def _loads(value: str | None, default: Any) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return default


@dataclass(frozen=True)
class TrainingJob:
    job_id: str
    backend: str
    priority: int
    status: str
    config: dict[str, Any]
    model_path: str
    dataset_path: str
    output_path: str
    record: dict[str, Any]
    attempt: int
    max_attempts: int
    cancel_requested: bool
    error: str | None
    created_at: str
    queued_at: str
    started_at: str | None
    finished_at: str | None
    updated_at: str
    lease_owner: str | None = None
    lease_acquired_at: str | None = None
    lease_heartbeat_at: str | None = None
    lease_expires_at: str | None = None

    @property
    def task_id(self) -> str:
        return self.job_id


class TrainingJobRepository:
    """Authoritative durable queue, event log, and worker registry."""

    def __init__(self, db_path: str = APP_DB_PATH):
        self.db_path = str(Path(db_path))
        self._pool = get_db_pool(self.db_path)
        self.ensure_schema()

    def ensure_schema(self) -> None:
        migrations = Path(__file__).resolve().parents[1] / "core" / "migrations"
        for name in ("015_training_worker.sql", "016_training_logs.sql"):
            self._pool.safe_execute_script((migrations / name).read_text(encoding="utf-8"))

    @staticmethod
    def _job_from_row(row) -> TrainingJob:
        return TrainingJob(
            job_id=row["job_id"],
            backend=row["backend"],
            priority=int(row["priority"]),
            status=row["status"],
            config=_loads(row["config_json"], {}),
            model_path=row["model_path"],
            dataset_path=row["dataset_path"],
            output_path=row["output_path"],
            record=_loads(row["record_json"], {}),
            attempt=int(row["attempt"]),
            max_attempts=int(row["max_attempts"]),
            cancel_requested=bool(row["cancel_requested"]),
            error=row["error"],
            created_at=row["created_at"],
            queued_at=row["queued_at"],
            started_at=row["started_at"],
            finished_at=row["finished_at"],
            updated_at=row["updated_at"],
            lease_owner=row["lease_owner"],
            lease_acquired_at=row["lease_acquired_at"],
            lease_heartbeat_at=row["lease_heartbeat_at"],
            lease_expires_at=row["lease_expires_at"],
        )

    @staticmethod
    def _job_select(where: str = "") -> str:
        return f"""
            SELECT j.*, l.owner_id AS lease_owner,
                   l.acquired_at AS lease_acquired_at,
                   l.heartbeat_at AS lease_heartbeat_at,
                   l.expires_at AS lease_expires_at
            FROM training_jobs AS j
            LEFT JOIN training_job_leases AS l ON l.job_id = j.job_id
            {where}
        """

    def enqueue(
        self,
        *,
        job_id: str,
        backend: str,
        priority: int,
        config: dict[str, Any],
        model_path: str,
        dataset_path: str,
        output_path: str,
        record: dict[str, Any],
        max_attempts: int = 3,
        now: datetime | None = None,
        allow_requeue_terminal: bool = False,
    ) -> TrainingJob:
        timestamp = _iso(now)
        requeued_terminal = False
        with self._pool.get_connection() as conn:
            existing = conn.execute(
                "SELECT status FROM training_jobs WHERE job_id = ?",
                (job_id,),
            ).fetchone()
            if existing is not None:
                status = existing["status"]
                if status in ACTIVE_JOB_STATUSES or status == "queued":
                    raise ValueError(f"Training job {job_id} is already {status}; cannot enqueue")
                if not allow_requeue_terminal:
                    raise ValueError(f"Training job {job_id} already exists with status {status}")
                requeued_terminal = True
                conn.execute(
                    """
                    UPDATE training_jobs
                    SET backend = ?, priority = ?, status = 'queued',
                        config_json = ?, model_path = ?, dataset_path = ?,
                        output_path = ?, record_json = ?, attempt = 0,
                        max_attempts = ?, cancel_requested = 0, error = NULL,
                        queued_at = ?, started_at = NULL, finished_at = NULL,
                        updated_at = ?
                    WHERE job_id = ?
                    """,
                    (
                        backend,
                        int(priority),
                        json.dumps(config, ensure_ascii=False),
                        model_path,
                        dataset_path,
                        output_path,
                        json.dumps(record, ensure_ascii=False),
                        max(1, int(max_attempts)),
                        timestamp,
                        timestamp,
                        job_id,
                    ),
                )
                conn.execute("DELETE FROM training_job_leases WHERE job_id = ?", (job_id,))
            else:
                conn.execute(
                    """
                    INSERT INTO training_jobs (
                        job_id, backend, priority, status, config_json, model_path,
                        dataset_path, output_path, record_json, attempt, max_attempts,
                        cancel_requested, created_at, queued_at, updated_at
                    ) VALUES (?, ?, ?, 'queued', ?, ?, ?, ?, ?, 0, ?, 0, ?, ?, ?)
                    """,
                    (
                        job_id,
                        backend,
                        int(priority),
                        json.dumps(config, ensure_ascii=False),
                        model_path,
                        dataset_path,
                        output_path,
                        json.dumps(record, ensure_ascii=False),
                        max(1, int(max_attempts)),
                        timestamp,
                        timestamp,
                        timestamp,
                    ),
                )
        self.append_event(
            task_id=job_id,
            phase="queued",
            kind="task_queued",
            payload={
                "status": "queued",
                "priority": int(priority),
                "message": "Training task queued",
                "requeued_terminal": requeued_terminal,
            },
            now=now,
        )
        job = self.get_job(job_id)
        if job is None:  # pragma: no cover - insert/read invariant
            raise RuntimeError(f"Training job disappeared after enqueue: {job_id}")
        return job

    def get_job(self, job_id: str) -> TrainingJob | None:
        with self._pool.get_readonly_connection() as conn:
            row = conn.execute(self._job_select("WHERE j.job_id = ?"), (job_id,)).fetchone()
        return self._job_from_row(row) if row else None

    def update_record(self, job_id: str, record: dict[str, Any], *, now: datetime | None = None) -> bool:
        """Persist downstream evaluation/deployment metadata on a training record."""
        timestamp = _iso(now)
        with self._pool.get_connection() as conn:
            updated = conn.execute(
                "UPDATE training_jobs SET record_json = ?, updated_at = ? WHERE job_id = ?",
                (json.dumps(record, ensure_ascii=False), timestamp, job_id),
            ).rowcount
        return updated == 1

    def list_jobs(self, *, statuses: set[str] | None = None, limit: int = 100) -> list[TrainingJob]:
        params: list[Any] = []
        where = ""
        if statuses:
            placeholders = ",".join("?" for _ in statuses)
            where = f"WHERE j.status IN ({placeholders})"
            params.extend(sorted(statuses))
        sql = self._job_select(where) + " ORDER BY j.created_at DESC LIMIT ?"
        params.append(max(1, min(int(limit), 1000)))
        with self._pool.get_readonly_connection() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [self._job_from_row(row) for row in rows]

    def has_active_job(self, *, conn=None) -> bool:
        sql = (
            "SELECT 1 FROM training_jobs "
            f"WHERE status IN ({','.join('?' for _ in ACTIVE_JOB_STATUSES)}) LIMIT 1"
        )
        params = tuple(sorted(ACTIVE_JOB_STATUSES))
        if conn is not None:
            return conn.execute(sql, params).fetchone() is not None
        with self._pool.get_readonly_connection() as readonly:
            return readonly.execute(sql, params).fetchone() is not None

    def claim_next(
        self,
        worker_id: str,
        *,
        lease_seconds: int,
        now: datetime | None = None,
    ) -> TrainingJob | None:
        moment = now or _utcnow()
        timestamp = _iso(moment)
        expires = _iso(moment + timedelta(seconds=max(1, int(lease_seconds))))
        job_id: str | None = None
        with self._pool.get_connection() as conn:
            if self.has_active_job(conn=conn):
                return None
            row = conn.execute(
                """
                SELECT job_id FROM training_jobs
                WHERE status = 'queued' AND cancel_requested = 0
                ORDER BY priority ASC, queued_at ASC
                LIMIT 1
                """
            ).fetchone()
            if row is None:
                return None
            job_id = row["job_id"]
            updated = conn.execute(
                """
                UPDATE training_jobs
                SET status = 'leased', attempt = attempt + 1, error = NULL,
                    started_at = COALESCE(started_at, ?), updated_at = ?
                WHERE job_id = ? AND status = 'queued' AND cancel_requested = 0
                  AND NOT EXISTS (
                      SELECT 1 FROM training_jobs
                      WHERE status IN ('leased', 'running', 'cancellation_requested')
                        AND job_id != ?
                  )
                """,
                (timestamp, timestamp, job_id, job_id),
            ).rowcount
            if updated != 1:  # pragma: no cover - BEGIN IMMEDIATE serializes claimers
                return None
            row_rec = conn.execute(
                "SELECT record_json FROM training_jobs WHERE job_id = ?", (job_id,)
            ).fetchone()
            record = _loads(row_rec["record_json"] if row_rec else None, {})
            record["status"] = record_status_for_job_status("leased")
            conn.execute(
                "UPDATE training_jobs SET record_json = ? WHERE job_id = ?",
                (json.dumps(record, ensure_ascii=False), job_id),
            )
            conn.execute(
                """
                INSERT INTO training_job_leases
                    (job_id, owner_id, acquired_at, heartbeat_at, expires_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(job_id) DO UPDATE SET
                    owner_id = excluded.owner_id,
                    acquired_at = excluded.acquired_at,
                    heartbeat_at = excluded.heartbeat_at,
                    expires_at = excluded.expires_at
                """,
                (job_id, worker_id, timestamp, timestamp, expires),
            )
        self.append_event(
            task_id=job_id,
            phase="loading",
            kind="task_leased",
            payload={"status": "leased", "worker_id": worker_id},
            now=moment,
        )
        return self.get_job(job_id)

    def mark_running(self, job_id: str, worker_id: str, *, now: datetime | None = None) -> bool:
        timestamp = _iso(now)
        with self._pool.get_connection() as conn:
            row = conn.execute(
                """
                SELECT record_json FROM training_jobs
                WHERE job_id = ? AND status = 'leased'
                  AND EXISTS (
                      SELECT 1 FROM training_job_leases
                      WHERE job_id = training_jobs.job_id AND owner_id = ?
                  )
                """,
                (job_id, worker_id),
            ).fetchone()
            if row is None:
                return False
            record = _loads(row["record_json"], {})
            record["status"] = record_status_for_job_status("running")
            updated = conn.execute(
                """
                UPDATE training_jobs
                SET status = 'running', record_json = ?, updated_at = ?
                WHERE job_id = ? AND status = 'leased'
                  AND EXISTS (
                      SELECT 1 FROM training_job_leases
                      WHERE job_id = training_jobs.job_id AND owner_id = ?
                  )
                """,
                (json.dumps(record, ensure_ascii=False), timestamp, job_id, worker_id),
            ).rowcount
        if updated:
            self.append_event(
                task_id=job_id,
                phase="loading",
                kind="task_started",
                payload={"status": "loading", "worker_id": worker_id, "message": "Worker started training"},
                now=now,
            )
        return updated == 1

    def heartbeat(
        self,
        job_id: str,
        worker_id: str,
        *,
        lease_seconds: int,
        now: datetime | None = None,
    ) -> bool:
        moment = now or _utcnow()
        timestamp = _iso(moment)
        expires = _iso(moment + timedelta(seconds=max(1, int(lease_seconds))))
        with self._pool.get_connection() as conn:
            updated = conn.execute(
                """
                UPDATE training_job_leases
                SET heartbeat_at = ?, expires_at = ?
                WHERE job_id = ? AND owner_id = ?
                """,
                (timestamp, expires, job_id, worker_id),
            ).rowcount
            if updated:
                conn.execute(
                    "UPDATE training_jobs SET updated_at = ? WHERE job_id = ?",
                    (timestamp, job_id),
                )
        return updated == 1

    def finish(
        self,
        job_id: str,
        worker_id: str,
        *,
        status: str,
        record: dict[str, Any],
        error: str | None = None,
        now: datetime | None = None,
    ) -> bool:
        if status not in TERMINAL_JOB_STATUSES:
            raise ValueError(f"Unsupported terminal training status: {status}")
        timestamp = _iso(now)
        record = dict(record)
        record["status"] = status
        record.setdefault("end_time", timestamp)
        with self._pool.get_connection() as conn:
            owner = conn.execute(
                "SELECT owner_id FROM training_job_leases WHERE job_id = ?",
                (job_id,),
            ).fetchone()
            if owner is None or owner["owner_id"] != worker_id:
                return False
            updated = conn.execute(
                """
                UPDATE training_jobs
                SET status = ?, record_json = ?, error = ?, finished_at = ?, updated_at = ?
                WHERE job_id = ? AND status IN ('leased', 'running', 'cancellation_requested')
                """,
                (status, json.dumps(record, ensure_ascii=False), error, timestamp, timestamp, job_id),
            ).rowcount
            if updated:
                conn.execute("DELETE FROM training_job_leases WHERE job_id = ?", (job_id,))
        if updated:
            phase = "stopped" if status in {"stopped", "cancelled"} else status
            self.append_event(
                task_id=job_id,
                phase=phase,
                kind=f"task_{status}",
                payload={"status": status, "error": error},
                now=now,
            )
        return updated == 1

    def request_cancel(self, job_id: str, *, now: datetime | None = None) -> str | None:
        timestamp = _iso(now)
        result: str | None = None
        with self._pool.get_connection() as conn:
            row = conn.execute(
                "SELECT status, record_json FROM training_jobs WHERE job_id = ?", (job_id,)
            ).fetchone()
            if row is None or row["status"] in TERMINAL_JOB_STATUSES:
                return None
            if row["status"] == "queued":
                record = _loads(row["record_json"], {})
                record["status"] = "cancelled"
                record["end_time"] = timestamp
                conn.execute(
                    """
                    UPDATE training_jobs
                    SET status = 'cancelled', cancel_requested = 1,
                        record_json = ?, finished_at = ?, updated_at = ? WHERE job_id = ?
                    """,
                    (json.dumps(record, ensure_ascii=False), timestamp, timestamp, job_id),
                )
                result = "cancelled"
            else:
                record = _loads(row["record_json"], {})
                record["status"] = record_status_for_job_status("cancellation_requested")
                conn.execute(
                    """
                    UPDATE training_jobs
                    SET status = 'cancellation_requested', cancel_requested = 1,
                        record_json = ?, updated_at = ?
                    WHERE job_id = ?
                    """,
                    (json.dumps(record, ensure_ascii=False), timestamp, job_id),
                )
                result = "cancellation_requested"
        phase = "stopped" if result == "cancelled" else "stopping"
        kind = "task_cancelled" if result == "cancelled" else "task_cancellation_requested"
        self.append_event(
            task_id=job_id,
            phase=phase,
            kind=kind,
            payload={"status": result, "message": "Training cancellation requested by user"},
            now=now,
        )
        return result

    def recover_expired(self, *, now: datetime | None = None) -> dict[str, int]:
        moment = now or _utcnow()
        timestamp = _iso(moment)
        recovered: list[tuple[str, str]] = []
        with self._pool.get_connection() as conn:
            rows = conn.execute(
                """
                SELECT j.job_id, j.attempt, j.max_attempts, j.cancel_requested, j.record_json
                FROM training_jobs AS j
                JOIN training_job_leases AS l ON l.job_id = j.job_id
                WHERE j.status IN ('leased', 'running', 'cancellation_requested')
                  AND l.expires_at <= ?
                """,
                (timestamp,),
            ).fetchall()
            for row in rows:
                if bool(row["cancel_requested"]):
                    status = "cancelled"
                    error = "worker lease expired after cancellation request"
                    finished_at = timestamp
                    record = _loads(row["record_json"], {})
                    record["status"] = "cancelled"
                    record["end_time"] = timestamp
                elif int(row["attempt"]) < int(row["max_attempts"]):
                    status = "queued"
                    error = "worker lease expired; queued for recovery"
                    finished_at = None
                    record = _loads(row["record_json"], {})
                    record["status"] = "queued"
                else:
                    status = "interrupted"
                    error = "worker lease expired after maximum attempts"
                    finished_at = timestamp
                    record = _loads(row["record_json"], {})
                    record["status"] = "interrupted"
                    record["end_time"] = timestamp
                conn.execute(
                    """
                    UPDATE training_jobs
                    SET status = ?, cancel_requested = 0, error = ?, record_json = ?,
                        queued_at = CASE WHEN ? = 'queued' THEN ? ELSE queued_at END,
                        finished_at = ?, updated_at = ?
                    WHERE job_id = ?
                    """,
                    (
                        status,
                        error,
                        json.dumps(record, ensure_ascii=False),
                        status,
                        timestamp,
                        finished_at,
                        timestamp,
                        row["job_id"],
                    ),
                )
                conn.execute("DELETE FROM training_job_leases WHERE job_id = ?", (row["job_id"],))
                recovered.append((row["job_id"], status))
        for job_id, status in recovered:
            if status == "cancelled":
                phase = "stopped"
                kind = "task_cancelled"
            elif status == "queued":
                phase = "queued"
                kind = "task_requeued"
            else:
                phase = "failed"
                kind = "task_interrupted"
            self.append_event(
                task_id=job_id,
                phase=phase,
                kind=kind,
                payload={"status": status, "reason": "worker_lease_expired"},
                now=moment,
            )
        return {
            "requeued": sum(1 for _, status in recovered if status == "queued"),
            "interrupted": sum(1 for _, status in recovered if status == "interrupted"),
            "cancelled": sum(1 for _, status in recovered if status == "cancelled"),
        }

    def queue_status(self) -> dict[str, Any]:
        with self._pool.get_readonly_connection() as conn:
            rows = conn.execute(
                "SELECT status, COUNT(*) AS count FROM training_jobs GROUP BY status"
            ).fetchall()
        counts = {row["status"]: int(row["count"]) for row in rows}
        return {
            "mode": "worker",
            "queue_size": counts.get("queued", 0),
            "running_count": sum(counts.get(status, 0) for status in ACTIVE_JOB_STATUSES),
            "status_counts": counts,
            "workers": self.worker_status(),
        }

    def active_job(self) -> TrainingJob | None:
        jobs = self.list_jobs(statuses=set(ACTIVE_JOB_STATUSES), limit=1)
        return jobs[0] if jobs else None

    def append_event(
        self,
        *,
        task_id: str,
        phase: str,
        kind: str,
        payload: dict[str, Any] | None = None,
        now: datetime | None = None,
        force: bool = False,
    ) -> TrainingEventV2 | None:
        """Append a durable V2 event; may sample high-frequency progress rows.

        Returns None when a progress_updated event is sampled out.
        """
        payload = dict(payload or {})
        if not force and kind == "progress_updated":
            if self._should_sample_out_progress(task_id, payload):
                return None

        timestamp = _iso(now)
        event_id = f"tev2-{uuid.uuid4().hex}"
        with self._pool.get_connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO training_events (event_id, version, ts, task_id, phase, kind, payload_json)
                VALUES (?, 'v2', ?, ?, ?, ?, ?)
                """,
                (event_id, timestamp, task_id, phase, kind, json.dumps(payload, ensure_ascii=False)),
            )
            sequence = int(cursor.lastrowid)
            event_id = f"tev2-{sequence}-{event_id[-8:]}"
            conn.execute(
                "UPDATE training_events SET event_id = ? WHERE sequence = ?",
                (event_id, sequence),
            )
        # Opportunistic prune every ~64 inserts to keep the table bounded.
        if sequence % 64 == 0:
            try:
                self.prune_events()
            except Exception:
                pass
        return TrainingEventV2(
            event_id=event_id,
            ts=timestamp,
            task_id=task_id,
            phase=phase,
            kind=kind,
            payload=payload,
            sequence=sequence,
        )

    def _should_sample_out_progress(self, task_id: str, payload: dict[str, Any]) -> bool:
        """Return True when this progress_updated should be dropped as redundant."""
        try:
            from core.config import get_settings

            min_delta = int(getattr(get_settings(), "training_events_progress_min_step_delta", 1) or 1)
        except Exception:
            min_delta = 1
        if min_delta <= 1:
            return False
        step = payload.get("step")
        if step is None:
            return False
        try:
            step_i = int(step)
        except (TypeError, ValueError):
            return False
        latest = self.latest_event(task_id)
        if latest is None or latest.kind != "progress_updated":
            return False
        try:
            prev = int((latest.payload or {}).get("step") or 0)
        except (TypeError, ValueError):
            return False
        # Always keep first steps and terminal-ish statuses.
        status = str(payload.get("status") or "")
        if status in {"completed", "failed", "stopped", "cancelled", "interrupted", "stopping"}:
            return False
        if step_i == prev:
            # Drop only when status is unchanged.
            return status == str((latest.payload or {}).get("status") or "")
        return (step_i - prev) < min_delta

    def prune_events(
        self,
        *,
        max_rows: int | None = None,
        max_age_days: int | None = None,
        now: datetime | None = None,
    ) -> dict[str, int]:
        """Delete old training_events by age and row-count cap."""
        try:
            from core.config import get_settings

            settings = get_settings()
            if max_rows is None:
                max_rows = int(getattr(settings, "training_events_max_rows", 50_000))
            if max_age_days is None:
                max_age_days = int(getattr(settings, "training_events_max_age_days", 14))
        except Exception:
            max_rows = max_rows or 50_000
            max_age_days = max_age_days or 14

        moment = now or _utcnow()
        cutoff = _iso(moment - timedelta(days=max(1, int(max_age_days))))
        deleted_age = 0
        deleted_cap = 0
        with self._pool.get_connection() as conn:
            deleted_age = conn.execute(
                "DELETE FROM training_events WHERE ts < ?",
                (cutoff,),
            ).rowcount
            # Keep the newest max_rows by sequence.
            row = conn.execute("SELECT COUNT(*) AS c FROM training_events").fetchone()
            count = int(row["c"] if row else 0)
            excess = max(0, count - max(1, int(max_rows)))
            if excess > 0:
                deleted_cap = conn.execute(
                    """
                    DELETE FROM training_events WHERE sequence IN (
                        SELECT sequence FROM training_events
                        ORDER BY sequence ASC
                        LIMIT ?
                    )
                    """,
                    (excess,),
                ).rowcount
        return {"deleted_by_age": int(deleted_age or 0), "deleted_by_cap": int(deleted_cap or 0)}

    @staticmethod
    def _event_from_row(row) -> TrainingEventV2:
        return TrainingEventV2(
            event_id=row["event_id"],
            version=row["version"],
            ts=row["ts"],
            task_id=row["task_id"],
            phase=row["phase"],
            kind=row["kind"],
            payload=_loads(row["payload_json"], {}),
            sequence=int(row["sequence"]),
        )

    def list_events(
        self,
        *,
        after_sequence: int = 0,
        task_id: str | None = None,
        limit: int = 1000,
    ) -> list[TrainingEventV2]:
        sql = "SELECT * FROM training_events WHERE sequence > ?"
        params: list[Any] = [max(0, int(after_sequence))]
        if task_id is not None:
            sql += " AND task_id = ?"
            params.append(task_id)
        sql += " ORDER BY sequence ASC LIMIT ?"
        params.append(max(1, min(int(limit), 5000)))
        with self._pool.get_readonly_connection() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [self._event_from_row(row) for row in rows]

    def latest_event(self, task_id: str | None = None) -> TrainingEventV2 | None:
        sql = "SELECT * FROM training_events"
        params: tuple[Any, ...] = ()
        if task_id is not None:
            sql += " WHERE task_id = ?"
            params = (task_id,)
        sql += " ORDER BY sequence DESC LIMIT 1"
        with self._pool.get_readonly_connection() as conn:
            row = conn.execute(sql, params).fetchone()
        return self._event_from_row(row) if row else None

    def current_event_sequence(self) -> int:
        with self._pool.get_readonly_connection() as conn:
            row = conn.execute("SELECT COALESCE(MAX(sequence), 0) AS sequence FROM training_events").fetchone()
        return int(row["sequence"])

    def append_log(
        self,
        *,
        task_id: str,
        level: str,
        logger: str,
        message: str,
        now: datetime | None = None,
    ) -> int:
        with self._pool.get_connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO training_logs (task_id, ts, level, logger, message)
                VALUES (?, ?, ?, ?, ?)
                """,
                (task_id, _iso(now), level, logger, message),
            )
            return int(cursor.lastrowid)

    def list_logs(
        self,
        task_id: str,
        *,
        after_sequence: int = 0,
        limit: int = 500,
    ) -> list[dict[str, Any]]:
        with self._pool.get_readonly_connection() as conn:
            rows = conn.execute(
                """
                SELECT sequence, task_id, ts, level, logger, message
                FROM training_logs
                WHERE task_id = ? AND sequence > ?
                ORDER BY sequence ASC LIMIT ?
                """,
                (task_id, max(0, int(after_sequence)), max(1, min(int(limit), 5000))),
            ).fetchall()
        return [dict(row) for row in rows]

    def recent_logs(self, task_id: str, *, limit: int = 50) -> list[dict[str, Any]]:
        with self._pool.get_readonly_connection() as conn:
            rows = conn.execute(
                """
                SELECT sequence, task_id, ts, level, logger, message
                FROM training_logs WHERE task_id = ?
                ORDER BY sequence DESC LIMIT ?
                """,
                (task_id, max(1, min(int(limit), 5000))),
            ).fetchall()
        return [dict(row) for row in reversed(rows)]

    def register_worker(
        self,
        worker_id: str,
        *,
        pid: int | None = None,
        hostname: str | None = None,
        metadata: dict[str, Any] | None = None,
        now: datetime | None = None,
    ) -> None:
        timestamp = _iso(now)
        with self._pool.get_connection() as conn:
            conn.execute(
                """
                INSERT INTO training_workers
                    (worker_id, pid, hostname, status, started_at, heartbeat_at, stopped_at, metadata_json)
                VALUES (?, ?, ?, 'online', ?, ?, NULL, ?)
                ON CONFLICT(worker_id) DO UPDATE SET
                    pid = excluded.pid, hostname = excluded.hostname, status = 'online',
                    started_at = excluded.started_at, heartbeat_at = excluded.heartbeat_at,
                    stopped_at = NULL, metadata_json = excluded.metadata_json
                """,
                (
                    worker_id,
                    int(pid if pid is not None else os.getpid()),
                    hostname or socket.gethostname(),
                    timestamp,
                    timestamp,
                    json.dumps(metadata or {}, ensure_ascii=False),
                ),
            )

    def heartbeat_worker(self, worker_id: str, *, now: datetime | None = None) -> bool:
        with self._pool.get_connection() as conn:
            updated = conn.execute(
                """
                UPDATE training_workers SET status = 'online', heartbeat_at = ?
                WHERE worker_id = ? AND status != 'stopped'
                """,
                (_iso(now), worker_id),
            ).rowcount
        return updated == 1

    def stop_worker(self, worker_id: str, *, now: datetime | None = None) -> bool:
        timestamp = _iso(now)
        with self._pool.get_connection() as conn:
            updated = conn.execute(
                """
                UPDATE training_workers SET status = 'stopped', heartbeat_at = ?, stopped_at = ?
                WHERE worker_id = ?
                """,
                (timestamp, timestamp, worker_id),
            ).rowcount
        return updated == 1

    def worker_status(
        self,
        *,
        stale_after_seconds: int = 30,
        now: datetime | None = None,
    ) -> list[dict[str, Any]]:
        moment = now or _utcnow()
        with self._pool.get_readonly_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM training_workers ORDER BY heartbeat_at DESC"
            ).fetchall()
        result = []
        for row in rows:
            status = row["status"]
            heartbeat = datetime.fromisoformat(row["heartbeat_at"])
            if status == "online" and heartbeat + timedelta(seconds=stale_after_seconds) < moment:
                status = "stale"
            result.append(
                {
                    "worker_id": row["worker_id"],
                    "pid": int(row["pid"]),
                    "hostname": row["hostname"],
                    "status": status,
                    "started_at": row["started_at"],
                    "heartbeat_at": row["heartbeat_at"],
                    "stopped_at": row["stopped_at"],
                    "metadata": _loads(row["metadata_json"], {}),
                }
            )
        return result


class TrainingEventRepositoryHub:
    """Adapter exposing the existing V2 event-hub contract over SQLite."""

    def __init__(self, repository: TrainingJobRepository):
        self.repository = repository

    def publish(self, *, task_id: str, phase: str, kind: str, payload=None) -> TrainingEventV2:
        event = self.repository.append_event(task_id=task_id, phase=phase, kind=kind, payload=payload)
        if event is not None:
            return event
        # Sampled-out progress: return latest durable event so callers keep a stable contract.
        latest = self.repository.latest_event(task_id)
        if latest is not None:
            return latest
        forced = self.repository.append_event(
            task_id=task_id, phase=phase, kind=kind, payload=payload, force=True
        )
        assert forced is not None
        return forced

    def list_since(self, sequence: int = 0, task_id: str | None = None) -> list[TrainingEventV2]:
        return self.repository.list_events(after_sequence=sequence, task_id=task_id)

    def get_latest(self, task_id: str | None = None) -> TrainingEventV2 | None:
        return self.repository.latest_event(task_id)

    @staticmethod
    def parse_last_event_id(last_event_id: str | None) -> int:
        if not last_event_id:
            return 0
        try:
            if last_event_id.startswith("tev2-"):
                return int(last_event_id.split("-", 2)[1])
            return int(last_event_id)
        except (TypeError, ValueError, IndexError):
            return 0

    def current_sequence(self) -> int:
        return self.repository.current_event_sequence()


_repositories: dict[str, TrainingJobRepository] = {}


def get_training_job_repository(db_path: str = APP_DB_PATH) -> TrainingJobRepository:
    normalized = str(Path(db_path).resolve())
    repository = _repositories.get(normalized)
    if repository is None:
        repository = TrainingJobRepository(normalized)
        _repositories[normalized] = repository
    return repository


def reset_training_job_repositories_for_tests() -> None:
    _repositories.clear()


__all__ = [
    "ACTIVE_JOB_STATUSES",
    "JOB_STATUS_TO_RECORD_STATUS",
    "TERMINAL_JOB_STATUSES",
    "TrainingEventRepositoryHub",
    "TrainingJob",
    "TrainingJobRepository",
    "get_training_job_repository",
    "record_status_for_job_status",
    "reset_training_job_repositories_for_tests",
]
