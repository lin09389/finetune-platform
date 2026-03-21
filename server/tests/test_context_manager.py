"""
对话上下文管理模块单元测试
"""
import pytest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from context.manager import (
    ContextManager,
    ChatMessage,
    MessageRole,
    MessagePriority,
    ContextWindow,
    get_context_manager,
    remove_context_manager,
    list_context_managers,
)


class TestContextWindow:
    """上下文窗口测试"""
    
    def test_default_window(self):
        """测试默认窗口配置"""
        window = ContextWindow()
        assert window.max_tokens == 4096
        assert window.reserved_tokens == 512
        assert window.available_tokens == 3584
    
    def test_available_tokens(self):
        """测试可用 token 计算"""
        window = ContextWindow(max_tokens=1000, reserved_tokens=100)
        window.current_tokens = 500
        assert window.available_tokens == 400
    
    def test_utilization(self):
        """测试利用率计算"""
        window = ContextWindow(max_tokens=1000, reserved_tokens=100)
        window.current_tokens = 450
        assert abs(window.utilization - 0.5) < 0.01


class TestChatMessage:
    """对话消息测试"""
    
    def test_message_creation(self):
        """测试消息创建"""
        msg = ChatMessage(
            id="test_1",
            role=MessageRole.USER,
            content="Hello World"
        )
        assert msg.id == "test_1"
        assert msg.role == MessageRole.USER
        assert msg.content == "Hello World"
        assert msg.priority == MessagePriority.NORMAL
    
    def test_message_to_dict(self):
        """测试消息序列化"""
        msg = ChatMessage(
            id="test_2",
            role=MessageRole.ASSISTANT,
            content="Hi there",
            token_count=10
        )
        data = msg.to_dict()
        assert data["id"] == "test_2"
        assert data["role"] == "assistant"
        assert data["content"] == "Hi there"
        assert data["token_count"] == 10
    
    def test_message_from_dict(self):
        """测试消息反序列化"""
        data = {
            "id": "test_3",
            "role": "user",
            "content": "Test message",
            "timestamp": "2024-01-01T12:00:00",
            "priority": "high",
            "token_count": 5,
            "importance": 0.8
        }
        msg = ChatMessage.from_dict(data)
        assert msg.id == "test_3"
        assert msg.role == MessageRole.USER
        assert msg.priority == MessagePriority.HIGH


class TestContextManager:
    """上下文管理器测试"""
    
    @pytest.fixture
    def manager(self):
        return ContextManager(max_tokens=1000, reserved_tokens=100)
    
    def test_initialization(self, manager):
        """测试初始化"""
        assert manager.window.max_tokens == 1000
        assert manager.window.reserved_tokens == 100
        assert len(manager.messages) == 0
    
    def test_estimate_tokens(self, manager):
        """测试 token 估算"""
        assert manager.estimate_tokens("") == 0
        assert manager.estimate_tokens("hello") > 0
        assert manager.estimate_tokens("你好世界") > 0
    
    def test_add_user_message(self, manager):
        """测试添加用户消息"""
        msg = manager.add_message(
            role=MessageRole.USER,
            content="Hello"
        )
        assert len(manager.messages) == 1
        assert manager.messages[0].role == MessageRole.USER
        assert manager.window.current_tokens > 0
    
    def test_add_system_message(self, manager):
        """测试添加系统消息"""
        msg = manager.add_message(
            role=MessageRole.SYSTEM,
            content="You are a helpful assistant"
        )
        assert manager.system_message is not None
        assert manager.system_message.content == "You are a helpful assistant"
        assert manager.system_message.priority == MessagePriority.CRITICAL
    
    def test_add_multiple_messages(self, manager):
        """测试添加多条消息"""
        manager.add_message(MessageRole.USER, "Hello")
        manager.add_message(MessageRole.ASSISTANT, "Hi there")
        manager.add_message(MessageRole.USER, "How are you?")
        
        assert len(manager.messages) == 3
        assert manager.window.current_tokens > 0
    
    def test_get_context(self, manager):
        """测试获取上下文"""
        manager.add_message(MessageRole.SYSTEM, "System prompt")
        manager.add_message(MessageRole.USER, "Hello")
        manager.add_message(MessageRole.ASSISTANT, "Hi")
        
        context = manager.get_context()
        assert len(context) == 3
        assert context[0]["role"] == "system"
    
    def test_get_context_without_system(self, manager):
        """测试获取上下文（不含系统消息）"""
        manager.add_message(MessageRole.SYSTEM, "System prompt")
        manager.add_message(MessageRole.USER, "Hello")
        
        context = manager.get_context(include_system=False)
        assert len(context) == 1
        assert context[0]["role"] == "user"
    
    def test_get_context_max_messages(self, manager):
        """测试限制消息数量"""
        for i in range(10):
            manager.add_message(MessageRole.USER, f"Message {i}")
        
        context = manager.get_context(max_messages=5)
        assert len(context) == 5
    
    def test_get_context_string(self, manager):
        """测试获取上下文字符串"""
        manager.add_message(MessageRole.SYSTEM, "System")
        manager.add_message(MessageRole.USER, "Hello")
        
        text = manager.get_context_string()
        assert "System" in text
        assert "Hello" in text
    
    def test_clear_context(self, manager):
        """测试清空上下文"""
        manager.add_message(MessageRole.USER, "Hello")
        manager.add_message(MessageRole.ASSISTANT, "Hi")
        
        manager.clear()
        assert len(manager.messages) == 0
        assert manager.window.current_tokens == 0
    
    def test_clear_context_keep_system(self, manager):
        """测试清空上下文但保留系统消息"""
        manager.add_message(MessageRole.SYSTEM, "System")
        manager.add_message(MessageRole.USER, "Hello")
        
        manager.clear(keep_system=True)
        assert len(manager.messages) == 0
        assert manager.system_message is not None
    
    def test_get_stats(self, manager):
        """测试获取统计信息"""
        manager.add_message(MessageRole.USER, "Hello")
        manager.add_message(MessageRole.ASSISTANT, "Hi")
        
        stats = manager.get_stats()
        assert stats["total_messages"] == 2
        assert stats["total_tokens"] > 0
        assert "utilization" in stats
    
    def test_auto_compress(self, manager):
        """测试自动压缩"""
        manager.compression_threshold = 0.5
        manager.target_utilization = 0.3
        
        for i in range(20):
            manager.add_message(
                MessageRole.USER,
                f"This is a longer message number {i} to trigger compression"
            )
        
        assert manager.window.utilization < 1.0
    
    def test_get_recent_messages(self, manager):
        """测试获取最近消息"""
        for i in range(10):
            manager.add_message(MessageRole.USER, f"Message {i}")
        
        recent = manager.get_recent_messages(3)
        assert len(recent) == 3
    
    def test_find_messages(self, manager):
        """测试搜索消息"""
        manager.add_message(MessageRole.USER, "Hello world")
        manager.add_message(MessageRole.USER, "Goodbye")
        manager.add_message(MessageRole.USER, "Hello again")
        
        found = manager.find_messages("hello")
        assert len(found) == 2
    
    def test_get_messages_by_role(self, manager):
        """测试按角色获取消息"""
        manager.add_message(MessageRole.USER, "User message")
        manager.add_message(MessageRole.ASSISTANT, "Assistant message")
        manager.add_message(MessageRole.USER, "Another user message")
        
        user_messages = manager.get_messages_by_role(MessageRole.USER)
        assert len(user_messages) == 2


class TestGlobalFunctions:
    """全局函数测试"""
    
    def test_get_context_manager(self):
        """测试获取上下文管理器"""
        manager1 = get_context_manager("test_session_1")
        manager2 = get_context_manager("test_session_1")
        assert manager1 is manager2
        
        manager3 = get_context_manager("test_session_2")
        assert manager1 is not manager3
    
    def test_remove_context_manager(self):
        """测试移除上下文管理器"""
        get_context_manager("test_remove")
        assert "test_remove" in list_context_managers()
        
        result = remove_context_manager("test_remove")
        assert result is True
        assert "test_remove" not in list_context_managers()
    
    def test_list_context_managers(self):
        """测试列出上下文管理器"""
        get_context_manager("list_test_1")
        get_context_manager("list_test_2")
        
        managers = list_context_managers()
        assert "list_test_1" in managers
        assert "list_test_2" in managers


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
