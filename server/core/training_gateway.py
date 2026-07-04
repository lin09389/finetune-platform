"""Training execution gateway.

This module abstracts the two training execution modes:

- ``in_process``: training runs inside the API process via ``TrainingContext``.
- ``worker``: training is enqueued in SQLite and executed by a separate worker.

Routing code in ``api/training`` delegates to the gateway instead of branching
on ``training_execution_mode`` directly.
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from core.config import get_settings, settings


class TrainingGateway(ABC):
    """Abstract training execution gateway."""

    @abstractmethod
    async def stop(self) -> dict[str, Any]:
        """Request training to stop."""
        ...

    @abstractmethod
    def get_progress(self, task_id: str | None = None) -> dict[str, Any]:
        """Return current training progress as a dict."""
        ...

    @abstractmethod
    async def progress_stream(self, timeout: int, heartbeat: int):
        """Yield SSE events for training progress."""
        ...

    @abstractmethod
    def get_output_dir(self, task_id: str) -> Path:
        """Return the output directory for a given training task."""
        ...

    @abstractmethod
    def is_training_in_progress(self) -> bool:
        """Return whether a training task is currently active."""
        ...

    @abstractmethod
    async def start(self, config: dict[str, Any]) -> dict[str, Any]:
        """Start a training run."""
        ...

    @abstractmethod
    def get_history(self) -> list[dict[str, Any]]:
        """Return training history."""
        ...

    @abstractmethod
    def get_status(self) -> dict[str, Any]:
        """Return overall training status."""
        ...


class InProcessTrainingGateway(TrainingGateway):
    """Training gateway that runs training inside the API process."""

    def __init__(self):
        from core.training_context import get_training_context

        self.context = get_training_context()

    async def stop(self) -> dict[str, Any]:
        from training_engine.callbacks import queue_training_progress

        state = self.context.state
        if not state.is_training():
            raise ValueError("No training in progress")
        if state.should_stop():
            return {"message": "Stop already requested", "status": "stopping"}
        state.request_stop()
        queue_training_progress(
            state,
            status="stopping",
            message="Stop requested, waiting for current step to finish",
        )
        return {"message": "Stop requested", "status": "stopping"}

    def get_progress(self, task_id: str | None = None) -> dict[str, Any]:
        from training_engine.reporter import legacy_progress_from_v2_event
        from training_engine.schemas import TrainingProgressResponse

        from core.training_events_v2 import get_training_event_hub_v2

        progress = self.context.state.get_progress()
        latest_event = get_training_event_hub_v2().get_latest()
        if latest_event:
            merged = legacy_progress_from_v2_event(latest_event, progress)
            return TrainingProgressResponse(**merged).model_dump()
        return TrainingProgressResponse(**progress.model_dump()).model_dump()

    async def progress_stream(self, timeout: int, heartbeat: int):
        from core.training_events_v2 import get_training_event_hub_v2

        state = self.context.state
        hub = get_training_event_hub_v2()

        FORCE_SEND_INTERVAL = 5
        last_step = -1
        last_status = ""
        last_message = ""
        last_seq = 0
        idle_count = 0

        import asyncio

        while True:
            progress = state.get_progress()
            event = hub.get_latest()
            seq = event.sequence if event else last_seq
            changed = (
                progress.step != last_step
                or progress.status != last_status
                or progress.message != last_message
                or seq != last_seq
            )
            if changed or idle_count * 1 >= FORCE_SEND_INTERVAL:
                payload = progress.model_dump_json()
                yield f"data: {payload}\n\n"
                last_step = progress.step
                last_status = progress.status
                last_message = progress.message
                last_seq = seq
                idle_count = 0
            else:
                idle_count += 1
            if progress.status in {"completed", "failed", "stopped", "cancelled", "interrupted"}:
                break
            await asyncio.sleep(1)

    def get_output_dir(self, task_id: str) -> Path:
        from training_engine.checkpoint_manager import _resolve_training_output_dir

        return _resolve_training_output_dir(self.context.state, get_settings(), task_id)

    def is_training_in_progress(self) -> bool:
        return self.context.state.is_training()

    async def start(self, config: dict[str, Any]) -> dict[str, Any]:
        from services.training.orchestrator import start_training_task

        return await start_training_task(config)

    def get_history(self) -> list[Any]:
        return self.context.state.get_history()

    def get_status(self) -> dict[str, Any]:
        return self.context.get_status()


class WorkerTrainingGateway(TrainingGateway):
    """Training gateway backed by the durable SQLite worker queue."""

    def __init__(self):
        from training_worker.repository import get_training_job_repository

        self.repo = get_training_job_repository()

    async def stop(self) -> dict[str, Any]:
        job = self.repo.active_job()
        if job is None:
            raise ValueError("No training in progress")
        result = self.repo.request_cancel(job.job_id)
        if result is None:
            raise ValueError("Training is already terminal")
        return {"message": "Stop requested", "status": "stopping", "task_id": job.job_id}

    def _worker_progress(self, task_id: str | None = None) -> dict[str, Any]:
        from training_engine.schemas import TrainingProgressResponse

        job = self.repo.get_job(task_id) if task_id else self.repo.active_job()
        if job is None and task_id is None:
            jobs = self.repo.list_jobs(limit=1)
            job = jobs[0] if jobs else None
        event = self.repo.latest_event(job.job_id) if job else None
        payload = dict(event.payload) if event else {}
        status = payload.get("status") or (job.status if job else "idle")
        if status == "running":
            status = "training"
        if status in {"leased", "queued"}:
            status = "loading"
        defaults = {
            "epoch": 0,
            "step": 0,
            "total_steps": 0,
            "loss": 0.0,
            "lr": 0.0,
            "vram_used": 0.0,
            "elapsed_time": 0.0,
            "eta": 0.0,
            "status": status,
            "message": payload.get("message") or (f"Training job {job.status}" if job else ""),
        }
        response = TrainingProgressResponse(**defaults)
        for field in response.model_fields:
            if field in payload:
                setattr(response, field, payload[field])
        return response.model_dump()

    def get_progress(self, task_id: str | None = None) -> dict[str, Any]:
        return self._worker_progress(task_id)

    async def progress_stream(self, timeout: int, heartbeat: int):
        import asyncio
        import time

        started = time.time()
        last_payload = None
        while time.time() - started <= timeout:
            progress = self._worker_progress()
            payload = json.dumps(progress)
            if payload != last_payload:
                yield f"data: {payload}\n\n"
                last_payload = payload
            if progress["status"] in {"completed", "failed", "stopped", "cancelled", "interrupted"}:
                break
            await asyncio.sleep(1)

    def get_output_dir(self, task_id: str) -> Path:
        job = self.repo.get_job(task_id)
        if job:
            return Path(job.output_path)
        raise ValueError(f"Training job not found: {task_id}")

    def is_training_in_progress(self) -> bool:
        return self.repo.active_job() is not None

    async def start(self, config: dict[str, Any]) -> dict[str, Any]:
        from services.training.orchestrator import start_training_task

        return await start_training_task(config)

    def get_history(self) -> list[Any]:
        from services.training.records import list_training_records

        return list_training_records()

    def get_status(self) -> dict[str, Any]:
        status = self.repo.queue_status()
        job = self.repo.active_job()
        status["is_training"] = job is not None
        status["status"] = job.status if job else "idle"
        return status


def get_training_gateway() -> TrainingGateway:
    """Return the active training gateway based on current settings."""
    if settings.training_execution_mode == "worker":
        return WorkerTrainingGateway()
    return InProcessTrainingGateway()
