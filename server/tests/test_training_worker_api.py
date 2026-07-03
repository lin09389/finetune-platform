from __future__ import annotations

import importlib
import json

import pytest
from training_engine.schemas import TrainingConfigInput
from training_worker.repository import TrainingEventRepositoryHub, TrainingJobRepository

from core.config import Settings
from core.storage import run_schema_migrations

training_api = importlib.import_module("api.training")


class _ControlState:
    def __init__(self):
        self.current = None
        self.training = False

    def is_training(self):
        return self.training

    def set_current_record(self, record):
        self.current = record

    def queue_training_state(self, value):
        self.training = value


def _worker_settings(tmp_path) -> Settings:
    models = tmp_path / "models"
    datasets = tmp_path / "datasets"
    outputs = tmp_path / "outputs"
    (models / "demo-model").mkdir(parents=True)
    (datasets / "demo-dataset").mkdir(parents=True)
    (datasets / "demo-dataset" / "data.json").write_text(
        json.dumps([{"instruction": "hi", "output": "there"}]),
        encoding="utf-8",
    )
    return Settings(
        training_execution_mode="worker",
        models_dir=models,
        datasets_dir=datasets,
        outputs_dir=outputs,
    )


@pytest.mark.asyncio
async def test_start_endpoint_only_enqueues_in_worker_mode(tmp_path, monkeypatch):
    settings = _worker_settings(tmp_path)
    repository = TrainingJobRepository(str(tmp_path / "jobs.db"))

    monkeypatch.setattr(training_api, "get_settings", lambda: settings)
    monkeypatch.setattr(
        training_api,
        "get_training_context",
        lambda: pytest.fail("worker-mode control plane must not initialize TrainingContext"),
    )
    monkeypatch.setattr("training_worker.repository.get_training_job_repository", lambda: repository)

    result = await training_api.start_training(
        TrainingConfigInput(model_id="demo-model", dataset_id="demo-dataset"),
        skip_resource_check=True,
    )

    job = repository.get_job(result.id)
    assert result.status == "queued"
    assert job is not None and job.status == "queued"
    assert job.model_path.endswith("demo-model")


@pytest.mark.asyncio
async def test_worker_queue_status_task_and_cancel_endpoints(tmp_path, monkeypatch):
    repository = TrainingJobRepository(str(tmp_path / "jobs.db"))
    repository.enqueue(
        job_id="job",
        backend="native",
        priority=1,
        config={},
        model_path="model",
        dataset_path="data",
        output_path="output",
        record={"id": "job"},
    )
    monkeypatch.setattr(training_api, "_worker_mode", lambda: True)
    monkeypatch.setattr(training_api, "_training_job_repository", lambda: repository)

    queue = await training_api.get_queue_status()
    task = await training_api.get_task_status("job")
    cancelled = await training_api.cancel_task("job")

    assert queue["mode"] == "worker" and queue["queue_size"] == 1
    assert task["status"] == "queued"
    assert cancelled["status"] == "cancelled"
    assert repository.get_job("job").status == "cancelled"


@pytest.mark.asyncio
async def test_worker_log_stream_reads_persisted_database_logs(tmp_path, monkeypatch):
    repository = TrainingJobRepository(str(tmp_path / "jobs.db"))
    repository.append_log(
        task_id="job",
        level="INFO",
        logger="training.job",
        message="persisted log line",
    )
    monkeypatch.setattr(training_api, "_worker_mode", lambda: True)
    monkeypatch.setattr(training_api, "_training_job_repository", lambda: repository)

    response = await training_api.stream_training_logs("job", history=50)
    iterator = response.body_iterator
    first_chunk = await anext(iterator)
    await iterator.aclose()

    assert "persisted log line" in first_chunk


def test_sqlite_event_hub_replays_last_event_id_after_api_restart(tmp_path):
    db_path = str(tmp_path / "jobs.db")
    first = TrainingEventRepositoryHub(TrainingJobRepository(db_path))
    event = first.publish(task_id="job", phase="running", kind="progress_updated", payload={"step": 7})

    restarted = TrainingEventRepositoryHub(TrainingJobRepository(db_path))
    cursor = restarted.parse_last_event_id(event.event_id)
    assert cursor == event.sequence
    assert restarted.list_since(cursor - 1, task_id="job")[0].payload["step"] == 7


def test_schema_migration_installs_training_worker_tables(tmp_path):
    db_path = str(tmp_path / "app.db")
    result = run_schema_migrations(db_path)
    assert result["failed"] == []

    import sqlite3

    with sqlite3.connect(db_path) as conn:
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert {
        "training_jobs",
        "training_job_leases",
        "training_events",
        "training_logs",
        "training_workers",
    } <= tables
