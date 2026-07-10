"""Read-only diagnostic behavior for agent training proposals."""

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent_training.models import TrainingProposalRequest
from agent_training.service import AgentTrainingService
from training_engine.schemas import ValidationResult


class _Settings:
    def __init__(self, models_dir, datasets_dir):
        self.models_dir_resolved = models_dir
        self.datasets_dir_resolved = datasets_dir
        self.training_execution_mode = "worker"


def test_proposal_runs_diagnostics_without_creating_outputs_or_submitting(tmp_path, monkeypatch):
    import agent_training.service as service_module

    model_path = tmp_path / "models" / "tiny-model"
    dataset_file = tmp_path / "datasets" / "tiny-dataset" / "data.jsonl"
    model_path.mkdir(parents=True)
    dataset_file.parent.mkdir(parents=True)
    dataset_file.write_text('{"text":"sample"}\n', encoding="utf-8")
    settings = _Settings(model_path.parent, dataset_file.parent.parent)
    calls = {"validator": 0, "estimate": 0, "submit": 0}

    async def fake_validate(config, received_settings):
        assert received_settings is settings
        calls["validator"] += 1
        return ValidationResult(warnings=["Dataset is very small"])

    monkeypatch.setattr(service_module.TrainingValidator, "validate_config", fake_validate)
    monkeypatch.setattr(service_module, "resolve_dataset_file", lambda *_: dataset_file)
    monkeypatch.setattr(
        service_module,
        "estimate_preflight_required_vram",
        lambda _: calls.__setitem__("estimate", calls["estimate"] + 1) or 4.5,
    )
    monkeypatch.setattr(
        service_module,
        "start_training_task",
        lambda **_: calls.__setitem__("submit", calls["submit"] + 1),
    )

    proposal = asyncio.run(
        AgentTrainingService(settings=settings, proposal_id_factory=lambda: "proposal-1").create_proposal(
            TrainingProposalRequest(config={"model_id": "tiny-model", "dataset_id": "tiny-dataset"})
        )
    )

    assert proposal.proposal_id == "proposal-1"
    assert proposal.status == "warning"
    assert proposal.required_vram_gb == 4.5
    assert proposal.blockers == []
    assert proposal.warnings == ["Dataset is very small"]
    assert calls == {"validator": 1, "estimate": 1, "submit": 0}
    assert list(tmp_path.rglob("train_*")) == []


def test_proposal_is_blocked_when_resolution_or_validation_fails(tmp_path, monkeypatch):
    import agent_training.service as service_module

    settings = _Settings(tmp_path / "models", tmp_path / "datasets")

    async def fake_validate(*_):
        return ValidationResult(errors=["Configuration is invalid"])

    monkeypatch.setattr(service_module.TrainingValidator, "validate_config", fake_validate)
    monkeypatch.setattr(service_module, "resolve_dataset_file", lambda *_: None)
    monkeypatch.setattr(service_module, "estimate_preflight_required_vram", lambda _: 2.0)

    proposal = asyncio.run(
        AgentTrainingService(settings=settings, proposal_id_factory=lambda: "proposal-2").create_proposal(
            TrainingProposalRequest(config={"model_id": "missing-model", "dataset_id": "missing-dataset"})
        )
    )

    assert proposal.status == "blocked"
    assert proposal.blockers == [
        "Model not found: missing-model",
        "Dataset file not found: missing-dataset",
        "Configuration is invalid",
    ]
