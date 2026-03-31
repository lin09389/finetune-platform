"""
记忆 API 服务
"""
import logging
import uuid
from datetime import datetime
from typing import Any

from .models import MemoryItem, MemorySearchResult, MemoryType

logger = logging.getLogger(__name__)


class MemoryAPIService:
    """记忆 API 服务"""

    def __init__(self):
        self._memories: dict[str, MemoryItem] = {}
        self._user_memories: dict[str, list[str]] = {}

    def create_memory(
        self,
        user_id: str,
        content: str,
        memory_type: MemoryType = MemoryType.KNOWLEDGE,
        importance: float = 0.5,
        metadata: dict[str, Any] = None
    ) -> MemoryItem:
        """创建记忆"""
        memory_id = f"mem_{uuid.uuid4().hex[:8]}"

        memory = MemoryItem(
            id=memory_id,
            content=content,
            type=memory_type,
            importance=importance,
            metadata=metadata or {}
        )

        self._memories[memory_id] = memory

        if user_id not in self._user_memories:
            self._user_memories[user_id] = []
        self._user_memories[user_id].append(memory_id)

        logger.info(f"创建记忆: {memory_id} for user {user_id}")
        return memory

    def get_memory(self, memory_id: str) -> MemoryItem | None:
        """获取记忆"""
        memory = self._memories.get(memory_id)
        if memory:
            memory.access_count += 1
            memory.updated_at = datetime.now()
        return memory

    def list_memories(
        self,
        user_id: str,
        memory_type: MemoryType = None,
        limit: int = 50
    ) -> list[MemoryItem]:
        """列出记忆"""
        memory_ids = self._user_memories.get(user_id, [])

        memories = []
        for mid in memory_ids:
            memory = self._memories.get(mid)
            if memory:
                if memory_type and memory.type != memory_type:
                    continue
                memories.append(memory)

        memories.sort(key=lambda m: m.importance, reverse=True)
        return memories[:limit]

    def update_memory(
        self,
        memory_id: str,
        content: str = None,
        importance: float = None,
        metadata: dict[str, Any] = None
    ) -> MemoryItem | None:
        """更新记忆"""
        memory = self._memories.get(memory_id)
        if not memory:
            return None

        if content is not None:
            memory.content = content
        if importance is not None:
            memory.importance = importance
        if metadata is not None:
            memory.metadata.update(metadata)

        memory.updated_at = datetime.now()
        return memory

    def delete_memory(self, memory_id: str) -> bool:
        """删除记忆"""
        if memory_id not in self._memories:
            return False

        del self._memories[memory_id]

        for user_id, memory_ids in self._user_memories.items():
            if memory_id in memory_ids:
                memory_ids.remove(memory_id)

        return True

    def search_memories(
        self,
        user_id: str,
        query: str,
        top_k: int = 5,
        memory_type: MemoryType = None
    ) -> list[MemorySearchResult]:
        """搜索记忆"""
        memory_ids = self._user_memories.get(user_id, [])

        results = []
        query_lower = query.lower()

        for mid in memory_ids:
            memory = self._memories.get(mid)
            if not memory:
                continue

            if memory_type and memory.type != memory_type:
                continue

            content_lower = memory.content.lower()

            if query_lower in content_lower:
                relevance = 0.8
            else:
                query_words = set(query_lower.split())
                content_words = set(content_lower.split())
                common = query_words & content_words
                if query_words:
                    relevance = len(common) / len(query_words)
                else:
                    relevance = 0.0

            if relevance > 0:
                results.append(MemorySearchResult(
                    id=memory.id,
                    content=memory.content,
                    type=memory.type,
                    importance=memory.importance,
                    relevance=relevance,
                    created_at=memory.created_at
                ))

        results.sort(key=lambda r: r.relevance, reverse=True)
        return results[:top_k]

    def get_stats(self, user_id: str) -> dict[str, Any]:
        """获取统计信息"""
        memory_ids = self._user_memories.get(user_id, [])

        type_counts = {}
        total_importance = 0.0

        for mid in memory_ids:
            memory = self._memories.get(mid)
            if memory:
                type_counts[memory.type.value] = type_counts.get(memory.type.value, 0) + 1
                total_importance += memory.importance

        count = len(memory_ids)

        return {
            "total_memories": count,
            "by_type": type_counts,
            "avg_importance": total_importance / count if count > 0 else 0.0
        }

    def clear_memories(self, user_id: str) -> int:
        """清空用户记忆"""
        memory_ids = self._user_memories.get(user_id, [])

        for mid in memory_ids:
            if mid in self._memories:
                del self._memories[mid]

        self._user_memories[user_id] = []

        return len(memory_ids)

    def export_state(self, user_id: str) -> dict:
        """导出记忆状态"""
        memory_ids = self._user_memories.get(user_id, [])
        memories = []
        for mid in memory_ids:
            memory = self._memories.get(mid)
            if memory:
                memories.append({
                    "id": memory.id,
                    "content": memory.content,
                    "type": memory.type.value,
                    "importance": memory.importance,
                    "metadata": memory.metadata,
                    "created_at": memory.created_at.isoformat()
                })
        return {"memories": memories, "user_id": user_id}

    def import_state(self, user_id: str, state: dict) -> bool:
        """导入记忆状态"""
        try:
            memories = state.get("memories", [])
            for m in memories:
                self.create_memory(
                    user_id=user_id,
                    content=m.get("content", ""),
                    memory_type=MemoryType(m.get("type", "knowledge")),
                    importance=m.get("importance", 0.5),
                    metadata=m.get("metadata", {})
                )
            return True
        except Exception as e:
            logger.error(f"导入记忆状态失败: {e}")
            return False

    def get_summary(self, user_id: str) -> dict:
        """获取记忆摘要"""
        memory_ids = self._user_memories.get(user_id, [])
        by_type = {}
        for mid in memory_ids:
            memory = self._memories.get(mid)
            if memory:
                type_name = memory.type.value
                if type_name not in by_type:
                    by_type[type_name] = []
                by_type[type_name].append(memory.id)

        return {
            "total_count": len(memory_ids),
            "by_type": by_type,
            "knowledge_graph": {"nodes": 0, "edges": 0}
        }

    def get_context(self, user_id: str, query: str, session_id: str = None) -> str:
        """获取记忆上下文"""
        results = self.search_memories(user_id, query, top_k=5)
        if not results:
            return ""
        context_parts = [f"[记忆] {r.content}" for r in results]
        return "\n".join(context_parts)

    def list_sessions(self) -> list[str]:
        """列出会话"""
        return list(self._sessions.keys()) if hasattr(self, '_sessions') else []

    def get_session_context(self, session_id: str, max_tokens: int = 4000) -> dict:
        """获取会话上下文"""
        return {
            "context": "",
            "summary": {"message_count": 0, "total_tokens": 0}
        }

    def add_session_message(self, session_id: str, role: str, content: str, entities: list[str] = None) -> bool:
        """添加会话消息"""
        return True

    def clear_session(self, session_id: str) -> bool:
        """清空会话"""
        return True

    def get_active_entities(self, session_id: str, threshold: float = 0.3) -> list[str]:
        """获取活跃实体"""
        return []

    def add_entity(self, name: str, entity_type: str, attributes: dict = None, confidence: float = 0.5) -> tuple:
        """添加实体"""
        entity_id = f"ent_{uuid.uuid4().hex[:8]}"
        return entity_id, True

    def add_relation(self, source_name: str, target_name: str, relation_type: str, evidence: str = "") -> str:
        """添加关系"""
        return f"rel_{uuid.uuid4().hex[:8]}"

    def get_entity(self, entity_id: str) -> dict | None:
        """获取实体"""
        return None

    def get_entity_context(self, entity_id: str, depth: int = 2) -> dict:
        """获取实体上下文"""
        return {"entity": None, "relations": [], "related_entities": []}

    def find_path(self, source_id: str, target_id: str, max_depth: int = 4) -> list:
        """查找路径"""
        return []

    def search_graph(self, query: str, entity_types: list[str] = None, limit: int = 10) -> list:
        """搜索图谱"""
        return []

    def get_graph_stats(self) -> dict:
        """获取图谱统计"""
        return {"entity_types": {}, "total_entities": 0, "total_relations": 0}

    def delete_entity(self, entity_id: str) -> bool:
        """删除实体"""
        return True

    def list_relations(self) -> list:
        """列出关系"""
        return []


_memory_api_service: MemoryAPIService | None = None


def get_memory_api_service() -> MemoryAPIService:
    """获取记忆 API 服务实例"""
    global _memory_api_service
    if _memory_api_service is None:
        _memory_api_service = MemoryAPIService()
    return _memory_api_service
