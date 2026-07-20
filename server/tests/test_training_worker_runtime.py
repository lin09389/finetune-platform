from __future__ import annotations

import logging
import subprocess
import sys
import threading
import time
from pathlib import Path

from training_worker.repository import TrainingEventRepositoryHub, TrainingJobRepository
from training_worker.worker import TrainingWorker

from core.config import Settings
from core.training_events_v2 import (
    configure_training_event_hub_v2,
    get_training_event_hub_v2,
    reset_training_event_hub_v2,
)


def _settings(tmp_path) -> Settings:
    return Settings(
        training_execution_mode="worker",
        training_worker_heartbeat_seconds=0.5,
        training_worker_lease_seconds=5,
        training_worker_poll_seconds=0.1,
        models_dir=tmp_path / "models",
        datasets_dir=tmp_path / "datasets",
        outputs_dir=tmp_path / "outputs",
    )


def _enqueue(repo: TrainingJobRepository, job_id: str = "job"):
    return repo.enqueue(
        job_id=job_id,
        backend="native",
        priority=2,
        config={"model_id": "model", "dataset_id": "dataset"},
        model_path="models/model",
        dataset_path="datasets/dataset/data.jsonl",
        output_path=f"outputs/{job_id}",
        record={
            "id": job_id,
            "model_name": "model",
            "dataset_name": "dataset",
            "method": "qlora",
            "status": "queued",
            "start_time": "2026-07-03T00:00:00+00:00",
            "config": {"model_id": "model", "dataset_id": "dataset"},
            "output_path": f"outputs/{job_id}",
        },
    )


def test_worker_executes_claimed_job_and_persists_terminal_record(tmp_path):
    repo = TrainingJobRepository(str(tmp_path / "jobs.db"))
    _enqueue(repo)

    def executor(job, _cancel):
        record = dict(job.record)
        record.update(status="completed", final_loss=0.25)
        return record

    worker = TrainingWorker(repo, settings=_settings(tmp_path), worker_id="worker-a", executor=executor)
    # P0-3: dispatch 通过 self.executors.get(job.backend, self.executor) 派发,
    # 对 backend="native" 任务会命中 self.executors["native"],绕过构造参数
    # executor。必须直接 patch executors dict(同 PR25 修复模式)。
    worker.executors["native"] = executor
    assert worker.run_once() is True

    job = repo.get_job("job")
    assert job.status == "completed"
    assert job.record["final_loss"] == 0.25
    assert job.lease_owner is None
    assert [event.kind for event in repo.list_events(task_id="job")][-1] == "task_completed"


def test_worker_failure_is_terminal_and_does_not_escape_poll_loop(tmp_path):
    repo = TrainingJobRepository(str(tmp_path / "jobs.db"))
    _enqueue(repo)

    def executor(_job, _cancel):
        raise RuntimeError("simulated CUDA OOM")

    worker = TrainingWorker(repo, settings=_settings(tmp_path), worker_id="worker-a", executor=executor)
    worker.executors["native"] = executor  # 同上,绕过 dispatch 的 fallback
    assert worker.run_once() is True
    job = repo.get_job("job")
    assert job.status == "failed"
    assert job.error == "simulated CUDA OOM"


def test_worker_pipeline_events_are_persisted_for_control_plane_replay(tmp_path):
    repo = TrainingJobRepository(str(tmp_path / "jobs.db"))
    _enqueue(repo)
    configure_training_event_hub_v2(TrainingEventRepositoryHub(repo))

    def executor(job, _cancel):
        task_logger = logging.getLogger(f"training.{job.job_id}")
        task_logger.setLevel(logging.INFO)
        task_logger.info("durable worker log")
        get_training_event_hub_v2().publish(
            task_id=job.job_id,
            phase="running",
            kind="progress_updated",
            payload={"status": "running", "step": 9, "loss": 0.4},
        )
        record = dict(job.record)
        record["status"] = "completed"
        return record

    try:
        worker = TrainingWorker(repo, settings=_settings(tmp_path), worker_id="worker-a", executor=executor)
        worker.executors["native"] = executor  # 同上,绕过 dispatch 的 fallback
        assert worker.run_once() is True
    finally:
        reset_training_event_hub_v2()

    progress = [event for event in repo.list_events(task_id="job") if event.kind == "progress_updated"]
    assert progress[-1].payload == {"status": "running", "step": 9, "loss": 0.4}
    assert repo.recent_logs("job")[-1]["message"] == "durable worker log"


def test_running_worker_observes_durable_cancellation_request(tmp_path):
    repo = TrainingJobRepository(str(tmp_path / "jobs.db"))
    _enqueue(repo)
    started = threading.Event()

    def executor(job, cancel):
        started.set()
        assert cancel.wait(4), "worker did not observe durable cancellation"
        record = dict(job.record)
        record["status"] = "stopped"
        return record

    worker = TrainingWorker(repo, settings=_settings(tmp_path), worker_id="worker-a", executor=executor)
    worker.executors["native"] = executor  # 同上,绕过 dispatch 的 fallback
    thread = threading.Thread(target=worker.run_once)
    thread.start()
    assert started.wait(2)
    assert repo.request_cancel("job") == "cancellation_requested"
    thread.join(timeout=6)

    assert not thread.is_alive()
    assert repo.get_job("job").status == "stopped"


def test_worker_crash_lease_is_recovered_by_fresh_process_view(tmp_path):
    db_path = str(tmp_path / "jobs.db")
    first_process = TrainingJobRepository(db_path)
    _enqueue(first_process)
    claimed = first_process.claim_next("dead-worker", lease_seconds=1)
    assert claimed and claimed.status == "leased"

    time.sleep(1.05)
    restarted_control_plane = TrainingJobRepository(db_path)
    assert restarted_control_plane.recover_expired() == {
        "requeued": 1,
        "interrupted": 0,
        "cancelled": 0,
    }
    recovered = restarted_control_plane.claim_next("replacement-worker", lease_seconds=5)
    assert recovered and recovered.job_id == "job"
    assert recovered.attempt == 2


def test_hard_killed_worker_process_leaves_api_database_recoverable(tmp_path):
    db_path = str(tmp_path / "process-crash.db")
    control_plane = TrainingJobRepository(db_path)
    _enqueue(control_plane)
    script = """
import os
import sys
from training_worker.repository import TrainingJobRepository

repo = TrainingJobRepository(sys.argv[1])
job = repo.claim_next('killed-worker', lease_seconds=1)
assert job and job.job_id == 'job'
repo.mark_running('job', 'killed-worker')
os._exit(23)
"""
    completed = subprocess.run(
        [sys.executable, "-c", script, db_path],
        cwd=Path(__file__).resolve().parents[1],
        check=False,
    )
    assert completed.returncode == 23
    assert control_plane.get_job("job").status == "running"

    time.sleep(1.05)
    result = control_plane.recover_expired()
    assert result == {"requeued": 1, "interrupted": 0, "cancelled": 0}
    assert control_plane.get_job("job").status == "queued"
