"""P1 control-plane tests: durable records, gateway, SSE, cancel, skip_resource_check."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from training_engine.schemas import TrainingConfigInput
from training_worker.repository import TrainingJobRepository, record_status_for_job_status

from core.training_gateway import (
    InProcessTrainingGateway,
    WorkerTrainingGateway,
    allow_skip_resource_check,
    map_progress_status,
)
from core.training_state import TrainingProgress


def _enqueue(repo: TrainingJobRepository, job_id: str, **kwargs):
    return repo.enqueue(
        job_id=job_id,
        backend="native",
        priority=kwargs.get("priority", 2),
        config={"model_id": "m", "dataset_id": "d", "method": "lora"},
        model_path="models/m",
        dataset_path="datasets/d/data.jsonl",
        output_path=f"outputs/{job_id}",
        record={
            "id": job_id,
            "status": "queued",
            "model_name": "m",
            "dataset_name": "d",
            "method": "lora",
            "start_time": "2026-07-15T00:00:00+00:00",
            "config": {"model_id": "m", "dataset_id": "d", "method": "lora"},
            "output_path": f"outputs/{job_id}",
            "end_time": None,
        },
        max_attempts=kwargs.get("max_attempts", 3),
    )


# ---------------------------------------------------------------------------
# Durable record lifecycle
# ---------------------------------------------------------------------------


def test_mark_running_updates_record_status_not_stuck_queued(tmp_path):
    repo = TrainingJobRepository(str(tmp_path / "jobs.db"))
    _enqueue(repo, "job-1")
    claimed = repo.claim_next("worker-a", lease_seconds=30)
    assert claimed is not None
    assert claimed.record["status"] == record_status_for_job_status("leased")
    assert claimed.record["status"] != "queued"

    assert repo.mark_running("job-1", "worker-a")
    job = repo.get_job("job-1")
    assert job.status == "running"
    assert job.record["status"] == "running"
    assert job.record["status"] != "queued"


def test_list_training_records_prefers_durable_job_status(tmp_path, monkeypatch):
    from services.training import records as records_mod

    repo = TrainingJobRepository(str(tmp_path / "jobs.db"))
    _enqueue(repo, "job-hist")
    # Simulate stale record_json while job is running (pre-fix dual-write).
    with repo._pool.get_connection() as conn:
        conn.execute(
            "UPDATE training_jobs SET status = 'running', record_json = ? WHERE job_id = ?",
            (
                json.dumps(
                    {
                        "id": "job-hist",
                        "status": "queued",
                        "model_name": "m",
                        "dataset_name": "d",
                        "method": "lora",
                        "start_time": "2026-07-15T00:00:00+00:00",
                        "config": {},
                        "output_path": "outputs/job-hist",
                        "end_time": None,
                    }
                ),
                "job-hist",
            ),
        )

    monkeypatch.setattr(
        records_mod.get_settings,
        "__call__",
        lambda: SimpleNamespace(training_execution_mode="worker"),
    )
    # Patch get_settings used inside list_training_records
    monkeypatch.setattr(records_mod, "get_settings", lambda: SimpleNamespace(training_execution_mode="worker"))
    monkeypatch.setattr(
        "training_worker.repository.get_training_job_repository",
        lambda: repo,
    )

    listed = records_mod.list_training_records()
    assert listed
    assert listed[0].status == "running"
    assert listed[0].status != "queued"


# ---------------------------------------------------------------------------
# Gateway contracts
# ---------------------------------------------------------------------------


def test_map_progress_status_vocabulary():
    assert map_progress_status("queued") == "loading"
    assert map_progress_status("leased") == "loading"
    assert map_progress_status("running") == "training"
    assert map_progress_status("cancellation_requested") == "stopping"
    assert map_progress_status("training") == "training"
    assert map_progress_status("completed") == "completed"


def test_worker_gateway_start_uses_orchestrator_kwargs(tmp_path, monkeypatch):
    repo = TrainingJobRepository(str(tmp_path / "jobs.db"))
    gateway = WorkerTrainingGateway()
    gateway.repo = repo

    captured = {}

    def fake_start(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(id="started-1", status="queued", model_dump=lambda: {"id": "started-1"})

    monkeypatch.setattr(
        "services.training.orchestrator.start_training_task",
        fake_start,
    )
    settings = SimpleNamespace(
        training_execution_mode="worker",
        training_worker_max_attempts=3,
        outputs_dir_resolved=tmp_path / "out",
    )
    config = TrainingConfigInput(model_id="m", dataset_id="d", method="lora")
    (tmp_path / "model").mkdir()
    ds = tmp_path / "data.jsonl"
    ds.write_text('{"instruction":"a","output":"b"}\n', encoding="utf-8")

    result = gateway.start(
        config=config,
        model_path=tmp_path / "model",
        dataset_file=ds,
        settings=settings,
        priority="normal",
    )
    assert captured["config"] is config
    assert captured["state"] is None
    assert Path(captured["model_path"]) == tmp_path / "model"
    assert result.id == "started-1"


@pytest.mark.asyncio
async def test_worker_progress_stream_timeout_and_keepalive(tmp_path):
    repo = TrainingJobRepository(str(tmp_path / "jobs.db"))
    gateway = WorkerTrainingGateway()
    gateway.repo = repo
    _enqueue(repo, "sse-job")
    # Idle queued job maps to loading — stream should emit data + keepalive and end on timeout.
    chunks = []
    async for chunk in gateway.progress_stream(timeout=2, heartbeat=1):
        chunks.append(chunk)

    assert chunks, "expected at least one SSE chunk"
    assert any(c.startswith("data: ") for c in chunks)
    assert any(c.startswith(": keepalive") or "keepalive" in c for c in chunks)


@pytest.mark.asyncio
async def test_worker_stop_idle_raises(tmp_path):
    gateway = WorkerTrainingGateway()
    gateway.repo = TrainingJobRepository(str(tmp_path / "jobs.db"))
    with pytest.raises(ValueError, match="No training in progress"):
        await gateway.stop()


# ---------------------------------------------------------------------------
# In-process gateway (mode parity for start/stop/progress/SSE)
# ---------------------------------------------------------------------------


class _FakeInProcessContext:
    def __init__(self, state):
        self.state = state

    def get_status(self):
        return {
            "training": {
                "is_training": self.state.is_training(),
                "progress": self.state.get_progress().model_dump(),
            },
            "queue": {"queue_size": 0},
        }


class _FakeInProcessState:
    def __init__(self):
        self._training = False
        self._stop = False
        self._progress = TrainingProgress(status="idle", message="idle")

    def is_training(self):
        return self._training

    def should_stop(self):
        return self._stop

    def request_stop(self):
        self._stop = True

    def get_progress(self):
        return self._progress

    def queue_progress_update(self, **kwargs):
        for k, v in kwargs.items():
            if hasattr(self._progress, k):
                setattr(self._progress, k, v)


def test_in_process_gateway_start_passes_state_to_orchestrator(tmp_path, monkeypatch):
    state = _FakeInProcessState()
    gateway = InProcessTrainingGateway.__new__(InProcessTrainingGateway)
    gateway.context = _FakeInProcessContext(state)
    captured = {}

    def fake_start(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(id="ip-1", status="running")

    monkeypatch.setattr("services.training.orchestrator.start_training_task", fake_start)
    config = TrainingConfigInput(model_id="m", dataset_id="d", method="lora")
    settings = SimpleNamespace(training_execution_mode="in_process", outputs_dir_resolved=tmp_path)
    result = gateway.start(
        config=config,
        model_path=tmp_path / "m",
        dataset_file=tmp_path / "d.jsonl",
        settings=settings,
        priority="high",
    )
    assert captured["state"] is state
    assert captured["config"] is config
    assert captured["priority"] == "high"
    assert result.id == "ip-1"


@pytest.mark.asyncio
async def test_in_process_gateway_stop_and_progress(monkeypatch):
    state = _FakeInProcessState()
    state._training = True
    state._progress = TrainingProgress(status="running", message="step", step=3)
    gateway = InProcessTrainingGateway.__new__(InProcessTrainingGateway)
    gateway.context = _FakeInProcessContext(state)

    # Avoid V2 hub side effects from queue_training_progress
    monkeypatch.setattr(
        "training_engine.callbacks.queue_training_progress",
        lambda st, **kw: st.queue_progress_update(**kw),
    )
    monkeypatch.setattr(
        "core.training_events_v2.get_training_event_hub_v2",
        lambda: SimpleNamespace(get_latest=lambda: None),
    )

    progress = gateway.get_progress()
    assert progress["status"] == "training"  # mapped from running
    assert progress["step"] == 3

    stopped = await gateway.stop()
    assert stopped["status"] == "stopping"
    assert state.should_stop() is True
    after = gateway.get_progress()
    assert after["status"] == "stopping"

    with pytest.raises(ValueError, match="No training in progress"):
        idle = InProcessTrainingGateway.__new__(InProcessTrainingGateway)
        idle.context = _FakeInProcessContext(_FakeInProcessState())
        await idle.stop()


@pytest.mark.asyncio
async def test_in_process_progress_stream_timeout_and_keepalive(monkeypatch):
    state = _FakeInProcessState()
    state._progress = TrainingProgress(status="loading", message="wait")
    gateway = InProcessTrainingGateway.__new__(InProcessTrainingGateway)
    gateway.context = _FakeInProcessContext(state)
    monkeypatch.setattr(
        "core.training_events_v2.get_training_event_hub_v2",
        lambda: SimpleNamespace(get_latest=lambda: None),
    )

    chunks = []
    async for chunk in gateway.progress_stream(timeout=2, heartbeat=1):
        chunks.append(chunk)

    assert chunks, "expected SSE chunks before timeout"
    assert any(c.startswith("data: ") for c in chunks)
    assert any("keepalive" in c for c in chunks)
    # Stream must terminate on timeout (not hang forever)
    assert len(chunks) >= 2


# ---------------------------------------------------------------------------
# Cancel / stop
# ---------------------------------------------------------------------------


def test_cancel_queued_is_terminal_and_running_is_stopping(tmp_path):
    repo = TrainingJobRepository(str(tmp_path / "jobs.db"))
    _enqueue(repo, "run")
    _enqueue(repo, "wait")
    claimed = repo.claim_next("w", lease_seconds=30)
    assert claimed.job_id == "run"
    repo.mark_running("run", "w")

    assert repo.request_cancel("wait") == "cancelled"
    assert repo.get_job("wait").status == "cancelled"
    assert repo.get_job("wait").record["status"] == "cancelled"

    assert repo.request_cancel("run") == "cancellation_requested"
    job = repo.get_job("run")
    assert job.status == "cancellation_requested"
    assert job.record["status"] == "stopping"
    assert job.cancel_requested is True


# ---------------------------------------------------------------------------
# skip_resource_check policy
# ---------------------------------------------------------------------------


def test_allow_skip_resource_check_false_in_production():
    assert allow_skip_resource_check(SimpleNamespace(environment="production")) is False
    assert allow_skip_resource_check(SimpleNamespace(environment="staging")) is False
    assert allow_skip_resource_check(SimpleNamespace(environment="development")) is True


@pytest.mark.asyncio
async def test_start_training_rejects_skip_in_production(tmp_path, monkeypatch):
    import api.training as training_api
    import core.training_gateway as gw_mod

    settings = SimpleNamespace(
        environment="production",
        training_execution_mode="worker",
        models_dir_resolved=tmp_path / "models",
        datasets_dir_resolved=tmp_path / "datasets",
        outputs_dir_resolved=tmp_path / "outputs",
    )
    (settings.models_dir_resolved / "m").mkdir(parents=True)
    ds_dir = settings.datasets_dir_resolved / "d"
    ds_dir.mkdir(parents=True)
    (ds_dir / "data.jsonl").write_text('{"instruction":"a","output":"b"}\n', encoding="utf-8")

    monkeypatch.setattr(training_api, "get_settings", lambda: settings)
    monkeypatch.setattr(training_api, "_worker_mode", lambda: True)
    monkeypatch.setattr(
        gw_mod,
        "get_training_gateway",
        lambda: SimpleNamespace(is_training_in_progress=lambda: False),
    )
    monkeypatch.setattr(gw_mod, "allow_skip_resource_check", lambda _s=None: False)

    with pytest.raises(training_api.HTTPException) as ei:
        await training_api.start_training(
            TrainingConfigInput(model_id="m", dataset_id="d", method="lora"),
            skip_resource_check=True,
        )
    assert ei.value.status_code == 403
    assert "skip_resource_check" in str(ei.value.detail)


@pytest.mark.asyncio
async def test_resume_still_rejects_missing_trainer_state(tmp_path, monkeypatch):
    """P0/P1 non-regression: incomplete checkpoint cannot resume."""
    import api.training as training_api
    from core.training_state import TrainingRecord

    task_id = "resume-incomplete"
    output_dir = tmp_path / "out"
    ckpt = output_dir / "checkpoints" / "checkpoint-1"
    ckpt.mkdir(parents=True)
    (ckpt / "pytorch_model.bin").write_text("x", encoding="utf-8")
    (ckpt / "config.json").write_text("{}", encoding="utf-8")
    # no trainer_state.json

    history = TrainingRecord(
        id=task_id,
        model_name="m",
        dataset_name="d",
        method="qlora",
        status="stopped",
        start_time="2026-07-15T00:00:00",
        config={"model_id": "m", "dataset_id": "d", "method": "qlora"},
        output_path=str(output_dir),
        end_time=None,
    )

    class FakeState:
        def is_training(self):
            return False

        def get_history(self):
            return [history]

        def try_claim_training_slot(self):
            return True

        def queue_training_state(self, _v):
            pass

    settings = SimpleNamespace(
        training_execution_mode="in_process",
        models_dir_resolved=tmp_path / "models",
        datasets_dir_resolved=tmp_path / "datasets",
        outputs_dir_resolved=tmp_path / "outputs",
    )
    (settings.models_dir_resolved / "m").mkdir(parents=True)
    (settings.datasets_dir_resolved / "d").mkdir(parents=True)
    (settings.datasets_dir_resolved / "d" / "data.json").write_text(
        '[{"instruction":"a","output":"b"}]', encoding="utf-8"
    )

    monkeypatch.setattr(
        training_api,
        "get_training_context",
        lambda: SimpleNamespace(state=FakeState()),
    )
    monkeypatch.setattr(training_api, "get_settings", lambda: settings)
    monkeypatch.setattr(training_api, "_worker_mode", lambda: False)

    with pytest.raises(training_api.HTTPException) as ei:
        await training_api.resume_training(task_id, "checkpoint-1")
    assert ei.value.status_code == 400
    assert "trainer_state" in str(ei.value.detail).lower() or "missing" in str(ei.value.detail).lower()
