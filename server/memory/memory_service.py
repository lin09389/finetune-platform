"""
智能记忆服务
核心业务逻辑：提取、存储、检索、管理记忆
"""
import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from core.storage import MemoryRepository, vector_reconcile_enabled

from .memory_extractor import MemoryExtractor
from .models import MEMORY_TYPE_LABELS, MemoryType

logger = logging.getLogger(__name__)


class MemoryService:
    """智能记忆服务"""

    def __init__(self, vector_db_path: str = "data/memories"):
        """
        初始化记忆服务
        Args:
            vector_db_path: 向量数据库路径
        """
        self.embedder = None
        self.vector_store = None
        self._embedding_available = False

        try:
            from rag.embedder import get_embedder
            from rag.vector_store import get_vector_store

            self.embedder = get_embedder("shibing624/text2vec-base-chinese")
            self.vector_store = get_vector_store(vector_db_path)
            self._embedding_available = True
            logger.info("嵌入模型加载成功，完整记忆功能可用")
        except Exception as e:
            logger.warning(f"嵌入模型加载失败，使用简化模式: {e}")
            logger.warning("记忆提取功能可用，但向量检索功能不可用")

        self.extractor = MemoryExtractor()
        self.repository = MemoryRepository()
        self.simple_memories: dict[str, list[dict]] = {}

        self.data_dir = Path(vector_db_path).parent
        self.data_dir.mkdir(parents=True, exist_ok=True)

        logger.info("记忆服务已初始化")

    def extract_and_store(
        self,
        message: str,
        role: str,
        user_id: str = "default"
    ) -> list[dict[str, Any]]:
        """
        提取并存储记忆
        Args:
            message: 消息内容
            role: 角色
            user_id: 用户 ID

        Returns:
            存储的记忆列表
        """
        extracted = self.extractor.extract(message, role)

        if not extracted:
            return []

        stored = []
        for mem in extracted:
            try:
                memory_id = self._store_memory(user_id, mem)
                stored.append({
                    'id': memory_id,
                    'content': mem['content'],
                    'type': mem['type']
                })
                logger.debug(f"记忆已存储: {mem['content'][:30]}...")
            except Exception as e:
                logger.error(f"存储记忆失败: {e}")

        if stored:
            logger.info(f"成功存储 {len(stored)} 条记忆")

        return stored

    def _store_memory(self, user_id: str, memory: dict) -> str:
        """存储单条记忆"""
        memory_id = memory.get("id") or f"mem_{uuid.uuid4().hex[:8]}"
        now = datetime.now().isoformat()
        item = self.repository.create({
            "id": memory_id,
            "user_id": user_id,
            "content": memory.get("content", ""),
            "type": memory.get("type", "knowledge"),
            "importance": memory.get("importance", 0.5),
            "source": memory.get("source", "unknown"),
            "metadata": memory.get("metadata", {}) or {},
            "vector_state": "pending",
            "created_at": memory.get("created_at") or now,
            "updated_at": memory.get("updated_at") or now,
        })

        if self._upsert_vector(item):
            self.repository.update_vector_state(memory_id, "ready")
        else:
            self.repository.update_vector_state(memory_id, "failed")

        return memory_id

    def _upsert_vector(self, memory: dict[str, Any]) -> bool:
        if not (self._embedding_available and self.embedder and self.vector_store):
            return False

        try:
            collection_name = f"memories_{memory['user_id']}"
            try:
                self.vector_store.delete_documents(collection_name=collection_name, ids=[memory["id"]])
            except Exception:
                pass
            embedding = self.embedder.embed_single(memory["content"])
            metadata = {
                "id": memory["id"],
                "user_id": memory["user_id"],
                "type": memory.get("type", "knowledge"),
                "importance": memory.get("importance", 0.5),
                "source": memory.get("source", "unknown"),
                "created_at": memory.get("created_at", datetime.now().isoformat()),
                "access_count": memory.get("access_count", 0),
            }
            self.vector_store.add_documents(
                collection_name=collection_name,
                documents=[memory["content"]],
                embeddings=[embedding],
                metadatas=[metadata],
                ids=[memory["id"]],
            )
            return True
        except Exception as e:
            logger.warning(f"向量写入失败，标记为 failed: {e}")
            return False

    def recall(
        self,
        query: str,
        user_id: str = "default",
        top_k: int = 5,
        memory_type: str | None = None
    ) -> list[dict[str, Any]]:
        """
        检索相关记忆
        Args:
            query: 查询文本
            user_id: 用户 ID
            top_k: 返回数量
            memory_type: 记忆类型过滤

        Returns:
            相关记忆列表
        """
        if self._embedding_available and self.embedder and self.vector_store:
            try:
                query_embedding = self.embedder.embed_single(query)

                filter_metadata = None
                if memory_type:
                    filter_metadata = {"type": memory_type}

                results = self.vector_store.search(
                    collection_name=f"memories_{user_id}",
                    query_embedding=query_embedding,
                    top_k=top_k,
                    filter_metadata=filter_metadata
                )

                ids: list[str] = []
                scores: dict[str, float] = {}
                for result in results:
                    meta = result.get('metadata', {})
                    memory_id = meta.get("id")
                    if memory_id:
                        ids.append(memory_id)
                        scores[memory_id] = float(result.get("score", 0) or 0)

                memories = self.repository.get_many(ids, user_id=user_id)
                for memory in memories:
                    memory["relevance"] = scores.get(memory["id"], 0.0)
                    memory["storage_mode"] = "vector"

                logger.info(f"向量检索到 {len(memories)} 条相关记忆")
                if memories:
                    return memories
            except Exception as e:
                logger.warning(f"向量检索失败，使用简化检索: {e}")

        memories = self.repository.search_text(
            query=query,
            user_id=user_id,
            top_k=top_k,
            memory_type=memory_type,
        )
        for memory in memories:
            memory["storage_mode"] = "text_only"
        return memories

    def list_memories(
        self,
        user_id: str = "default",
        memory_type: str | None = None,
        limit: int = 50
    ) -> list[dict[str, Any]]:
        """
        列出所有记忆
        Args:
            user_id: 用户 ID
            memory_type: 记忆类型过滤
            limit: 返回数量

        Returns:
            记忆列表
        """
        return self.repository.list(user_id=user_id, memory_type=memory_type, limit=limit)

    def forget(self, user_id: str, memory_id: str) -> bool:
        """
        删除记忆

        Args:
            user_id: 用户 ID
            memory_id: 记忆 ID

        Returns:
            是否成功
        """
        success = self.repository.delete(memory_id=memory_id, user_id=user_id)

        if self._embedding_available and self.vector_store:
            try:
                self.vector_store.delete_documents(
                    collection_name=f"memories_{user_id}",
                    ids=[memory_id]
                )
            except Exception as e:
                logger.warning(f"向量存储删除失败: {e}")

        if success:
            logger.info(f"记忆已删除: {memory_id}")

        return success

    def clear_all(self, user_id: str = "default") -> bool:
        """
        清除用户所有记忆
        Args:
            user_id: 用户 ID

        Returns:
            是否成功
        """
        try:
            cleared = self.repository.clear_user(user_id)
            if self.vector_store:
                try:
                    self.vector_store.delete_collection(f"memories_{user_id}")
                except Exception as e:
                    logger.warning(f"向量集合清除失败: {e}")
            logger.info(f"已清除用户 {user_id} 的所有记忆")
            return cleared >= 0
        except Exception as e:
            logger.error(f"清除记忆失败: {e}")
            return False

    def get_context_with_memory(
        self,
        query: str,
        user_id: str = "default",
        max_memories: int = 5
    ) -> str:
        """
        获取包含记忆的上下文

        Args:
            query: 查询文本
            user_id: 用户 ID
            max_memories: 最大记忆数量
        Returns:
            格式化的上下文
        """
        memories = self.recall(query, user_id, top_k=max_memories)

        if not memories:
            return ""

        context_parts = ["【相关记忆】"]
        for mem in memories:
            context_parts.append(f"- {mem['content']}")

        return "\n".join(context_parts)

    def get_user_summary(self, user_id: str = "default") -> dict[str, Any]:
        """
        获取用户记忆摘要

        Args:
            user_id: 用户 ID

        Returns:
            摘要信息
        """
        memories = self.list_memories(user_id, limit=100)

        by_type: dict[str, list[str]] = {}
        for mem in memories:
            mem_type = mem['type']
            if mem_type not in by_type:
                by_type[mem_type] = []
            by_type[mem_type].append(mem['content'])

        summary = {
            'total_count': len(memories),
            'by_type': {
                MEMORY_TYPE_LABELS.get(MemoryType(k), k): v
                for k, v in by_type.items()
            },
            'recent_memories': memories[:5] if memories else []
        }

        return summary

    def get_stats(self, user_id: str = "default") -> dict[str, Any]:
        """
        获取记忆统计

        Args:
            user_id: 用户 ID

        Returns:
            统计信息
        """
        try:
            stats = self.repository.stats(user_id)
            if self.vector_store:
                try:
                    vector_stats = self.vector_store.get_collection_stats(f"memories_{user_id}")
                    stats["vector_collection_count"] = vector_stats.get("count", 0)
                    stats["collection_name"] = vector_stats.get("name", "")
                except Exception:
                    stats["vector_collection_count"] = 0
            return stats
        except Exception:
            return {'total_memories': 0}

    def update_memory(
        self,
        memory_id: str,
        user_id: str = "default",
        content: str | None = None,
        importance: float | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        current = self.repository.get(memory_id, user_id=user_id, increment_access=False)
        if not current:
            return None
        updates: dict[str, Any] = {}
        if content is not None:
            updates["content"] = content
            updates["vector_state"] = "pending"
        if importance is not None:
            updates["importance"] = importance
        if metadata is not None:
            merged = current.get("metadata", {}).copy()
            merged.update(metadata)
            updates["metadata"] = merged
        updated = self.repository.update(memory_id=memory_id, user_id=user_id, **updates)
        if updated and content is not None:
            if self._upsert_vector(updated):
                self.repository.update_vector_state(memory_id, "ready")
                updated["vector_state"] = "ready"
                updated["storage_mode"] = "vector"
            else:
                self.repository.update_vector_state(memory_id, "failed")
                updated["vector_state"] = "failed"
                updated["storage_mode"] = "text_only"
        return updated

    def get_memory(
        self,
        memory_id: str,
        user_id: str = "default",
        increment_access: bool = True,
    ) -> dict[str, Any] | None:
        return self.repository.get(memory_id, user_id=user_id, increment_access=increment_access)

    def reconcile_vectors(self, limit: int = 100) -> dict[str, Any]:
        if not vector_reconcile_enabled():
            return {"enabled": False, "attempted": 0, "ready": 0, "failed": 0}

        pending = self.repository.pending_vectors(limit=limit)
        result = {"enabled": True, "attempted": len(pending), "ready": 0, "failed": 0}
        for memory in pending:
            if self._upsert_vector(memory):
                self.repository.update_vector_state(memory["id"], "ready")
                result["ready"] += 1
            else:
                self.repository.update_vector_state(memory["id"], "failed")
                result["failed"] += 1
        return result


_memory_service: MemoryService | None = None


def get_memory_service() -> MemoryService:
    """获取记忆服务实例"""
    global _memory_service
    if _memory_service is None:
        _memory_service = MemoryService()
    return _memory_service


def reset_memory_service(vector_db_path: str = "data/memories") -> MemoryService:
    """重置记忆服务"""
    global _memory_service
    _memory_service = MemoryService(vector_db_path)
    return _memory_service
