"""Training execution gateway (worker / in_process)."""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from core.config import Settings, get_settings, settings
from services.training.policy import allow_skip_resource_check, map_progress_status

TERMINAL_PROGRESS_STATUSES = frozenset(
    {"completed", "failed", "stopped", "cancelled", "interrupted"}
)

# Re-exported so callers and tests can import control-plane policy helpers from
# the gateway module without reaching into services.training.policy directly.
__all__ = [
    "TERMINAL_PROGRESS_STATUSES",
    "TrainingGateway",
    "InProcessTrainingGateway",
    "WorkerTrainingGateway",
    "allow_skip_resource_check",
    "get_training_gateway",
    "map_progress_status",
]


class TrainingGateway(ABC):
    @abstractmethod
    async def stop(self) -> dict[str, Any]:
        ...

    @abstractmethod
    def get_progress(self, task_id: str | None = None) -> dict[str, Any]:
        ...

    @abstractmethod
    async def progress_stream(self, timeout: int, heartbeat: int):
        ...

    @abstractmethod
    def get_output_dir(self, task_id: str) -> Path:
        ...

    @abstractmethod
    def is_training_in_progress(self) -> bool:
        ...

    @abstractmethod
    def start(
        self,
        *,
        config: Any,
        model_path: Path,
        dataset_file: Path,
        settings: Settings | None = None,
        use_queue: bool = False,
        priority: str = "normal",
        record_id: str | None = None,
        output_path: Path | None = None,
    ) -> Any:
        ...

    @abstractmethod
    def get_history(self) -> list[Any]:
        ...

    @abstractmethod
    def get_status(self) -> dict[str, Any]:
        ...


class InProcessTrainingGateway(TrainingGateway):
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

        # P1-2: when task_id is provided, ensure we only return progress for
        # that task — otherwise concurrent in_process tasks would cross-pollute
        # via state.get_progress() which always returns the latest snapshot.
        state = self.context.state
        if task_id is not None:
            current_record = state.get_current_record() if hasattr(state, "get_current_record") else None
            if current_record is not None and getattr(current_record, "id", None) != task_id:
                # Requested task is not the active one — return idle progress.
                from training_engine.schemas import TrainingProgressResponse as _PR
                idle = _PR(status="idle", message="Task not active")
                return idle.model_dump()

        progress = state.get_progress()
        latest_event = get_training_event_hub_v2().get_latest()
        if latest_event:
            merged = legacy_progress_from_v2_event(latest_event, progress)
            if "status" in merged:
                merged["status"] = map_progress_status(str(merged["status"]))
            return TrainingProgressResponse(**merged).model_dump()
        data = progress.model_dump()
        data["status"] = map_progress_status(str(data.get("status") or "idle"))
        return TrainingProgressResponse(**data).model_dump()

    async def progress_stream(self, timeout: int, heartbeat: int):
        import asyncio
        import time

        started = time.time()
        last_payload: str | None = None
        heartbeat = max(1, int(heartbeat))
        timeout = max(1, int(timeout))
        ticks_since_emit = 0
        while time.time() - started <= timeout:
            progress = self.get_progress()
            payload = json.dumps(progress, ensure_ascii=False)
            ticks_since_emit += 1
            if payload != last_payload:
                yield f"data: {payload}\n\n"
                last_payload = payload
                ticks_since_emit = 0
            elif ticks_since_emit >= heartbeat:
                yield ": keepalive\n\n"
                ticks_since_emit = 0
            if progress.get("status") in TERMINAL_PROGRESS_STATUSES:
                break
            await asyncio.sleep(1)

    def get_output_dir(self, task_id: str) -> Path:
        from services.training.paths import resolve_training_output_dir

        return resolve_training_output_dir(task_id)

    def is_training_in_progress(self) -> bool:
        return self.context.state.is_training()

    def start(
        self,
        *,
        config: Any,
        model_path: Path,
        dataset_file: Path,
        settings: Settings | None = None,
        use_queue: bool = False,
        priority: str = "normal",
        record_id: str | None = None,
        output_path: Path | None = None,
    ) -> Any:
        from services.training.orchestrator import start_training_task

        return start_training_task(
            config=config,
            state=self.context.state,
            settings=settings or get_settings(),
            model_path=Path(model_path),
            dataset_file=Path(dataset_file),
            use_queue=use_queue,
            priority=priority,
            record_id=record_id,
            output_path=Path(output_path) if output_path is not None else None,
        )

    def get_history(self) -> list[Any]:
        return self.context.state.get_history()

    def get_status(self) -> dict[str, Any]:
        from services.training.policy import history_authority

        status = self.context.get_status()
        if isinstance(status, dict):
            status["history_authority"] = history_authority()
            progress = (status.get("training") or {}).get("progress")
            if isinstance(progress, dict) and "status" in progress:
                progress["status"] = map_progress_status(str(progress.get("status")))
            if "status" not in status:
                is_training = bool((status.get("training") or {}).get("is_training"))
                status["status"] = "training" if is_training else "idle"
                status["is_training"] = is_training
        return status


class WorkerTrainingGateway(TrainingGateway):
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
        status = "stopping" if result == "cancellation_requested" else result
        return {"message": "Stop requested", "status": status, "task_id": job.job_id}

    def _worker_progress(self, task_id: str | None = None) -> dict[str, Any]:
        from training_engine.schemas import TrainingProgressResponse

        job = self.repo.get_job(task_id) if task_id else self.repo.active_job()
        if job is None and task_id is None:
            jobs = self.repo.list_jobs(limit=1)
            job = jobs[0] if jobs else None
        event = self.repo.latest_event(job.job_id) if job else None
        payload = dict(event.payload) if event else {}
        raw_status = payload.get("status") or (job.status if job else "idle")
        status = map_progress_status(str(raw_status), job_status=job.status if job else None)
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
            "message": payload.get("message")
            or (f"Training job {job.status}" if job else ""),
        }
        response = TrainingProgressResponse(**defaults)
        for field in type(response).model_fields:
            if field in payload and field != "status":
                setattr(response, field, payload[field])
        response.status = status
        return response.model_dump()

    def get_progress(self, task_id: str | None = None) -> dict[str, Any]:
        return self._worker_progress(task_id)

    async def progress_stream(self, timeout: int, heartbeat: int):
        import asyncio
        import time

        started = time.time()
        last_payload: str | None = None
        heartbeat = max(1, int(heartbeat))
        timeout = max(1, int(timeout))
        ticks_since_emit = 0
        while time.time() - started <= timeout:
            progress = self._worker_progress()
            payload = json.dumps(progress, ensure_ascii=False)
            ticks_since_emit += 1
            if payload != last_payload:
                yield f"data: {payload}\n\n"
                last_payload = payload
                ticks_since_emit = 0
            elif ticks_since_emit >= heartbeat:
                yield ": keepalive\n\n"
                ticks_since_emit = 0
            if progress["status"] in TERMINAL_PROGRESS_STATUSES:
                break
            await asyncio.sleep(1)

    def get_output_dir(self, task_id: str) -> Path:
        from services.training.paths import resolve_training_output_dir

        return resolve_training_output_dir(task_id)

    def is_training_in_progress(self) -> bool:
        return self.repo.active_job() is not None

    def start(
        self,
        *,
        config: Any,
        model_path: Path,
        dataset_file: Path,
        settings: Settings | None = None,
        use_queue: bool = False,
        priority: str = "normal",
        record_id: str | None = None,
        output_path: Path | None = None,
    ) -> Any:
        from services.training.orchestrator import start_training_task

        return start_training_task(
            config=config,
            state=None,
            settings=settings or get_settings(),
            model_path=Path(model_path),
            dataset_file=Path(dataset_file),
            use_queue=use_queue,
            priority=priority,
            record_id=record_id,
            output_path=Path(output_path) if output_path is not None else None,
        )

    def get_history(self) -> list[Any]:
        from services.training.records import list_training_records

        return list_training_records()

    def get_status(self) -> dict[str, Any]:
        from services.training.policy import history_authority

        status = self.repo.queue_status()
        job = self.repo.active_job()
        status["is_training"] = job is not None
        raw = job.status if job else "idle"
        status["status"] = map_progress_status(raw, job_status=raw)
        status["job_status"] = raw if job else "idle"
        status["history_authority"] = history_authority()
        if job:
            status["task_id"] = job.job_id
        return status


def get_training_gateway() -> TrainingGateway:
    if settings.training_execution_mode == "worker":
        return WorkerTrainingGateway()
    return InProcessTrainingGateway()
