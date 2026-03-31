import pytest
from httpx import ASGITransport, AsyncClient

from api.chat.session import get_session_manager
from main import app


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


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
