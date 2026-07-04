"""Regression tests for the worker-mode training gateway."""

from __future__ import annotations

import json

import pytest
from training_worker.repository import TrainingJobRepository

from core.training_gateway import WorkerTrainingGateway


@pytest.fixture
def worker_training_gateway(tmp_path):
    """Return a WorkerTrainingGateway backed by an isolated repository."""
    repo = TrainingJobRepository(str(tmp_path / "training_jobs.db"))
    gateway = WorkerTrainingGateway()
    gateway.repo = repo
    return gateway


@pytest.mark.asyncio
async def test_worker_progress_stream_yields_dict_json(worker_training_gateway):
    """Regression: progress_stream must treat _worker_progress() as a dict.

    Previously it called progress.model_dump_json() and progress.status on a
    plain dict, raising AttributeError at runtime.
    """
    gateway = worker_training_gateway
    repo = gateway.repo

    job = repo.enqueue(
        job_id="test-job-1",
        backend="huggingface",
        priority=1,
        config={},
        model_path="/models/base",
        dataset_path="/datasets/d1",
        output_path="/outputs/d1",
        record={},
    )
    repo.claim_next(worker_id="worker-1", lease_seconds=60)
    repo.mark_running(job.job_id, worker_id="worker-1")
    repo.append_event(
        task_id=job.job_id,
        phase="training",
        kind="task_step",
        payload={"status": "training", "step": 1, "loss": 0.5},
    )

    chunks = []
    async for chunk in gateway.progress_stream(timeout=1, heartbeat=1):
        chunks.append(chunk)
        break  # Only need one event to verify formatting

    assert chunks
    assert chunks[0].startswith("data: ")
    payload = json.loads(chunks[0].removeprefix("data: ").strip())
    assert payload["status"] == "training"
    assert "step" in payload
