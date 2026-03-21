# -*- coding: utf-8 -*-
"""
智能记忆服务
核心业务逻辑：提取、存储、检索、管理记忆
"""
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
        self.simple_memories: Dict[str, List[Dict]] = {}

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

    def _store_memory(self, user_id: str, memory: Dict) -> str:
        """存储单条记忆"""
        memory_id = f"mem_{uuid.uuid4().hex[:8]}"

        metadata = {
            'user_id': user_id,
            'type': memory['type'],
            'importance': memory['importance'],
            'source': memory.get('source', 'unknown'),
            'created_at': datetime.now().isoformat(),
            'access_count': 0
        }

        if self._embedding_available and self.embedder and self.vector_store:
            try:
                embedding = self.embedder.embed_single(memory['content'])

                self.vector_store.add_documents(
                    collection_name=f"memories_{user_id}",
                    documents=[memory['content']],
                    embeddings=[embedding],
                    metadatas=[metadata],
                    ids=[memory_id]
                )
                return memory_id
            except Exception as e:
                logger.warning(f"向量存储失败，使用简化存储: {e}")

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
        检索相关记忆
        Args:
            query: 查询文本
            user_id: 用户 ID
            top_k: 返回数量
            memory_type: 记忆类型过滤

        Returns:
            相关记忆列表
        """
        memories = []

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

                for result in results:
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

                logger.info(f"向量检索到 {len(memories)} 条相关记忆")
                return memories
            except Exception as e:
                logger.warning(f"向量检索失败，使用简化检索: {e}")

        if user_id in self.simple_memories:
            for mem in self.simple_memories[user_id]:
                if memory_type and mem.get('type') != memory_type:
                    continue

                relevance = 0.5
                query_lower = query.lower()
                content_lower = mem['content'].lower()

                query_words = set(query_lower.split())
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

        memories.sort(key=lambda x: x.get('relevance', 0), reverse=True)
        return memories[:top_k]

    def list_memories(
        self,
        user_id: str = "default",
        memory_type: Optional[str] = None,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """
        列出所有记忆
        Args:
            user_id: 用户 ID
            memory_type: 记忆类型过滤
            limit: 返回数量

        Returns:
            记忆列表
        """
        memories = []

        if self._embedding_available and self.vector_store:
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

        if user_id in self.simple_memories:
            for mem in self.simple_memories[user_id]:
                if memory_type and mem.get('type') != memory_type:
                    continue
                memories.append(mem)

        memories.sort(key=lambda x: x['importance'], reverse=True)

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

        if self._embedding_available and self.vector_store:
            try:
                self.vector_store.delete_documents(
                    collection_name=f"memories_{user_id}",
                    ids=[memory_id]
                )
                success = True
            except Exception as e:
                logger.warning(f"向量存储删除失败: {e}")

        if user_id in self.simple_memories:
            self.simple_memories[user_id] = [
                m for m in self.simple_memories[user_id]
                if m['id'] != memory_id
            ]
            success = True

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
            self.vector_store.delete_collection(f"memories_{user_id}")
            logger.info(f"已清除用户 {user_id} 的所有记忆")
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

    def get_user_summary(self, user_id: str = "default") -> Dict[str, Any]:
        """
        获取用户记忆摘要

        Args:
            user_id: 用户 ID

        Returns:
            摘要信息
        """
        memories = self.list_memories(user_id, limit=100)

        by_type: Dict[str, List[str]] = {}
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
