"""Resolve training artifact paths from durable identity, not path heuristics."""

from __future__ import annotations

from pathlib import Path

from core.config import get_settings


def resolve_training_output_dir(task_id: str) -> Path:
    """Return the output directory for a training task.

    Preference order:
    1. Durable worker job.output_path (worker mode)
    2. Training record.output_path from history (in_process)
    3. Fallback ``outputs/train_{task_id[:8]}`` for legacy rows
    """
    settings = get_settings()
    if getattr(settings, "training_execution_mode", "worker") == "worker":
        try:
            from training_worker.repository import get_training_job_repository

            job = get_training_job_repository().get_job(task_id)
            if job and job.output_path:
                return Path(job.output_path)
        except Exception:
            pass
    else:
        try:
            from core.training_context import get_training_context

            for record in get_training_context().state.get_history():
                if record.id == task_id and record.output_path:
                    return Path(record.output_path)
        except Exception:
            pass

    # Legacy fallback only — prefer not to invent new callers for this form.
    return settings.outputs_dir_resolved / f"train_{task_id[:8]}"


def resolve_training_metrics_file(task_id: str) -> Path:
    return resolve_training_output_dir(task_id) / "metrics.jsonl"


def resolve_training_log_file(task_id: str) -> Path:
    return resolve_training_output_dir(task_id) / "training.log"


__all__ = [
    "resolve_training_log_file",
    "resolve_training_metrics_file",
    "resolve_training_output_dir",
]
