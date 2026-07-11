"""Approval and submission safeguards for agent training proposals."""

import os
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent_training.errors import AgentTrainingError
from agent_training.models import ApprovedTrainingAction, TrainingProposal
from agent_training.service import AgentTrainingService
from agent_training.store import TrainingProposalStore


class _Settings:
    training_execution_mode = "worker"

    def __init__(self, models_dir, datasets_dir):
        self.models_dir_resolved = models_dir
        self.datasets_dir_resolved = datasets_dir


def _proposal(status="ready"):
    return TrainingProposal(
        proposal_id="proposal-1",
        config={"model_id": "tiny-model", "dataset_id": "tiny-dataset"},
        status=status,
        blockers=["Dataset is invalid"] if status == "blocked" else [],
    )


def _service(tmp_path):
    settings = _Settings(tmp_path / "models", tmp_path / "datasets")
    return AgentTrainingService(settings=settings, proposal_store=TrainingProposalStore()), settings


def test_submission_requires_explicit_approval_and_known_ready_proposal(tmp_path):
    service, _ = _service(tmp_path)

    with pytest.raises(AgentTrainingError, match="approved=True") as approval_error:
        service.submit_approved_training(ApprovedTrainingAction(proposal_id="missing", approved=False))
    assert approval_error.value.code == "approval_required"

    with pytest.raises(AgentTrainingError, match="unknown or expired") as unknown_error:
        service.submit_approved_training(ApprovedTrainingAction(proposal_id="missing", approved=True))
    assert unknown_error.value.code == "proposal_not_found"


def test_submission_rejects_blocked_proposals_without_calling_orchestrator(tmp_path, monkeypatch):
    import agent_training.service as service_module

    service, _ = _service(tmp_path)
    service._proposal_store.add(_proposal(status="blocked"))
    monkeypatch.setattr(service_module, "start_training_task", lambda **_: pytest.fail("must not submit"))

    with pytest.raises(AgentTrainingError, match="Blocked") as error:
        service.submit_approved_training(ApprovedTrainingAction(proposal_id="proposal-1", approved=True))

    assert error.value.code == "proposal_blocked"


def test_submission_re_resolves_paths_and_rejects_duplicate_proposals(tmp_path, monkeypatch):
    import agent_training.service as service_module

    service, settings = _service(tmp_path)
    service._proposal_store.add(_proposal())
    model_path = settings.models_dir_resolved / "tiny-model"
    dataset_file = settings.datasets_dir_resolved / "tiny-dataset" / "data.jsonl"
    model_path.mkdir(parents=True)
    dataset_file.parent.mkdir(parents=True)
    dataset_file.write_text('{"text":"sample"}\n', encoding="utf-8")
    calls = {"resolve": 0, "submit": 0}

    def fake_resolve(received_settings, dataset_id):
        assert received_settings is settings
        assert dataset_id == "tiny-dataset"
        calls["resolve"] += 1
        return dataset_file

    def fake_submit(**kwargs):
        assert kwargs["model_path"] == model_path
        assert kwargs["dataset_file"] == dataset_file
        calls["submit"] += 1
        return SimpleNamespace(id="task-1", status="queued")

    monkeypatch.setattr(service_module, "resolve_dataset_file", fake_resolve)
    monkeypatch.setattr(service_module, "start_training_task", fake_submit)
    async def valid_preflight(*_):
        return SimpleNamespace(errors=[])
    monkeypatch.setattr(service_module.TrainingValidator, "validate_config", valid_preflight)

    submission = service.submit_approved_training(
        ApprovedTrainingAction(proposal_id="proposal-1", approved=True)
    )
    assert submission.task_id == "task-1"
    assert calls == {"resolve": 1, "submit": 1}

    with pytest.raises(AgentTrainingError, match="already been submitted") as duplicate_error:
        service.submit_approved_training(ApprovedTrainingAction(proposal_id="proposal-1", approved=True))
    assert duplicate_error.value.code == "proposal_already_submitted"
    assert calls == {"resolve": 1, "submit": 1}


def test_submission_rejects_a_proposal_when_paths_are_no_longer_resolvable(tmp_path, monkeypatch):
    import agent_training.service as service_module

    service, _ = _service(tmp_path)
    service._proposal_store.add(_proposal())
    monkeypatch.setattr(service_module, "resolve_dataset_file", lambda *_: None)
    monkeypatch.setattr(service_module, "start_training_task", lambda **_: pytest.fail("must not submit"))

    with pytest.raises(AgentTrainingError, match="Model is no longer available") as error:
        service.submit_approved_training(ApprovedTrainingAction(proposal_id="proposal-1", approved=True))
    assert error.value.code == "proposal_stale"


def test_submission_requires_the_same_owner_and_agent_session(tmp_path):
    service, _ = _service(tmp_path)
    service._proposal_store.add(TrainingProposal(
        proposal_id="proposal-1",
        config={"model_id": "tiny-model", "dataset_id": "tiny-dataset"},
        status="ready",
        owner_id="user-a",
        session_id="session-a",
    ))

    with pytest.raises(AgentTrainingError, match="different user") as error:
        service.submit_approved_training(
            ApprovedTrainingAction(proposal_id="proposal-1", approved=True),
            owner_id="user-b",
            session_id="session-a",
        )

    assert error.value.code == "proposal_scope_mismatch"


def test_sqlite_proposal_store_preserves_claims_across_store_instances(tmp_path):
    path = tmp_path / "proposals.sqlite3"
    first = TrainingProposalStore(db_path=path)
    first.add(_proposal())

    second = TrainingProposalStore(db_path=path)
    assert second.get("proposal-1") is not None
    assert second.claim_submission("proposal-1") is True
    assert first.claim_submission("proposal-1") is False


def test_submission_preflight_succeeds_when_called_on_a_running_event_loop(tmp_path, monkeypatch):
    import asyncio

    import agent_training.service as service_module

    service, settings = _service(tmp_path)
    service._proposal_store.add(_proposal())
    model_path = settings.models_dir_resolved / "tiny-model"
    dataset_file = settings.datasets_dir_resolved / "tiny-dataset" / "data.jsonl"
    model_path.mkdir(parents=True)
    dataset_file.parent.mkdir(parents=True)
    dataset_file.write_text('{"text":"sample"}\n', encoding="utf-8")

    monkeypatch.setattr(service_module, "resolve_dataset_file", lambda *_: dataset_file)
    monkeypatch.setattr(
        service_module,
        "start_training_task",
        lambda **_: SimpleNamespace(id="task-loop-1", status="queued"),
    )

    async def valid_preflight(*_):
        return SimpleNamespace(errors=[])

    monkeypatch.setattr(service_module.TrainingValidator, "validate_config", valid_preflight)

    async def submit_on_loop():
        return service.submit_approved_training(
            ApprovedTrainingAction(proposal_id="proposal-1", approved=True)
        )

    submission = asyncio.run(submit_on_loop())
    assert submission.task_id == "task-loop-1"
    assert submission.status == "queued"


def test_sqlite_store_does_not_revive_a_claimed_submission_on_readd(tmp_path):
    path = tmp_path / "proposals.sqlite3"
    store = TrainingProposalStore(db_path=path)
    store.add(_proposal())
    assert store.claim_submission("proposal-1") is True

    store.add(_proposal())
    assert store.claim_submission("proposal-1") is False
