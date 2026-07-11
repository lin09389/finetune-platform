"""Read-only summary mapping for submitted training runs."""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent_training.errors import AgentTrainingError
from agent_training.service import AgentTrainingService
from core.training_state import TrainingRecord


def test_run_summary_maps_the_authoritative_training_record(monkeypatch):
    import agent_training.service as service_module

    record = TrainingRecord(
        id="task-1",
        model_name="display-model",
        dataset_name="display-dataset",
        base_model_id="tiny-model",
        dataset_id="tiny-dataset",
        task_goal="qa_assistant",
        method="qlora",
        status="completed",
        start_time="2026-07-10T08:00:00",
        end_time="2026-07-10T08:03:00",
        config={},
        output_path="/outputs/train_task-1",
        adapter_path="/outputs/train_task-1/lora_adapter",
        checkpoint_path="/outputs/train_task-1/checkpoint-10",
        final_loss=0.25,
        elapsed_time=180.0,
    )
    monkeypatch.setattr(service_module, "find_training_record", lambda task_id: record if task_id == "task-1" else None)

    summary = AgentTrainingService().get_run_summary("task-1")
    payload = summary.model_dump()

    assert payload["task_id"] == "task-1"
    assert payload["status"] == "completed"
    assert payload["model_id"] == "tiny-model"
    assert payload["dataset_id"] == "tiny-dataset"
    assert payload["method"] == "qlora"
    assert payload["task_goal"] == "qa_assistant"
    assert payload["started_at"] == "2026-07-10T08:00:00"
    assert payload["completed_at"] == "2026-07-10T08:03:00"
    assert payload["output_path"] == "/outputs/train_task-1"
    assert payload["adapter_path"] == "/outputs/train_task-1/lora_adapter"
    assert payload["checkpoint_path"] == "/outputs/train_task-1/checkpoint-10"
    assert payload["final_loss"] == 0.25
    assert payload["elapsed_time"] == 180.0


def test_run_summary_rejects_unknown_runs(monkeypatch):
    import agent_training.service as service_module

    monkeypatch.setattr(service_module, "find_training_record", lambda _: None)

    with pytest.raises(AgentTrainingError, match="not found") as error:
        AgentTrainingService().get_training_run_summary("missing-task")

    assert error.value.code == "training_run_not_found"
