"""
记忆模块服务�?- 整合记忆管理功能
"""
from typing import Dict, List, Optional, Any
import logging
from datetime import datetime
import uuid

logger = logging.getLogger(__name__)


class MemoryService:
    """记忆服务 - 统一记忆管理"""
    
    def __init__(self):
        self._memory_service = None
        self._enhanced_service = None
        self._short_term_memories: Dict[str, Dict[str, Any]] = {}
    
    def _get_base_service(self):
        """延迟加载基础记忆服务"""
        if self._memory_service is None:
            from memory.memory_service import get_memory_service
            self._memory_service = get_memory_service()
        return self._memory_service
    
    def _get_enhanced_service(self):
        """延迟加载增强记忆服务"""
        if self._enhanced_service is None:
            try:
                from memory.enhanced_memory_service import get_enhanced_memory_service
                self._enhanced_service = get_enhanced_memory_service()
            except Exception as e:
                logger.warning(f"增强记忆服务加载失败: {e}")
        return self._enhanced_service
    
    def extract_and_store(
        self,
        message: str,
        role: str,
        user_id: str = "default"
    ) -> List[Dict[str, Any]]:
        """从消息中提取并存储记�?""
        base_service = self._get_base_service()
        
        memories = base_service.extract_and_store(
            message=message,
            role=role,
            user_id=user_id
        )
        
        enhanced_service = self._get_enhanced_service()
        if enhanced_service:
            try:
                enhanced_service.process_message(
                    message=message,
                    role=role,
                    user_id=user_id
                )
            except Exception as e:
                logger.warning(f"增强记忆处理失败: {e}")
        
        return memories
    
    def recall(
        self,
        query: str,
        user_id: str = "default",
        top_k: int = 5,
        memory_type: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """检索相关记�?""
        base_service = self._get_base_service()
        
        memories = base_service.recall(
            query=query,
            user_id=user_id,
            top_k=top_k,
            memory_type=memory_type
        )
        
        return memories
    
    def store(
        self,
        content: str,
        memory_type: str = "fact",
        user_id: str = "default",
        confidence: float = 1.0,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """直接存储记忆"""
        base_service = self._get_base_service()
        
        memory = base_service.store(
            content=content,
            memory_type=memory_type,
            user_id=user_id,
            confidence=confidence,
            metadata=metadata
        )
        
        return memory
    
    def list_memories(
        self,
        user_id: str = "default",
        memory_type: Optional[str] = None,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """列出所有记�?""
        base_service = self._get_base_service()
        
        memories = base_service.list_memories(
            user_id=user_id,
            memory_type=memory_type,
            limit=limit
        )
        
        return memories
    
    def forget(self, user_id: str, memory_id: str) -> bool:
        """删除记忆"""
        base_service = self._get_base_service()
        
        success = base_service.forget(user_id, memory_id)
        
        return success
    
    def clear_memories(
        self,
        user_id: str = "default",
        memory_type: Optional[str] = None
    ) -> int:
        """清空记忆"""
        base_service = self._get_base_service()
        
        count = base_service.clear_memories(user_id, memory_type)
        
        return count
    
    def get_stats(self, user_id: str = "default") -> Dict[str, Any]:
        """获取统计信息"""
        base_service = self._get_base_service()
        
        stats = base_service.get_stats(user_id)
        
        enhanced_service = self._get_enhanced_service()
        if enhanced_service:
            try:
                enhanced_stats = enhanced_service.get_stats(user_id)
                stats["enhanced"] = enhanced_stats
            except Exception as e:
                logger.warning(f"获取增强记忆统计失败: {e}")
        
        return stats
    
    def get_knowledge_graph(
        self,
        user_id: str = "default",
        entity_type: Optional[str] = None
    ) -> Dict[str, Any]:
        """获取知识图谱"""
        enhanced_service = self._get_enhanced_service()
        
        if enhanced_service and hasattr(enhanced_service, 'get_knowledge_graph'):
            return enhanced_service.get_knowledge_graph(user_id, entity_type)
        
        return {"entities": [], "relations": []}
    
    def get_short_term_memory(self, session_id: str) -> Dict[str, Any]:
        """获取短期记忆"""
        if session_id in self._short_term_memories:
            return self._short_term_memories[session_id]
        
        return {
            "messages": [],
            "entity_mentions": {},
            "summary": None
        }
    
    def update_short_term_memory(
        self,
        session_id: str,
        message: Dict[str, Any],
        entities: Optional[Dict[str, float]] = None
    ):
        """更新短期记忆"""
        if session_id not in self._short_term_memories:
            self._short_term_memories[session_id] = {
                "messages": [],
                "entity_mentions": {},
                "summary": None
            }
        
        stm = self._short_term_memories[session_id]
        stm["messages"].append(message)
        
        if entities:
            for entity, score in entities.items():
                current = stm["entity_mentions"].get(entity, 0)
                stm["entity_mentions"][entity] = max(current, score)
    
    def clear_short_term_memory(self, session_id: str):
        """清空短期记忆"""
        if session_id in self._short_term_memories:
            del self._short_term_memories[session_id]


_memory_service: Optional[MemoryService] = None


def get_memory_service() -> MemoryService:
    """获取记忆服务单例"""
    global _memory_service
    if _memory_service is None:
        _memory_service = MemoryService()
    return _memory_service
