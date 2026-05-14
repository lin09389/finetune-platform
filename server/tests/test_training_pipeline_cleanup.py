from __future__ import annotations

from types import SimpleNamespace

from training_engine.pipeline import TrainingPipeline


class _DummyState:
    def __init__(self) -> None:
        self.unregistered: list[str] = []

    def unregister_training_task(self, task_id: str) -> None:
        self.unregistered.append(task_id)


class _DummyBus:
    def __init__(self) -> None:
        self.training_states: list[bool] = []
        self.events: list[tuple[str, str, dict]] = []

    def publish_training_state(self, value: bool) -> None:
        self.training_states.append(value)

    def publish_event(self, *, phase: str, kind: str, payload: dict) -> None:
        self.events.append((phase, kind, payload))


class _ImmediateThread:
    def __init__(self, target, args=(), daemon=False):
        self._target = target
        self._args = args
        self.daemon = daemon

    def start(self) -> None:
        self._target(*self._args)


def test_run_cleanup_async_path_executes_without_scope_error(monkeypatch):
    cleaned: list[object] = []
    gpu_cleaned: list[bool] = []

    monkeypatch.setattr("training_engine.pipeline.safe_cleanup_model", lambda model: cleaned.append(model))
    monkeypatch.setattr("training_engine.pipeline.cleanup_gpu_memory", lambda aggressive=True: gpu_cleaned.append(bool(aggressive)))
    monkeypatch.setattr("threading.Thread", _ImmediateThread)

    state = _DummyState()
    bus = _DummyBus()
    model = object()
    ctx = SimpleNamespace(
        task_id="task-001",
        state=state,
        model=model,
        tokenizer=object(),
        trainer=object(),
    )
    pipeline = TrainingPipeline(ctx=ctx, event_bus=bus)

    pipeline._run_cleanup()

    assert bus.training_states and bus.training_states[-1] is False
    assert state.unregistered == ["task-001"]
    assert cleaned == [model]
    assert gpu_cleaned == [True]
    assert ctx.model is None
    assert ctx.tokenizer is None
    assert ctx.trainer is None

