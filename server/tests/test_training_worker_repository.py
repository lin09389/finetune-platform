from __future__ import annotations

from datetime import UTC, datetime, timedelta

from training_worker.repository import TrainingJobRepository


def _enqueue(repo: TrainingJobRepository, job_id: str, *, priority: int = 2, max_attempts: int = 3):
    return repo.enqueue(
        job_id=job_id,
        backend="native",
        priority=priority,
        config={"model_id": "model", "dataset_id": "dataset", "method": "lora"},
        model_path="models/model",
        dataset_path="datasets/dataset/data.jsonl",
        output_path=f"outputs/{job_id}",
        record={"id": job_id, "status": "queued"},
        max_attempts=max_attempts,
    )


def test_enqueue_claim_is_atomic_and_priority_ordered(tmp_path):
    repo = TrainingJobRepository(str(tmp_path / "jobs.db"))
    _enqueue(repo, "normal", priority=2)
    _enqueue(repo, "urgent", priority=0)

    claimed = repo.claim_next("worker-a", lease_seconds=30)
    competing = repo.claim_next("worker-b", lease_seconds=30)

    assert claimed and claimed.job_id == "urgent"
    assert claimed.status == "leased"
    assert claimed.attempt == 1
    assert competing and competing.job_id == "normal"
    assert repo.claim_next("worker-c", lease_seconds=30) is None


def test_heartbeat_requires_owner_and_renews_lease(tmp_path):
    repo = TrainingJobRepository(str(tmp_path / "jobs.db"))
    _enqueue(repo, "job")
    now = datetime(2026, 7, 2, tzinfo=UTC)
    repo.claim_next("worker-a", lease_seconds=10, now=now)

    assert repo.heartbeat("job", "worker-b", lease_seconds=60, now=now) is False
    assert repo.heartbeat("job", "worker-a", lease_seconds=60, now=now) is True
    assert repo.get_job("job").lease_expires_at == (now + timedelta(seconds=60)).isoformat()


def test_cancel_queued_job_is_terminal_and_running_job_is_requested(tmp_path):
    repo = TrainingJobRepository(str(tmp_path / "jobs.db"))
    _enqueue(repo, "running")
    _enqueue(repo, "queued")
    claimed = repo.claim_next("worker", lease_seconds=30)
    assert claimed and claimed.job_id == "running"
    assert repo.mark_running("running", "worker")

    assert repo.request_cancel("queued") == "cancelled"
    assert repo.request_cancel("running") == "cancellation_requested"
    assert repo.get_job("queued").status == "cancelled"
    assert repo.get_job("running").cancel_requested is True


def test_expired_lease_requeues_then_interrupts_after_attempt_limit(tmp_path):
    repo = TrainingJobRepository(str(tmp_path / "jobs.db"))
    _enqueue(repo, "job", max_attempts=2)
    started = datetime(2026, 7, 2, tzinfo=UTC)

    repo.claim_next("worker-a", lease_seconds=5, now=started)
    assert repo.recover_expired(now=started + timedelta(seconds=6)) == {
        "requeued": 1,
        "interrupted": 0,
        "cancelled": 0,
    }
    assert repo.get_job("job").status == "queued"

    repo.claim_next("worker-b", lease_seconds=5, now=started + timedelta(seconds=7))
    assert repo.recover_expired(now=started + timedelta(seconds=13)) == {
        "requeued": 0,
        "interrupted": 1,
        "cancelled": 0,
    }
    job = repo.get_job("job")
    assert job.status == "interrupted"
    assert job.error == "worker lease expired after maximum attempts"


def test_terminal_update_persists_record_and_releases_lease(tmp_path):
    repo = TrainingJobRepository(str(tmp_path / "jobs.db"))
    _enqueue(repo, "job")
    repo.claim_next("worker", lease_seconds=30)
    repo.mark_running("job", "worker")

    assert repo.finish(
        "job",
        "worker",
        status="completed",
        record={"id": "job", "status": "completed", "final_loss": 0.1},
    )
    job = repo.get_job("job")
    assert job.status == "completed"
    assert job.record["final_loss"] == 0.1
    assert job.lease_owner is None
    assert job.finished_at


def test_events_replay_across_repository_instances(tmp_path):
    db_path = str(tmp_path / "jobs.db")
    first = TrainingJobRepository(db_path)
    _enqueue(first, "job")
    event = first.append_event(
        task_id="job",
        phase="running",
        kind="progress_updated",
        payload={"step": 3},
    )

    second = TrainingJobRepository(db_path)
    replayed = second.list_events(after_sequence=event.sequence - 1, task_id="job")

    assert replayed[-1].event_id == event.event_id
    assert replayed[-1].sequence == event.sequence
    assert replayed[-1].payload == {"step": 3}
    assert second.latest_event("job").event_id == event.event_id


def test_logs_are_persisted_and_resumable_by_sequence(tmp_path):
    db_path = str(tmp_path / "jobs.db")
    first = TrainingJobRepository(db_path)
    first_sequence = first.append_log(
        task_id="job", level="INFO", logger="training.job", message="loading model"
    )
    second_sequence = first.append_log(
        task_id="job", level="INFO", logger="training.job", message="step 1"
    )

    restarted = TrainingJobRepository(db_path)
    assert [row["message"] for row in restarted.recent_logs("job", limit=2)] == [
        "loading model",
        "step 1",
    ]
    resumed = restarted.list_logs("job", after_sequence=first_sequence)
    assert len(resumed) == 1
    assert resumed[0]["sequence"] == second_sequence
    assert resumed[0]["message"] == "step 1"


def test_worker_registration_and_stale_detection(tmp_path):
    repo = TrainingJobRepository(str(tmp_path / "jobs.db"))
    now = datetime(2026, 7, 2, tzinfo=UTC)
    repo.register_worker("worker", pid=123, hostname="host", now=now)
    assert repo.worker_status(stale_after_seconds=10, now=now)[0]["status"] == "online"
    assert repo.worker_status(stale_after_seconds=10, now=now + timedelta(seconds=11))[0]["status"] == "stale"
    repo.stop_worker("worker", now=now + timedelta(seconds=12))
    assert repo.worker_status(now=now + timedelta(seconds=12))[0]["status"] == "stopped"


def test_expired_lease_preserves_durable_cancellation(tmp_path):
    repo = TrainingJobRepository(str(tmp_path / "jobs.db"))
    _enqueue(repo, "job")
    started = datetime(2026, 7, 2, tzinfo=UTC)
    repo.claim_next("worker", lease_seconds=5, now=started)
    repo.mark_running("job", "worker", now=started)
    assert repo.request_cancel("job", now=started + timedelta(seconds=1)) == "cancellation_requested"

    assert repo.recover_expired(now=started + timedelta(seconds=6)) == {
        "requeued": 0,
        "interrupted": 0,
        "cancelled": 1,
    }
    job = repo.get_job("job")
    assert job.status == "cancelled"
    assert job.record["status"] == "cancelled"
