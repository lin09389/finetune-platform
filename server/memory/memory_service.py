"""
智能记忆服务
核心业务逻辑：提取、存储、检索、管理记�?"""
from typing import List, Dict, Any, Optional
from datetime import datetime
import uuid
import logging
import os
from pathlib import Path

from .memory_extractor import MemoryExtractor
from .models import MemoryType, MEMORY_IMPORTANCE, MEMORY_TYPE_LABELS

logger = logging.getLogger(__name__)


class MemoryService:
    """智能记忆服务"""

    def __init__(self, vector_db_path: str = "data/memories"):
        """
        初始化记忆服�?
        Args:
            vector_db_path: 向量数据库路�?        """
        # 尝试加载嵌入模型（可能失败）
        self.embedder = None
        self.vector_store = None
        self._embedding_available = False

        try:
            from rag.embedder import get_embedder
            from rag.vector_store import get_vector_store

            self.embedder = get_embedder("shibing624/text2vec-base-chinese")
            self.vector_store = get_vector_store(vector_db_path)
            self._embedding_available = True
            logger.info("嵌入模型加载成功，完整记忆功能可�?)
        except Exception as e:
            logger.warning(f"嵌入模型加载失败，使用简化模�? {e}")
            logger.warning("记忆提取功能可用，但向量检索功能不可用")

        # 记忆提取器（始终可用�?        self.extractor = MemoryExtractor()

        # 简化存储（无向量时的备选方案）
        self.simple_memories: Dict[str, List[Dict]] = {}

        # 确保数据目录存在
        self.data_dir = Path(vector_db_path).parent
        self.data_dir.mkdir(parents=True, exist_ok=True)

        logger.info("记忆服务已初始化")

    def extract_and_store(
        self,
        message: str,
        role: str,
        user_id: str = "default"
    ) -> List[Dict[str, Any]]:
        """
        提取并存储记�?
        Args:
            message: 消息内容
            role: 角色
            user_id: 用户 ID

        Returns:
            存储的记忆列�?        """
        # 1. 提取记忆
        extracted = self.extractor.extract(message, role)

        if not extracted:
            return []

        # 2. 存储记忆
        stored = []
        for mem in extracted:
            try:
                memory_id = self._store_memory(user_id, mem)
                stored.append({
                    'id': memory_id,
                    'content': mem['content'],
                    'type': mem['type']
                })
                logger.debug(f"记忆已存�? {mem['content'][:30]}...")
            except Exception as e:
                logger.error(f"存储记忆失败: {e}")

        if stored:
            logger.info(f"成功存储 {len(stored)} 条记�?)

        return stored

    def _store_memory(self, user_id: str, memory: Dict) -> str:
        """存储单条记忆"""
        memory_id = f"mem_{uuid.uuid4().hex[:8]}"

        # 元数�?        metadata = {
            'user_id': user_id,
            'type': memory['type'],
            'importance': memory['importance'],
            'source': memory.get('source', 'unknown'),
            'created_at': datetime.now().isoformat(),
            'access_count': 0
        }

        # 如果嵌入模型可用，使用向量存�?        if self._embedding_available and self.embedder and self.vector_store:
            try:
                # 向量�?                embedding = self.embedder.embed_single(memory['content'])

                # 存储到向量库
                self.vector_store.add_documents(
                    collection_name=f"memories_{user_id}",
                    documents=[memory['content']],
                    embeddings=[embedding],
                    metadatas=[metadata],
                    ids=[memory_id]
                )
                return memory_id
            except Exception as e:
                logger.warning(f"向量存储失败，使用简化存�? {e}")

        # 简化存储（无向量）
        if user_id not in self.simple_memories:
            self.simple_memories[user_id] = []

        self.simple_memories[user_id].append({
            'id': memory_id,
            'content': memory['content'],
            **metadata
        })

        return memory_id

    def recall(
        self,
        query: str,
        user_id: str = "default",
        top_k: int = 5,
        memory_type: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        检索相关记�?
        Args:
            query: 查询文本
            user_id: 用户 ID
            top_k: 返回数量
            memory_type: 记忆类型过滤

        Returns:
            相关记忆列表
        """
        memories = []

        # 如果嵌入模型可用，使用向量搜�?        if self._embedding_available and self.embedder and self.vector_store:
            try:
                # 向量化查�?                query_embedding = self.embedder.embed_single(query)

                # 构建过滤条件
                filter_metadata = None
                if memory_type:
                    filter_metadata = {"type": memory_type}

                # 搜索
                results = self.vector_store.search(
                    collection_name=f"memories_{user_id}",
                    query_embedding=query_embedding,
                    top_k=top_k,
                    filter_metadata=filter_metadata
                )

                # 格式化结�?                for result in results:
                    meta = result.get('metadata', {})
                    memories.append({
                        'id': meta.get('id', ''),
                        'content': result['content'],
                        'type': meta.get('type', 'knowledge'),
                        'importance': meta.get('importance', 0.5),
                        'created_at': meta.get('created_at', ''),
                        'access_count': meta.get('access_count', 0),
                        'relevance': result.get('score', 0)
                    })

                logger.info(f"向量检索到 {len(memories)} 条相关记�?)
                return memories
            except Exception as e:
                logger.warning(f"向量检索失败，使用简化检�? {e}")

        # 简化检索（关键词匹配）
        if user_id in self.simple_memories:
            for mem in self.simple_memories[user_id]:
                if memory_type and mem.get('type') != memory_type:
                    continue

                # 简单的关键词匹�?                relevance = 0.5
                query_lower = query.lower()
                content_lower = mem['content'].lower()

                # 计算简单的相关性分�?                query_words = set(query_lower.split())
                content_words = set(content_lower.split())
                common_words = query_words & content_words
                if query_words:
                    relevance = len(common_words) / len(query_words)

                memories.append({
                    'id': mem['id'],
                    'content': mem['content'],
                    'type': mem.get('type', 'knowledge'),
                    'importance': mem.get('importance', 0.5),
                    'created_at': mem.get('created_at', ''),
                    'access_count': mem.get('access_count', 0),
                    'relevance': relevance
                })

        # 按相关性排�?        memories.sort(key=lambda x: x.get('relevance', 0), reverse=True)
        return memories[:top_k]

    def list_memories(
        self,
        user_id: str = "default",
        memory_type: Optional[str] = None,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """
        列出所有记�?
        Args:
            user_id: 用户 ID
            memory_type: 记忆类型过滤
            limit: 返回数量

        Returns:
            记忆列表
        """
        memories = []

        # 如果嵌入模型可用，使用向量存�?        if self._embedding_available and self.vector_store:
            try:
                collection = self.vector_store.get_or_create_collection(
                    f"memories_{user_id}"
                )

                all_data = collection.get(include=["metadatas", "documents"])

                if all_data['metadatas'] and all_data['documents']:
                    for i, (meta, doc) in enumerate(
                        zip(all_data['metadatas'], all_data['documents'])
                    ):
                        if memory_type and meta.get('type') != memory_type:
                            continue

                        memories.append({
                            'id': all_data['ids'][i],
                            'content': doc,
                            'type': meta.get('type', 'knowledge'),
                            'importance': meta.get('importance', 0.5),
                            'created_at': meta.get('created_at', ''),
                            'access_count': meta.get('access_count', 0)
                        })
            except Exception as e:
                logger.warning(f"向量存储读取失败: {e}")

        # 简化存�?        if user_id in self.simple_memories:
            for mem in self.simple_memories[user_id]:
                if memory_type and mem.get('type') != memory_type:
                    continue
                memories.append(mem)

        # 按重要性排�?        memories.sort(key=lambda x: x['importance'], reverse=True)

        return memories[:limit]

    def forget(self, user_id: str, memory_id: str) -> bool:
        """
        删除记忆

        Args:
            user_id: 用户 ID
            memory_id: 记忆 ID

        Returns:
            是否成功
        """
        success = False

        # 尝试从向量存储删�?        if self._embedding_available and self.vector_store:
            try:
                self.vector_store.delete_documents(
                    collection_name=f"memories_{user_id}",
                    ids=[memory_id]
                )
                success = True
            except Exception as e:
                logger.warning(f"向量存储删除失败: {e}")

        # 从简化存储删�?        if user_id in self.simple_memories:
            self.simple_memories[user_id] = [
                m for m in self.simple_memories[user_id]
                if m['id'] != memory_id
            ]
            success = True

        if success:
            logger.info(f"记忆已删�? {memory_id}")

        return success

    def clear_all(self, user_id: str = "default") -> bool:
        """
        清除用户所有记�?
        Args:
            user_id: 用户 ID

        Returns:
            是否成功
        """
        try:
            self.vector_store.delete_collection(f"memories_{user_id}")
            logger.info(f"已清除用�?{user_id} 的所有记�?)
            return True
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
            max_memories: 最大记忆数�?
        Returns:
            格式化的上下�?        """
        # 检索相关记�?        memories = self.recall(query, user_id, top_k=max_memories)

        if not memories:
            return ""

        # 构建上下�?        context_parts = ["【相关记忆�?]
        for mem in memories:
            context_parts.append(f"- {mem['content']}")

        return "\n".join(context_parts)

    def get_user_summary(self, user_id: str = "default") -> Dict[str, Any]:
        """
        获取用户记忆摘要

        Args:
            user_id: 用户 ID

        Returns:
            摘要信息
        """
        memories = self.list_memories(user_id, limit=100)

        # 按类型分�?        by_type: Dict[str, List[str]] = {}
        for mem in memories:
            mem_type = mem['type']
            if mem_type not in by_type:
                by_type[mem_type] = []
            by_type[mem_type].append(mem['content'])

        # 统计
        summary = {
            'total_count': len(memories),
            'by_type': {
                MEMORY_TYPE_LABELS.get(MemoryType(k), k): v
                for k, v in by_type.items()
            },
            'recent_memories': memories[:5] if memories else []
        }

        return summary

    def get_stats(self, user_id: str = "default") -> Dict[str, Any]:
        """
        获取记忆统计

        Args:
            user_id: 用户 ID

        Returns:
            统计信息
        """
        try:
            stats = self.vector_store.get_collection_stats(f"memories_{user_id}")
            return {
                'total_memories': stats.get('count', 0),
                'collection_name': stats.get('name', '')
            }
        except Exception:
            return {'total_memories': 0}


# 单例实例
_memory_service: Optional[MemoryService] = None


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
