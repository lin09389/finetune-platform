"""
Gateway 模块单元测试
"""
from unittest.mock import Mock

import pytest
from agent.config import AgentConfig
from gateway.agent_isolation import AgentIsolationManager
from gateway.binding import BindingManager
from gateway.cross_agent import (
    CrossAgentCommunicator,
)
from gateway.device_auth import (
    DeviceAuthManager,
    DeviceType,
    PermissionLevel,
)
from gateway.models import AgentInfo, BindingRule


class TestBindingManager:
    """Binding Manager 测试"""

    @pytest.fixture
    def binding_manager(self):
        return BindingManager()

    @pytest.fixture
    def sample_agent(self):
        return AgentInfo(
            id="agent_1",
            name="Test Agent",
            workspace_path="/tmp/workspaces/agent_1",
        )

    @pytest.fixture
    def sample_binding(self, sample_agent):
        return BindingRule(
            id="binding_1",
            agent_id=sample_agent.id,
            priority=10,
            peer_id="peer_123",
            guild_id="guild_456",
            enabled=True,
        )

    def test_register_agent(self, binding_manager, sample_agent):
        """测试 Agent 注册"""
        binding_manager.register_agent(sample_agent)

        assert sample_agent.id in binding_manager._agents
        assert binding_manager._agents[sample_agent.id] == sample_agent

    def test_unregister_agent(self, binding_manager, sample_agent):
        """测试 Agent 注销"""
        binding_manager.register_agent(sample_agent)
        binding_manager.unregister_agent(sample_agent.id)

        assert sample_agent.id not in binding_manager._agents

    def test_add_binding(self, binding_manager, sample_agent, sample_binding):
        """测试添加绑定规则"""
        binding_manager.register_agent(sample_agent)
        result = binding_manager.add_binding(sample_binding)

        assert result is True
        assert sample_binding.id in binding_manager._bindings

    def test_add_binding_nonexistent_agent(self, binding_manager, sample_binding):
        """测试添加绑定规则到不存在的 Agent"""
        result = binding_manager.add_binding(sample_binding)

        assert result is False

    def test_remove_binding(self, binding_manager, sample_agent, sample_binding):
        """测试移除绑定规则"""
        binding_manager.register_agent(sample_agent)
        binding_manager.add_binding(sample_binding)
        result = binding_manager.remove_binding(sample_binding.id)

        assert result is True
        assert sample_binding.id not in binding_manager._bindings

    def test_find_agent_exact_match(self, binding_manager, sample_agent, sample_binding):
        """测试精确匹配 Agent"""
        binding_manager.register_agent(sample_agent)
        binding_manager.add_binding(sample_binding)

        found_agent = binding_manager.find_agent(
            peer_id="peer_123",
            guild_id="guild_456",
        )

        assert found_agent == sample_agent.id

    def test_find_agent_no_match(self, binding_manager, sample_agent, sample_binding):
        """测试无匹配 Agent"""
        binding_manager.register_agent(sample_agent)
        binding_manager.add_binding(sample_binding)

        found_agent = binding_manager.find_agent(
            peer_id="nonexistent_peer",
        )

        assert found_agent is None

    def test_find_agent_most_specific_match(self, binding_manager, sample_agent):
        """测试最具体匹配优先"""
        binding_manager.register_agent(sample_agent)

        binding1 = BindingRule(
            id="binding_1",
            agent_id=sample_agent.id,
            priority=5,
            guild_id="guild_456",
            enabled=True,
        )
        binding2 = BindingRule(
            id="binding_2",
            agent_id=sample_agent.id,
            priority=10,
            peer_id="peer_123",
            guild_id="guild_456",
            enabled=True,
        )

        binding_manager.add_binding(binding1)
        binding_manager.add_binding(binding2)

        found_agent = binding_manager.find_agent(
            peer_id="peer_123",
            guild_id="guild_456",
        )

        assert found_agent == sample_agent.id

    def test_set_default_agent(self, binding_manager, sample_agent):
        """测试设置默认 Agent"""
        binding_manager.register_agent(sample_agent)
        result = binding_manager.set_default_agent(sample_agent.id)

        assert result is True
        assert binding_manager._default_agent_id == sample_agent.id

    def test_get_stats(self, binding_manager, sample_agent, sample_binding):
        """测试获取统计信息"""
        binding_manager.register_agent(sample_agent)
        binding_manager.add_binding(sample_binding)

        stats = binding_manager.get_stats()

        assert stats["total_agents"] == 1
        assert stats["total_bindings"] == 1
        assert stats["enabled_bindings"] == 1


class TestAgentIsolationManager:
    """Agent 隔离管理器测试"""

    @pytest.fixture
    def isolation_manager(self, tmp_path):
        return AgentIsolationManager(base_workspace_path=tmp_path / "workspaces")

    def test_create_agent(self, isolation_manager):
        """测试创建 Agent 环境"""
        result = isolation_manager.create_agent(
            agent_id="agent_1",
            name="Test Agent",
        )

        assert result is True
        assert "agent_1" in isolation_manager._workspaces

    def test_delete_agent(self, isolation_manager):
        """测试删除 Agent 环境"""
        isolation_manager.create_agent(
            agent_id="agent_1",
            name="Test Agent",
        )

        result = isolation_manager.delete_agent("agent_1")

        assert result is True
        assert "agent_1" not in isolation_manager._workspaces

    def test_get_workspace(self, isolation_manager):
        """测试获取工作空间"""
        isolation_manager.create_agent(
            agent_id="agent_1",
            name="Test Agent",
        )

        workspace = isolation_manager.get_workspace("agent_1")

        assert workspace is not None
        assert workspace.exists()

    def test_get_config(self, isolation_manager):
        """测试获取配置"""
        isolation_manager.create_agent(
            agent_id="agent_1",
            name="Test Agent",
            config={"max_memory_mb": 8192},
        )

        config = isolation_manager.get_config("agent_1")

        assert config is not None
        assert config.max_memory_mb == 8192

    def test_session_store(self, isolation_manager):
        """测试 session store"""
        isolation_manager.create_agent(
            agent_id="agent_1",
            name="Test Agent",
        )

        isolation_manager.set_session_data("agent_1", "key1", "value1")
        value = isolation_manager.get_session_data("agent_1", "key1")

        assert value == "value1"

    def test_check_capability(self, isolation_manager):
        """测试能力检测"""
        isolation_manager.create_agent(
            agent_id="agent_1",
            name="Test Agent",
            config={"allowed_capabilities": ["chat", "inference"]},
        )

        assert isolation_manager.check_capability("agent_1", "chat") is True
        assert isolation_manager.check_capability("agent_1", "admin") is False

    def test_get_agent_stats(self, isolation_manager):
        """测试获取 Agent 统计"""
        isolation_manager.create_agent(
            agent_id="agent_1",
            name="Test Agent",
        )

        stats = isolation_manager.get_agent_stats("agent_1")

        assert stats["agent_id"] == "agent_1"
        assert stats["workspace_exists"] is True


class TestDeviceAuthManager:
    """设备认证管理器测试"""

    @pytest.fixture
    def auth_manager(self):
        return DeviceAuthManager()

    @pytest.mark.asyncio
    async def test_register_device(self, auth_manager):
        """测试设备注册"""
        result = await auth_manager.register_device(
            device_id="device_1",
            device_type=DeviceType.WEB,
            device_name="Test Device",
        )

        assert result["device_id"] == "device_1"
        assert "token" in result
        assert "secret" in result

    def test_unregister_device(self, auth_manager):
        """测试设备注销"""
        auth_manager._devices["device_1"] = Mock()
        result = auth_manager.unregister_device("device_1")

        assert result is True
        assert "device_1" not in auth_manager._devices

    def test_authenticate_device(self, auth_manager):
        """测试设备认证"""
        from gateway.device_auth import DeviceCredentials

        credentials = DeviceCredentials(
            device_id="device_1",
            token="test_token",
            secret="test_secret",
        )
        auth_manager._devices["device_1"] = credentials

        result = auth_manager.authenticate_device("device_1", "test_token")

        assert result is True

    def test_authenticate_device_invalid_token(self, auth_manager):
        """测试无效 Token 认证"""
        from gateway.device_auth import DeviceCredentials

        credentials = DeviceCredentials(
            device_id="device_1",
            token="test_token",
            secret="test_secret",
        )
        auth_manager._devices["device_1"] = credentials

        result = auth_manager.authenticate_device("device_1", "wrong_token")

        assert result is False

    def test_create_challenge(self, auth_manager):
        """测试创建挑战"""
        from gateway.device_auth import DeviceCredentials

        credentials = DeviceCredentials(
            device_id="device_1",
            token="test_token",
            secret="test_secret",
        )
        auth_manager._devices["device_1"] = credentials

        result = auth_manager.create_challenge("device_1")

        assert result is not None
        assert "challenge_id" in result
        assert "challenge_data" in result

    def test_check_permission(self, auth_manager):
        """测试权限检查"""
        from gateway.device_auth import DevicePermissions

        permissions = DevicePermissions(
            device_id="device_1",
            level=PermissionLevel.USER,
            allowed_actions=["chat", "inference"],
        )
        auth_manager._permissions["device_1"] = permissions

        assert auth_manager.check_permission("device_1", "chat") is True
        assert auth_manager.check_permission("device_1", "admin") is False

    def test_get_stats(self, auth_manager):
        """测试获取统计"""
        stats = auth_manager.get_stats()

        assert "total_devices" in stats
        assert "online_devices" in stats


class TestCrossAgentCommunicator:
    """跨 Agent 通信管理器测试"""

    @pytest.fixture
    def communicator(self):
        return CrossAgentCommunicator()

    def test_register_agent(self, communicator):
        """测试注册 Agent"""
        communicator.register_agent("agent_1")

        assert "agent_1" in communicator._message_queues

    def test_unregister_agent(self, communicator):
        """测试注销 Agent"""
        communicator.register_agent("agent_1")
        communicator.unregister_agent("agent_1")

        assert "agent_1" not in communicator._message_queues

    @pytest.mark.asyncio
    async def test_send_message(self, communicator):
        """测试发送消息"""
        communicator.register_agent("agent_1")
        communicator.register_agent("agent_2")

        message = await communicator.send_message(
            source_agent="agent_1",
            target_agent="agent_2",
            payload={"content": "Hello"},
        )

        assert message is not None
        assert message.source_agent == "agent_1"
        assert message.target_agent == "agent_2"

    @pytest.mark.asyncio
    async def test_send_message_nonexistent_target(self, communicator):
        """测试发送消息到不存在的 Agent"""
        communicator.register_agent("agent_1")

        message = await communicator.send_message(
            source_agent="agent_1",
            target_agent="nonexistent",
            payload={"content": "Hello"},
        )

        assert message is None

    @pytest.mark.asyncio
    async def test_broadcast(self, communicator):
        """测试广播消息"""
        communicator.register_agent("agent_1")
        communicator.register_agent("agent_2")
        communicator.register_agent("agent_3")

        sent_to = await communicator.broadcast(
            source_agent="agent_1",
            payload={"content": "Broadcast"},
        )

        assert len(sent_to) == 2
        assert "agent_1" not in sent_to

    @pytest.mark.asyncio
    async def test_receive_message(self, communicator):
        """测试接收消息"""
        communicator.register_agent("agent_1")
        communicator.register_agent("agent_2")

        await communicator.send_message(
            source_agent="agent_1",
            target_agent="agent_2",
            payload={"content": "Hello"},
        )

        message = await communicator.receive_message("agent_2", timeout=1.0)

        assert message is not None
        assert message.payload["content"] == "Hello"

    def test_merge_results_combine(self, communicator):
        """测试合并结果 - combine 策略"""
        results = {
            "agent_1": {"score": 0.8},
            "agent_2": {"score": 0.9},
        }

        merged = communicator.merge_results(results, strategy="combine")

        assert "agent_1" in merged
        assert "agent_2" in merged

    def test_merge_results_best(self, communicator):
        """测试合并结果 - best 策略"""
        results = {
            "agent_1": {"score": 0.8},
            "agent_2": {"score": 0.9},
        }

        merged = communicator.merge_results(results, strategy="best")

        assert merged["score"] == 0.9

    def test_get_channel_stats(self, communicator):
        """测试获取通道统计"""
        stats = communicator.get_channel_stats()

        assert "total_channels" in stats
        assert "total_messages" in stats


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
