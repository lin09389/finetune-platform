from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

import pytest
from agent_session.repository import AgentSessionRepository
from agent_session.training_run_sync import (
    LocalSQLiteTrainingEventSource,
    TrainingEventSource,
    TrainingRunReconciler,
)
from agent_training.models import TrainingRunSummary, training_activity_for


def _session(repository: AgentSessionRepository, session_id: str, owner_id: str = "alice", task_mode: str = "train") -> dict[str, Any]:
    return repository.create_session(
        {"id": session_id, "agent_id": "build", "status": "idle", "title": session_id, "metadata": {"user_id": owner_id, "task_mode": task_mode}}
    )


def test_training_link_is_ownership_bound_idempotent_and_cursor_is_monotonic(tmp_path):
    repository = AgentSessionRepository(str(tmp_path / "agents.db"))
    _session(repository, "session-a", "alice")
    _session(repository, "session-b", "bob")

    first = repository.create_training_link(
        session_id="session-a", owner_id="alice", proposal_id="proposal-1", task_id="task-1"
    )
    duplicate = repository.create_training_link(
        session_id="session-a", owner_id="alice", proposal_id="proposal-1", task_id="task-1"
    )

    assert duplicate["part_id"] == first["part_id"]
    assert repository.get_part(first["part_id"])["payload"]["training_activity"]["task_id"] == "task-1"
    assert repository.advance_training_link("task-1", sequence=4, status="running") is True
    assert repository.advance_training_link("task-1", sequence=3, status="queued") is False
    assert repository.get_training_link("task-1")["last_event_sequence"] == 4
    assert repository.list_training_links_for_reconciliation()[0]["task_id"] == "task-1"

    with pytest.raises(PermissionError):
        repository.create_training_link(session_id="session-a", owner_id="bob", proposal_id="proposal-2", task_id="task-2")
    with pytest.raises(ValueError):
        repository.create_training_link(session_id="session-b", owner_id="bob", proposal_id="proposal-1", task_id="task-1")


def test_terminal_link_is_not_reconciled_after_its_final_projection(tmp_path):
    repository = AgentSessionRepository(str(tmp_path / "agents.db"))
    _session(repository, "session-a")
    repository.create_training_link(session_id="session-a", owner_id="alice", proposal_id="proposal-1", task_id="task-1")
    repository.advance_training_link("task-1", sequence=8, status="completed")

    assert repository.list_training_links_for_reconciliation() == []
    assert repository.get_terminal_training_link("task-1")["status"] == "completed"


def test_build_sessions_cannot_link_training_and_hybrid_sync_leaves_coding_state_untouched(tmp_path):
    repository = AgentSessionRepository(str(tmp_path / "agents.db"))
    _session(repository, "build-session", task_mode="build")
    with pytest.raises(ValueError, match="Train or Hybrid"):
        repository.create_training_link(session_id="build-session", owner_id="alice", proposal_id="proposal-build", task_id="task-build")

    _session(repository, "hybrid-session", task_mode="hybrid")
    coding_part = repository.add_part("hybrid-session", "command", status="completed", title="pytest", content="passed", payload={"changed_files": ["app.py"]})
    link = repository.create_training_link(session_id="hybrid-session", owner_id="alice", proposal_id="proposal-hybrid", task_id="task-hybrid")
    repository.advance_training_link("task-hybrid", sequence=1, status="completed")

    assert repository.get_session("hybrid-session")["status"] == "idle"
    assert repository.get_part(coding_part["id"]) == coding_part
    assert repository.get_part(link["part_id"])["status"] == "completed"


def test_safe_run_summary_projection_allows_only_valid_display_metrics():
    summary = TrainingRunSummary(
        task_id="task-1", status="completed", model_id="tiny-model", dataset_id="tiny-dataset", method="qlora",
        started_at="2026-07-11T00:00:00Z", completed_at="2026-07-11T00:01:00Z", output_path="C:\\private\\output",
        adapter_path="C:\\private\\adapter", checkpoint_path="C:\\private\\checkpoint", phase="completed",
        step=10, total_steps=10, epoch=1.0, loss=0.125, elapsed_time=60, eta=0, updated_at="2026-07-11T00:01:00Z",
        artifact_available=True,
    )
    activity = training_activity_for(summary).model_dump()

    assert activity["step"] == 10
    assert activity["artifact_available"] is True
    assert "private" not in str(activity)

    with pytest.raises(ValueError):
        TrainingRunSummary(
            task_id="task-1", status="running", model_id="m", dataset_id="d", method="qlora", started_at="now",
            output_path="/unsafe", loss=-1,
        )


@dataclass(frozen=True)
class _Event:
    sequence: int
    task_id: str
    phase: str
    kind: str
    payload: dict[str, Any]


class _Source(TrainingEventSource):
    def __init__(self, events: list[_Event], summary: TrainingRunSummary | None):
        self.events = events
        self.summary = summary

    def list_events(self, task_id: str, after_sequence: int, limit: int):
        return [event for event in self.events if event.task_id == task_id and event.sequence > after_sequence][:limit]

    def get_run_summary(self, task_id: str):
        return self.summary if self.summary and self.summary.task_id == task_id else None


def test_reconciler_replays_ordered_events_without_raw_payload_leaks_or_duplicate_parts(tmp_path):
    repository = AgentSessionRepository(str(tmp_path / "agents.db"))
    _session(repository, "session-a")
    link = repository.create_training_link(session_id="session-a", owner_id="alice", proposal_id="proposal-1", task_id="task-1")
    source = _Source(
        [
            _Event(1, "task-1", "loading", "task_started", {"worker_id": "secret-worker", "path": "C:\\private\\checkpoint"}),
            _Event(2, "task-1", "running", "progress", {"loss": -999, "raw": "C:\\private\\output"}),
            _Event(3, "task-1", "running", "unknown_future_event", {"token": "secret"}),
        ],
        TrainingRunSummary(task_id="task-1", status="running", model_id="tiny-model", dataset_id="tiny-dataset", method="qlora", started_at="2026-07-11T00:00:00Z", output_path="C:\\private\\output", phase="running", step=2, total_steps=10, loss=0.2, updated_at="2026-07-11T00:00:02Z"),
    )
    reconciler = TrainingRunReconciler(repository=repository, event_source=source)

    assert asyncio.run(reconciler.reconcile_once()) == 1
    assert asyncio.run(reconciler.reconcile_once()) == 0
    stored_link = repository.get_training_link("task-1")
    part = repository.get_part(link["part_id"])

    assert stored_link["last_event_sequence"] == 3
    assert stored_link["status"] == "running"
    assert part["payload"]["training_activity"] == training_activity_for(source.summary).model_dump()
    assert len([item for item in repository.list_parts("session-a") if item["id"] == link["part_id"]]) == 1
    assert "private" not in str(part)
    assert "secret-worker" not in str(part)
    assert "secret\"" not in str(part)


def test_unknown_event_advances_only_cursor_and_never_changes_visible_training_projection(tmp_path):
    repository = AgentSessionRepository(str(tmp_path / "agents.db"))
    _session(repository, "session-a")
    link = repository.create_training_link(session_id="session-a", owner_id="alice", proposal_id="proposal-1", task_id="task-1")
    before = repository.get_part(link["part_id"])["payload"]["training_activity"]
    source = _Source(
        [_Event(1, "task-1", "future", "future_event", {"path": "C:\\private\\output"})],
        TrainingRunSummary(task_id="task-1", status="completed", model_id="tiny-model", dataset_id="tiny-dataset", method="qlora", started_at="now", completed_at="later", output_path="C:\\private\\output"),
    )

    assert asyncio.run(TrainingRunReconciler(repository=repository, event_source=source).reconcile_once()) == 1
    assert repository.get_training_link("task-1")["last_event_sequence"] == 1
    assert repository.get_training_link("task-1")["status"] == "queued"
    assert repository.get_part(link["part_id"])["payload"]["training_activity"] == before


def test_local_sqlite_source_returns_ordered_task_events_and_none_for_missing_job(tmp_path):
    from training_worker.repository import TrainingJobRepository

    jobs = TrainingJobRepository(str(tmp_path / "jobs.db"))
    jobs.enqueue(job_id="task-1", backend="native", priority=1, config={"model_id": "tiny-model", "dataset_id": "tiny-dataset", "method": "qlora"}, model_path="C:\\private\\model", dataset_path="C:\\private\\data", output_path="C:\\private\\output", record={"id": "task-1", "model_name": "tiny-model", "dataset_name": "tiny-dataset", "base_model_id": "tiny-model", "dataset_id": "tiny-dataset", "method": "qlora", "status": "queued", "start_time": "2026-07-11T00:00:00Z", "output_path": "C:\\private\\output"})
    jobs.append_event(task_id="task-1", phase="running", kind="progress", payload={"step": 1})
    source = LocalSQLiteTrainingEventSource(jobs)

    assert [event.sequence for event in source.list_events("task-1", 0, 10)] == [1, 2]
    assert source.get_run_summary("missing") is None
    assert source.get_run_summary("task-1").task_id == "task-1"


def test_missing_job_uses_bounded_grace_and_persists_safe_terminal_state(tmp_path):
    repository = AgentSessionRepository(str(tmp_path / "agents.db"))
    _session(repository, "session-a")
    link = repository.create_training_link(
        session_id="session-a", owner_id="alice", proposal_id="proposal-1", task_id="task-1"
    )
    reconciler = TrainingRunReconciler(
        repository=repository,
        event_source=_Source([], None),
        missing_grace_attempts=2,
    )

    assert asyncio.run(reconciler.reconcile_once()) == 1
    assert repository.get_training_link("task-1")["status"] == "degraded"
    assert repository.get_part(link["part_id"])["payload"]["training_activity"]["status"] == "degraded"
    assert asyncio.run(reconciler.reconcile_once()) == 1
    assert repository.get_training_link("task-1")["status"] == "missing"
    activity = repository.get_part(link["part_id"])["payload"]["training_activity"]
    assert activity["status"] == "missing"
    assert "path" not in str(activity).lower()
    assert repository.list_training_links_for_reconciliation() == []
