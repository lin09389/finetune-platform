"""Session-scoped, approval-gated adapters for agent training tools."""

from __future__ import annotations

import asyncio
import json
import shutil
import uuid
from pathlib import Path

import pytest

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


pytestmark = pytest.mark.skip(
    reason="Legacy Agent training tools are disabled while Train/Hybrid migrate to the Native Agent Loop.",
)


class _Repository:
    def __init__(self):
        self.session = {"id": "session-train", "metadata": {"task_mode": "train"}}
        self.training_links = []

    def get_session(self, session_id):
        assert session_id == "session-train"
        return self.session

    def update_session(self, session_id, *, metadata):
        assert session_id == "session-train"
        self.session = {**self.session, "metadata": metadata}
        return self.session

    def create_training_link(self, **link):
        self.training_links.append(link)
        return link


class _TrainingService:
    def __init__(self):
        self.submissions = []
        self.resumes = []
        self.cancels = []
        self.propose_scopes = []
        self.submit_scopes = []
        self.fail_submit_once = False

    async def propose_training(self, request, **scope):
        assert request.config.model_id == "tiny-model"
        self.propose_scopes.append(scope)
        return TrainingProposal(
            proposal_id="proposal-1",
            config=request.config,
            status="ready",
            owner_id=scope.get("owner_id"),
            session_id=scope.get("session_id"),
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

    def submit_training(self, action, **scope):
        self.submit_scopes.append(scope)
        if self.fail_submit_once:
            self.fail_submit_once = False
            raise RuntimeError("orchestrator unavailable")
        self.submissions.append(action)
        return TrainingSubmission(proposal_id=action.proposal_id, task_id="task-1", status="queued")

    def resume_training(self, *, task_id, checkpoint_name, **scope):
        self.resumes.append({"task_id": task_id, "checkpoint_name": checkpoint_name, **scope})
        from agent_training.models import TrainingResumeResult

        return TrainingResumeResult(
            source_task_id=task_id,
            checkpoint_name=checkpoint_name,
            task_id="task-resume-1",
            status="queued",
        )

    def cancel_training(self, *, task_id, **scope):
        self.cancels.append({"task_id": task_id, **scope})
        from agent_training.models import TrainingCancelResult

        return TrainingCancelResult(task_id=task_id, status="stopping", message="Cancellation requested")


class _FailingLinkRepository(_Repository):
    def create_training_link(self, **link):
        raise RuntimeError("agent link store unavailable")


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
    assert [tool.name for tool in tools] == [
        "propose_training",
        "submit_training",
        "resume_training",
        "cancel_training",
        "get_training_summary",
    ]

    proposal = json.loads(
        asyncio.run(
            tools[0].ainvoke({"training_config": {"model_id": "tiny-model", "dataset_id": "tiny-dataset"}})
        )
    )
    summary = json.loads(asyncio.run(tools[4].ainvoke({"task_id": "task-1"})))

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
        "phase": None,
        "step": None,
        "total_steps": None,
        "epoch": None,
        "loss": None,
        "eta": None,
        "updated_at": None,
        "artifact_available": None,
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
    assert repository.training_links == [{"session_id": "session-train", "owner_id": None, "proposal_id": "proposal-1", "task_id": "task-1"}]
    assert consume_training_submission_grant(repository, "session-train", "proposal-1") is False


def test_submission_reports_live_sync_degraded_after_training_side_effect_succeeds():
    repository = _FailingLinkRepository()
    service = _TrainingService()
    submit = build_training_tools(_session(), repository=repository, training_service=service)[1]
    grant_approved_training_submissions(
        repository,
        {"session_id": "session-train", "id": "permission-1", "payload": {"official_hitl": True, "action_requests": [{"name": "submit_training", "args": {"proposal_id": "proposal-1"}}]}},
        [{"type": "approve"}],
    )

    result = json.loads(asyncio.run(submit.ainvoke({"proposal_id": "proposal-1"})))

    assert result == {
        "proposal_id": "proposal-1",
        "task_id": "task-1",
        "status": "queued",
        "sync_status": "degraded",
        "sync_message": "Training started, but live progress is temporarily unavailable.",
    }
    assert [action.proposal_id for action in service.submissions] == ["proposal-1"]


def test_tools_forward_owner_and_session_scope_to_the_training_service():
    repository = _Repository()
    service = _TrainingService()
    session = {
        "id": "session-train",
        "agent_id": "build",
        "metadata": {"task_mode": "train", "user_id": "alice"},
    }
    tools = {tool.name: tool for tool in build_training_tools(session, repository=repository, training_service=service)}
    propose, submit = tools["propose_training"], tools["submit_training"]

    asyncio.run(propose.ainvoke({"training_config": {"model_id": "tiny-model", "dataset_id": "tiny-dataset"}}))
    grant_approved_training_submissions(
        repository,
        {
            "session_id": "session-train",
            "id": "permission-1",
            "payload": {
                "official_hitl": True,
                "action_requests": [{"name": "submit_training", "args": {"proposal_id": "proposal-1"}}],
            },
        },
        [{"type": "approve"}],
    )
    asyncio.run(submit.ainvoke({"proposal_id": "proposal-1"}))

    assert service.propose_scopes == [{"owner_id": "alice", "session_id": "session-train"}]
    assert service.submit_scopes == [{"owner_id": "alice", "session_id": "session-train"}]
    assert repository.training_links[0]["owner_id"] == "alice"


def test_failed_submission_restores_the_one_time_grant_for_retry():
    repository = _Repository()
    service = _TrainingService()
    service.fail_submit_once = True
    submit = build_training_tools(_session(), repository=repository, training_service=service)[1]
    grant_approved_training_submissions(
        repository,
        {
            "session_id": "session-train",
            "id": "permission-1",
            "payload": {
                "official_hitl": True,
                "action_requests": [{"name": "submit_training", "args": {"proposal_id": "proposal-1"}}],
            },
        },
        [{"type": "approve"}],
    )

    failed = json.loads(asyncio.run(submit.ainvoke({"proposal_id": "proposal-1"})))
    assert failed["status"] == "failed"
    assert service.submissions == []

    # Grant was restored; the next attempt can succeed without re-approval.
    approved = json.loads(asyncio.run(submit.ainvoke({"proposal_id": "proposal-1"})))
    assert approved == {"proposal_id": "proposal-1", "task_id": "task-1", "status": "queued"}


def test_summary_is_denied_when_the_training_link_belongs_to_another_session():
    class _LinkedRepository(_Repository):
        def get_training_link(self, task_id):
            assert task_id == "task-1"
            return {
                "task_id": "task-1",
                "session_id": "session-other",
                "owner_id": "bob",
                "proposal_id": "proposal-1",
            }

    service = _TrainingService()
    tools = {tool.name: tool for tool in build_training_tools(_session(), repository=_LinkedRepository(), training_service=service)}
    denied = json.loads(asyncio.run(tools["get_training_summary"].ainvoke({"task_id": "task-1"})))

    assert denied["status"] == "failed"
    assert denied["code"] == "training_run_forbidden"


def test_summary_is_allowed_for_the_session_that_owns_the_training_link():
    class _LinkedRepository(_Repository):
        def get_training_link(self, task_id):
            return {
                "task_id": "task-1",
                "session_id": "session-train",
                "owner_id": None,
                "proposal_id": "proposal-1",
            }

    service = _TrainingService()
    tools = {tool.name: tool for tool in build_training_tools(_session(), repository=_LinkedRepository(), training_service=service)}
    result = json.loads(asyncio.run(tools["get_training_summary"].ainvoke({"task_id": "task-1"})))

    assert result["task_id"] == "task-1"
    assert result["status"] == "completed"


def test_successful_training_tool_results_reconstruct_strict_timeline_activities():
    repository = _Repository()
    service = _TrainingService()
    tools = {tool.name: tool for tool in build_training_tools(_session(), repository=repository, training_service=service)}
    propose, submit, summary = tools["propose_training"], tools["submit_training"], tools["get_training_summary"]

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


def test_approved_submission_creates_one_persisted_link_and_stable_training_card(tmp_path):
    from agent_session.repository import AgentSessionRepository

    repository = AgentSessionRepository(str(tmp_path / "agents.db"))
    session = repository.create_session(
        {"id": "session-train", "agent_id": "build", "status": "idle", "title": "train", "metadata": {"user_id": "alice", "task_mode": "train"}}
    )
    submit = build_training_tools(session, repository=repository, training_service=_TrainingService())[1]

    for permission_id in ("permission-1", "permission-2"):
        grant_approved_training_submissions(
            repository,
            {"session_id": "session-train", "id": permission_id, "payload": {"official_hitl": True, "action_requests": [{"name": "submit_training", "args": {"proposal_id": "proposal-1"}}]}},
            [{"type": "approve"}],
        )
        assert json.loads(asyncio.run(submit.ainvoke({"proposal_id": "proposal-1"}))) ["status"] == "queued"

    link = repository.get_training_link("task-1")
    assert link is not None
    assert len(repository.list_parts("session-train")) == 1
    assert repository.get_part(link["part_id"])["payload"]["training_activity"]["kind"] == "submission"


def test_resume_and_cancel_require_one_time_official_approval_grants():
    repository = _Repository()
    service = _TrainingService()
    tools = {tool.name: tool for tool in build_training_tools(_session(), repository=repository, training_service=service)}

    denied_resume = json.loads(
        asyncio.run(tools["resume_training"].ainvoke({"task_id": "task-1", "checkpoint_name": "checkpoint-10"}))
    )
    assert denied_resume["status"] == "failed"
    assert service.resumes == []

    grant_approved_training_submissions(
        repository,
        {
            "session_id": "session-train",
            "id": "permission-resume",
            "payload": {
                "official_hitl": True,
                "action_requests": [
                    {"name": "resume_training", "args": {"task_id": "task-1", "checkpoint_name": "checkpoint-10"}}
                ],
            },
        },
        [{"type": "approve"}],
    )
    resumed = json.loads(
        asyncio.run(tools["resume_training"].ainvoke({"task_id": "task-1", "checkpoint_name": "checkpoint-10"}))
    )
    assert resumed["task_id"] == "task-resume-1"
    assert resumed["source_task_id"] == "task-1"
    assert resumed["checkpoint_name"] == "checkpoint-10"
    assert service.resumes[0]["task_id"] == "task-1"
    assert any(link["task_id"] == "task-resume-1" for link in repository.training_links)

    denied_cancel = json.loads(asyncio.run(tools["cancel_training"].ainvoke({"task_id": "task-1"})))
    assert denied_cancel["status"] == "failed"
    assert service.cancels == []

    grant_approved_training_submissions(
        repository,
        {
            "session_id": "session-train",
            "id": "permission-cancel",
            "payload": {
                "official_hitl": True,
                "action_requests": [{"name": "cancel_training", "args": {"task_id": "task-1"}}],
            },
        },
        [{"type": "approve"}],
    )
    cancelled = json.loads(asyncio.run(tools["cancel_training"].ainvoke({"task_id": "task-1"})))
    assert cancelled["status"] == "stopping"
    assert service.cancels[0]["task_id"] == "task-1"


def test_build_manifest_does_not_list_training_tools():
    from pathlib import Path
    import yaml

    manifest = yaml.safe_load(
        (Path(__file__).resolve().parents[1] / "agent_session" / "agents" / "build.agent.yaml").read_text(
            encoding="utf-8"
        )
    )
    allowed = set(manifest.get("Tools", {}).get("allowed") or [])
    assert not {
        "propose_training",
        "submit_training",
        "resume_training",
        "cancel_training",
        "get_training_summary",
    } & allowed


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
