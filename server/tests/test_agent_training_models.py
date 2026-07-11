"""DTO contracts for the agent-facing training foundation."""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent_training.models import (
    ApprovedTrainingAction,
    TrainingProposal,
    TrainingProposalRequest,
    TrainingRunSummary,
    TrainingSubmission,
    training_activity_for,
)


def test_agent_training_dtos_preserve_the_training_config_and_approval_boundary():
    request = TrainingProposalRequest(
        config={"model_id": "tiny-model", "dataset_id": "tiny-dataset"},
        use_queue=True,
        priority="high",
    )

    proposal = TrainingProposal(
        proposal_id="proposal-1",
        config=request.config,
        status="warning",
        blockers=[],
        warnings=["VRAM headroom is limited"],
        suggestions=["Use QLoRA"],
        required_vram_gb=6.5,
    )
    action = ApprovedTrainingAction(proposal_id=proposal.proposal_id, approved=True)
    submission = TrainingSubmission(
        proposal_id=proposal.proposal_id,
        task_id="task-1",
        status="queued",
    )

    assert request.config.model_id == "tiny-model"
    assert proposal.config.dataset_id == "tiny-dataset"
    assert proposal.required_vram_gb == 6.5
    assert action.approved is True
    assert submission.model_dump() == {
        "proposal_id": "proposal-1",
        "task_id": "task-1",
        "status": "queued",
    }


@pytest.mark.parametrize("field", ["model_id", "dataset_id"])
def test_training_catalog_ids_reject_paths(field: str):
    with pytest.raises(ValueError, match="不能包含路径"):
        TrainingProposalRequest(config={
            "model_id": "tiny-model",
            "dataset_id": "tiny-dataset",
            field: "../outside",
        })


def test_training_activity_projection_has_stable_ids_and_uses_only_safe_display_fields():
    proposal = TrainingProposal(
        proposal_id="proposal-1",
        config={"model_id": "tiny-model", "dataset_id": "tiny-dataset", "method": "qlora"},
        status="warning",
        warnings=["Output at C:\\private\\output"],
        suggestions=["Set TOKEN=super-secret before retrying"],
    )
    submission = TrainingSubmission(proposal_id="proposal-1", task_id="task-1", status="queued")
    run = TrainingRunSummary(
        task_id="task-1",
        status="completed",
        model_id="tiny-model",
        dataset_id="tiny-dataset",
        method="qlora",
        task_goal="qa assistant",
        started_at="2026-07-11T00:00:00Z",
        completed_at="2026-07-11T00:01:00Z",
        output_path="C:\\private\\output",
        adapter_path="C:\\private\\adapter",
        checkpoint_path="C:\\private\\checkpoint",
    )

    proposal_activity = training_activity_for(proposal)
    submission_activity = training_activity_for(submission)
    run_activity = training_activity_for(run)

    assert proposal_activity.model_dump() == {
        "kind": "proposal",
        "source_tool": "propose_training",
        "proposal_id": "proposal-1",
        "status": "warning",
        "summary": "Training proposal needs review.",
        "model_id": "tiny-model",
        "dataset_id": "tiny-dataset",
        "method": "qlora",
        "blockers": [],
        "warnings": ["Output at [redacted path]"],
        "suggestions": ["Set TOKEN=[redacted secret] before retrying"],
        "required_vram_gb": None,
    }
    assert submission_activity.model_dump() == {
        "kind": "submission",
        "source_tool": "submit_training",
        "proposal_id": "proposal-1",
        "task_id": "task-1",
        "status": "queued",
        "summary": "Training task queued.",
    }
    assert run_activity.model_dump() == {
        "kind": "run_summary",
        "source_tool": "get_training_summary",
        "task_id": "task-1",
        "status": "completed",
        "summary": "Training run completed.",
        "model_id": "tiny-model",
        "dataset_id": "tiny-dataset",
        "method": "qlora",
        "task_goal": "qa assistant",
        "started_at": "2026-07-11T00:00:00Z",
        "completed_at": "2026-07-11T00:01:00Z",
        "final_loss": None,
        "elapsed_time": None,
        "phase": None,
        "step": None,
        "total_steps": None,
        "epoch": None,
        "loss": None,
        "eta": None,
        "updated_at": None,
        "artifact_available": None,
    }
    assert "private" not in str([proposal_activity, submission_activity, run_activity])
    assert "super-secret" not in str([proposal_activity, submission_activity, run_activity])
