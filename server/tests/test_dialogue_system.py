"""
AI 对话系统后端单元测试

测试覆盖：
- 对话上下文管理
- 会话存储
- 技能系统
- 知识库集成
"""
import pytest
from datetime import datetime
from unittest.mock import Mock, patch, MagicMock
import tempfile
import os
import json

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from context.manager import (
    ContextManager,
    MessageRole,
    MessagePriority,
    ChatMessage,
    ContextWindow,
    get_context_manager,
    remove_context_manager,
    list_context_managers,
)
from context.session_store import (
    SessionStore,
    SessionStatus,
    ChatSession,
    SessionMessage,
    SessionMetadata,
    get_session_store,
)


class TestContextManager:
    """对话上下文管理器测试"""

    def test_context_manager_creation(self):
        manager = ContextManager(session_id="test_session")
        assert manager.session_id == "test_session"
        assert manager.window.max_tokens == 4096
        assert len(manager.messages) == 0

    def test_context_manager_custom_config(self):
        manager = ContextManager(
            session_id="custom_session",
            max_tokens=8192,
            reserved_tokens=1024,
            compression_threshold=0.0,
            target_utilization=0.5
        )
        assert manager.window.max_tokens == 8192
        assert manager.window.reserved_tokens == 1024

    def test_add_message_user(self):
        manager = ContextManager(session_id="test")
        msg = manager.add_message(
            role=MessageRole.USER,
            content="Hello, this is a test message"
        )
        assert len(manager.messages) == 1
        assert msg.role == MessageRole.USER
        assert msg.content == "Hello, this is a test message"
        assert msg.token_count > 0

    def test_add_message_assistant(self):
        manager = ContextManager(session_id="test")
        msg = manager.add_message(
            role=MessageRole.ASSISTANT,
            content="This is the assistant response"
        )
        assert len(manager.messages) == 1
        assert msg.role == MessageRole.ASSISTANT

    def test_add_message_system(self):
        manager = ContextManager(session_id="test")
        msg = manager.add_message(
            role=MessageRole.SYSTEM,
            content="You are a helpful assistant"
        )
        assert msg.role == MessageRole.SYSTEM
        assert msg.priority == MessagePriority.CRITICAL

    def test_estimate_tokens_english(self):
        manager = ContextManager(session_id="test")
        tokens = manager._estimate_tokens("Hello world this is a test")
        assert tokens > 0

    def test_estimate_tokens_chinese(self):
        manager = ContextManager(session_id="test")
        tokens = manager._estimate_tokens("你好世界这是一个测试")
        assert tokens > 0
        assert tokens >= 8

    def test_calculate_importance_system(self):
        manager = ContextManager(session_id="test")
        importance = manager._calculate_importance("System message", MessageRole.SYSTEM)
        assert importance == 1.0

    def test_calculate_importance_user_with_keywords(self):
        manager = ContextManager(session_id="test")
        importance = manager._calculate_importance("这是重要的信息，请记住", MessageRole.USER)
        assert importance >= 0.7

    def test_get_context(self):
        manager = ContextManager(session_id="test")
        manager.add_message(MessageRole.USER, "Hello")
        manager.add_message(MessageRole.ASSISTANT, "Hi there")
        
        context = manager.get_context()
        assert len(context) == 2
        assert context[0]["role"] == "user"
        assert context[1]["role"] == "assistant"

    def test_get_context_max_messages(self):
        manager = ContextManager(session_id="test")
        for i in range(10):
            manager.add_message(MessageRole.USER, f"Message {i}")
        
        context = manager.get_context(max_messages=3)
        assert len(context) == 3

    def test_get_context_string_default(self):
        manager = ContextManager(session_id="test")
        manager.add_message(MessageRole.USER, "Hello")
        manager.add_message(MessageRole.ASSISTANT, "Hi")
        
        context_str = manager.get_context_string()
        assert "[User]:" in context_str
        assert "[Assistant]:" in context_str

    def test_get_context_string_markdown(self):
        manager = ContextManager(session_id="test")
        manager.add_message(MessageRole.USER, "Hello")
        
        context_str = manager.get_context_string(format_type="markdown")
        assert "## User" in context_str

    def test_clear_context(self):
        manager = ContextManager(session_id="test")
        manager.add_message(MessageRole.USER, "Hello")
        manager.add_message(MessageRole.SYSTEM, "System message")
        
        manager.clear(keep_system=True)
        assert len(manager.messages) == 0

    def test_get_stats(self):
        manager = ContextManager(session_id="test")
        manager.add_message(MessageRole.USER, "Hello")
        manager.add_message(MessageRole.ASSISTANT, "Hi there")
        
        stats = manager.get_stats()
        assert stats["message_count"] == 2
        assert stats["total_tokens"] > 0
        assert "utilization" in stats

    def test_get_messages_by_role(self):
        manager = ContextManager(session_id="test")
        manager.add_message(MessageRole.USER, "Hello")
        manager.add_message(MessageRole.ASSISTANT, "Hi")
        manager.add_message(MessageRole.USER, "How are you?")
        
        user_messages = manager.get_messages_by_role(MessageRole.USER)
        assert len(user_messages) == 2

    def test_get_recent_messages(self):
        manager = ContextManager(session_id="test")
        for i in range(10):
            manager.add_message(MessageRole.USER, f"Message {i}")
        
        recent = manager.get_recent_messages(3)
        assert len(recent) == 3

    def test_find_messages(self):
        manager = ContextManager(session_id="test")
        manager.add_message(MessageRole.USER, "Hello world")
        manager.add_message(MessageRole.USER, "Python is great")
        manager.add_message(MessageRole.USER, "Testing Python code")
        
        found = manager.find_messages("Python")
        assert len(found) == 2

    def test_set_max_tokens(self):
        manager = ContextManager(session_id="test")
        manager.set_max_tokens(8192)
        assert manager.window.max_tokens == 8192


class TestContextWindow:
    """上下文窗口测试"""

    def test_available_tokens(self):
        window = ContextWindow(max_tokens=4096, reserved_tokens=512, current_tokens=1000)
        assert window.available_tokens == 4096 - 512 - 1000

    def test_utilization(self):
        window = ContextWindow(max_tokens=4096, reserved_tokens=512, current_tokens=1000)
        expected_util = 1000 / (4096 - 512)
        assert abs(window.utilization - expected_util) < 0.01


class TestChatMessage:
    """上下文消息测试"""

    def test_message_creation(self):
        msg = ChatMessage(
            id="msg_001",
            role=MessageRole.USER,
            content="Test message",
            timestamp=datetime.now(),
            token_count=10,
            importance=0.8
        )
        assert msg.id == "msg_001"
        assert msg.role == MessageRole.USER
        assert msg.importance == 0.8

    def test_message_to_dict(self):
        msg = ChatMessage(
            id="msg_001",
            role=MessageRole.USER,
            content="Test message",
            timestamp=datetime.now(),
            token_count=10
        )
        data = msg.to_dict()
        assert data["id"] == "msg_001"
        assert data["role"] == "user"
        assert data["content"] == "Test message"


class TestGlobalContextManager:
    """全局上下文管理器函数测试"""

    def test_get_context_manager(self):
        manager1 = get_context_manager("session_1")
        manager2 = get_context_manager("session_1")
        assert manager1 is manager2

    def test_get_different_context_managers(self):
        manager1 = get_context_manager("session_1")
        manager2 = get_context_manager("session_2")
        assert manager1 is not manager2

    def test_remove_context_manager(self):
        get_context_manager("session_to_remove")
        result = remove_context_manager("session_to_remove")
        assert result is True

    def test_remove_nonexistent_context_manager(self):
        result = remove_context_manager("nonexistent_session")
        assert result is False

    def test_list_context_managers(self):
        get_context_manager("session_a")
        get_context_manager("session_b")
        managers = list_context_managers()
        assert "session_a" in managers
        assert "session_b" in managers


class TestSessionStore:
    """会话存储测试"""

    @pytest.fixture
    def temp_storage(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir

    def test_session_store_creation(self, temp_storage):
        store = SessionStore(storage_path=temp_storage)
        assert store.storage_path.exists()

    def test_create_session(self, temp_storage):
        store = SessionStore(storage_path=temp_storage)
        session = store.create_session(
            title="Test Session",
            model_id="test_model"
        )
        assert session.id.startswith("session_")
        assert session.metadata.title == "Test Session"
        assert session.metadata.model_id == "test_model"

    def test_get_session(self, temp_storage):
        store = SessionStore(storage_path=temp_storage)
        created = store.create_session(title="Test")
        retrieved = store.get_session(created.id)
        assert retrieved is not None
        assert retrieved.id == created.id

    def test_get_nonexistent_session(self, temp_storage):
        store = SessionStore(storage_path=temp_storage)
        session = store.get_session("nonexistent_id")
        assert session is None

    def test_update_session(self, temp_storage):
        store = SessionStore(storage_path=temp_storage)
        session = store.create_session(title="Original")
        result = store.update_session(session.id, title="Updated")
        assert result is True
        updated = store.get_session(session.id)
        assert updated.metadata.title == "Updated"

    def test_delete_session_soft(self, temp_storage):
        store = SessionStore(storage_path=temp_storage)
        session = store.create_session(title="To Delete")
        result = store.delete_session(session.id, soft_delete=True)
        assert result is True
        deleted = store.get_session(session.id)
        assert deleted.metadata.status == SessionStatus.DELETED

    def test_delete_session_hard(self, temp_storage):
        store = SessionStore(storage_path=temp_storage)
        session = store.create_session(title="To Delete")
        result = store.delete_session(session.id, soft_delete=False)
        assert result is True
        deleted = store.get_session(session.id)
        assert deleted is None

    def test_restore_session(self, temp_storage):
        store = SessionStore(storage_path=temp_storage)
        session = store.create_session(title="To Restore")
        store.delete_session(session.id, soft_delete=True)
        restored = store.restore_session(session.id)
        assert restored is not None
        assert restored.metadata.status == SessionStatus.ACTIVE

    def test_archive_session(self, temp_storage):
        store = SessionStore(storage_path=temp_storage)
        session = store.create_session(title="To Archive")
        result = store.archive_session(session.id)
        assert result is True
        archived = store.get_session(session.id)
        assert archived.metadata.status == SessionStatus.ARCHIVED

    def test_add_message(self, temp_storage):
        store = SessionStore(storage_path=temp_storage)
        session = store.create_session(title="Test")
        msg = store.add_message(
            session_id=session.id,
            role="user",
            content="Hello"
        )
        assert msg is not None
        assert msg.content == "Hello"

    def test_add_messages_batch(self, temp_storage):
        store = SessionStore(storage_path=temp_storage)
        session = store.create_session(title="Test")
        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there"}
        ]
        count = store.add_messages_batch(session.id, messages)
        assert count == 2

    def test_get_messages(self, temp_storage):
        store = SessionStore(storage_path=temp_storage)
        session = store.create_session(title="Test")
        store.add_message(session.id, "user", "Message 1")
        store.add_message(session.id, "assistant", "Message 2")
        store.add_message(session.id, "user", "Message 3")
        
        messages = store.get_messages(session.id)
        assert len(messages) == 3

    def test_get_messages_with_limit(self, temp_storage):
        store = SessionStore(storage_path=temp_storage)
        session = store.create_session(title="Test")
        for i in range(10):
            store.add_message(session.id, "user", f"Message {i}")
        
        messages = store.get_messages(session.id, limit=5)
        assert len(messages) == 5

    def test_delete_message(self, temp_storage):
        store = SessionStore(storage_path=temp_storage)
        session = store.create_session(title="Test")
        msg = store.add_message(session.id, "user", "To delete")
        result = store.delete_message(session.id, msg.id)
        assert result is True

    def test_search_sessions_by_query(self, temp_storage):
        store = SessionStore(storage_path=temp_storage)
        store.create_session(title="Python Tutorial")
        store.create_session(title="JavaScript Guide")
        
        sessions, total = store.search_sessions(query="Python")
        assert total == 1
        assert sessions[0].metadata.title == "Python Tutorial"

    def test_search_sessions_by_status(self, temp_storage):
        store = SessionStore(storage_path=temp_storage)
        store.create_session(title="Active 1")
        session2 = store.create_session(title="To Archive")
        store.archive_session(session2.id)
        
        sessions, total = store.search_sessions(status=SessionStatus.ARCHIVED)
        assert total == 1

    def test_get_statistics(self, temp_storage):
        store = SessionStore(storage_path=temp_storage)
        store.create_session(title="Session 1")
        store.create_session(title="Session 2")
        
        stats = store.get_statistics()
        assert stats["total_sessions"] == 2
        assert stats["active_sessions"] == 2

    def test_export_session_json(self, temp_storage):
        store = SessionStore(storage_path=temp_storage)
        session = store.create_session(title="Test")
        store.add_message(session.id, "user", "Hello")
        
        exported = store.export_session(session.id, format="json")
        assert exported is not None
        data = json.loads(exported)
        assert data["id"] == session.id

    def test_export_session_markdown(self, temp_storage):
        store = SessionStore(storage_path=temp_storage)
        session = store.create_session(title="Test")
        store.add_message(session.id, "user", "Hello")
        
        exported = store.export_session(session.id, format="markdown")
        assert exported is not None
        assert "# Test" in exported

    def test_get_all_tags(self, temp_storage):
        store = SessionStore(storage_path=temp_storage)
        store.create_session(title="Test 1", tags=["python", "tutorial"])
        store.create_session(title="Test 2", tags=["python", "advanced"])
        
        tags = store.get_all_tags()
        assert len(tags) >= 2
        python_tag = next((t for t in tags if t["tag"] == "python"), None)
        assert python_tag is not None
        assert python_tag["count"] == 2


class TestSessionMetadata:
    """会话元数据测试"""

    def test_metadata_creation(self):
        metadata = SessionMetadata(
            title="Test Session",
            description="A test session",
            model_id="model_001",
            tags=["test", "demo"]
        )
        assert metadata.title == "Test Session"
        assert metadata.status == SessionStatus.ACTIVE
        assert len(metadata.tags) == 2


class TestChatSession:
    """聊天会话测试"""

    def test_session_creation(self):
        session = ChatSession(
            id="session_001",
            metadata=SessionMetadata(title="Test"),
            created_at=datetime.now().isoformat(),
            updated_at=datetime.now().isoformat()
        )
        assert session.id == "session_001"
        assert session.message_count == 0


class TestSessionMessage:
    """会话消息测试"""

    def test_message_creation(self):
        msg = SessionMessage(
            id="msg_001",
            session_id="session_001",
            role="user",
            content="Hello",
            timestamp=datetime.now()
        )
        assert msg.id == "msg_001"
        assert msg.role == "user"

    def test_message_to_dict(self):
        msg = SessionMessage(
            id="msg_001",
            session_id="session_001",
            role="user",
            content="Hello",
            timestamp=datetime.now()
        )
        data = msg.to_dict()
        assert data["id"] == "msg_001"
        assert data["role"] == "user"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
