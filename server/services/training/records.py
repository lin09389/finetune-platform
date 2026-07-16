"""Authoritative training-record access across worker and compatibility modes.

History authority (P2 dual-persistence policy)
----------------------------------------------
- ``training_execution_mode=worker``: SQLite ``training_jobs`` (+ ``record_json``)
  is the single source of truth. List/history never merge process-local JSON.
- ``training_execution_mode=in_process``: JSON history under outputs (TrainingState)
  is authoritative. Switching modes does **not** auto-migrate rows; callers must
  not expect a silent union of both stores.
"""

from __future__ import annotations

from typing import Any

from core.config import get_settings
from core.training_context import get_training_context
from core.training_state import TrainingRecord
from services.training.policy import history_authority


def _record_from_durable_job(job: Any) -> TrainingRecord:
    from training_worker.repository import record_status_for_job_status

    payload = dict(job.record or {})
    payload["status"] = record_status_for_job_status(job.status)
    if not payload.get("id"):
        payload["id"] = job.job_id
    if not payload.get("output_path"):
        payload["output_path"] = job.output_path
    payload.setdefault("model_name", (job.config or {}).get("model_id", "unknown"))
    payload.setdefault("dataset_name", (job.config or {}).get("dataset_id", "unknown"))
    payload.setdefault("method", (job.config or {}).get("method", "qlora"))
    payload.setdefault("start_time", job.created_at or job.queued_at)
    payload.setdefault("config", job.config or {})
    payload.setdefault("end_time", job.finished_at)
    return TrainingRecord(**payload)


def list_training_records(*, limit: int = 1000) -> list[TrainingRecord]:
    if get_settings().training_execution_mode == "worker":
        from training_worker.repository import get_training_job_repository

        return [
            _record_from_durable_job(job)
            for job in get_training_job_repository().list_jobs(limit=limit)
        ]
    return list(get_training_context().state.get_history())


def find_training_record(task_id: str | None) -> TrainingRecord | None:
    if not task_id:
        return None
    if get_settings().training_execution_mode == "worker":
        from training_worker.repository import get_training_job_repository

        job = get_training_job_repository().get_job(task_id)
        return _record_from_durable_job(job) if job else None
    return next(
        (record for record in get_training_context().state.get_history() if record.id == task_id),
        None,
    )


def save_training_record(record: TrainingRecord) -> None:
    if get_settings().training_execution_mode == "worker":
        from training_worker.repository import get_training_job_repository

        if not get_training_job_repository().update_record(record.id, record.model_dump()):
            raise KeyError(f"Training record not found: {record.id}")
        return
    get_training_context().state.add_to_history_sync(record)


def history_meta() -> dict[str, str]:
    """Small descriptor for API clients about where history is read from."""
    return {
        "authority": history_authority(),
        "mode": getattr(get_settings(), "training_execution_mode", "worker"),
    }


__all__ = [
    "find_training_record",
    "history_meta",
    "list_training_records",
    "save_training_record",
]
