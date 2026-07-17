from __future__ import annotations

import pytest

from agent_session.repository import AgentSessionRepository
from agent_session.service import AgentSessionService
from agent_session.task_modes import AgentCapabilityMigratingError
from agent_session.training_tools import (
    build_training_tools,
    grant_approved_training_actions,
    training_tools_enabled_for_session,
)


class _TrainingService:
    pass


@pytest.mark.parametrize("task_mode", ["build", "train", "hybrid"])
def test_all_agent_task_modes_hide_legacy_training_tools(task_mode: str):
    session = {"id": f"session-{task_mode}", "agent_id": "build", "metadata": {"task_mode": task_mode}}

    assert training_tools_enabled_for_session(session) is False
    assert build_training_tools(session, repository=object(), training_service=_TrainingService()) == []


@pytest.mark.parametrize("task_mode", ["train", "hybrid"])
def test_direct_agent_training_grant_and_permission_service_cannot_bypass_migration(tmp_path, task_mode: str):
    repository = AgentSessionRepository(str(tmp_path / "agents.db"))
    service = AgentSessionService(repository)
    session = repository.create_session(
        {
            "agent_id": "build",
            "title": "migrating Agent training",
            "project_path": str(tmp_path),
            "metadata": {"task_mode": task_mode},
        }
    )
    permission = repository.add_part(
        session["id"],
        "permission",
        status="pending",
        title="training approval",
        payload={
            "official_hitl": True,
            "action_requests": [{"name": "submit_training", "args": {"proposal_id": "proposal-1"}}],
        },
    )

    grant_approved_training_actions(
        repository,
        permission,
        [{"type": "approve"}],
    )
    assert "approved_training_submissions" not in repository.get_session(session["id"])["metadata"]

    with pytest.raises(AgentCapabilityMigratingError):
        service.start_permission_resume_background(permission["id"], [{"type": "approve"}], background_tasks=object())

    assert repository.get_part(permission["id"])["status"] == "pending"
