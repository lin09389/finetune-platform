"""Gateway integration tests for the unified gateway API contract."""

import pytest
from gateway.cross_agent import get_cross_agent_communicator
from gateway.device_auth import get_device_auth_manager
from httpx import ASGITransport, AsyncClient
from main import app


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


class TestGatewayAPI:
    @pytest.mark.asyncio
    async def test_get_gateway_status(self, client):
        response = await client.get("/gateway/status")

        assert response.status_code == 200
        data = response.json()

        assert data["tier"] == "experimental"
        assert data["available"] is True
        assert data["failure_mode"] == "explicit_status"
        assert "dependency_status" in data
        assert "runtime_status" in data
        assert "message" in data
        assert "gateway" in data
        assert "router" in data
        assert "sessions" in data
        assert "bindings" in data
        assert "auth" in data
        assert "communication" in data

    @pytest.mark.asyncio
    async def test_device_register_and_authenticate(self, client):
        register_response = await client.post(
            "/gateway/devices/register",
            json={
                "device_type": "web",
                "device_name": "Test Device",
            },
        )

        assert register_response.status_code == 200
        register_data = register_response.json()

        assert register_data["success"] is True
        assert "device_id" in register_data
        assert "token" in register_data

        device_id = register_data["device_id"]
        token = register_data["token"]

        auth_response = await client.post(
            "/gateway/devices/authenticate",
            json={
                "device_id": device_id,
                "token": token,
            },
        )

        assert auth_response.status_code == 200
        auth_data = auth_response.json()

        assert auth_data["success"] is True
        assert auth_data["authenticated"] is True

    @pytest.mark.asyncio
    async def test_list_devices(self, client):
        response = await client.get("/gateway/devices")

        assert response.status_code == 200
        data = response.json()

        assert "devices" in data
        assert "total" in data
        assert isinstance(data["devices"], list)

    @pytest.mark.asyncio
    async def test_create_and_delete_binding(self, client):
        auth_manager = get_device_auth_manager()
        await auth_manager.register_device(
            device_id="test_agent_device",
            device_type="cli",
            device_name="Test Agent Device",
        )

        create_response = await client.post(
            "/gateway/bindings",
            json={
                "agent_id": "test_agent_device",
                "priority": 10,
                "peer_id": "peer_test",
                "enabled": True,
            },
        )

        assert create_response.status_code == 200
        create_data = create_response.json()

        assert create_data["success"] is True
        assert "rule_id" in create_data

        rule_id = create_data["rule_id"]

        list_response = await client.get("/gateway/bindings")

        assert list_response.status_code == 200
        list_data = list_response.json()

        assert "bindings" in list_data
        assert list_data["total"] >= 1

        delete_response = await client.delete(f"/gateway/bindings/{rule_id}")

        assert delete_response.status_code == 200
        assert delete_response.json()["success"] is True

    @pytest.mark.asyncio
    async def test_send_message(self, client):
        communicator = get_cross_agent_communicator()
        communicator.register_agent("test_source")
        communicator.register_agent("test_target")

        response = await client.post(
            "/gateway/messages/send",
            json={
                "target_agent": "test_target",
                "message_type": "request",
                "priority": "normal",
                "payload": {"content": "Hello"},
            },
        )

        assert response.status_code == 200
        data = response.json()

        assert data["success"] is True
        assert "message_id" in data

    @pytest.mark.asyncio
    async def test_broadcast_message(self, client):
        communicator = get_cross_agent_communicator()
        communicator.register_agent("broadcast_source")
        communicator.register_agent("broadcast_target_1")
        communicator.register_agent("broadcast_target_2")

        response = await client.post(
            "/gateway/messages/broadcast",
            json={"payload": {"content": "Broadcast message"}},
        )

        assert response.status_code == 200
        data = response.json()

        assert data["success"] is True
        assert "sent_to" in data
        assert "count" in data

    @pytest.mark.asyncio
    async def test_spawn_agent(self, client):
        communicator = get_cross_agent_communicator()
        communicator.register_agent("parent_agent")

        response = await client.post(
            "/gateway/agents/spawn",
            json={
                "parent_agent": "parent_agent",
                "task_type": "test_task",
            },
        )

        assert response.status_code == 200
        data = response.json()

        assert data["success"] is True
        assert "spawned_id" in data

    @pytest.mark.asyncio
    async def test_collect_results(self, client):
        communicator = get_cross_agent_communicator()
        communicator.register_agent("result_agent_1")
        communicator.register_agent("result_agent_2")

        response = await client.post(
            "/gateway/agents/results/collect?timeout=5&merge_strategy=combine",
            json=["result_agent_1", "result_agent_2"],
        )

        assert response.status_code == 200
        data = response.json()

        assert "results" in data
        assert "merged" in data


class TestGatewayErrorHandling:
    @pytest.mark.asyncio
    async def test_device_not_found(self, client):
        response = await client.get("/gateway/devices/nonexistent_device")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_binding_not_found(self, client):
        response = await client.delete("/gateway/bindings/nonexistent_binding")
        assert response.status_code == 404


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
