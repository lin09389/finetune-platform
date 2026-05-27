from __future__ import annotations

from datetime import datetime, timedelta
from types import SimpleNamespace

from training_engine.callbacks import ProgressCallback


def test_on_train_end_queues_saving_progress(monkeypatch):
    monkeypatch.setattr("training_engine.callbacks.get_vram_usage", lambda: 0.0)

    queued: list[dict] = []

    def _queue_training_progress(_state, **kwargs):
        queued.append(kwargs)

    monkeypatch.setattr("training_engine.callbacks.queue_training_progress", _queue_training_progress)

    callback = ProgressCallback(
        total_steps=10,
        start_time=datetime.now() - timedelta(seconds=5),
        state=SimpleNamespace(),
        record=SimpleNamespace(id="task-001"),
        config=SimpleNamespace(logging_steps=1, learning_rate=1e-4, epochs=1),
        event_loop=None,
    )
    callback.current_loss = 0.42

    callback.on_train_end(args=SimpleNamespace(learning_rate=1e-4), state=None, control=None)

    assert queued and queued[-1]["status"] == "saving"
