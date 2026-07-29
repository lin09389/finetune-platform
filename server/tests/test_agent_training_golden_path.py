"""CPU-only acceptance guard for the Agent training golden path."""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent_session.training_tools import (  # noqa: E402
    TRAINING_TOOL_NAMES,
    build_training_tools,
    grant_approved_training_submissions,
    training_tools_enabled_for_session,
)
from agent_training.models import (  # noqa: E402
    TrainingProposal,
    TrainingRunSummary,
    TrainingSubmission,
)

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "agent_training_golden_path.json"


class _Repository:
    def __init__(self, session: dict[str, object]):
        self.session = session
        self.training_links: list[dict[str, object]] = []

    def get_session(self, session_id: str):
        assert session_id == self.session["id"]
        return self.session

    def update_session(self, session_id: str, *, metadata: dict[str, object]):
        assert session_id == self.session["id"]
        self.session = {**self.session, "metadata": metadata}
        return self.session

    def create_training_link(self, **link):
        self.training_links.append(link)
        return link


class _TrainingService:
    def __init__(self):
        self.submissions: list[str] = []

    async def propose_training(self, request, **scope):
        return TrainingProposal(
            proposal_id="proposal-train-001",
            config=request.config,
            status="ready",
            owner_id=scope.get("owner_id"),
            session_id=scope.get("session_id"),
        )

    def submit_training(self, action, **scope):
        self.submissions.append(action.proposal_id)
        return TrainingSubmission(proposal_id=action.proposal_id, task_id="task-train-001", status="queued")

    def get_training_run_summary(self, task_id: str):
        return TrainingRunSummary(
            task_id=task_id,
            status="completed",
            model_id="tiny-model",
            dataset_id="tiny-dataset",
            method="qlora",
            task_goal="classify support requests",
            started_at="2026-07-11T09:00:00Z",
            completed_at="2026-07-11T09:02:00Z",
            output_path="/private/output",
        )


def _session(mode: str) -> dict[str, object]:
    return {"id": "session-golden-001", "agent_id": "build", "metadata": {"task_mode": mode}}


def _tools(session: dict[str, object], repository: _Repository, service: _TrainingService):
    return {tool.name: tool for tool in build_training_tools(session, repository=repository, training_service=service)}


def _scenario_map() -> dict[str, dict[str, object]]:
    fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    return {scenario["id"]: scenario for scenario in fixture["scenarios"]}


def test_golden_path_fixture_defines_all_required_scenarios_and_safe_timeline_contract():
    scenarios = _scenario_map()

    assert set(scenarios) == {
        "train-approval",
        "train-rejection",
        "duplicate-retry",
        "refresh-recovery",
        "hybrid-coexistence",
        "build-exclusion",
    }
    for scenario in scenarios.values():
        for item in scenario["timeline"]:
            activity = item.get("payload", {}).get("training_activity")
            if activity is None:
                continue
            assert activity["source_tool"] in TRAINING_TOOL_NAMES
            if activity["kind"] == "unknown":
                assert set(activity) == {"kind", "source_tool"}
                continue
            assert activity["kind"] in {"proposal", "submission", "run_summary"}
            assert "output_path" not in activity
            assert "adapter_path" not in activity
            assert "checkpoint_path" not in activity


def test_train_approval_rejection_and_duplicate_retry_submit_exactly_once():
    session = _session("train")
    repository = _Repository(session)
    service = _TrainingService()
    submit = _tools(session, repository, service)["submit_training"]

    denied = json.loads(asyncio.run(submit.ainvoke({"proposal_id": "proposal-train-001"})))
    assert denied["status"] == "failed"
    assert service.submissions == []

    permission = {
        "id": "permission-golden-001",
        "session_id": session["id"],
        "payload": {
            "official_hitl": True,
            "action_requests": [{"name": "submit_training", "args": {"proposal_id": "proposal-train-001"}}],
        },
    }
    grant_approved_training_submissions(repository, permission, [{"type": "reject"}])
    rejected = json.loads(asyncio.run(submit.ainvoke({"proposal_id": "proposal-train-001"})))
    assert rejected["status"] == "failed"
    assert service.submissions == []

    grant_approved_training_submissions(repository, permission, [{"type": "approve"}])
    approved = json.loads(asyncio.run(submit.ainvoke({"proposal_id": "proposal-train-001"})))
    retry = json.loads(asyncio.run(submit.ainvoke({"proposal_id": "proposal-train-001"})))

    assert approved == {"proposal_id": "proposal-train-001", "task_id": "task-train-001", "status": "queued"}
    assert retry["status"] == "failed"
    assert service.submissions == ["proposal-train-001"]


def test_refresh_recovery_keeps_the_same_session_scoped_training_identity():
    repository = _Repository(_session("train"))
    service = _TrainingService()
    before_refresh = _tools(repository.session, repository, service)
    after_refresh = _tools(dict(repository.session), repository, service)

    assert set(before_refresh) == set(after_refresh) == TRAINING_TOOL_NAMES
    assert repository.session["id"] == "session-golden-001"
    assert json.loads(asyncio.run(after_refresh["get_training_summary"].ainvoke({"task_id": "task-train-001"})))["task_id"] == "task-train-001"


def test_hybrid_coexists_with_the_training_toolset_while_build_is_excluded():
    hybrid = _session("hybrid")
    build = _session("build")

    assert training_tools_enabled_for_session(hybrid) is True
    assert set(_tools(hybrid, _Repository(hybrid), _TrainingService())) == TRAINING_TOOL_NAMES
    assert training_tools_enabled_for_session(build) is False
    assert build_training_tools(build, repository=_Repository(build), training_service=_TrainingService()) == []
