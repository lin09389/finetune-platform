"""
向量存储接口 - 用于向量数据库操作
实现依赖倒置原则，支持多种向量数据库后端
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class Document:
    """文档对象"""
    id: str
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)
    embedding: list[float] | None = None
    created_at: datetime = field(default_factory=datetime.now)


@dataclass
class SearchResult:
    """搜索结果"""
    id: str
    content: str
    score: float
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class CollectionStats:
    """集合统计"""
    name: str
    count: int
    metadata: dict[str, Any] = field(default_factory=dict)


class VectorStoreInterface(ABC):
    """
    向量存储接口

    定义向量数据库操作的标准接口，支持多种后端：
    - ChromaDB
    - Milvus
    - Pinecone
    - Weaviate
    """

    @abstractmethod
    def create_collection(
        self,
        collection_name: str,
        dimension: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        """
        创建集合

        Args:
            collection_name: 集合名称
            dimension: 向量维度
            metadata: 集合元数据

        Returns:
            是否成功
        """
        pass

    @abstractmethod
    def get_or_create_collection(
        self,
        collection_name: str,
        dimension: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Any:
        """
        获取或创建集合

        Args:
            collection_name: 集合名称
            dimension: 向量维度
            metadata: 集合元数据

        Returns:
            集合对象
        """
        pass

    @abstractmethod
    def delete_collection(self, collection_name: str) -> bool:
        """
        删除集合

        Args:
            collection_name: 集合名称

        Returns:
            是否成功
        """
        pass

    @abstractmethod
    def collection_exists(self, collection_name: str) -> bool:
        """
        检查集合是否存在

        Args:
            collection_name: 集合名称

        Returns:
            是否存在
        """
        pass

    @abstractmethod
    def add_documents(
        self,
        collection_name: str,
        documents: list[str],
        embeddings: list[list[float]],
        metadatas: list[dict[str, Any]] | None = None,
        ids: list[str] | None = None,
    ) -> list[str]:
        """
        添加文档

        Args:
            collection_name: 集合名称
            documents: 文档内容列表
            embeddings: 向量列表
            metadatas: 元数据列表
            ids: 文档 ID 列表

        Returns:
            文档 ID 列表
        """
        pass

    @abstractmethod
    def search(
        self,
        collection_name: str,
        query_embedding: list[float],
        top_k: int = 5,
        filter_metadata: dict[str, Any] | None = None,
    ) -> list[SearchResult]:
        """
        向量搜索

        Args:
            collection_name: 集合名称
            query_embedding: 查询向量
            top_k: 返回数量
            filter_metadata: 元数据过滤条件

        Returns:
            搜索结果列表
        """
        pass

    @abstractmethod
    def delete_documents(
        self,
        collection_name: str,
        ids: list[str],
    ) -> bool:
        """
        删除文档

        Args:
            collection_name: 集合名称
            ids: 文档 ID 列表

        Returns:
            是否成功
        """
        pass

    @abstractmethod
    def get_document(
        self,
        collection_name: str,
        document_id: str,
    ) -> Document | None:
        """
        获取单个文档

        Args:
            collection_name: 集合名称
            document_id: 文档 ID

        Returns:
            文档对象
        """
        pass

    @abstractmethod
    def get_collection_stats(self, collection_name: str) -> CollectionStats:
        """
        获取集合统计信息

        Args:
            collection_name: 集合名称

        Returns:
            集合统计
        """
        pass

    @abstractmethod
    def count(self, collection_name: str) -> int:
        """
        获取文档数量

        Args:
            collection_name: 集合名称

        Returns:
            文档数量
        """
        pass

    def update_document(
        self,
        collection_name: str,
        document_id: str,
        content: str | None = None,
        embedding: list[float] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        """
        更新文档（默认实现：删除后添加）

        Args:
            collection_name: 集合名称
            document_id: 文档 ID
            content: 新内容
            embedding: 新向量
            metadata: 新元数据

        Returns:
            是否成功
        """
        self.delete_documents(collection_name, [document_id])

        if content and embedding:
            self.add_documents(
                collection_name,
                [content],
                [embedding],
                [metadata] if metadata else None,
                [document_id],
            )

        return True

    def clear_collection(self, collection_name: str) -> bool:
        """
        清空集合

        Args:
            collection_name: 集合名称

        Returns:
            是否成功
        """
        stats = self.get_collection_stats(collection_name)
        if stats.count == 0:
            return True

        self.delete_collection(collection_name)
        self.create_collection(collection_name)
        return True
