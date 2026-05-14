from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from types import SimpleNamespace

from training_engine.callbacks import ProgressCallback


class _DummyLoop:
    def is_closed(self) -> bool:
        return False


class _DummyWsManager:
    def __init__(self) -> None:
        self.events: list[str] = []

    async def broadcast_event(self, _task_id: str, event_type: str, _data: dict) -> None:
        self.events.append(event_type)


def test_on_train_end_broadcasts_saving_and_training_completed(monkeypatch):
    ws = _DummyWsManager()

    async def _run_now(coro, _loop):
        await coro

    def _run_coroutine_threadsafe(coro, loop):
        asyncio.run(_run_now(coro, loop))
        return None

    monkeypatch.setattr("training_engine.callbacks.get_vram_usage", lambda: 0.0)
    monkeypatch.setattr("training_engine.callbacks.asyncio.run_coroutine_threadsafe", _run_coroutine_threadsafe)

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
        event_loop=_DummyLoop(),
    )
    callback.current_loss = 0.42
    callback._get_ws_manager = lambda: ws

    callback.on_train_end(args=SimpleNamespace(learning_rate=1e-4), state=None, control=None)

    assert "saving_model" in ws.events
    assert "training_completed" in ws.events
    assert queued and queued[-1]["status"] == "saving"

