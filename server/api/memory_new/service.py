# -*- coding: utf-8 -*-
"""
记忆 API 服务
"""
from typing import List, Dict, Optional, Any
import uuid
from datetime import datetime
import logging

from .models import MemoryItem, MemoryType, MemorySearchResult

logger = logging.getLogger(__name__)


class MemoryAPIService:
    """记忆 API 服务"""
    
    def __init__(self):
        self._memories: Dict[str, MemoryItem] = {}
        self._user_memories: Dict[str, List[str]] = {}
    
    def create_memory(
        self,
        user_id: str,
        content: str,
        memory_type: MemoryType = MemoryType.KNOWLEDGE,
        importance: float = 0.5,
        metadata: Dict[str, Any] = None
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
    
    def get_memory(self, memory_id: str) -> Optional[MemoryItem]:
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
    ) -> List[MemoryItem]:
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
        metadata: Dict[str, Any] = None
    ) -> Optional[MemoryItem]:
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
    ) -> List[MemorySearchResult]:
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
    
    def get_stats(self, user_id: str) -> Dict[str, Any]:
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


_memory_api_service: Optional[MemoryAPIService] = None


def get_memory_api_service() -> MemoryAPIService:
    """获取记忆 API 服务实例"""
    global _memory_api_service
    if _memory_api_service is None:
        _memory_api_service = MemoryAPIService()
    return _memory_api_service
