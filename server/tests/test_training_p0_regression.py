"""P0 regression tests: cover the core fixes from PR1-PR4.

- PR1: SSE authentication via ?token= query param + Authorization header
- PR2: Heartbeat resilience (exponential backoff + max consecutive failures)
- PR3: SWIFT backend routing through Worker queue (not direct subprocess)
- PR4: Cancel propagation from repository to TrainingState.should_stop()

Pattern follows test_training_p1_control_plane.py / test_training_worker_runtime.py:
- Real TrainingJobRepository against tmp_path / "jobs.db"
- TrainingWorker with custom executor callable for cancel test
- monkeypatch for settings + module-level patches
"""

from __future__ import annotations

import threading
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from training_engine.schemas import TrainingConfigInput
from training_worker.repository import TrainingJobRepository
from training_worker.worker import TrainingWorker

from core.config import Settings

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _settings(tmp_path) -> Settings:
    return Settings(
        training_execution_mode="worker",
        training_worker_heartbeat_seconds=0.5,
        training_worker_lease_seconds=5,
        training_worker_poll_seconds=0.1,
        training_worker_max_attempts=3,
        training_worker_stale_seconds=10,
        models_dir=tmp_path / "models",
        datasets_dir=tmp_path / "datasets",
        outputs_dir=tmp_path / "outputs",
    )


def _enqueue(repo: TrainingJobRepository, job_id: str = "job", *, backend: str = "native"):
    return repo.enqueue(
        job_id=job_id,
        backend=backend,
        priority=2,
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
        max_attempts=3,
    )


# ---------------------------------------------------------------------------
# PR1: SSE authentication
# ---------------------------------------------------------------------------


def test_authenticate_training_sse_skips_when_auth_disabled(monkeypatch):
    """PR1: ENABLE_AUTH=false → authenticate_training_sse returns None (no auth)."""
    from services.training.policy import authenticate_training_sse

    # Default test env has ENABLE_AUTH=false (see conftest.py)
    request = MagicMock()
    request.headers = {}
    request.query_params = {}
    result = authenticate_training_sse(request)
    assert result is None


def test_authenticate_training_sse_rejects_missing_token_when_enabled(monkeypatch):
    """PR1: ENABLE_AUTH=true + no token → HTTPException 401."""
    from fastapi import HTTPException
    from services.training.policy import authenticate_training_sse

    from core.config import settings

    monkeypatch.setattr(settings, "enable_auth", True)

    request = MagicMock()
    request.headers = {}
    request.query_params = {}

    with pytest.raises(HTTPException) as exc_info:
        authenticate_training_sse(request)
    assert exc_info.value.status_code == 401


def test_authenticate_training_sse_accepts_token_query_param(monkeypatch):
    """PR1: ENABLE_AUTH=true + ?token=xxx → verifies via jwt_auth."""
    from services.training import policy as policy_mod

    from core.config import settings

    monkeypatch.setattr(settings, "enable_auth", True)

    # Mock jwt_auth.verify_token to return a payload
    fake_payload = SimpleNamespace(sub="user-1", role="admin")
    fake_jwt = MagicMock()
    fake_jwt.verify_token.return_value = fake_payload
    monkeypatch.setattr(policy_mod, "get_jwt_auth", lambda: fake_jwt)

    request = MagicMock()
    request.headers = {}
    request.query_params = {"token": "fake-token"}

    result = policy_mod.authenticate_training_sse(request)
    assert result is fake_payload
    fake_jwt.verify_token.assert_called_once_with("fake-token")


def test_authenticate_training_sse_accepts_authorization_header(monkeypatch):
    """PR1: ENABLE_AUTH=true + Authorization: Bearer xxx → verifies."""
    from services.training import policy as policy_mod

    from core.config import settings

    monkeypatch.setattr(settings, "enable_auth", True)

    fake_payload = SimpleNamespace(sub="user-2", role="admin")
    fake_jwt = MagicMock()
    fake_jwt.verify_token.return_value = fake_payload
    monkeypatch.setattr(policy_mod, "get_jwt_auth", lambda: fake_jwt)

    request = MagicMock()
    request.headers = {"authorization": "Bearer header-token"}
    request.query_params = {}

    result = policy_mod.authenticate_training_sse(request)
    assert result is fake_payload
    fake_jwt.verify_token.assert_called_once_with("header-token")


# ---------------------------------------------------------------------------
# PR2: Heartbeat resilience
# ---------------------------------------------------------------------------


def test_heartbeat_consecutive_failures_triggers_cancel(tmp_path, monkeypatch):
    """PR2: 5 consecutive heartbeat failures → _current_cancel set, monitor exits.

    Verifies the monitor does NOT retry infinitely; after MAX_FAILURES=5 the
    cancel event is set so the executor can stop gracefully.
    """
    repo = TrainingJobRepository(str(tmp_path / "jobs.db"))
    _enqueue(repo, "hb-job")
    settings = _settings(tmp_path)

    worker = TrainingWorker(repo, settings=settings, worker_id="worker-hb")

    # Make heartbeat raise consistently — 5 failures should trigger cancel.
    call_count = {"n": 0}

    def fake_heartbeat(*args, **kwargs):
        call_count["n"] += 1
        raise RuntimeError("simulated DB lock")

    monkeypatch.setattr(repo, "heartbeat", fake_heartbeat)
    # heartbeat_worker also needs to succeed so we isolate the job-heartbeat failure path
    monkeypatch.setattr(repo, "heartbeat_worker", lambda *a, **kw: None)

    monitor_stop = threading.Event()
    cancel_event = worker._current_cancel

    # Run monitor in a thread; it should self-terminate after MAX_FAILURES=5
    monitor = threading.Thread(
        target=worker._monitor_job,
        args=("hb-job", monitor_stop),
        daemon=True,
    )
    monitor.start()

    # Wait up to 25s for cancel to be set (5 failures with exponential backoff
    # 1+2+4+8=15s plus 0.5s intervals between attempts ≈ 17.5s total)
    assert cancel_event.wait(25.0), "cancel event was not set after 5 heartbeat failures"
    monitor.join(timeout=5.0)
    assert not monitor.is_alive(), "monitor thread did not exit after cancel"

    # PR2 contract: exactly MAX_FAILURES=5 attempts (no infinite retry)
    assert call_count["n"] == 5, f"expected 5 heartbeat attempts, got {call_count['n']}"


def test_heartbeat_success_resets_consecutive_failures(tmp_path, monkeypatch):
    """PR2: a successful heartbeat resets the failure counter.

    序列:fail-1, fail-2, success(重置), fail-3, fail-4。
    success 重置后只 4 次连续失败,不够 MAX_FAILURES=5,因此 cancel_event
    不应被设置。序列结束后通过 monitor_stop 优雅退出。
    """
    repo = TrainingJobRepository(str(tmp_path / "jobs.db"))
    _enqueue(repo, "hb-reset")
    settings = _settings(tmp_path)

    worker = TrainingWorker(repo, settings=settings, worker_id="worker-reset")

    sequence = [
        RuntimeError("fail-1"),
        RuntimeError("fail-2"),
        True,  # success 重置 counter
        RuntimeError("fail-3"),
        RuntimeError("fail-4"),
    ]
    state = {"i": 0}
    monitor_stop = threading.Event()

    def fake_heartbeat(*args, **kwargs):
        i = state["i"]
        state["i"] += 1
        if i < len(sequence):
            value = sequence[i]
            if isinstance(value, Exception):
                raise value
            return True
        # 序列结束后,通过 monitor_stop 优雅退出(monitor 不检查 _current_cancel)
        monitor_stop.set()
        return True

    monkeypatch.setattr(repo, "heartbeat", fake_heartbeat)
    monkeypatch.setattr(repo, "heartbeat_worker", lambda *a, **kw: None)
    # Short-circuit gpu renew + job status check to keep test isolated
    monkeypatch.setattr(repo, "get_job", lambda *a, **kw: None)

    cancel_event = worker._current_cancel
    monitor = threading.Thread(
        target=worker._monitor_job,
        args=("hb-reset", monitor_stop),
        daemon=True,
    )
    monitor.start()
    # 序列总时间约 9s(0.5+1+0.5+2+0.5+0+0.5+1+0.5+2+0.5+0),给 15s 余量
    monitor.join(timeout=15.0)

    assert not monitor.is_alive(), "monitor should have exited"
    # PR2 契约:success 重置了 counter,4 次连续失败不够 MAX_FAILURES=5
    assert not cancel_event.is_set(), "cancel should NOT be set — success reset the counter"


# ---------------------------------------------------------------------------
# PR3: SWIFT routing through Worker queue
# ---------------------------------------------------------------------------


def test_swift_job_routes_through_worker_executor(tmp_path, monkeypatch):
    """PR3: a job with backend='swift' is dispatched to _execute_swift, not _execute_native.

    We replace _execute_swift with a spy that records the call, and verify
    the native executor is NOT invoked.
    """
    repo = TrainingJobRepository(str(tmp_path / "jobs.db"))
    _enqueue(repo, "swift-job", backend="swift")
    settings = _settings(tmp_path)

    worker = TrainingWorker(repo, settings=settings, worker_id="worker-swift")

    swift_calls: list[str] = []
    native_calls: list[str] = []

    def spy_swift(job, cancel_event):
        swift_calls.append(job.job_id)
        record = dict(job.record)
        record["status"] = "completed"
        return record

    def spy_native(job, cancel_event):
        native_calls.append(job.job_id)
        record = dict(job.record)
        record["status"] = "completed"
        return record

    # Patch both executors on the worker instance
    monkeypatch.setattr(worker, "_execute_swift", spy_swift)
    monkeypatch.setattr(worker, "_execute_native", spy_native)
    # Also update the executors dict that dispatch uses
    worker.executors["swift"] = spy_swift
    worker.executors["native"] = spy_native

    # Patch state-bridging calls that _run_claimed makes before dispatch
    # (avoid pulling in real TrainingState initialization)
    assert worker.run_once() is True

    assert swift_calls == ["swift-job"], f"expected swift executor called once, got {swift_calls}"
    assert native_calls == [], f"native executor should NOT be called for swift job, got {native_calls}"

    job = repo.get_job("swift-job")
    assert job.status == "completed"


def test_swift_job_with_unavailable_backend_fails_gracefully(tmp_path, monkeypatch):
    """PR3: if SwiftBackend.is_available() returns False, job fails with clear error."""
    repo = TrainingJobRepository(str(tmp_path / "jobs.db"))
    _enqueue(repo, "swift-unavailable", backend="swift")
    settings = _settings(tmp_path)

    worker = TrainingWorker(repo, settings=settings, worker_id="worker-swift-2")

    # Mock SwiftBackend.is_available → False
    fake_backend = MagicMock()
    fake_backend.is_available.return_value = False

    import sys
    swift_module = MagicMock()
    swift_module.get_swift_backend.return_value = fake_backend
    swift_module.SwiftTrainConfig = MagicMock()
    monkeypatch.setitem(sys.modules, "backends.swift_backend", swift_module)

    assert worker.run_once() is True

    job = repo.get_job("swift-unavailable")
    assert job.status == "failed"
    assert "SWIFT" in (job.error or "") or "swift" in (job.error or "").lower()


# ---------------------------------------------------------------------------
# PR4: Cancel propagation
# ---------------------------------------------------------------------------


def test_cancel_propagates_to_executor_stop_signal(tmp_path):
    """PR4: request_cancel on repository → worker observes cancel_event → executor stops.

    The executor callable receives a threading.Event that must be set when
    the job is cancelled. This is the P0-4 contract: cancel must propagate
    from the durable queue into the running training thread.
    """
    repo = TrainingJobRepository(str(tmp_path / "jobs.db"))
    _enqueue(repo, "cancel-job")
    settings = _settings(tmp_path)

    cancel_observed = threading.Event()
    executor_started = threading.Event()

    def executor(job, cancel_event):
        executor_started.set()
        # Wait for cancel to propagate — must happen within 5s
        if not cancel_event.wait(5.0):
            return {"status": "completed", **job.record}
        cancel_observed.set()
        record = dict(job.record)
        record["status"] = "stopped"
        return record

    worker = TrainingWorker(repo, settings=settings, worker_id="worker-cancel")
    # P0-4: dispatch 通过 self.executors.get(job.backend, self.executor) 派发,
    # 对 backend="native" 任务会命中 self.executors["native"]=self._execute_native,
    # 绕过构造参数 executor。必须直接 patch executors dict(同 PR3 测试模式)。
    worker.executors["native"] = executor

    # Run worker in a thread so we can request cancel mid-flight
    thread = threading.Thread(target=worker.run_once, daemon=True)
    thread.start()

    # Wait for executor to start
    assert executor_started.wait(2.0), "executor did not start"

    # Request cancel — this should propagate to the executor's cancel_event
    assert repo.request_cancel("cancel-job") == "cancellation_requested"

    thread.join(timeout=6.0)
    assert not thread.is_alive(), "worker thread did not exit after cancel"

    # PR4 contract: cancel_event reached the executor
    assert cancel_observed.is_set(), "executor did not observe cancel_event"

    job = repo.get_job("cancel-job")
    assert job.status == "stopped", f"expected stopped, got {job.status}"


def test_cancel_queued_job_does_not_start_executor(tmp_path):
    """PR4: cancelling a queued (not yet claimed) job short-circuits before execution."""
    repo = TrainingJobRepository(str(tmp_path / "jobs.db"))
    _enqueue(repo, "queued-cancel")
    settings = _settings(tmp_path)

    executor_called = threading.Event()

    def executor(job, cancel_event):
        executor_called.set()
        record = dict(job.record)
        record["status"] = "completed"
        return record

    worker = TrainingWorker(repo, settings=settings, worker_id="worker-q")
    # P0-4: 同 test_cancel_propagates_to_executor_stop_signal,必须直接 patch
    # executors dict 才能让自定义 executor 在 backend="native" 任务上生效。
    worker.executors["native"] = executor

    # Cancel before the worker claims it
    # P0-4: queued 状态的任务被 cancel 时,repository.request_cancel 直接置为
    # terminal "cancelled"(见 repository.py:463-475);只有 leased/running
    # 才返回 "cancellation_requested"。两种返回值都符合契约。
    assert repo.request_cancel("queued-cancel") in ("cancellation_requested", "cancelled")

    # Worker claims next queued job — but this job is now terminal "cancelled",
    # so claim_next's SQL (WHERE status='queued' AND cancel_requested=0) skips it,
    # returns None → run_once returns False, executor never invoked.
    worker.run_once()

    # The job should NOT have invoked the executor
    assert not executor_called.is_set(), "executor ran for a cancelled job"

    job = repo.get_job("queued-cancel")
    # Status should be terminal (cancelled or stopped), not running
    assert job.status in ("cancelled", "stopped"), f"expected terminal status, got {job.status}"
