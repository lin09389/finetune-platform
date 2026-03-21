"""
Gateway 集成测试

测试 Gateway API 端到端功能
"""
import pytest
import asyncio
from httpx import AsyncClient
from unittest.mock import Mock, patch, AsyncMock

from server.main import app
from server.gateway import get_gateway_server, get_binding_manager
from server.gateway.device_auth import get_device_auth_manager
from server.gateway.cross_agent import get_cross_agent_communicator


@pytest.fixture
async def client():
    """创建测试客户端"""
    async with AsyncClient(app=app, base_url="http://test") as ac:
        yield ac


class TestGatewayAPI:
    """Gateway API 集成测试"""
    
    @pytest.mark.asyncio
    async def test_get_gateway_status(self, client):
        """测试获取 Gateway 状态"""
        response = await client.get("/gateway/status")
        
        assert response.status_code == 200
        data = response.json()
        
        assert "gateway" in data
        assert "router" in data
        assert "sessions" in data
        assert "bindings" in data
        assert "auth" in data
        assert "communication" in data
    
    @pytest.mark.asyncio
    async def test_device_register_and_authenticate(self, client):
        """测试设备注册和认证流程"""
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
        """测试列出设备"""
        response = await client.get("/gateway/devices")
        
        assert response.status_code == 200
        data = response.json()
        
        assert "devices" in data
        assert "total" in data
        assert isinstance(data["devices"], list)
    
    @pytest.mark.asyncio
    async def test_create_and_delete_binding(self, client):
        """测试创建和删除绑定规则"""
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
        """测试发送消息"""
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
        """测试广播消息"""
        communicator = get_cross_agent_communicator()
        communicator.register_agent("broadcast_source")
        communicator.register_agent("broadcast_target_1")
        communicator.register_agent("broadcast_target_2")
        
        response = await client.post(
            "/gateway/messages/broadcast",
            json={"content": "Broadcast message"},
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["success"] is True
        assert "sent_to" in data
        assert "count" in data
    
    @pytest.mark.asyncio
    async def test_spawn_agent(self, client):
        """测试生成子 Agent"""
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
        """测试收集结果"""
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


class TestSetupAPI:
    """配置向导 API 集成测试"""
    
    @pytest.mark.asyncio
    async def test_get_system_info(self, client):
        """测试获取系统信息"""
        response = await client.get("/setup/system-info")
        
        assert response.status_code == 200
        data = response.json()
        
        assert "os" in data
        assert "python_version" in data
        assert "cpu_count" in data
        assert "total_memory_gb" in data
    
    @pytest.mark.asyncio
    async def test_get_installed_libraries(self, client):
        """测试获取已安装的库"""
        response = await client.get("/setup/libraries")
        
        assert response.status_code == 200
        data = response.json()
        
        assert isinstance(data, dict)
    
    @pytest.mark.asyncio
    async def test_get_config_suggestions(self, client):
        """测试获取配置建议"""
        response = await client.get("/setup/suggestions")
        
        assert response.status_code == 200
        data = response.json()
        
        assert "suggestions" in data
        assert "total" in data
    
    @pytest.mark.asyncio
    async def test_auto_configure(self, client):
        """测试自动配置"""
        response = await client.post(
            "/setup/auto-configure",
            json={"preferences": {"custom_setting": "value"}},
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["success"] is True
        assert "config" in data
    
    @pytest.mark.asyncio
    async def test_quick_start(self, client):
        """测试快速开始"""
        response = await client.get("/setup/quick-start")
        
        assert response.status_code == 200
        data = response.json()
        
        assert "system_info" in data
        assert "libraries" in data
        assert "recommended_config" in data
        assert "ready" in data
        assert "messages" in data
    
    @pytest.mark.asyncio
    async def test_wizard_flow(self, client):
        """测试配置向导流程"""
        start_response = await client.post("/setup/wizard/start")
        
        assert start_response.status_code == 200
        start_data = start_response.json()
        
        assert "wizard_id" in start_data
        wizard_id = start_data["wizard_id"]
        
        step_response = await client.post(
            f"/setup/wizard/{wizard_id}/step",
            json={"action": "set", "key": "test_key", "value": "test_value"},
        )
        
        assert step_response.status_code == 200
        step_data = step_response.json()
        
        assert step_data["config"]["test_key"] == "test_value"
        
        get_response = await client.get(f"/setup/wizard/{wizard_id}")
        
        assert get_response.status_code == 200
        
        delete_response = await client.delete(f"/setup/wizard/{wizard_id}")
        
        assert delete_response.status_code == 200


class TestErrorHandling:
    """错误处理集成测试"""
    
    @pytest.mark.asyncio
    async def test_wizard_not_found(self, client):
        """测试向导不存在错误"""
        response = await client.get("/setup/wizard/nonexistent_id")
        
        assert response.status_code == 404
    
    @pytest.mark.asyncio
    async def test_device_not_found(self, client):
        """测试设备不存在错误"""
        response = await client.get("/gateway/devices/nonexistent_device")
        
        assert response.status_code == 404
    
    @pytest.mark.asyncio
    async def test_binding_not_found(self, client):
        """测试绑定规则不存在错误"""
        response = await client.delete("/gateway/bindings/nonexistent_binding")
        
        assert response.status_code == 404


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
