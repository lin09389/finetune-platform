"""
重构后的记忆服务
实现依赖倒置原则，依赖抽象接口而非具体实现
"""
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from core.interfaces.embedder import EmbedderInterface
from core.interfaces.vector_store import VectorStoreInterface

logger = logging.getLogger(__name__)


@dataclass
class MemoryEntry:
    """记忆条目"""
    id: str
    content: str
    embedding: list[float] | None = None
    role: str = "user"
    timestamp: datetime = field(default_factory=datetime.now)
    importance: float = 0.5
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "content": self.content,
            "role": self.role,
            "timestamp": self.timestamp.isoformat(),
            "importance": self.importance,
            "metadata": self.metadata,
        }


@dataclass
class MemorySearchResult:
    """记忆搜索结果"""
    entry: MemoryEntry
    score: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "entry": self.entry.to_dict(),
            "score": self.score,
        }


class MemoryServiceRefactored:
    """
    重构后的记忆服务

    特性:
    - 依赖倒置：依赖 EmbedderInterface 和 VectorStoreInterface
    - 可测试性：可注入 Mock 实现
    - 支持多种嵌入器和向量存储后端
    """

    COLLECTION_NAME = "memory_store"

    def __init__(
        self,
        embedder: EmbedderInterface,
        vector_store: VectorStoreInterface,
        collection_name: str = "memory_store",
        max_entries: int = 10000,
    ):
        self.embedder = embedder
        self.vector_store = vector_store
        self.collection_name = collection_name
        self.max_entries = max_entries
        self._entry_cache: dict[str, MemoryEntry] = {}
        self._initialized = False

    def initialize(self) -> bool:
        """初始化记忆服务"""
        try:
            if not self.vector_store.collection_exists(self.collection_name):
                self.vector_store.create_collection(
                    self.collection_name,
                    dimension=self.embedder.dimension,
                )
            self._initialized = True
            logger.info(f"记忆服务初始化完成: {self.collection_name}")
            return True
        except Exception as e:
            logger.error(f"记忆服务初始化失败: {e}")
            return False

    def _ensure_initialized(self) -> None:
        """确保服务已初始化"""
        if not self._initialized:
            self.initialize()

    async def store(
        self,
        content: str,
        role: str = "user",
        importance: float = 0.5,
        metadata: dict[str, Any] | None = None,
    ) -> MemoryEntry:
        """
        存储记忆

        Args:
            content: 记忆内容
            role: 角色 (user/assistant/system)
            importance: 重要性 (0-1)
            metadata: 元数据

        Returns:
            记忆条目
        """
        self._ensure_initialized()

        import uuid
        entry_id = str(uuid.uuid4())[:8]

        embedding = self.embedder.embed_single(content)

        entry = MemoryEntry(
            id=entry_id,
            content=content,
            embedding=embedding,
            role=role,
            importance=importance,
            metadata=metadata or {},
        )

        self.vector_store.add_documents(
            self.collection_name,
            documents=[content],
            embeddings=[embedding],
            metadatas=[entry.to_dict()],
            ids=[entry_id],
        )

        self._entry_cache[entry_id] = entry

        logger.debug(f"存储记忆: {entry_id}")
        return entry

    async def search(
        self,
        query: str,
        top_k: int = 5,
        filter_role: str | None = None,
    ) -> list[MemorySearchResult]:
        """
        搜索记忆

        Args:
            query: 查询文本
            top_k: 返回数量
            filter_role: 过滤角色

        Returns:
            搜索结果列表
        """
        self._ensure_initialized()

        query_embedding = self.embedder.embed_single(query)

        filter_metadata = None
        if filter_role:
            filter_metadata = {"role": filter_role}

        results = self.vector_store.search(
            self.collection_name,
            query_embedding,
            top_k=top_k,
            filter_metadata=filter_metadata,
        )

        memory_results = []
        for result in results:
            entry = MemoryEntry(
                id=result.id,
                content=result.content,
                role=result.metadata.get("role", "user"),
                importance=result.metadata.get("importance", 0.5),
                metadata=result.metadata.get("metadata", {}),
            )
            memory_results.append(MemorySearchResult(entry=entry, score=result.score))

        return memory_results

    async def get(self, entry_id: str) -> MemoryEntry | None:
        """
        获取指定记忆

        Args:
            entry_id: 记忆 ID

        Returns:
            记忆条目
        """
        if entry_id in self._entry_cache:
            return self._entry_cache[entry_id]

        self._ensure_initialized()

        doc = self.vector_store.get_document(self.collection_name, entry_id)
        if doc:
            entry = MemoryEntry(
                id=doc.id,
                content=doc.content,
                embedding=doc.embedding,
                role=doc.metadata.get("role", "user"),
                importance=doc.metadata.get("importance", 0.5),
                metadata=doc.metadata.get("metadata", {}),
            )
            self._entry_cache[entry_id] = entry
            return entry

        return None

    async def delete(self, entry_id: str) -> bool:
        """
        删除记忆

        Args:
            entry_id: 记忆 ID

        Returns:
            是否成功
        """
        self._ensure_initialized()

        success = self.vector_store.delete_documents(self.collection_name, [entry_id])

        if success and entry_id in self._entry_cache:
            del self._entry_cache[entry_id]

        return success

    async def update_importance(self, entry_id: str, importance: float) -> bool:
        """
        更新记忆重要性

        Args:
            entry_id: 记忆 ID
            importance: 新的重要性

        Returns:
            是否成功
        """
        entry = await self.get(entry_id)
        if not entry:
            return False

        entry.importance = importance

        self.vector_store.update_document(
            self.collection_name,
            entry_id,
            metadata=entry.to_dict(),
        )

        return True

    async def get_recent(self, limit: int = 10) -> list[MemoryEntry]:
        """
        获取最近的记忆

        Args:
            limit: 返回数量

        Returns:
            记忆列表
        """
        self._ensure_initialized()

        count = self.vector_store.count(self.collection_name)
        if count == 0:
            return []

        results = await self.search("", top_k=limit)
        return [r.entry for r in results]

    async def clear(self) -> bool:
        """
        清空所有记忆

        Returns:
            是否成功
        """
        self._ensure_initialized()

        success = self.vector_store.clear_collection(self.collection_name)
        if success:
            self._entry_cache.clear()

        return success

    def get_stats(self) -> dict[str, Any]:
        """获取统计信息"""
        self._ensure_initialized()

        count = self.vector_store.count(self.collection_name)

        return {
            "collection_name": self.collection_name,
            "total_entries": count,
            "cache_size": len(self._entry_cache),
            "embedder": self.embedder.model_name,
            "dimension": self.embedder.dimension,
            "initialized": self._initialized,
        }


class MockEmbedder(EmbedderInterface):
    """Mock 嵌入器（用于测试）"""

    def __init__(self, dimension: int = 768):
        self._dimension = dimension
        self._model_name = "mock-embedder"

    def embed(self, texts: list[str]) -> list[list[float]]:
        import hashlib
        embeddings = []
        for text in texts:
            hash_obj = hashlib.md5(text.encode())
            hash_bytes = hash_obj.digest()
            embedding = [float(b) / 255.0 for b in hash_bytes]
            while len(embedding) < self._dimension:
                embedding.extend(embedding[:min(len(embedding), self._dimension - len(embedding))])
            embeddings.append(embedding[:self._dimension])
        return embeddings

    def embed_single(self, text: str) -> list[float]:
        return self.embed([text])[0]

    @property
    def dimension(self) -> int:
        return self._dimension

    @property
    def model_name(self) -> str:
        return self._model_name

    def is_available(self) -> bool:
        return True


class MockVectorStore(VectorStoreInterface):
    """Mock 向量存储（用于测试）"""

    def __init__(self):
        self._collections: dict[str, dict[str, Any]] = {}

    def create_collection(
        self,
        collection_name: str,
        dimension: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        self._collections[collection_name] = {
            "documents": {},
            "dimension": dimension,
        }
        return True

    def get_or_create_collection(
        self,
        collection_name: str,
        dimension: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Any:
        if collection_name not in self._collections:
            self.create_collection(collection_name, dimension)
        return self._collections[collection_name]

    def delete_collection(self, collection_name: str) -> bool:
        if collection_name in self._collections:
            del self._collections[collection_name]
        return True

    def collection_exists(self, collection_name: str) -> bool:
        return collection_name in self._collections

    def add_documents(
        self,
        collection_name: str,
        documents: list[str],
        embeddings: list[list[float]],
        metadatas: list[dict[str, Any]] | None = None,
        ids: list[str] | None = None,
    ) -> list[str]:
        collection = self._collections.get(collection_name, {})
        if "documents" not in collection:
            collection["documents"] = {}

        import uuid
        doc_ids = ids or [str(uuid.uuid4())[:8] for _ in documents]

        for i, doc_id in enumerate(doc_ids):
            collection["documents"][doc_id] = {
                "id": doc_id,
                "content": documents[i],
                "embedding": embeddings[i],
                "metadata": metadatas[i] if metadatas else {},
            }

        return doc_ids

    def search(
        self,
        collection_name: str,
        query_embedding: list[float],
        top_k: int = 5,
        filter_metadata: dict[str, Any] | None = None,
    ) -> list[Any]:
        from core.interfaces.vector_store import SearchResult

        collection = self._collections.get(collection_name, {})
        documents = collection.get("documents", {})

        results = []
        for doc_id, doc in documents.items():
            if filter_metadata:
                match = all(
                    doc["metadata"].get(k) == v
                    for k, v in filter_metadata.items()
                )
                if not match:
                    continue

            score = self._cosine_similarity(query_embedding, doc["embedding"])
            results.append(SearchResult(
                id=doc_id,
                content=doc["content"],
                score=score,
                metadata=doc["metadata"],
            ))

        results.sort(key=lambda x: x.score, reverse=True)
        return results[:top_k]

    def _cosine_similarity(self, a: list[float], b: list[float]) -> float:
        import math
        dot_product = sum(x * y for x, y in zip(a, b, strict=False))
        norm_a = math.sqrt(sum(x * x for x in a))
        norm_b = math.sqrt(sum(x * x for x in b))
        if norm_a == 0 or norm_b == 0:
            return 0
        return dot_product / (norm_a * norm_b)

    def delete_documents(self, collection_name: str, ids: list[str]) -> bool:
        collection = self._collections.get(collection_name, {})
        documents = collection.get("documents", {})

        for doc_id in ids:
            documents.pop(doc_id, None)

        return True

    def get_document(self, collection_name: str, document_id: str) -> Any | None:
        from core.interfaces.vector_store import Document

        collection = self._collections.get(collection_name, {})
        documents = collection.get("documents", {})

        doc = documents.get(document_id)
        if doc:
            return Document(
                id=doc["id"],
                content=doc["content"],
                embedding=doc["embedding"],
                metadata=doc["metadata"],
            )
        return None

    def get_collection_stats(self, collection_name: str) -> Any:
        from core.interfaces.vector_store import CollectionStats

        collection = self._collections.get(collection_name, {})
        documents = collection.get("documents", {})

        return CollectionStats(
            name=collection_name,
            count=len(documents),
        )

    def count(self, collection_name: str) -> int:
        collection = self._collections.get(collection_name, {})
        documents = collection.get("documents", {})
        return len(documents)


def create_memory_service(
    embedder: EmbedderInterface | None = None,
    vector_store: VectorStoreInterface | None = None,
    use_mock: bool = False,
) -> MemoryServiceRefactored:
    """
    创建记忆服务

    Args:
        embedder: 嵌入器实例
        vector_store: 向量存储实例
        use_mock: 是否使用 Mock 实现

    Returns:
        记忆服务实例
    """
    if use_mock:
        embedder = embedder or MockEmbedder()
        vector_store = vector_store or MockVectorStore()
    else:
        if embedder is None or vector_store is None:
            raise ValueError("必须提供 embedder 和 vector_store，或设置 use_mock=True")

    return MemoryServiceRefactored(
        embedder=embedder,
        vector_store=vector_store,
    )
