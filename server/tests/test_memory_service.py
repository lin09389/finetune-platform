"""
记忆服务单元测试
"""

import pytest

from memory.memory_service_refactored import (
    MemoryEntry,
    MockEmbedder,
    MockVectorStore,
    create_memory_service,
)


class TestMockEmbedder:
    """Mock 嵌入器测试"""

    def test_create_embedder(self):
        """测试创建嵌入器"""
        embedder = MockEmbedder(dimension=128)

        assert embedder.dimension == 128
        assert embedder.model_name == "mock-embedder"
        assert embedder.is_available() is True

    def test_embed_single(self):
        """测试单个文本嵌入"""
        embedder = MockEmbedder(dimension=64)

        embedding = embedder.embed_single("Hello world")

        assert len(embedding) == 64
        assert all(isinstance(x, float) for x in embedding)

    def test_embed_batch(self):
        """测试批量嵌入"""
        embedder = MockEmbedder(dimension=32)

        texts = ["Hello", "World", "Test"]
        embeddings = embedder.embed(texts)

        assert len(embeddings) == 3
        assert all(len(e) == 32 for e in embeddings)

    def test_deterministic_embedding(self):
        """测试确定性嵌入"""
        embedder = MockEmbedder(dimension=64)

        e1 = embedder.embed_single("same text")
        e2 = embedder.embed_single("same text")

        assert e1 == e2

    def test_different_texts_different_embeddings(self):
        """测试不同文本产生不同嵌入"""
        embedder = MockEmbedder(dimension=64)

        e1 = embedder.embed_single("text one")
        e2 = embedder.embed_single("text two")

        assert e1 != e2


class TestMockVectorStore:
    """Mock 向量存储测试"""

    @pytest.fixture
    def store(self):
        return MockVectorStore()

    def test_create_collection(self, store):
        """测试创建集合"""
        result = store.create_collection("test_collection", dimension=128)

        assert result is True
        assert store.collection_exists("test_collection")

    def test_collection_exists(self, store):
        """测试检查集合是否存在"""
        assert not store.collection_exists("nonexistent")

        store.create_collection("existing")

        assert store.collection_exists("existing")

    def test_add_documents(self, store):
        """测试添加文档"""
        store.create_collection("test")

        ids = store.add_documents(
            collection_name="test",
            documents=["doc1", "doc2"],
            embeddings=[[0.1] * 64, [0.2] * 64],
            metadatas=[{"key": "1"}, {"key": "2"}],
        )

        assert len(ids) == 2
        assert store.count("test") == 2

    def test_search(self, store):
        """测试搜索"""
        store.create_collection("test", dimension=64)
        store.add_documents(
            collection_name="test",
            documents=["hello world", "foo bar"],
            embeddings=MockEmbedder(64).embed(["hello world", "foo bar"]),
        )

        results = store.search(
            collection_name="test",
            query_embedding=MockEmbedder(64).embed_single("hello"),
            top_k=2,
        )

        assert len(results) == 2

    def test_delete_documents(self, store):
        """测试删除文档"""
        store.create_collection("test")
        ids = store.add_documents(
            collection_name="test",
            documents=["doc1"],
            embeddings=[[0.1] * 64],
        )

        result = store.delete_documents("test", ids)

        assert result is True
        assert store.count("test") == 0

    def test_get_document(self, store):
        """测试获取文档"""
        store.create_collection("test")
        ids = store.add_documents(
            collection_name="test",
            documents=["test doc"],
            embeddings=[[0.1] * 64],
            ids=["doc1"],
        )

        doc = store.get_document("test", "doc1")

        assert doc is not None
        assert doc.content == "test doc"

    def test_count(self, store):
        """测试计数"""
        store.create_collection("test")

        assert store.count("test") == 0

        store.add_documents(
            collection_name="test",
            documents=["a", "b", "c"],
            embeddings=[[0.1] * 64] * 3,
        )

        assert store.count("test") == 3


class TestMemoryServiceRefactored:
    """重构后的记忆服务测试"""

    @pytest.fixture
    def service(self):
        return create_memory_service(use_mock=True)

    def test_create_service(self, service):
        """测试创建服务"""
        assert service is not None
        assert service.embedder is not None
        assert service.vector_store is not None

    def test_initialize(self, service):
        """测试初始化"""
        result = service.initialize()

        assert result is True
        assert service._initialized is True

    @pytest.mark.asyncio
    async def test_store(self, service):
        """测试存储记忆"""
        service.initialize()

        entry = await service.store(
            content="Test memory content",
            role="user",
            importance=0.8,
        )

        assert entry.id is not None
        assert entry.content == "Test memory content"
        assert entry.role == "user"
        assert entry.importance == 0.8

    @pytest.mark.asyncio
    async def test_search(self, service):
        """测试搜索记忆"""
        service.initialize()

        await service.store("Hello world", role="user")
        await service.store("Goodbye world", role="assistant")

        results = await service.search("Hello", top_k=5)

        assert len(results) > 0

    @pytest.mark.asyncio
    async def test_get(self, service):
        """测试获取记忆"""
        service.initialize()

        entry = await service.store("Test entry")

        retrieved = await service.get(entry.id)

        assert retrieved is not None
        assert retrieved.content == "Test entry"

    @pytest.mark.asyncio
    async def test_get_nonexistent(self, service):
        """测试获取不存在的记忆"""
        service.initialize()

        result = await service.get("nonexistent_id")

        assert result is None

    @pytest.mark.asyncio
    async def test_delete(self, service):
        """测试删除记忆"""
        service.initialize()

        entry = await service.store("To be deleted")

        result = await service.delete(entry.id)

        assert result is True

        retrieved = await service.get(entry.id)
        assert retrieved is None

    @pytest.mark.asyncio
    async def test_update_importance(self, service):
        """测试更新重要性"""
        service.initialize()

        entry = await service.store("Test", importance=0.5)

        result = await service.update_importance(entry.id, 0.9)

        assert result is True

        updated = await service.get(entry.id)
        assert updated.importance == 0.9

    @pytest.mark.asyncio
    async def test_clear(self, service):
        """测试清空记忆"""
        service.initialize()

        await service.store("Memory 1")
        await service.store("Memory 2")

        result = await service.clear()

        assert result is True

        stats = service.get_stats()
        assert stats["total_entries"] == 0

    def test_get_stats(self, service):
        """测试获取统计"""
        service.initialize()

        stats = service.get_stats()

        assert "collection_name" in stats
        assert "total_entries" in stats
        assert "initialized" in stats


class TestMemoryEntry:
    """记忆条目测试"""

    def test_create_entry(self):
        """测试创建条目"""
        entry = MemoryEntry(
            id="test-id",
            content="Test content",
            role="user",
            importance=0.7,
        )

        assert entry.id == "test-id"
        assert entry.content == "Test content"
        assert entry.role == "user"
        assert entry.importance == 0.7

    def test_entry_to_dict(self):
        """测试条目转字典"""
        entry = MemoryEntry(
            id="test-id",
            content="Test",
        )

        data = entry.to_dict()

        assert data["id"] == "test-id"
        assert data["content"] == "Test"
