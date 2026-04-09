"""
RAG 知识库 - 向量存储
使用 ChromaDB 进行向量存储和检索
"""
import logging
import uuid
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class VectorStore:
    """向量存储"""

    def __init__(self, db_path: str = "data/vectors"):
        """
        初始化向量存储

        Args:
            db_path: 数据库路径
        """
        self.db_path = Path(db_path)
        self.db_path.mkdir(parents=True, exist_ok=True)

        self._client = None
        self._collections: dict[str, Any] = {}

    def _get_client(self):
        """懒加载客户端"""
        if self._client is None:
            import chromadb
            from chromadb.config import Settings

            self._client = chromadb.PersistentClient(
                path=str(self.db_path),
                settings=Settings(
                    anonymized_telemetry=False,
                    allow_reset=True
                )
            )
            logger.info(f"ChromaDB 已初始化：{self.db_path}")

        return self._client

    def get_or_create_collection(self, name: str) -> Any:
        """
        获取或创建集合

        Args:
            name: 集合名称

        Returns:
            集合对象
        """
        if name not in self._collections:
            client = self._get_client()
            self._collections[name] = client.get_or_create_collection(
                name=name,
                metadata={"hnsw:space": "cosine"}
            )
            logger.info(f"集合已加载：{name}")

        return self._collections[name]

    def add_documents(
        self,
        collection_name: str,
        documents: list[str],
        embeddings: list[list[float]] | None = None,
        metadatas: list[dict[str, Any]] | None = None,
        ids: list[str] | None = None
    ) -> list[str]:
        """
        添加文档到集合

        Args:
            collection_name: 集合名称
            documents: 文档内容列表
            embeddings: 向量列表（可选，不提供则使用集合默认）
            metadatas: 元数据列表
            ids: 文档 ID 列表（可选，自动生成）

        Returns:
            文档 ID 列表
        """
        collection = self.get_or_create_collection(collection_name)

        if ids is None:
            ids = [f"doc_{uuid.uuid4().hex[:12]}" for _ in range(len(documents))]

        add_data = {
            "documents": documents,
            "ids": ids
        }

        if embeddings:
            add_data["embeddings"] = embeddings

        if metadatas:
            add_data["metadatas"] = metadatas

        collection.add(**add_data)

        logger.info(f"已添加 {len(documents)} 个文档到集合 {collection_name}")
        return ids

    def search(
        self,
        collection_name: str,
        query_embedding: list[float],
        top_k: int = 5,
        filter_metadata: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        """
        搜索相似文档

        Args:
            collection_name: 集合名称
            query_embedding: 查询向量
            top_k: 返回结果数量
            filter_metadata: 元数据过滤条件

        Returns:
            搜索结果列表
        """
        collection = self.get_or_create_collection(collection_name)

        query_params = {
            "query_embeddings": [query_embedding],
            "n_results": top_k,
            "include": ["documents", "metadatas", "distances"]
        }

        if filter_metadata:
            query_params["where"] = filter_metadata

        results = collection.query(**query_params)

        if not results or not results['documents']:
            return []

        docs = results['documents'][0]
        metadatas = results['metadatas'][0] if results['metadatas'] else [{}] * len(docs)
        distances = results['distances'][0] if results['distances'] else [0.0] * len(docs)

        search_results = []
        for i, doc in enumerate(docs):
            search_results.append({
                "content": doc,
                "metadata": metadatas[i],
                "distance": float(distances[i]),
                "score": 1.0 - float(distances[i])
            })

        return search_results

    def search_by_text(
        self,
        collection_name: str,
        query_text: str,
        embedder: Any,
        top_k: int = 5,
        filter_metadata: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        """
        通过文本搜索相似文档

        Args:
            collection_name: 集合名称
            query_text: 查询文本
            embedder: 向量化器实例
            top_k: 返回结果数量
            filter_metadata: 元数据过滤条件

        Returns:
            搜索结果列表
        """
        query_embedding = embedder.embed_single(query_text)

        return self.search(collection_name, query_embedding, top_k, filter_metadata)

    def delete_collection(self, collection_name: str):
        """
        删除集合

        Args:
            collection_name: 集合名称
        """
        client = self._get_client()
        client.delete_collection(name=collection_name)

        if collection_name in self._collections:
            del self._collections[collection_name]

        logger.info(f"集合已删除：{collection_name}")

    def delete_documents(self, collection_name: str, ids: list[str]):
        """
        删除文档

        Args:
            collection_name: 集合名称
            ids: 文档 ID 列表
        """
        collection = self.get_or_create_collection(collection_name)
        collection.delete(ids=ids)
        logger.info(f"已删除 {len(ids)} 个文档")

    def get_collection_stats(self, collection_name: str) -> dict[str, Any]:
        """
        获取集合统计信息

        Args:
            collection_name: 集合名称

        Returns:
            统计信息
        """
        collection = self.get_or_create_collection(collection_name)

        return {
            "name": collection_name,
            "count": collection.count(),
            "path": str(self.db_path)
        }

    def list_collections(self) -> list[str]:
        """
        列出所有集合

        Returns:
            集合名称列表
        """
        client = self._get_client()
        collections = client.list_collections()
        return [c.name for c in collections]

    def get_documents_by_ids(
        self,
        collection_name: str,
        ids: list[str]
    ) -> list[dict[str, Any]]:
        """
        根据 ID 获取文档

        Args:
            collection_name: 集合名称
            ids: 文档 ID 列表

        Returns:
            文档列表
        """
        collection = self.get_or_create_collection(collection_name)

        results = collection.get(
            ids=ids,
            include=["documents", "metadatas"]
        )

        docs = []
        for i, doc in enumerate(results['documents']):
            docs.append({
                "id": results['ids'][i],
                "content": doc,
                "metadata": results['metadatas'][i] if results['metadatas'] else {}
            })

        return docs

    def list_documents(self, collection_name: str) -> list[str]:
        """列出集合中的所有文档 ID"""
        collection = self.get_or_create_collection(collection_name)
        results = collection.get(include=["metadatas"])

        doc_ids = set()
        if results['metadatas']:
            for meta in results['metadatas']:
                doc_id = meta.get('doc_id')
                if doc_id:
                    doc_ids.add(doc_id)

        return list(doc_ids)


_store_instance: VectorStore | None = None


def get_vector_store(db_path: str | None = None) -> VectorStore:
    """获取向量存储实例"""
    global _store_instance
    if _store_instance is None:
        path = db_path or "data/vectors"
        _store_instance = VectorStore(path)
    return _store_instance


def reset_vector_store(db_path: str) -> VectorStore:
    """重置向量存储"""
    global _store_instance
    _store_instance = VectorStore(db_path)
    return _store_instance
