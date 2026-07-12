"""Real-component integration path for Agent training tools.

Unlike golden-path fixture guards and pure Fake adapters, this suite wires:

- ``AgentSessionRepository`` (SQLite)
- ``AgentTrainingService`` + ``TrainingProposalStore`` (SQLite)
- production ``build_training_tools``
- ``DeepAgentsEventMapper`` part projection

Only the GPU/orchestrator edge is stubbed (``start_training_task`` /
``find_training_record`` / catalog preflight), so the event-loop submission
path, HITL grant, claim, link, and summary isolation stay real.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent_session.deepagents_events import DeepAgentsEventMapper
from agent_session.repository import AgentSessionRepository
from agent_session.training_tools import (
    build_training_tools,
    grant_approved_training_submissions,
)
from agent_training.models import training_activity_from_tool_result
from agent_training.service import AgentTrainingService
from agent_training.store import TrainingProposalStore
from core.training_state import TrainingRecord


class _Settings:
    training_execution_mode = "worker"

    def __init__(self, base_dir):
        self.base_dir = base_dir
        self.models_dir_resolved = base_dir / "models"
        self.datasets_dir_resolved = base_dir / "datasets"


def _seed_catalog(settings: _Settings) -> tuple:
    model_path = settings.models_dir_resolved / "tiny-model"
    dataset_file = settings.datasets_dir_resolved / "tiny-dataset" / "data.jsonl"
    model_path.mkdir(parents=True)
    dataset_file.parent.mkdir(parents=True)
    dataset_file.write_text('{"text":"sample"}\n', encoding="utf-8")
    return model_path, dataset_file


def _create_session(repository: AgentSessionRepository, *, session_id: str, owner_id: str) -> dict:
    return repository.create_session(
        {
            "id": session_id,
            "agent_id": "build",
            "status": "idle",
            "title": "integration train",
            "metadata": {
                "user_id": owner_id,
                "task_mode": "train",
            },
        }
    )


def _tools(session: dict, repository: AgentSessionRepository, service: AgentTrainingService):
    return {tool.name: tool for tool in build_training_tools(session, repository=repository, training_service=service)}


def _permission(session_id: str, proposal_id: str, part_id: str = "permission-1") -> dict:
    return {
        "id": part_id,
        "session_id": session_id,
        "payload": {
            "official_hitl": True,
            "action_requests": [
                {"name": "submit_training", "args": {"proposal_id": proposal_id}},
            ],
        },
    }


@pytest.fixture
def integration_env(tmp_path, monkeypatch):
    import agent_training.service as service_module

    base = tmp_path / "runtime"
    base.mkdir()
    settings = _Settings(base)
    model_path, dataset_file = _seed_catalog(settings)

    store = TrainingProposalStore(db_path=base / "agent_training_proposals.sqlite3")
    service = AgentTrainingService(
        settings=settings,
        proposal_store=store,
        proposal_id_factory=lambda: "proposal-integration-001",
    )
    repository = AgentSessionRepository(str(tmp_path / "agents.db"))
    session = _create_session(repository, session_id="session-integration", owner_id="alice")

    orchestrator_calls: list[dict] = []

    def fake_resolve(received_settings, dataset_id):
        assert dataset_id == "tiny-dataset"
        return dataset_file

    def fake_submit(**kwargs):
        assert kwargs["model_path"] == model_path
        assert kwargs["dataset_file"] == dataset_file
        orchestrator_calls.append(kwargs)
        return SimpleNamespace(id="task-integration-001", status="queued")

    async def valid_preflight(*_args):
        return SimpleNamespace(errors=[], warnings=[])

    record = TrainingRecord(
        id="task-integration-001",
        model_name="tiny-model",
        dataset_name="tiny-dataset",
        base_model_id="tiny-model",
        dataset_id="tiny-dataset",
        task_goal="qa_assistant",
        method="qlora",
        status="completed",
        start_time="2026-07-11T10:00:00",
        end_time="2026-07-11T10:02:00",
        config={},
        output_path=str(base / "outputs" / "train_task-integration-001"),
        adapter_path=str(base / "outputs" / "train_task-integration-001" / "adapter"),
        checkpoint_path=str(base / "outputs" / "train_task-integration-001" / "checkpoint-1"),
        final_loss=0.42,
        elapsed_time=120.0,
    )

    monkeypatch.setattr(service_module, "resolve_dataset_file", fake_resolve)
    monkeypatch.setattr(service_module, "start_training_task", fake_submit)
    monkeypatch.setattr(service_module.TrainingValidator, "validate_config", valid_preflight)
    monkeypatch.setattr(service_module, "estimate_preflight_required_vram", lambda _config: 3.5)
    monkeypatch.setattr(
        service_module,
        "find_training_record",
        lambda task_id: record if task_id == "task-integration-001" else None,
    )

    return SimpleNamespace(
        service=service,
        repository=repository,
        session=session,
        tools=_tools(session, repository, service),
        orchestrator_calls=orchestrator_calls,
        model_path=model_path,
        dataset_file=dataset_file,
    )


def test_real_event_loop_path_propose_grant_submit_link_summary_and_isolation(integration_env):
    env = integration_env
    propose = env.tools["propose_training"]
    submit = env.tools["submit_training"]
    summary = env.tools["get_training_summary"]

    async def run_path():
        denied = json.loads(await submit.ainvoke({"proposal_id": "proposal-integration-001"}))
        assert denied["status"] == "failed"
        assert env.orchestrator_calls == []

        proposal = json.loads(
            await propose.ainvoke(
                {
                    "training_config": {
                        "model_id": "tiny-model",
                        "dataset_id": "tiny-dataset",
                        "method": "qlora",
                    }
                }
            )
        )
        assert proposal["proposal_id"] == "proposal-integration-001"
        assert proposal["status"] == "ready"
        assert proposal["model_id"] == "tiny-model"
        assert proposal["dataset_id"] == "tiny-dataset"
        assert "private" not in json.dumps(proposal)
        activity = training_activity_from_tool_result("propose_training", proposal)
        assert activity is not None and activity.kind == "proposal"

        stored = env.service._proposal_store.get("proposal-integration-001")
        assert stored is not None
        assert stored.owner_id == "alice"
        assert stored.session_id == "session-integration"

        grant_approved_training_submissions(
            env.repository,
            _permission("session-integration", "proposal-integration-001"),
            [{"type": "approve"}],
        )

        submission = json.loads(await submit.ainvoke({"proposal_id": "proposal-integration-001"}))
        assert submission == {
            "proposal_id": "proposal-integration-001",
            "task_id": "task-integration-001",
            "status": "queued",
        }
        assert len(env.orchestrator_calls) == 1
        assert training_activity_from_tool_result("submit_training", submission).kind == "submission"

        duplicate = json.loads(await submit.ainvoke({"proposal_id": "proposal-integration-001"}))
        assert duplicate["status"] == "failed"
        assert len(env.orchestrator_calls) == 1

        link = env.repository.get_training_link("task-integration-001")
        assert link is not None
        assert link["session_id"] == "session-integration"
        assert link["owner_id"] == "alice"
        assert link["proposal_id"] == "proposal-integration-001"
        part = env.repository.get_part(link["part_id"])
        assert part["payload"]["training_activity"]["kind"] == "submission"
        assert part["payload"]["training_activity"]["task_id"] == "task-integration-001"

        run_summary = json.loads(await summary.ainvoke({"task_id": "task-integration-001"}))
        assert run_summary["task_id"] == "task-integration-001"
        assert run_summary["status"] == "completed"
        assert run_summary["model_id"] == "tiny-model"
        assert run_summary["final_loss"] == 0.42
        assert "output_path" not in run_summary
        assert "adapter_path" not in run_summary
        assert "checkpoint_path" not in run_summary
        assert training_activity_from_tool_result("get_training_summary", run_summary).kind == "run_summary"

        other = _create_session(env.repository, session_id="session-other", owner_id="bob")
        other_tools = _tools(other, env.repository, env.service)
        forbidden = json.loads(
            await other_tools["get_training_summary"].ainvoke({"task_id": "task-integration-001"})
        )
        assert forbidden["status"] == "failed"
        assert forbidden["code"] == "training_run_forbidden"

        # Project the three successful tool outputs through the production event mapper.
        events: list[dict] = []
        mapper = DeepAgentsEventMapper(
            env.repository,
            lambda _session_id, event: events.append(event),
            "session-integration",
        )
        for run_id, name, payload in (
            ("propose-run", "propose_training", proposal),
            ("submit-run", "submit_training", submission),
            ("summary-run", "get_training_summary", run_summary),
        ):
            mapper.handle(
                {
                    "event": "on_tool_start",
                    "name": name,
                    "run_id": run_id,
                    "data": {"input": {"marker": run_id}},
                }
            )
            mapper.handle(
                {
                    "event": "on_tool_end",
                    "name": name,
                    "run_id": run_id,
                    "data": {"output": json.dumps(payload, ensure_ascii=False)},
                }
            )

        projected = [
            part
            for part in env.repository.list_parts("session-integration")
            if isinstance(part.get("payload"), dict)
            and "training_activity" in part["payload"]
            and part["payload"].get("run_id") in {"propose-run", "submit-run", "summary-run"}
        ]
        kinds = [part["payload"]["training_activity"]["kind"] for part in projected]
        assert kinds == ["proposal", "submission", "run_summary"]
        assert "private" not in json.dumps(projected)
        assert any(event.get("event_type") == "tool_call_completed" for event in events)
        assert any(
            isinstance(event.get("payload"), dict)
            and isinstance(event["payload"].get("part"), dict)
            and "training_activity" in (event["payload"]["part"].get("payload") or {})
            for event in events
            if event.get("event_type") == "tool_call_completed"
        )

    asyncio.run(run_path())


def test_real_service_submit_failure_on_loop_restores_grant_and_does_not_start_task(integration_env, monkeypatch):
    import agent_training.service as service_module

    env = integration_env
    propose = env.tools["propose_training"]
    submit = env.tools["submit_training"]

    async def run_path():
        proposal = json.loads(
            await propose.ainvoke(
                {"training_config": {"model_id": "tiny-model", "dataset_id": "tiny-dataset"}}
            )
        )
        grant_approved_training_submissions(
            env.repository,
            _permission("session-integration", proposal["proposal_id"], part_id="permission-fail"),
            [{"type": "approve"}],
        )

        monkeypatch.setattr(
            service_module,
            "start_training_task",
            lambda **_: (_ for _ in ()).throw(RuntimeError("worker offline")),
        )

        failed = json.loads(await submit.ainvoke({"proposal_id": proposal["proposal_id"]}))
        assert failed["status"] == "failed"
        assert env.orchestrator_calls == []
        assert env.repository.get_training_link("task-integration-001") is None

        # Grant restored; claim released — a healthy orchestrator can still submit once.
        monkeypatch.setattr(
            service_module,
            "start_training_task",
            lambda **kwargs: env.orchestrator_calls.append(kwargs)
            or SimpleNamespace(id="task-integration-001", status="queued"),
        )
        recovered = json.loads(await submit.ainvoke({"proposal_id": proposal["proposal_id"]}))
        assert recovered["task_id"] == "task-integration-001"
        assert recovered["status"] == "queued"
        assert len(env.orchestrator_calls) == 1

    asyncio.run(run_path())


def test_real_sqlite_proposal_store_survives_service_recreation(tmp_path, monkeypatch):
    """Approvals must not disappear when a new API process opens the same store."""
    import agent_training.service as service_module
    from agent_training.models import ApprovedTrainingAction, TrainingProposalRequest

    base = tmp_path / "shared"
    base.mkdir()
    settings = _Settings(base)
    _seed_catalog(settings)
    db_path = base / "agent_training_proposals.sqlite3"

    async def valid_preflight(*_args):
        return SimpleNamespace(errors=[], warnings=[])

    monkeypatch.setattr(service_module.TrainingValidator, "validate_config", valid_preflight)
    monkeypatch.setattr(service_module, "estimate_preflight_required_vram", lambda _config: 1.0)
    monkeypatch.setattr(
        service_module,
        "resolve_dataset_file",
        lambda _settings, _dataset_id: settings.datasets_dir_resolved / "tiny-dataset" / "data.jsonl",
    )

    first = AgentTrainingService(
        settings=settings,
        proposal_store=TrainingProposalStore(db_path=db_path),
        proposal_id_factory=lambda: "proposal-shared-001",
    )
    proposal = asyncio.run(
        first.propose_training(
            TrainingProposalRequest(config={"model_id": "tiny-model", "dataset_id": "tiny-dataset"}),
            owner_id="alice",
            session_id="session-a",
        )
    )
    assert proposal.status == "ready"

    second = AgentTrainingService(
        settings=settings,
        proposal_store=TrainingProposalStore(db_path=db_path),
    )
    restored = second._proposal_store.get("proposal-shared-001")
    assert restored is not None
    assert restored.owner_id == "alice"
    assert restored.session_id == "session-a"

    monkeypatch.setattr(
        service_module,
        "start_training_task",
        lambda **_: SimpleNamespace(id="task-shared-001", status="queued"),
    )
    submission = second.submit_training(
        ApprovedTrainingAction(proposal_id="proposal-shared-001", approved=True),
        owner_id="alice",
        session_id="session-a",
    )
    assert submission.task_id == "task-shared-001"
    assert second._proposal_store.claim_submission("proposal-shared-001") is False
