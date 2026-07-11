from __future__ import annotations

import json

from agent_session.deepagents_events import DeepAgentsEventMapper
from agent_session.execution_context import AgentDefinition
from agent_session.execution_plan import build_initial_execution_plan
from agent_session.runtime_policy import build_agent_runtime_policy


class FakeRepository:
    def __init__(self):
        self.parts = []
        self.events = []
        self.session = {"id": "session-1", "metadata": {}}

    def add_part(self, session_id, part_type, *, status, title, content, payload):
        part = {
            "id": f"part-{len(self.parts) + 1}",
            "session_id": session_id,
            "type": part_type,
            "status": status,
            "title": title,
            "content": content,
            "payload": payload,
        }
        self.parts.append(part)
        return part

    def add_event(self, session_id, event_type, message, payload):
        event = {"id": f"event-{len(self.events) + 1}", "session_id": session_id, "type": event_type, "message": message, "payload": payload}
        self.events.append(event)
        return event

    def update_part(self, part_id, **updates):
        part = next(part for part in self.parts if part["id"] == part_id)
        part.update(updates)
        return part

    def get_session(self, _session_id):
        return self.session

    def update_session(self, _session_id, **updates):
        self.session.update(updates)
        return self.session


def test_deepagents_event_mapper_wraps_string_tool_input():
    repo = FakeRepository()
    emitted = []
    mapper = DeepAgentsEventMapper(repo, lambda _session_id, event: emitted.append(event), "session-1")

    mapper.handle(
        {
            "event": "on_tool_start",
            "name": "ls",
            "run_id": "run-1",
            "data": {"input": "/"},
        }
    )

    assert repo.parts[0]["payload"]["input"] == {"input": "/"}
    assert emitted[0]["type"] == "tool_call_started"


def test_deepagents_event_mapper_tags_subagent_tool_parts():
    repo = FakeRepository()
    emitted = []
    mapper = DeepAgentsEventMapper(repo, lambda _session_id, event: emitted.append(event), "session-1")

    mapper.handle(
        {
            "event": "on_tool_start",
            "name": "grep",
            "run_id": "run-1",
            "metadata": {"lc_agent_name": "explore", "ls_agent_type": "subagent"},
            "data": {"input": {"pattern": "AgentSession"}},
        }
    )

    assert repo.parts[0]["payload"]["agent_name"] == "explore"
    assert repo.parts[0]["payload"]["agent_role"] == "subagent"
    assert emitted[0]["payload"]["agent_name"] == "explore"


def test_deepagents_event_mapper_updates_execution_plan_from_tool_event():
    repo = FakeRepository()
    agent = AgentDefinition(id="build", name="Build", mode="primary", tools=["read_file"])
    policy = build_agent_runtime_policy(
        agent=agent,
        agent_id="build",
        project_path=".",
        metadata={},
        runtime_kind="agent_session",
        thread_id="agent_session:session-1:deepagents",
        checkpointer=True,
    )
    repo.session["metadata"] = {
        "execution_plan": build_initial_execution_plan(
            session={"id": "session-1", "agent_id": "build", "status": "running"},
            policy=policy,
            goal="inspect",
            status="running",
        )
    }
    mapper = DeepAgentsEventMapper(repo, lambda *_args: None, "session-1")

    mapper.handle(
        {
            "event": "on_tool_start",
            "name": "read_file",
            "run_id": "run-1",
            "data": {"input": {"file_path": "/workspace/README.md"}},
        }
    )

    plan = repo.session["metadata"]["execution_plan"]
    node = next(item for item in plan["nodes"] if item.get("source_part_id") == "part-1")
    assert node["status"] == "running"
    assert node["tool"] == "read_file"


def test_deepagents_event_mapper_accepts_dict_interrupt_payload():
    repo = FakeRepository()
    mapper = DeepAgentsEventMapper(repo, lambda *_args: None, "session-1")
    repo.get_session = lambda _session_id: {"metadata": {"runtime": "deepagents"}}
    repo.update_session = lambda *_args, **_kwargs: None

    mapper.handle(
        {
            "event": "on_chain_stream",
            "data": {
                "chunk": {
                    "__interrupt__": [
                        {
                            "value": {
                                "action_requests": {
                                    "name": "read_file",
                                    "args": {"file_path": "/workspace/README.md"},
                                },
                                "review_configs": {
                                    "action_name": "read_file",
                                    "allowed_decisions": ["approve", "reject"],
                                },
                            }
                        }
                    ]
                }
            },
        }
    )

    assert repo.parts[0]["type"] == "permission"
    assert repo.parts[0]["payload"]["tool"] == "read_file"


def test_deepagents_event_mapper_preserves_batched_interrupt_actions():
    repo = FakeRepository()
    mapper = DeepAgentsEventMapper(repo, lambda *_args: None, "session-1")
    repo.get_session = lambda _session_id: {"metadata": {"runtime": "deepagents"}}
    repo.update_session = lambda *_args, **_kwargs: None

    mapper.handle(
        {
            "event": "on_chain_stream",
            "data": {
                "chunk": {
                    "__interrupt__": [
                        {
                            "value": {
                                "action_requests": [
                                    {"name": "edit_file", "args": {"file_path": "/workspace/a.py"}},
                                    {"name": "execute", "args": {"command": "pytest -q"}},
                                ],
                                "review_configs": [
                                    {"action_name": "edit_file", "allowed_decisions": ["approve", "edit", "reject"]},
                                    {"action_name": "execute", "allowed_decisions": ["approve", "reject", "respond"]},
                                ],
                            }
                        }
                    ]
                }
            },
        }
    )

    payload = repo.parts[0]["payload"]
    assert repo.parts[0]["type"] == "permission"
    assert payload["official_hitl"] is True
    assert len(payload["action_requests"]) == 2
    assert len(payload["actions"]) == 2
    assert payload["actions"][0]["allowed_decisions"] == ["approve", "edit", "reject"]
    assert payload["actions"][1]["allowed_decisions"] == ["approve", "reject", "respond"]


def test_deepagents_event_mapper_persists_safe_training_activity_on_existing_tool_parts():
    repo = FakeRepository()
    mapper = DeepAgentsEventMapper(repo, lambda *_args: None, "session-1")

    mapper.handle({"event": "on_tool_start", "name": "propose_training", "run_id": "proposal", "data": {"input": {}}})
    mapper.handle(
        {
            "event": "on_tool_end",
            "name": "propose_training",
            "run_id": "proposal",
            "data": {"output": json.dumps({"proposal_id": "proposal-1", "status": "blocked", "model_id": "tiny-model", "dataset_id": "tiny-dataset", "method": "qlora", "blockers": ["Disk at C:\\private\\output"], "warnings": [], "suggestions": []})},
        }
    )
    mapper.handle({"event": "on_tool_start", "name": "submit_training", "run_id": "submission", "data": {"input": {}}})
    mapper.handle(
        {
            "event": "on_tool_end",
            "name": "submit_training",
            "run_id": "submission",
            "data": {"output": json.dumps({"proposal_id": "proposal-1", "task_id": "task-1", "status": "duplicate"})},
        }
    )
    mapper.handle({"event": "on_tool_start", "name": "get_training_summary", "run_id": "summary", "data": {"input": {}}})
    mapper.handle(
        {
            "event": "on_tool_end",
            "name": "get_training_summary",
            "run_id": "summary",
            "data": {"output": json.dumps({"task_id": "task-1", "status": "failed", "model_id": "tiny-model", "dataset_id": "tiny-dataset", "method": "qlora", "task_goal": "qa", "started_at": "2026-07-11T00:00:00Z"})},
        }
    )

    activities = [part["payload"]["training_activity"] for part in repo.parts]
    assert [activity["kind"] for activity in activities] == ["proposal", "submission", "run_summary"]
    assert activities[0]["proposal_id"] == "proposal-1"
    assert activities[1]["task_id"] == "task-1"
    assert activities[2]["status"] == "failed"
    assert "private" not in str(activities)
    assert repo.events[-1]["payload"]["part"]["payload"]["training_activity"] == activities[-1]


def test_deepagents_event_mapper_leaves_failed_or_malformed_training_results_generic():
    repo = FakeRepository()
    mapper = DeepAgentsEventMapper(repo, lambda *_args: None, "session-1")
    failed_results = [
        ("submit_training", {"proposal_id": "proposal-1", "status": "failed", "code": "rejected"}),
        ("submit_training", {"proposal_id": "proposal-1", "status": "failed", "code": "stale"}),
        ("get_training_summary", {"task_id": "missing-task", "status": "failed", "code": "missing_run"}),
        ("propose_training", "not json"),
    ]

    for index, (name, output) in enumerate(failed_results):
        run_id = f"run-{index}"
        mapper.handle({"event": "on_tool_start", "name": name, "run_id": run_id, "data": {"input": {}}})
        mapper.handle(
            {
                "event": "on_tool_end",
                "name": name,
                "run_id": run_id,
                "data": {"output": output if isinstance(output, str) else json.dumps(output)},
            }
        )

    assert all("training_activity" not in part["payload"] for part in repo.parts)
    assert all(part["type"] == "tool_call" for part in repo.parts)
