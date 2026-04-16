import importlib
from types import SimpleNamespace

import pytest

training_api = importlib.import_module("api.training")


def _make_record(
    *,
    record_id: str,
    status: str,
    model_name: str = "demo-model",
    dataset_name: str = "demo-dataset",
    start_time: str = "2026-04-16T00:00:00",
    method: str = "qlora",
    config: dict | None = None,
):
    return training_api.TrainingRecord(
        id=record_id,
        model_name=model_name,
        dataset_name=dataset_name,
        method=method,
        status=status,
        start_time=start_time,
        config=config or {},
        output_path=f"/tmp/{record_id}",
        checkpoint_path=None,
    )


@pytest.mark.asyncio
async def test_recovery_options_aggregates_tasks_with_checkpoints(monkeypatch):
    records = [
        _make_record(record_id="task-1", status="failed", start_time="2026-04-16T10:00:00", config={"batch_size": 1}),
        _make_record(record_id="task-2", status="stopped", start_time="2026-04-16T09:00:00", config={"batch_size": 2}),
        _make_record(record_id="task-3", status="completed", start_time="2026-04-16T08:00:00"),
    ]

    class _State:
        def get_history(self):
            return records

    monkeypatch.setattr(training_api, "get_training_context", lambda: SimpleNamespace(state=_State()))
    monkeypatch.setattr(training_api, "get_settings", lambda: SimpleNamespace())
    monkeypatch.setattr(
        training_api,
        "_load_checkpoints_for_task",
        lambda _state, _settings, task_id: [{"name": "checkpoint-100", "step": 100}] if task_id != "task-2" else [],
    )

    payload = await training_api.get_recovery_options(limit=5)

    assert "generatedAt" in payload
    assert len(payload["options"]) == 1
    assert payload["options"][0]["taskId"] == "task-1"
    assert payload["options"][0]["latestCheckpointName"] == "checkpoint-100"


@pytest.mark.asyncio
async def test_failure_analytics_returns_expected_shape(monkeypatch):
    records = [
        _make_record(
            record_id="task-1",
            status="failed",
            model_name="qwen-7b",
            dataset_name="dataset-a",
            config={"batch_size": 2, "max_seq_length": 2048, "quantization": 0},
        ),
        _make_record(
            record_id="task-2",
            status="failed",
            model_name="qwen-7b",
            dataset_name="dataset-b",
            method="lora",
            config={"batch_size": 1, "max_seq_length": 512, "quantization": 4},
        ),
        _make_record(record_id="task-3", status="completed"),
    ]

    class _State:
        def get_history(self):
            return records

    monkeypatch.setattr(training_api, "get_training_context", lambda: SimpleNamespace(state=_State()))

    payload = await training_api.get_failure_analytics()

    assert payload["totalRuns"] == 3
    assert payload["failedRuns"] == 2
    assert payload["completedRuns"] == 1
    assert payload["suspectedVramPressureCount"] == 1
    assert payload["topFailedModels"][0] == "qwen-7b"
