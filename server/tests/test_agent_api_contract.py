import importlib

import pytest
from httpx import ASGITransport, AsyncClient
from main import app

from agent.intent.models import IntentCategory, IntentResult
from api.chat.session import get_session_manager

agent_api = importlib.import_module("api.agent")


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


def test_get_unified_detector_syncs_bert_toggle(monkeypatch):
    class DummyConfig:
        use_bert_classifier = True

    class DummyDetector:
        _config = DummyConfig()

    monkeypatch.setattr(agent_api, "_detector", DummyDetector())
    monkeypatch.setattr(agent_api.settings, "intent_use_bert_classifier", False)

    detector = agent_api.get_unified_detector()
    assert detector._config.use_bert_classifier is False


@pytest.mark.asyncio
async def test_detect_intent_contract(client):
    resp = await client.post("/agent/detect-intent", json={"message": "create test.txt"})
    assert resp.status_code == 200
    data = resp.json()

    for key in ["detected", "intent_type", "action", "params", "confidence", "need_confirm", "execution"]:
        assert key in data


@pytest.mark.asyncio
async def test_detect_intent_multi_contract(client):
    resp = await client.post("/agent/detect-intent-multi", json={"message": "create test.txt and read test.txt"})
    assert resp.status_code == 200
    data = resp.json()

    for key in ["detected", "intents", "has_ambiguity", "clarification_dialog", "chain"]:
        assert key in data
    assert isinstance(data["intents"], list)
    if data["intents"]:
        for key in ["detected", "intent_type", "action", "params", "confidence", "need_confirm", "execution"]:
            assert key in data["intents"][0]


@pytest.mark.asyncio
async def test_chat_execute_contract_and_timeline(client):
    create = await client.post("/chat/sessions", params={"title": "contract test"})
    assert create.status_code == 200
    session_id = create.json()["id"]

    resp = await client.post(
        "/agent/chat-execute",
        json={
            "message": "create hello.txt with content hi",
            "session_id": session_id,
            "auto_confirm": True,
        },
    )
    assert resp.status_code == 200
    data = resp.json()

    for key in ["detected", "intent_type", "action", "params", "confidence", "need_confirm", "execution"]:
        assert key in data
    for key in ["route", "route_confidence", "policy_decision", "policy_reason"]:
        assert key in data

    session = get_session_manager().get_session(session_id)
    assert session is not None
    timeline = session.metadata.get("execution_timeline", [])
    assert isinstance(timeline, list)
    assert len(timeline) >= 1
    assert any("stage" in item for item in timeline)


@pytest.mark.asyncio
async def test_save_intent_generate_only(client):
    resp = await client.post("/agent/detect-intent", json={"message": "please generate a summary paragraph"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["detected"] is True
    assert data["intent_type"] == "content_generation"
    assert data["execution"]["status"] == "planned"


@pytest.mark.asyncio
async def test_save_intent_save_only_with_content(client):
    resp = await client.post(
        "/agent/detect-intent",
        json={
            "message": "save to notes.txt",
            "context": {"content": "hello world", "target_path": "notes.txt"},
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["detected"] is True
    assert data["intent_type"] == "save_content"
    assert data["need_confirm"] is False
    assert data["params"]["preconditions"]["has_content"] is True


@pytest.mark.asyncio
async def test_save_intent_generate_and_save_composite(client):
    resp = await client.post(
        "/agent/detect-intent",
        json={"message": "generate release notes and save to release.md"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["detected"] is True
    assert data["intent_type"] == "composite_content_save"
    assert data["params"]["target_path"] == "release.md"


@pytest.mark.asyncio
async def test_save_intent_ambiguous_needs_clarification(client):
    resp = await client.post("/agent/detect-intent", json={"message": "save this"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["detected"] is True
    assert data["intent_type"] == "save_content"
    assert data["need_confirm"] is True


@pytest.mark.asyncio
async def test_save_content_missing_preconditions_returns_validation_error_code(client):
    create = await client.post("/chat/sessions", params={"title": "save precondition test"})
    assert create.status_code == 200
    session_id = create.json()["id"]

    resp = await client.post(
        "/agent/chat-execute",
        json={
            "message": "save this",
            "session_id": session_id,
            "auto_confirm": True,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["detected"] is True
    assert data["intent_type"] == "save_content"
    assert data["execution"]["status"] == "needs_confirmation"
    assert data["execution"]["error_code"] == "validation_error"


@pytest.mark.asyncio
async def test_save_content_path_violation_returns_block_or_permission_error_code(client):
    create = await client.post("/chat/sessions", params={"title": "save path violation test"})
    assert create.status_code == 200
    session_id = create.json()["id"]

    resp = await client.post(
        "/agent/chat-execute",
        json={
            "message": "save to ../../../etc/passwd",
            "session_id": session_id,
            "auto_confirm": True,
            "context": {"content": "hello", "target_path": "../../../etc/passwd"},
        },
    )

    # Current middleware may block traversal payload at the gateway/security layer.
    if resp.status_code == 400:
        body = resp.json()
        assert "detail" in body
    else:
        assert resp.status_code == 200
        data = resp.json()
        assert data["detected"] is True
        assert data["intent_type"] == "save_content"
        assert data["execution"]["status"] in ("failed", "needs_confirmation")
        if data["execution"]["status"] == "failed":
            assert data["execution"]["error_code"] in ("permission_denied", "validation_error")


@pytest.mark.asyncio
async def test_run_loop_returns_specific_recovery_hint_for_failed_tests(client):
    resp = await client.post(
        "/agent/run-loop",
        json={
            "message": "run tests",
            "max_steps": 1,
            "auto_confirm": True,
            "context": {
                "detected_intents": [
                    {
                        "detected": True,
                        "intent_type": "tests_run",
                        "action": "tests_run",
                        "params": {
                            "command": [
                                "python",
                                "-c",
                                (
                                    "import sys; "
                                    "print('FAILED tests/test_chat.py::test_resume - AssertionError: boom'); "
                                    "print('1 failed, 4 passed in 0.12s'); "
                                    "sys.exit(1)"
                                ),
                            ]
                        },
                        "description": "run the test suite",
                        "confidence": 1.0,
                        "need_confirm": False,
                    }
                ]
            },
        },
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["execution"]["status"] == "failed"
    assert "test_resume" in data["result"]["recovery_hint"]
    assert data["result"]["last_result"]["data"]["test_summary"]["failed"] == 1
    assert "Completed 0 step(s) before the task failed." in data["result"]["loop_summary"]
    assert "test_resume" in data["result"]["recommended_next_step"]


@pytest.mark.asyncio
async def test_run_loop_auto_repair_pipeline_reads_failure_file_and_returns_prompt_override(client):
    resp = await client.post(
        "/agent/run-loop",
        json={
            "message": "run tests and repair automatically",
            "max_steps": 2,
            "auto_confirm": True,
            "context": {
                "auto_repair_pipeline": True,
                "detected_intents": [
                    {
                        "detected": True,
                        "intent_type": "tests_run",
                        "action": "tests_run",
                        "params": {
                            "command": [
                                "python",
                                "-c",
                                (
                                    "import sys; "
                                    "print('FAILED tests/test_agent_api_contract.py::test_run_loop_auto_repair_pipeline_reads_failure_file_and_returns_prompt_override - AssertionError: boom'); "
                                    "print('1 failed, 0 passed in 0.01s'); "
                                    "sys.exit(1)"
                                ),
                            ]
                        },
                        "description": "run tests",
                        "confidence": 1.0,
                        "need_confirm": False,
                    }
                ],
            },
        },
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["execution"]["status"] == "failed"
    assert data["result"]["need_inference"] is True
    assert data["result"]["auto_repair_pipeline"] is True
    assert data["result"]["pipeline_stage"] == "repair_context_loaded"
    assert "draft a concrete patch proposal" in data["result"]["prompt_override"]
    assert "tests/test_agent_api_contract.py" in data["result"]["prompt_override"]
    assert "python" in data["result"]["rerun_command"]
    assert any(action["action"] == "file_read" for action in data["result"]["completed_actions"])
    assert "Automatic repair prep completed" in data["result"]["recommended_next_step"]


@pytest.mark.asyncio
async def test_run_loop_returns_completion_summary_for_successful_steps(client):
    resp = await client.post(
        "/agent/run-loop",
        json={
            "message": "run a safe command",
            "max_steps": 1,
            "auto_confirm": True,
            "context": {
                "detected_intents": [
                    {
                        "detected": True,
                        "intent_type": "command_run",
                        "action": "command_run",
                        "params": {"command": ["python", "-c", "print('ok from run-loop')"]},
                        "description": "run a safe command",
                        "confidence": 1.0,
                        "need_confirm": False,
                    }
                ]
            },
        },
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["execution"]["status"] == "executed"
    assert data["result"]["completed_steps"] == 1
    assert "Completed 1 step(s) successfully." in data["result"]["loop_summary"]
    assert "command run" in data["result"]["loop_summary"]
    assert "Review the latest result" in data["result"]["recommended_next_step"]


@pytest.mark.asyncio
async def test_chat_execute_model_identity_query_falls_back_to_conversation_when_detector_misfires(client, monkeypatch):
    class FakeDetector:
        def detect(self, message, session_id=None, context=None):  # noqa: ANN001
            return IntentResult(
                detected=True,
                intent_type="ocr_recognize",
                action="ocr_recognize",
                params={},
                description="OCR detect",
                confidence=0.9,
                category=IntentCategory.CUA_OPERATION,
            )

    monkeypatch.setattr(agent_api, "get_unified_detector", lambda: FakeDetector())

    resp = await client.post(
        "/agent/chat-execute",
        json={
            "message": "你是哪个模型",
            "auto_confirm": False,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["detected"] is True
    assert data["intent_type"] == "conversation"
    assert data["action"] == "conversation"
    assert data["result"]["need_inference"] is True
    assert data["policy_decision"] == "needs_inference"


@pytest.mark.asyncio
async def test_chat_execute_greeting_falls_back_to_conversation_when_detector_misfires(client, monkeypatch):
    class FakeDetector:
        def detect(self, message, session_id=None, context=None):  # noqa: ANN001
            return IntentResult(
                detected=True,
                intent_type="ocr_recognize",
                action="ocr_recognize",
                params={},
                description="OCR detect",
                confidence=0.95,
                category=IntentCategory.CUA_OPERATION,
            )

    monkeypatch.setattr(agent_api, "get_unified_detector", lambda: FakeDetector())

    resp = await client.post(
        "/agent/chat-execute",
        json={
            "message": "你好",
            "auto_confirm": False,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["detected"] is True
    assert data["intent_type"] == "conversation"
    assert data["action"] == "conversation"
    assert data["result"]["need_inference"] is True
    assert data["policy_decision"] == "needs_inference"


@pytest.mark.asyncio
async def test_chat_execute_low_confidence_tool_falls_back_to_conversation(client, monkeypatch):
    class FakeDetector:
        def detect(self, message, session_id=None, context=None):  # noqa: ANN001
            return IntentResult(
                detected=True,
                intent_type="file_read",
                action="file_read",
                params={"file_path": "README.md"},
                description="read file",
                confidence=0.60,
                category=IntentCategory.FILE_OPERATION,
            )

    monkeypatch.setattr(agent_api, "get_unified_detector", lambda: FakeDetector())
    resp = await client.post("/agent/chat-execute", json={"message": "read README.md", "auto_confirm": True})
    assert resp.status_code == 200
    data = resp.json()
    assert data["intent_type"] == "conversation"
    assert data["result"]["need_inference"] is True
    assert data["policy_decision"] == "needs_inference"
    assert data["policy_reason"] in ("medium_confidence", "low_action_confidence")


@pytest.mark.asyncio
async def test_chat_execute_unsupported_action_falls_back_to_conversation(client, monkeypatch):
    class FakeDetector:
        def detect(self, message, session_id=None, context=None):  # noqa: ANN001
            return IntentResult(
                detected=True,
                intent_type="unknown_tool",
                action="non_existing_action",
                params={},
                description="unknown action",
                confidence=0.98,
                category=IntentCategory.UNKNOWN,
            )

    monkeypatch.setattr(agent_api, "get_unified_detector", lambda: FakeDetector())
    resp = await client.post("/agent/chat-execute", json={"message": "do something", "auto_confirm": True})
    assert resp.status_code == 200
    data = resp.json()
    assert data["intent_type"] == "conversation"
    assert data["policy_decision"] == "needs_inference"
    assert data["policy_reason"] == "unsupported_action"
