"""DTO contracts for the agent-facing training foundation."""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent_training.models import (
    ApprovedTrainingAction,
    TrainingProposal,
    TrainingProposalRequest,
    TrainingSubmission,
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
