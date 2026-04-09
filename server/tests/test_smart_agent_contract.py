import pytest
from httpx import ASGITransport, AsyncClient
from main import app


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
async def test_smart_execute_generate_only(client):
    resp = await client.post(
        "/smart-agent/smart-execute",
        json={"message": "generate a short summary", "auto_execute": True},
    )
    assert resp.status_code == 200
    data = resp.json()

    assert data["detected"] is True
    assert data["intent_type"] == "content_generation"
    assert data["execution"]["status"] == "planned"


@pytest.mark.asyncio
async def test_smart_execute_save_only_missing_preconditions(client):
    resp = await client.post(
        "/smart-agent/smart-execute",
        json={"message": "save this", "auto_execute": True},
    )
    assert resp.status_code == 200
    data = resp.json()

    assert data["detected"] is True
    assert data["intent_type"] == "save_content"
    assert data["need_confirm"] is True
    assert data["execution"]["status"] == "needs_confirmation"
    assert data["execution"]["error_code"] == "validation_error"


@pytest.mark.asyncio
async def test_smart_execute_generate_and_save_composite(client):
    resp = await client.post(
        "/smart-agent/smart-execute",
        json={"message": "generate changelog and save to changelog.md", "auto_execute": True},
    )
    assert resp.status_code == 200
    data = resp.json()

    assert data["detected"] is True
    assert data["intent_type"] == "composite_content_save"
    assert data["execution"]["status"] == "planned"
    assert data["result_data"]["need_inference"] is True


@pytest.mark.asyncio
async def test_supported_operations_contract(client):
    resp = await client.get("/smart-agent/supported-operations")
    assert resp.status_code == 200
    data = resp.json()

    assert "actions" in data
    assert "count" in data
    assert isinstance(data["actions"], list)
