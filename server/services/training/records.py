"""Authoritative training-record access across worker and compatibility modes."""

from __future__ import annotations

from core.config import get_settings
from core.training_context import get_training_context
from core.training_state import TrainingRecord


def list_training_records(*, limit: int = 1000) -> list[TrainingRecord]:
    if get_settings().training_execution_mode == "worker":
        from training_worker.repository import get_training_job_repository

        return [
            TrainingRecord(**job.record)
            for job in get_training_job_repository().list_jobs(limit=limit)
        ]
    return list(get_training_context().state.get_history())


def find_training_record(task_id: str | None) -> TrainingRecord | None:
    if not task_id:
        return None
    if get_settings().training_execution_mode == "worker":
        from training_worker.repository import get_training_job_repository

        job = get_training_job_repository().get_job(task_id)
        return TrainingRecord(**job.record) if job else None
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


__all__ = ["find_training_record", "list_training_records", "save_training_record"]
