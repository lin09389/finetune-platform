from __future__ import annotations

from agent_session.deepagents_events import DeepAgentsEventMapper


class FakeRepository:
    def __init__(self):
        self.parts = []
        self.events = []

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
        event = {"session_id": session_id, "type": event_type, "message": message, "payload": payload}
        self.events.append(event)
        return event


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
