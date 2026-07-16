"""P2 training control-plane: events prune, metrics path, WS auth, skip, RBAC, dual history."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from training_worker.repository import TrainingJobRepository

from services.training.paths import resolve_training_metrics_file, resolve_training_output_dir
from services.training.policy import (
    allow_skip_resource_check,
    authenticate_training_websocket,
    history_authority,
    map_progress_status,
)


def _enqueue(repo: TrainingJobRepository, job_id: str, **kwargs):
    return repo.enqueue(
        job_id=job_id,
        backend="native",
        priority=kwargs.get("priority", 2),
        config={"model_id": "m", "dataset_id": "d", "method": "lora"},
        model_path="models/m",
        dataset_path="datasets/d/data.jsonl",
        output_path=kwargs.get("output_path", f"outputs/{job_id}"),
        record={
            "id": job_id,
            "status": "queued",
            "model_name": "m",
            "dataset_name": "d",
            "method": "lora",
            "start_time": "2026-07-15T00:00:00+00:00",
            "config": {"model_id": "m", "dataset_id": "d", "method": "lora"},
            "output_path": kwargs.get("output_path", f"outputs/{job_id}"),
            "end_time": None,
        },
        max_attempts=3,
    )


def test_mark_running_syncs_record_status(tmp_path):
    repo = TrainingJobRepository(str(tmp_path / "jobs.db"))
    _enqueue(repo, "j1")
    repo.claim_next("w", lease_seconds=30)
    assert repo.get_job("j1").record["status"] == "loading"
    assert repo.mark_running("j1", "w")
    assert repo.get_job("j1").record["status"] == "running"


def test_claim_blocks_second_active(tmp_path):
    repo = TrainingJobRepository(str(tmp_path / "jobs.db"))
    _enqueue(repo, "a", priority=0)
    _enqueue(repo, "b", priority=1)
    assert repo.claim_next("w1", lease_seconds=30).job_id == "a"
    assert repo.claim_next("w2", lease_seconds=30) is None
    repo.mark_running("a", "w1")
    assert repo.claim_next("w2", lease_seconds=30) is None
    repo.finish("a", "w1", status="completed", record={"id": "a", "status": "completed"})
    assert repo.claim_next("w2", lease_seconds=30).job_id == "b"


def test_prune_events_by_age_and_cap(tmp_path, monkeypatch):
    repo = TrainingJobRepository(str(tmp_path / "jobs.db"))
    monkeypatch.setattr(
        "core.config.get_settings",
        lambda: SimpleNamespace(
            training_events_max_rows=5,
            training_events_max_age_days=1,
            training_events_progress_min_step_delta=1,
        ),
    )
    old = datetime(2020, 1, 1, tzinfo=UTC)
    for i in range(10):
        repo.append_event(
            task_id="t",
            phase="running",
            kind="progress_updated",
            payload={"step": i, "status": "training"},
            now=old if i < 3 else None,
            force=True,
        )
    result = repo.prune_events(max_rows=5, max_age_days=1)
    assert result["deleted_by_age"] >= 3
    remaining = repo.list_events(after_sequence=0, limit=100)
    assert len(remaining) <= 5


def test_progress_sampling_drops_redundant_steps(tmp_path, monkeypatch):
    repo = TrainingJobRepository(str(tmp_path / "jobs.db"))
    monkeypatch.setattr(
        "core.config.get_settings",
        lambda: SimpleNamespace(
            training_events_max_rows=50_000,
            training_events_max_age_days=14,
            training_events_progress_min_step_delta=5,
        ),
    )
    e1 = repo.append_event(
        task_id="t",
        phase="running",
        kind="progress_updated",
        payload={"step": 0, "status": "training"},
    )
    assert e1 is not None
    # step +1 < delta 5 → sampled out
    assert (
        repo.append_event(
            task_id="t",
            phase="running",
            kind="progress_updated",
            payload={"step": 1, "status": "training"},
        )
        is None
    )
    e3 = repo.append_event(
        task_id="t",
        phase="running",
        kind="progress_updated",
        payload={"step": 10, "status": "training"},
    )
    assert e3 is not None
    assert e3.payload["step"] == 10


def test_resolve_metrics_uses_job_output_path(tmp_path, monkeypatch):
    repo = TrainingJobRepository(str(tmp_path / "jobs.db"))
    custom = tmp_path / "custom-out"
    custom.mkdir()
    (custom / "metrics.jsonl").write_text('{"step":1}\n', encoding="utf-8")
    _enqueue(repo, "task-xyz", output_path=str(custom))
    monkeypatch.setattr(
        "core.config.get_settings",
        lambda: SimpleNamespace(
            training_execution_mode="worker",
            outputs_dir_resolved=tmp_path / "outputs",
        ),
    )
    monkeypatch.setattr(
        "training_worker.repository.get_training_job_repository",
        lambda: repo,
    )
    path = resolve_training_metrics_file("task-xyz")
    assert path == custom / "metrics.jsonl"
    assert path.exists()
    # Must not invent train_{id[:8]} when durable path exists
    assert "train_task-xy" not in str(path)


def test_history_authority_by_mode(monkeypatch):
    monkeypatch.setattr(
        "services.training.policy.get_settings",
        lambda: SimpleNamespace(training_execution_mode="worker"),
    )
    assert history_authority() == "sqlite_jobs"
    monkeypatch.setattr(
        "services.training.policy.get_settings",
        lambda: SimpleNamespace(training_execution_mode="in_process"),
    )
    assert history_authority() == "json_history"


def test_allow_skip_false_in_production():
    assert allow_skip_resource_check(SimpleNamespace(environment="production")) is False
    assert allow_skip_resource_check(SimpleNamespace(environment="development")) is True


def test_map_progress_status():
    assert map_progress_status("leased") == "loading"
    assert map_progress_status("running") == "training"
    assert map_progress_status("cancellation_requested") == "stopping"


def test_ws_auth_rejects_missing_token_when_auth_enabled(monkeypatch):
    monkeypatch.setattr(
        "services.training.policy.get_settings",
        lambda: SimpleNamespace(enable_auth=True),
    )
    ws = MagicMock()
    ws.headers = {}
    ws.query_params = {}
    with pytest.raises(Exception) as ei:
        authenticate_training_websocket(ws)
    assert getattr(ei.value, "status_code", None) == 401


def test_ws_auth_accepts_query_token(monkeypatch):
    monkeypatch.setattr(
        "services.training.policy.get_settings",
        lambda: SimpleNamespace(enable_auth=True),
    )
    payload = SimpleNamespace(sub="u1", role="admin")

    class FakeAuth:
        def verify_token(self, token):
            assert token == "good-token"
            return payload

    monkeypatch.setattr("services.training.policy.get_jwt_auth", lambda: FakeAuth())
    ws = MagicMock()
    ws.headers = {}
    ws.query_params = {"token": "good-token"}
    assert authenticate_training_websocket(ws) is payload


def test_ws_auth_skipped_when_auth_disabled(monkeypatch):
    monkeypatch.setattr(
        "services.training.policy.get_settings",
        lambda: SimpleNamespace(enable_auth=False),
    )
    ws = MagicMock()
    ws.headers = {}
    ws.query_params = {}
    assert authenticate_training_websocket(ws) is None


@pytest.mark.asyncio
async def test_require_training_operator_admin_when_auth_on(monkeypatch):
    from services.training.policy import require_training_operator
    from security.jwt_auth import Role, TokenPayload

    monkeypatch.setattr(
        "services.training.policy.get_settings",
        lambda: SimpleNamespace(enable_auth=True),
    )

    class FakeAuth:
        def has_role(self, user, role):
            return user.role in {Role.ADMIN, Role.SUPER_ADMIN} or (
                role == Role.ADMIN and user.role == Role.SUPER_ADMIN
            )

    monkeypatch.setattr("services.training.policy.get_jwt_auth", lambda: FakeAuth())

    user = TokenPayload(user_id="1", username="u", role=Role.USER)
    with pytest.raises(Exception) as ei:
        await require_training_operator(current_user=user)
    assert ei.value.status_code == 403

    admin = TokenPayload(user_id="2", username="a", role=Role.ADMIN)
    assert await require_training_operator(current_user=admin) is admin


@pytest.mark.asyncio
async def test_gateway_start_signature_and_sse(tmp_path, monkeypatch):
    from core.training_gateway import WorkerTrainingGateway

    repo = TrainingJobRepository(str(tmp_path / "jobs.db"))
    gw = WorkerTrainingGateway()
    gw.repo = repo
    captured = {}

    def fake_start(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(id="x", status="queued")

    monkeypatch.setattr("services.training.orchestrator.start_training_task", fake_start)
    from training_engine.schemas import TrainingConfigInput

    gw.start(
        config=TrainingConfigInput(model_id="m", dataset_id="d", method="lora"),
        model_path=tmp_path / "m",
        dataset_file=tmp_path / "d.jsonl",
        settings=SimpleNamespace(training_execution_mode="worker"),
    )
    assert "config" in captured and captured["state"] is None

    _enqueue(repo, "sse")
    chunks = []
    async for c in gw.progress_stream(timeout=2, heartbeat=1):
        chunks.append(c)
    assert any(c.startswith("data: ") for c in chunks)
    assert any("keepalive" in c for c in chunks)
