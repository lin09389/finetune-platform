"""Session-scoped, approval-gated adapters for agent training tools."""

from __future__ import annotations

import asyncio
import json
import shutil
import uuid
from pathlib import Path

from agent_session.training_tools import (
    build_training_tools,
    consume_training_submission_grant,
    grant_approved_training_submissions,
    training_tools_enabled_for_session,
)
from agent_training.models import (
    TrainingProposal,
    TrainingRunSummary,
    TrainingSubmission,
    training_activity_from_tool_result,
)


class _Repository:
    def __init__(self):
        self.session = {"id": "session-train", "metadata": {"task_mode": "train"}}

    def get_session(self, session_id):
        assert session_id == "session-train"
        return self.session

    def update_session(self, session_id, *, metadata):
        assert session_id == "session-train"
        self.session = {**self.session, "metadata": metadata}
        return self.session


class _TrainingService:
    def __init__(self):
        self.submissions = []

    async def propose_training(self, request):
        assert request.config.model_id == "tiny-model"
        return TrainingProposal(
            proposal_id="proposal-1",
            config=request.config,
            status="ready",
            warnings=["Output would be C:\\private\\output"],
        )

    def get_training_run_summary(self, task_id):
        assert task_id == "task-1"
        return TrainingRunSummary(
            task_id=task_id,
            status="completed",
            model_id="tiny-model",
            dataset_id="tiny-dataset",
            method="qlora",
            task_goal="qa_assistant",
            started_at="2026-07-10T00:00:00",
            completed_at="2026-07-10T00:01:00",
            output_path="C:\\private\\output",
            adapter_path="C:\\private\\adapter",
            checkpoint_path="C:\\private\\checkpoint",
        )

    def submit_training(self, action):
        self.submissions.append(action)
        return TrainingSubmission(proposal_id=action.proposal_id, task_id="task-1", status="queued")


def _session(*, agent_id="build", task_mode="train"):
    return {"id": "session-train", "agent_id": agent_id, "metadata": {"task_mode": task_mode}}


def test_training_tools_are_limited_to_train_or_hybrid_build_sessions():
    assert training_tools_enabled_for_session(_session(task_mode="train")) is True
    assert training_tools_enabled_for_session(_session(task_mode="hybrid")) is True
    assert training_tools_enabled_for_session(_session(task_mode="build")) is False
    assert training_tools_enabled_for_session(_session(agent_id="explore", task_mode="train")) is False
    assert training_tools_enabled_for_session(_session(agent_id="review", task_mode="hybrid")) is False


def test_proposal_and_summary_tools_are_read_only_and_never_expose_absolute_paths():
    service = _TrainingService()
    tools = build_training_tools(_session(), repository=_Repository(), training_service=service)
    assert [tool.name for tool in tools] == ["propose_training", "submit_training", "get_training_summary"]

    proposal = json.loads(
        asyncio.run(
            tools[0].ainvoke({"training_config": {"model_id": "tiny-model", "dataset_id": "tiny-dataset"}})
        )
    )
    summary = json.loads(asyncio.run(tools[2].ainvoke({"task_id": "task-1"})))

    assert proposal["proposal_id"] == "proposal-1"
    assert proposal["model_id"] == "tiny-model"
    assert proposal["dataset_id"] == "tiny-dataset"
    assert proposal["warnings"] == ["Output would be [redacted path]"]
    assert summary == {
        "task_id": "task-1",
        "status": "completed",
        "model_id": "tiny-model",
        "dataset_id": "tiny-dataset",
        "method": "qlora",
        "task_goal": "qa_assistant",
        "started_at": "2026-07-10T00:00:00",
        "completed_at": "2026-07-10T00:01:00",
        "final_loss": None,
        "elapsed_time": None,
    }
    assert "private" not in json.dumps({"proposal": proposal, "summary": summary})


def test_submission_requires_a_one_time_official_approval_grant():
    repository = _Repository()
    service = _TrainingService()
    submit = build_training_tools(_session(), repository=repository, training_service=service)[1]

    denied = json.loads(asyncio.run(submit.ainvoke({"proposal_id": "proposal-1"})))
    assert denied["status"] == "failed"
    assert service.submissions == []

    grant_approved_training_submissions(
        repository,
        {"session_id": "session-train", "id": "permission-rejected", "payload": {"official_hitl": True, "action_requests": [{"name": "submit_training", "args": {"proposal_id": "proposal-1"}}]}},
        [{"type": "reject"}],
    )
    rejected = json.loads(asyncio.run(submit.ainvoke({"proposal_id": "proposal-1"})))
    assert rejected["status"] == "failed"
    assert service.submissions == []

    grant_approved_training_submissions(
        repository,
        {"session_id": "session-train", "id": "permission-1", "payload": {"official_hitl": True, "action_requests": [{"name": "submit_training", "args": {"proposal_id": "proposal-1"}}]}},
        [{"type": "approve"}],
    )
    assert consume_training_submission_grant(repository, "session-train", "proposal-1") is True

    grant_approved_training_submissions(
        repository,
        {"session_id": "session-train", "id": "permission-2", "payload": {"official_hitl": True, "action_requests": [{"name": "submit_training", "args": {"proposal_id": "proposal-1"}}]}},
        [{"type": "approve"}],
    )
    approved = json.loads(asyncio.run(submit.ainvoke({"proposal_id": "proposal-1"})))

    assert approved == {"proposal_id": "proposal-1", "task_id": "task-1", "status": "queued"}
    assert [action.model_dump() for action in service.submissions] == [{"proposal_id": "proposal-1", "approved": True}]
    assert consume_training_submission_grant(repository, "session-train", "proposal-1") is False


def test_successful_training_tool_results_reconstruct_strict_timeline_activities():
    repository = _Repository()
    service = _TrainingService()
    propose, submit, summary = build_training_tools(_session(), repository=repository, training_service=service)

    proposal_result = json.loads(
        asyncio.run(propose.ainvoke({"training_config": {"model_id": "tiny-model", "dataset_id": "tiny-dataset"}}))
    )
    grant_approved_training_submissions(
        repository,
        {"session_id": "session-train", "id": "permission-1", "payload": {"official_hitl": True, "action_requests": [{"name": "submit_training", "args": {"proposal_id": "proposal-1"}}]}},
        [{"type": "approve"}],
    )
    submission_result = json.loads(asyncio.run(submit.ainvoke({"proposal_id": "proposal-1"})))
    summary_result = json.loads(asyncio.run(summary.ainvoke({"task_id": "task-1"})))

    assert training_activity_from_tool_result("propose_training", proposal_result).model_dump()["kind"] == "proposal"
    assert training_activity_from_tool_result("submit_training", submission_result).model_dump()["kind"] == "submission"
    assert training_activity_from_tool_result("get_training_summary", summary_result).model_dump()["kind"] == "run_summary"


def test_submit_training_waits_for_official_hitl_then_submits_once(tmp_path):
    from agent_session.models import AgentPromptRequest, AgentSessionCreate
    from agent_session.repository import AgentSessionRepository
    from agent_session.service import AgentSessionService

    training_service = _TrainingService()
    responses = iter([
        json.dumps({"tool": "submit_training", "arguments": {"proposal_id": "proposal-1"}}),
        json.dumps({"type": "final", "content": "训练任务已提交。"}),
    ])

    async def model_call(_messages):
        return next(responses)

    workspace = Path.cwd() / "tmp" / f"agent-training-hitl-{uuid.uuid4().hex[:8]}"
    workspace.mkdir(parents=True)
    try:
        service = AgentSessionService(AgentSessionRepository(str(tmp_path / "agents.db")), model_call=model_call)
        service.deepagents_runner.training_service = training_service
        session = service.create_session(
            AgentSessionCreate(title="submit training", project_path=str(workspace), task_mode="train")
        )

        waiting = asyncio.run(service.prompt(session.id, AgentPromptRequest(content="提交 proposal-1")))
        permission = next(part for part in waiting.parts if part.type == "permission" and part.status == "pending")

        assert waiting.status == "waiting_approval"
        assert permission.payload["actions"][0]["name"] == "submit_training"
        assert permission.payload["actions"][0]["allowed_decisions"] == ["approve", "reject"]
        assert training_service.submissions == []

        _, decision = service.approval_service._record_permission_decision(permission.id, [{"type": "approve"}])
        completed = asyncio.run(service.deepagents_runner.resume(session.id, decision))

        assert completed["status"] == "completed"
        assert [action.model_dump() for action in training_service.submissions] == [
            {"proposal_id": "proposal-1", "approved": True}
        ]
    finally:
        shutil.rmtree(workspace, ignore_errors=True)
