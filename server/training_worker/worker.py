"""Worker runtime that executes one durable training job at a time."""

from __future__ import annotations

import logging
import os
import socket
import threading
import uuid
from collections.abc import Callable
from typing import Any

from training_engine.schemas import TrainingConfigInput
from training_engine.training_thread import training_thread

from core.config import Settings, get_settings
from core.training_context import get_training_context
from core.training_events_v2 import configure_training_event_hub_v2, reset_training_event_hub_v2
from core.training_state import TrainingRecord

from .repository import TrainingEventRepositoryHub, TrainingJob, TrainingJobRepository

logger = logging.getLogger(__name__)

TrainingExecutor = Callable[[TrainingJob, threading.Event], dict[str, Any] | None]


def _convert_config_to_swift(config: TrainingConfigInput, output_path: str) -> "SwiftTrainConfig":
    """P0-3: Build a SwiftTrainConfig from a TrainingConfigInput.

    Field defaults mirror the historical /start-swift endpoint mapping at
    ``api/training.py`` so behaviour is preserved when SWIFT tasks sink into
    the worker queue. Missing fields fall back to SwiftTrainConfig defaults.
    """
    from backends.swift_backend import SwiftTrainConfig

    method = config.method
    # Strip the "swift_" prefix that the API layer adds for backend disambiguation
    if method.startswith("swift_"):
        method = method[len("swift_"):]

    return SwiftTrainConfig(
        model_id=config.model_id,
        dataset_id=config.dataset_id,
        method=method,
        learning_rate=config.learning_rate,
        epochs=config.epochs,
        batch_size=config.batch_size,
        gradient_accumulation=config.gradient_accumulation,
        max_seq_length=config.max_seq_length,
        lora_rank=getattr(config, "rank", 8),
        lora_alpha=getattr(config, "alpha", 16),
        lora_dropout=0.05,
        quantization_bit=config.quantization if method == "qlora" else 0,
        output_dir=output_path,
        save_steps=config.save_steps,
        logging_steps=config.logging_steps,
        warmup_steps=config.warmup_steps,
        warmup_ratio=0.1,
        weight_decay=0.01,
        max_grad_norm=1.0,
        val_size=0.0,
    )


class _DurableTrainingLogHandler(logging.Handler):
    def __init__(self, repository: TrainingJobRepository, task_id: str):
        super().__init__(level=logging.INFO)
        self.repository = repository
        self.task_id = task_id

    def emit(self, record: logging.LogRecord) -> None:
        if not record.name.startswith("training."):
            return
        try:
            self.repository.append_log(
                task_id=self.task_id,
                level=record.levelname,
                logger=record.name,
                message=self.format(record),
            )
        except Exception:
            # Logging must never make a training run fail or recurse through DB logging.
            return


class TrainingWorker:
    def __init__(
        self,
        repository: TrainingJobRepository,
        *,
        settings: Settings | None = None,
        worker_id: str | None = None,
        executor: TrainingExecutor | None = None,
    ):
        self.repository = repository
        self.settings = settings or get_settings()
        self.worker_id = worker_id or f"{socket.gethostname()}-{os.getpid()}-{uuid.uuid4().hex[:8]}"
        self.executor = executor or self._execute_native
        # P0-3: dispatch by job.backend — SWIFT tasks sink into the durable queue
        # alongside native ones so they share lease/heartbeat/recovery semantics.
        self.executors: dict[str, TrainingExecutor] = {
            "native": self._execute_native,
            "swift": self._execute_swift,
        }
        self._stop = threading.Event()
        self._current_cancel = threading.Event()

    def stop(self) -> None:
        self._stop.set()
        self._current_cancel.set()

    def run_forever(self) -> None:
        self.repository.register_worker(
            self.worker_id,
            metadata={"execution_mode": "worker", "backends": ["native"]},
        )
        configure_training_event_hub_v2(TrainingEventRepositoryHub(self.repository))
        try:
            while not self._stop.is_set():
                did_work = self.run_once()
                if not did_work:
                    self.repository.heartbeat_worker(self.worker_id)
                    self._stop.wait(self.settings.training_worker_poll_seconds)
        finally:
            self.repository.stop_worker(self.worker_id)
            reset_training_event_hub_v2()

    def run_once(self) -> bool:
        self.repository.recover_expired()
        job = self.repository.claim_next(
            self.worker_id,
            lease_seconds=self.settings.training_worker_lease_seconds,
        )
        if job is None:
            return False
        self._run_claimed(job)
        return True

    def _run_claimed(self, job: TrainingJob) -> None:
        if not self.repository.mark_running(job.job_id, self.worker_id):
            logger.warning("Training job lease lost before start: %s", job.job_id)
            return

        self._current_cancel = threading.Event()
        monitor_stop = threading.Event()
        monitor = threading.Thread(
            target=self._monitor_job,
            args=(job.job_id, monitor_stop),
            name=f"training-lease-{job.job_id[:8]}",
            daemon=True,
        )
        monitor.start()
        durable_log_handler = _DurableTrainingLogHandler(self.repository, job.job_id)
        durable_log_handler.setFormatter(logging.Formatter("%(message)s"))
        logging.getLogger().addHandler(durable_log_handler)
        error: str | None = None
        try:
            # P0-3: dispatch to backend-specific executor (native or swift).
            # Falls back to self.executor for backends not in the registry
            # (preserves backward compatibility for custom executor injection).
            executor = self.executors.get(job.backend, self.executor)
            record = executor(job, self._current_cancel) or dict(job.record)
            status = str(record.get("status") or "completed")
            if status not in {"completed", "failed", "stopped", "cancelled", "interrupted"}:
                status = "failed"
                error = f"training executor returned non-terminal status: {record.get('status')}"
                record["status"] = status
            self.repository.finish(
                job.job_id,
                self.worker_id,
                status=status,
                record=record,
                error=error,
            )
        except Exception as exc:
            logger.exception("Training job %s failed in worker", job.job_id)
            error = str(exc)
            self.repository.append_log(
                task_id=job.job_id,
                level="ERROR",
                logger=__name__,
                message=error,
            )
            record = dict(job.record)
            record["status"] = "failed"
            self.repository.finish(
                job.job_id,
                self.worker_id,
                status="failed",
                record=record,
                error=error,
            )
        finally:
            # Safety net: always drop training GPU lease after a job ends
            # (pipeline cleanup should already release; this covers hard failures).
            try:
                from core.gpu_coordination import release_training_gpu

                release_training_gpu()
            except Exception:
                pass
            logging.getLogger().removeHandler(durable_log_handler)
            durable_log_handler.close()
            monitor_stop.set()
            monitor.join(timeout=max(1.0, self.settings.training_worker_heartbeat_seconds * 2))

    def _monitor_job(self, job_id: str, monitor_stop: threading.Event) -> None:
        interval = self.settings.training_worker_heartbeat_seconds
        gpu_lease_seconds = max(float(self.settings.training_worker_lease_seconds) * 4.0, 60.0)
        # P0-2: heartbeat resilience — exponential backoff + max consecutive failures
        # guards against transient DB locks (sqlite3.OperationalError) silently
        # killing the monitor thread and leaving the job without lease protection.
        MAX_FAILURES = 5
        BASE_BACKOFF = 1.0
        MAX_BACKOFF = 30.0
        consecutive_failures = 0
        while not monitor_stop.wait(interval):
            try:
                self.repository.heartbeat_worker(self.worker_id)
                if not self.repository.heartbeat(
                    job_id,
                    self.worker_id,
                    lease_seconds=self.settings.training_worker_lease_seconds,
                ):
                    self._current_cancel.set()
                    return
                consecutive_failures = 0  # success resets the backoff window
            except Exception as exc:
                consecutive_failures += 1
                backoff = min(BASE_BACKOFF * (2 ** (consecutive_failures - 1)), MAX_BACKOFF)
                logger.warning(
                    "Heartbeat failed for %s (attempt %d/%d): %s; backing off %.1fs",
                    job_id, consecutive_failures, MAX_FAILURES, exc, backoff,
                )
                if consecutive_failures >= MAX_FAILURES:
                    logger.error(
                        "Heartbeat failed %d consecutive times for %s, requesting cancel",
                        consecutive_failures, job_id,
                    )
                    self._current_cancel.set()
                    return
                # Backoff — wait() returns True immediately if monitor_stop is set
                if monitor_stop.wait(backoff):
                    return
                continue
            try:
                from core.gpu_coordination import renew_training_gpu

                renew_training_gpu(lease_seconds=gpu_lease_seconds)
            except Exception:
                pass
            current = self.repository.get_job(job_id)
            if current and current.cancel_requested:
                self._current_cancel.set()

    def _execute_native(self, job: TrainingJob, cancel_event: threading.Event) -> dict[str, Any]:
        config = TrainingConfigInput(**job.config)
        config.output_path = job.output_path
        record = TrainingRecord(**job.record)
        state = get_training_context().state
        state.clear_stop_request()
        state.set_current_record(record)
        state.queue_training_state(True)
        state.register_training_task(job.job_id, threading.current_thread())

        self._apply_recovery_checkpoint(job, config, state)

        cancellation_stop = threading.Event()

        def bridge_cancellation() -> None:
            while not cancellation_stop.wait(0.25):
                if cancel_event.is_set():
                    state.request_stop()
                    return

        cancellation_thread = threading.Thread(
            target=bridge_cancellation,
            name=f"training-cancel-{job.job_id[:8]}",
            daemon=True,
        )
        cancellation_thread.start()
        try:
            training_thread(
                config,
                job.model_path,
                job.dataset_path,
                state,
                record,
                event_loop=None,
                task_id=job.job_id,
            )
            return record.model_dump()
        finally:
            cancellation_stop.set()
            cancellation_thread.join(timeout=1.0)
            state.queue_training_state(False)
            state.unregister_training_task(job.job_id)

    def _execute_swift(self, job: TrainingJob, cancel_event: threading.Event) -> dict[str, Any]:
        """P0-3: SWIFT executor sunk into the durable Worker queue.

        Mirrors ``_execute_native``'s state-bridging contract (C5):
        ``set_current_record`` + ``queue_training_state(True)`` + ``register_training_task``
        so that progress/heartbeat/cancel observers see this task identically.
        """
        from backends.swift_backend import SwiftTrainConfig, get_swift_backend
        from pathlib import Path

        config = TrainingConfigInput(**job.config)
        config.output_path = job.output_path
        record = TrainingRecord(**job.record)
        state = get_training_context().state
        state.clear_stop_request()
        state.set_current_record(record)
        state.queue_training_state(True)
        state.register_training_task(job.job_id, threading.current_thread())

        swift_config = _convert_config_to_swift(config, job.output_path)
        backend = get_swift_backend()
        if not backend.is_available():
            raise RuntimeError("SWIFT framework is not installed (pip install ms-swift -U)")

        log_dir = Path(job.output_path) / "swift_logs"
        if not backend.start_training(swift_config, log_dir, job.job_id):
            raise RuntimeError(
                "SWIFT start_training returned False — another SWIFT process may be running "
                "(SwiftBackend is a singleton with a single process slot)"
            )

        try:
            # Poll process status until exit or cancel. cancel_event is set by
            # _monitor_job when the lease is lost or the user requests cancel.
            while not cancel_event.wait(2.0):
                status = backend.get_training_status()
                if status.get("status") != "running":
                    break
            if cancel_event.is_set():
                backend.stop_training()

            final = backend.get_training_status()
            final_status = final.get("status", "failed")
            if final_status == "completed":
                record.status = "completed"
                record.end_time = __import__("datetime").datetime.now().isoformat()
                record.checkpoint_path = str(Path(job.output_path) / "adapter_model")
                record.adapter_path = record.checkpoint_path
            elif final_status == "failed":
                record.status = "failed"
                record.end_time = __import__("datetime").datetime.now().isoformat()
                log_tail = backend.get_log_tail(20)
                record.error = "\n".join(log_tail) if log_tail else "SWIFT process exited non-zero"
            else:
                record.status = "failed"
                record.end_time = __import__("datetime").datetime.now().isoformat()
                record.error = f"SWIFT ended in unexpected status: {final_status}"
            backend.cleanup()
            return record.model_dump()
        finally:
            state.queue_training_state(False)
            state.unregister_training_task(job.job_id)

    def _apply_recovery_checkpoint(self, job: TrainingJob, config: TrainingConfigInput, state) -> None:
        if job.attempt <= 1 or config.resume_from_checkpoint:
            return
        try:
            from training_engine.checkpoint_manager import get_latest_checkpoint

            checkpoint = get_latest_checkpoint(state, self.settings, job.job_id)
            if checkpoint and checkpoint.get("valid") and "recovery-exception" not in checkpoint.get("name", ""):
                config.resume_from_checkpoint = checkpoint["path"]
                config.resume_from_adapter = None
                self.repository.append_event(
                    task_id=job.job_id,
                    phase="loading",
                    kind="checkpoint_recovery_selected",
                    payload={"checkpoint": checkpoint["path"], "attempt": job.attempt},
                )
        except Exception:
            logger.exception("Failed to discover recovery checkpoint for %s", job.job_id)


__all__ = ["TrainingWorker"]
