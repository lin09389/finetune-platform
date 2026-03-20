"""
Gateway 综合测试
"""
import pytest
import asyncio
from datetime import datetime
from unittest.mock import Mock, AsyncMock, patch
import json

from gateway.server import GatewayServer
from gateway.router import MessageRouter
from gateway.session import SessionManager
from gateway.binding import BindingRouter, BindingManager, BindingType, Binding
from gateway.agent_isolation import AgentIsolationManager, IsolationLevel
from gateway.device_auth import DeviceAuthManager, DeviceType, DeviceStatus


class TestBindingRouter:
    """绑定路由器测试"""
    
    def test_add_binding(self):
        """测试添加绑定"""
        router = BindingRouter()
        
        binding = Binding(
            binding_id="test_binding_1",
            binding_type=BindingType.PEER,
            target_id="peer_123",
            agent_id="agent_001",
            priority=1
        )
        
        router.add_binding(binding)
        
        result = router.route(peer_id="peer_123")
        
        assert result is not None
        assert result.binding.agent_id == "agent_001"
    
    def test_remove_binding(self):
        """测试移除绑定"""
        router = BindingRouter()
        
        binding = Binding(
            binding_id="test_binding_2",
            binding_type=BindingType.PEER,
            target_id="peer_456",
            agent_id="agent_002"
        )
        
        router.add_binding(binding)
        assert router.remove_binding("test_binding_2") is True
        assert router.route(peer_id="peer_456") is None
    
    def test_priority_routing(self):
        """测试优先级路由"""
        router = BindingRouter()
        
        binding1 = Binding(
            binding_id="binding_peer",
            binding_type=BindingType.PEER,
            target_id="target_1",
            agent_id="agent_peer",
            priority=1
        )
        
        binding2 = Binding(
            binding_id="binding_guild",
            binding_type=BindingType.GUILD,
            target_id="target_1",
            agent_id="agent_guild",
            priority=1
        )
        
        router.add_binding(binding1)
        router.add_binding(binding2)
        
        result = router.route(peer_id="target_1", guild_id="target_1")
        
        assert result is not None
        assert result.binding.binding_type == BindingType.PEER


class TestBindingManager:
    """绑定管理器测试"""
    
    def test_create_binding(self):
        """测试创建绑定"""
        manager = BindingManager()
        
        binding = manager.create_binding(
            binding_type=BindingType.CHANNEL,
            target_id="channel_001",
            agent_id="agent_001"
        )
        
        assert binding.binding_id is not None
        assert binding.binding_type == BindingType.CHANNEL
        assert binding.target_id == "channel_001"
    
    def test_route_message(self):
        """测试消息路由"""
        manager = BindingManager()
        
        manager.create_binding(
            binding_type=BindingType.PEER,
            target_id="user_123",
            agent_id="agent_for_user"
        )
        
        agent_id = manager.route_message(peer_id="user_123")
        
        assert agent_id == "agent_for_user"
    
    def test_delete_binding(self):
        """测试删除绑定"""
        manager = BindingManager()
        
        binding = manager.create_binding(
            binding_type=BindingType.GUILD,
            target_id="guild_001",
            agent_id="agent_001"
        )
        
        assert manager.delete_binding(binding.binding_id) is True
        assert manager.route_message(guild_id="guild_001") is None


class TestAgentIsolationManager:
    """Agent 隔离管理器测试"""
    
    def test_create_agent(self):
        """测试创建 Agent"""
        manager = AgentIsolationManager()
        
        workspace = manager.create_agent(
            agent_id="test_agent_001",
            isolation_level=IsolationLevel.STANDARD
        )
        
        assert workspace is not None
        assert workspace.agent_id == "test_agent_001"
    
    def test_create_session(self):
        """测试创建会话"""
        manager = AgentIsolationManager()
        
        manager.create_agent("test_agent_002")
        session = manager.create_session("test_agent_002")
        
        assert session is not None
        assert session.agent_id == "test_agent_002"
    
    def test_file_access_control(self):
        """测试文件访问控制"""
        manager = AgentIsolationManager()
        
        manager.create_agent("test_agent_003")
        
        workspace = manager.get_agent_workspace("test_agent_003")
        assert workspace is not None
        
        test_path = str(workspace.workspace_path / "test.txt")
        assert manager.check_file_access("test_agent_003", test_path) is True


class TestDeviceAuthManager:
    """设备认证管理器测试"""
    
    @pytest.mark.asyncio
    async def test_register_device(self):
        """测试设备注册"""
        manager = DeviceAuthManager()
        
        result = await manager.register_device(
            device_id="device_001",
            device_type=DeviceType.WEB,
            device_name="Test Device"
        )
        
        assert result["device_id"] == "device_001"
        assert "token" in result
        assert "secret" in result
    
    def test_authenticate_device(self):
        """测试设备认证"""
        manager = DeviceAuthManager()
        
        from gateway.device_auth import DeviceCredentials, DeviceStatus
        from datetime import datetime
        
        credentials = DeviceCredentials(
            device_id="device_002",
            token="test_token_123",
            secret="test_secret_456",
            device_type=DeviceType.WEB,
            status=DeviceStatus.ACTIVE
        )
        manager._devices["device_002"] = credentials
        manager._token_index["test_token_123"] = "device_002"
        
        assert manager.authenticate_device("device_002", "test_token_123") is True
    
    def test_check_permission(self):
        """测试权限检查"""
        manager = DeviceAuthManager()
        
        from gateway.device_auth import DevicePermissions, PermissionLevel
        
        permissions = DevicePermissions(
            device_id="device_003",
            level=PermissionLevel.USER,
            allowed_actions=["read", "write"]
        )
        manager._permissions["device_003"] = permissions
        
        assert manager.check_permission("device_003", "read") is True
        assert manager.check_permission("device_003", "delete") is False


class TestSessionManager:
    """会话管理器测试"""
    
    def test_create_session(self):
        """测试创建会话"""
        from gateway.agent_isolation import SessionManager
        
        manager = SessionManager()
        
        session = manager.create_session("agent_001")
        
        assert session is not None
        assert session.agent_id == "agent_001"
        assert session.session_id.startswith("agent_001")
    
    def test_update_session_state(self):
        """测试更新会话状态"""
        from gateway.agent_isolation import SessionManager
        
        manager = SessionManager()
        session = manager.create_session("agent_002")
        
        result = manager.update_session_state(
            session.session_id,
            {"key": "value"}
        )
        
        assert result is True
        updated = manager.get_session(session.session_id)
        assert updated.state.get("key") == "value"
    
    def test_close_session(self):
        """测试关闭会话"""
        from gateway.agent_isolation import SessionManager
        
        manager = SessionManager()
        session = manager.create_session("agent_003")
        
        result = manager.close_session(session.session_id)
        
        assert result is True
        assert manager.get_session(session.session_id) is None


class TestWorkspaceManager:
    """工作空间管理器测试"""
    
    def test_create_workspace(self):
        """测试创建工作空间"""
        from gateway.agent_isolation import WorkspaceManager
        
        manager = WorkspaceManager()
        
        workspace = manager.create_workspace("agent_004")
        
        assert workspace is not None
        assert workspace.agent_id == "agent_004"
    
    def test_delete_workspace(self):
        """测试删除工作空间"""
        from gateway.agent_isolation import WorkspaceManager
        
        manager = WorkspaceManager()
        
        manager.create_workspace("agent_005")
        result = manager.delete_workspace("agent_005")
        
        assert result is True
        assert manager.get_workspace("agent_005") is None


class TestMessageRouter:
    """消息路由器测试"""
    
    def test_route_to_agent(self):
        """测试路由到 Agent"""
        router = MessageRouter()
        
        router.register_agent("agent_001", ["intent_a", "intent_b"])
        
        target = router.route("intent_a")
        
        assert target == "agent_001"
    
    def test_no_matching_agent(self):
        """测试无匹配 Agent"""
        router = MessageRouter()
        
        router.register_agent("agent_001", ["intent_a"])
        
        target = router.route("intent_unknown")
        
        assert target is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
