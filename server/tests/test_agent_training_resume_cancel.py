"""Service-level tests for Agent training resume/cancel review fixes."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from agent_session.execution_context import AgentDefinition
from agent_session.permission import permission_policy_for_agent
from agent_training.errors import AgentTrainingError
from agent_training.service import AgentTrainingService
from services.training.resume_identity import ResumeIdentityError, validate_resume_identity


def test_sanitize_checkpoint_name_rejects_traversal():
    with pytest.raises(AgentTrainingError) as exc:
        AgentTrainingService._sanitize_checkpoint_name("../escape")
    assert exc.value.code == "invalid_checkpoint_name"

    with pytest.raises(AgentTrainingError):
        AgentTrainingService._sanitize_checkpoint_name("a/b")

    assert AgentTrainingService._sanitize_checkpoint_name("checkpoint-10") == "checkpoint-10"


def test_resume_identity_mismatch_raises(tmp_path: Path):
    checkpoint = tmp_path / "checkpoint-1"
    checkpoint.mkdir()
    (checkpoint / "checkpoint_metadata.json").write_text(
        '{"base_model_id": "model-a", "dataset_id": "ds-a", "config_hash": "abc"}',
        encoding="utf-8",
    )
    record = SimpleNamespace(
        base_model_id="model-b",
        dataset_id="ds-a",
        model_name="model-b",
        dataset_name="ds-a",
        config={"model_id": "model-b", "dataset_id": "ds-a"},
        config_hash=None,
    )
    with pytest.raises(ResumeIdentityError):
        validate_resume_identity(
            original_record=record,
            config_dict={"model_id": "model-b", "dataset_id": "ds-a"},
            checkpoint_path=checkpoint,
        )


def test_resume_identity_missing_metadata_is_soft_warning(tmp_path: Path):
    checkpoint = tmp_path / "checkpoint-1"
    checkpoint.mkdir()
    record = SimpleNamespace(
        base_model_id="model-a",
        dataset_id="ds-a",
        model_name="model-a",
        dataset_name="ds-a",
        config={},
        config_hash=None,
    )
    warnings = validate_resume_identity(
        original_record=record,
        config_dict={"model_id": "model-a", "dataset_id": "ds-a"},
        checkpoint_path=checkpoint,
    )
    assert warnings
    assert "checkpoint_metadata.json" in warnings[0]


def test_cancel_in_process_refuses_wrong_active_task(monkeypatch):
    service = AgentTrainingService()
    monkeypatch.setattr(service._settings, "training_execution_mode", "in_process")

    class _State:
        def is_training(self):
            return True

        def get_current_record(self):
            return SimpleNamespace(id="task-active")

        def should_stop(self):
            return False

        def request_stop(self):
            raise AssertionError("must not stop wrong task")

    monkeypatch.setattr(service, "_submission_state", lambda: _State())

    with pytest.raises(AgentTrainingError) as exc:
        service.cancel_training(task_id="task-other")
    assert exc.value.code == "training_run_mismatch"


def test_cancel_in_process_stops_matching_active_task(monkeypatch):
    service = AgentTrainingService()
    monkeypatch.setattr(service._settings, "training_execution_mode", "in_process")
    stopped = {"value": False}
    progress = {"value": False}

    class _State:
        def is_training(self):
            return True

        def get_current_record(self):
            return SimpleNamespace(id="task-active")

        def should_stop(self):
            return False

        def request_stop(self):
            stopped["value"] = True

    monkeypatch.setattr(service, "_submission_state", lambda: _State())

    def _progress(*_args, **_kwargs):
        progress["value"] = True

    monkeypatch.setattr("training_engine.callbacks.queue_training_progress", _progress)

    result = service.cancel_training(task_id="task-active")
    assert result.status == "stopping"
    assert stopped["value"] is True
    assert progress["value"] is True


def test_read_only_strips_mutating_training_tools():
    agent = AgentDefinition(
        id="build",
        name="Build",
        tools=["ls", "read_file", "write_file", "execute", "submit_training", "propose_training"],
    )
    policy = permission_policy_for_agent(
        agent,
        "build",
        {"autonomy_mode": "read_only", "task_mode": "train"},
    )
    allowed = policy.allowed_tools()
    assert allowed is not None
    assert "write_file" not in allowed
    assert "execute" not in allowed
    assert "submit_training" not in allowed
    assert "resume_training" not in allowed
    assert "cancel_training" not in allowed
    # Read-only diagnostics remain allowed when listed / injected.
    assert "propose_training" in allowed or "get_training_summary" in allowed or "ls" in allowed
