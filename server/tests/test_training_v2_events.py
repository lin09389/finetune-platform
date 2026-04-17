import importlib
import json
from types import SimpleNamespace

import pytest

from core.training_events_v2 import TrainingEventHubV2, normalize_phase_v2

training_api = importlib.import_module("api.training")


def test_event_hub_sequence_monotonic_and_replay():
    hub = TrainingEventHubV2(max_events=16)
    e1 = hub.publish(task_id="task-1", phase="queued", kind="task_queued", payload={"step": 0})
    e2 = hub.publish(task_id="task-1", phase="running", kind="progress_updated", payload={"step": 1})
    e3 = hub.publish(task_id="task-2", phase="failed", kind="progress_updated", payload={"step": 3})

    assert e1.sequence < e2.sequence < e3.sequence
    assert hub.parse_last_event_id(e1.event_id) == e1.sequence

    replay = hub.list_since(e1.sequence, task_id="task-1")
    assert len(replay) == 1
    assert replay[0].event_id == e2.event_id


def test_normalize_phase_v2_contract():
    assert normalize_phase_v2("training") == "running"
    assert normalize_phase_v2("running") == "running"
    assert normalize_phase_v2("queued") == "queued"
    assert normalize_phase_v2("idle") is None


def test_queue_training_progress_publishes_event_with_record(monkeypatch):
    hub = TrainingEventHubV2(max_events=16)
    monkeypatch.setattr(training_api, "get_training_event_hub_v2", lambda: hub)

    class _State:
        def __init__(self):
            self.progress = {}

        def queue_progress_update(self, **kwargs):
            self.progress = kwargs

        def get_current_record(self):
            return SimpleNamespace(id="task-1")

    state = _State()
    training_api._queue_training_progress(
        state,
        status="running",
        message="ok",
        step=2,
        total_steps=10,
        loss=0.2,
        lr=0.001,
    )

    events = hub.list_since(0, task_id="task-1")
    assert len(events) == 1
    assert events[0].phase == "running"
    assert events[0].payload["step"] == 2


@pytest.mark.asyncio
async def test_get_status_prefers_v2_progress_payload(monkeypatch):
    hub = TrainingEventHubV2(max_events=16)
    hub.publish(
        task_id="task-1",
        phase="completed",
        kind="progress_updated",
        payload={"final_loss": 0.123, "final_lr": 0.0002, "status": "completed", "message": "done"},
    )
    monkeypatch.setattr(training_api, "get_training_event_hub_v2", lambda: hub)

    class _State:
        def get_status(self):
            return {
                "is_training": False,
                "record": {"id": "task-1"},
                "progress": {
                    "epoch": 1,
                    "step": 10,
                    "total_steps": 10,
                    "loss": 0.0,
                    "lr": 0.0,
                    "vram_used": 0.0,
                    "elapsed_time": 1.0,
                    "eta": 0.0,
                    "status": "completed",
                    "message": "",
                },
            }

    monkeypatch.setattr(training_api, "get_training_context", lambda: SimpleNamespace(state=_State()))
    status = await training_api.get_status()
    assert status["progress"]["loss"] == 0.123
    assert status["progress"]["lr"] == 0.0002


async def test_metrics_v2_cursor_pagination(tmp_path, monkeypatch):
    task_id = "12345678-task"
    out_dir = tmp_path / f"train_{task_id[:8]}"
    out_dir.mkdir(parents=True, exist_ok=True)
    metrics_file = out_dir / "metrics.jsonl"
    records = [{"step": i, "loss": i / 10} for i in range(5)]
    metrics_file.write_text("\n".join(json.dumps(item) for item in records), encoding="utf-8")

    monkeypatch.setattr(
        training_api,
        "get_settings",
        lambda: SimpleNamespace(outputs_dir_resolved=tmp_path),
    )

    page1 = await training_api.get_training_metrics_v2(task_id=task_id, cursor=0, limit=2)
    page2 = await training_api.get_training_metrics_v2(task_id=task_id, cursor=page1["next_cursor"], limit=2)

    assert len(page1["items"]) == 2
    assert page1["next_cursor"] == 2
    assert page1["has_more"] is True
    assert len(page2["items"]) == 2


@pytest.mark.asyncio
async def test_cancel_task_emits_cancelled_event_for_queued_task(monkeypatch):
    hub = TrainingEventHubV2(max_events=16)
    monkeypatch.setattr(training_api, "get_training_event_hub_v2", lambda: hub)

    class _Queue:
        def cancel(self, task_id):
            return True

    class _State:
        def get_current_record(self):
            return None

        def is_training(self):
            return False

    monkeypatch.setattr(
        training_api,
        "get_training_context",
        lambda: SimpleNamespace(queue=_Queue(), state=_State()),
    )

    payload = await training_api.cancel_task("task-queued")
    assert "cancelled" in payload["message"]

    events = hub.list_since(0, task_id="task-queued")
    assert len(events) == 1
    assert events[0].phase == "stopped"
    assert events[0].kind == "task_cancelled"


@pytest.mark.asyncio
async def test_cancel_task_emits_stopping_event_for_running_task(monkeypatch):
    hub = TrainingEventHubV2(max_events=16)
    monkeypatch.setattr(training_api, "get_training_event_hub_v2", lambda: hub)

    class _Queue:
        def cancel(self, task_id):
            return True

    class _State:
        def request_stop(self):
            return None

        def get_current_record(self):
            return SimpleNamespace(id="task-running")

        def is_training(self):
            return True

        def queue_progress_update(self, **_kwargs):
            return None

    monkeypatch.setattr(
        training_api,
        "get_training_context",
        lambda: SimpleNamespace(queue=_Queue(), state=_State()),
    )

    await training_api.cancel_task("task-running")
    events = hub.list_since(0, task_id="task-running")
    assert len(events) >= 1
    assert any(event.kind == "task_cancellation_requested" for event in events)
