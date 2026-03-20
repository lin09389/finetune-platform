from skills.base import SkillBase, SkillContext
from skills.models import SkillExecution, SkillResult
from memory.memory_service import MemoryService
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timedelta
import json
import re
import logging

logger = logging.getLogger(__name__)


class MemoryAwareSkill(SkillBase):
    """
    记忆感知技能基�?    
    功能�?    - 记忆上下文注入钩�?    - 记忆相关性排�?    - 记忆压缩和摘�?    - 跨会话记忆检�?    - 用户偏好学习
    """
    
    def __init__(self):
        super().__init__()
        self._memory_service: Optional[MemoryService] = None
        self._user_id: str = "default"
        self._session_id: Optional[str] = None
        self._memory_context: Dict[str, Any] = {}
    
    def set_memory_service(self, memory_service: MemoryService) -> None:
        self._memory_service = memory_service
    
    def set_user_id(self, user_id: str) -> None:
        self._user_id = user_id
    
    def set_session_id(self, session_id: str) -> None:
        self._session_id = session_id
    
    async def recall_memory(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        if not self._memory_service:
            return []
        return await self._memory_service.recall(
            query=query,
            user_id=self._user_id,
            top_k=top_k
        )
    
    async def store_memory(self, content: str, memory_type: str = "operation", importance: float = 0.5) -> List[Dict[str, Any]]:
        if not self._memory_service:
            return []
        return await self._memory_service.extract_and_store(
            message=content,
            role="assistant",
            user_id=self._user_id
        )
    
    async def get_user_preferences(self) -> Dict[str, Any]:
        memories = await self.recall_memory("用户偏好 设置 偏好", top_k=10)
        preferences = {}
        for mem in memories:
            content = mem.get("content", "")
            if "=" in content or ":" in content:
                separator = "=" if "=" in content else ":"
                parts = content.split(separator, 1)
                if len(parts) == 2:
                    key = parts[0].strip().replace("用户偏好", "").strip()
                    value = parts[1].strip()
                    if key:
                        preferences[key] = value
        return preferences
    
    async def rank_memories_by_relevance(
        self, 
        memories: List[Dict[str, Any]], 
        query: str,
        context: Optional[Dict[str, Any]] = None
    ) -> List[Tuple[Dict[str, Any], float]]:
        """
        按相关性排序记�?        
        使用多维度评分：
        - 语义相似�?        - 时间衰减
        - 重要性权�?        - 上下文匹�?        """
        ranked = []
        query_lower = query.lower()
        query_keywords = set(re.findall(r'\w+', query_lower))
        
        now = datetime.now()
        
        for mem in memories:
            score = 0.0
            content = mem.get("content", "").lower()
            
            keyword_overlap = len(query_keywords & set(re.findall(r'\w+', content)))
            score += keyword_overlap * 0.3
            
            timestamp_str = mem.get("timestamp") or mem.get("created_at")
            if timestamp_str:
                try:
                    timestamp = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
                    age_hours = (now - timestamp).total_seconds() / 3600
                    time_score = max(0, 1 - (age_hours / 720))
                    score += time_score * 0.3
                except Exception:
                    pass
            
            importance = mem.get("importance", 0.5)
            score += importance * 0.2
            
            if context:
                context_keys = set(context.keys())
                mem_keys = set(mem.get("metadata", {}).keys())
                context_match = len(context_keys & mem_keys) / max(len(context_keys), 1)
                score += context_match * 0.2
            
            ranked.append((mem, score))
        
        ranked.sort(key=lambda x: x[1], reverse=True)
        return ranked
    
    async def compress_memories(
        self, 
        memories: List[Dict[str, Any]], 
        max_length: int = 1000
    ) -> str:
        """
        压缩和摘要记�?        
        将多条记忆压缩为简洁的摘要
        """
        if not memories:
            return ""
        
        total_length = sum(len(mem.get("content", "")) for mem in memories)
        
        if total_length <= max_length:
            return "\n".join(mem.get("content", "") for mem in memories)
        
        type_groups: Dict[str, List[str]] = {}
        for mem in memories:
            mem_type = mem.get("memory_type", "general")
            content = mem.get("content", "")
            if mem_type not in type_groups:
                type_groups[mem_type] = []
            type_groups[mem_type].append(content)
        
        summaries = []
        for mem_type, contents in type_groups.items():
            if len(contents) > 3:
                summary = f"[{mem_type}] �?{len(contents)} 条记�?
                unique_items = list(set(contents))[:3]
                for item in unique_items:
                    summary += f"\n  - {item[:100]}..."
            else:
                summary = f"[{mem_type}]\n" + "\n".join(f"  - {c[:100]}" for c in contents)
            summaries.append(summary)
        
        return "\n\n".join(summaries)
    
    async def recall_cross_session(
        self, 
        query: str, 
        exclude_current: bool = True,
        top_k: int = 10
    ) -> List[Dict[str, Any]]:
        """
        跨会话记忆检�?        
        检索所有会话中的相关记�?        """
        if not self._memory_service:
            return []
        
        memories = await self._memory_service.recall(
            query=query,
            user_id=self._user_id,
            top_k=top_k * 2
        )
        
        if exclude_current and self._session_id:
            memories = [
                mem for mem in memories
                if mem.get("session_id") != self._session_id
            ]
        
        return memories[:top_k]
    
    async def inject_memory_context(
        self, 
        parameters: Dict[str, Any],
        max_memories: int = 5,
        max_context_length: int = 2000
    ) -> Dict[str, Any]:
        """
        注入记忆上下文到参数
        
        在技能执行前自动调用
        """
        query = json.dumps(parameters, ensure_ascii=False)
        
        raw_memories = await self.recall_memory(query, top_k=max_memories * 2)
        ranked_memories = await self.rank_memories_by_relevance(raw_memories, query)
        top_memories = [m for m, s in ranked_memories[:max_memories]]
        
        compressed = await self.compress_memories(top_memories, max_context_length)
        
        preferences = await self.get_user_preferences()
        
        self._memory_context = {
            "relevant_memories": top_memories,
            "compressed_context": compressed,
            "user_preferences": preferences,
            "injected_at": datetime.now().isoformat(),
        }
        
        parameters["_memory_context"] = self._memory_context
        
        return parameters
    
    async def run_with_memory(
        self,
        parameters: Dict[str, Any],
        execution_id: Optional[str] = None,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        **kwargs
    ) -> SkillExecution:
        if user_id:
            self._user_id = user_id
        if session_id:
            self._session_id = session_id
        
        parameters = await self.inject_memory_context(parameters)
        
        execution = await self.run(
            parameters=parameters,
            execution_id=execution_id,
            user_id=self._user_id,
            session_id=self._session_id,
            **kwargs
        )
        
        await self._after_execute(execution)
        
        return execution
    
    async def _before_execute(self, parameters: Dict[str, Any]) -> Dict[str, Any]:
        context: Dict[str, Any] = {}
        query = json.dumps(parameters, ensure_ascii=False)
        memories = await self.recall_memory(query)
        context["relevant_memories"] = memories
        preferences = await self.get_user_preferences()
        context["user_preferences"] = preferences
        return context
    
    async def _after_execute(self, execution: SkillExecution) -> None:
        if execution.result and execution.result.success:
            await self.store_memory(
                content=f"执行技�?{execution.skill_name}: {execution.result.message or '成功'}",
                memory_type="operation"
            )


class OperationMemoryMixin:
    _memory_service: Optional[MemoryService] = None
    _user_id: str = "default"
    
    async def recall_memory(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        if not self._memory_service:
            return []
        return await self._memory_service.recall(
            query=query,
            user_id=self._user_id,
            top_k=top_k
        )
    
    async def store_memory(self, content: str, memory_type: str = "operation", importance: float = 0.5) -> List[Dict[str, Any]]:
        if not self._memory_service:
            return []
        return await self._memory_service.extract_and_store(
            message=content,
            role="assistant",
            user_id=self._user_id
        )
    
    async def record_operation(self, operation_type: str, params: Dict[str, Any], result: Optional[SkillResult]) -> None:
        record = {
            "operation_type": operation_type,
            "params": params,
            "result": result.model_dump() if result else None,
            "timestamp": datetime.now().isoformat()
        }
        await self.store_memory(
            content=json.dumps(record, ensure_ascii=False),
            memory_type="operation_history"
        )
    
    async def get_operation_history(self, operation_type: Optional[str] = None, limit: int = 20) -> List[Dict[str, Any]]:
        query = f"操作 {operation_type}" if operation_type else "操作历史"
        memories = await self.recall_memory(query, top_k=limit)
        return memories


class PreferenceLearningMixin:
    _memory_service: Optional[MemoryService] = None
    _user_id: str = "default"
    
    async def recall_memory(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        if not self._memory_service:
            return []
        return await self._memory_service.recall(
            query=query,
            user_id=self._user_id,
            top_k=top_k
        )
    
    async def store_memory(self, content: str, memory_type: str = "preference", importance: float = 0.5) -> List[Dict[str, Any]]:
        if not self._memory_service:
            return []
        return await self._memory_service.extract_and_store(
            message=content,
            role="assistant",
            user_id=self._user_id
        )
    
    async def get_user_preferences(self) -> Dict[str, Any]:
        memories = await self.recall_memory("用户偏好 设置 偏好", top_k=10)
        preferences = {}
        for mem in memories:
            content = mem.get("content", "")
            if "=" in content or ":" in content:
                separator = "=" if "=" in content else ":"
                parts = content.split(separator, 1)
                if len(parts) == 2:
                    key = parts[0].strip().replace("用户偏好", "").strip()
                    value = parts[1].strip()
                    if key:
                        preferences[key] = value
        return preferences
    
    async def learn_preference(self, key: str, value: Any) -> None:
        await self.store_memory(
            content=f"用户偏好: {key} = {value}",
            memory_type="preference",
            importance=0.8
        )
    
    async def apply_preference(self, params: Dict[str, Any]) -> Dict[str, Any]:
        preferences = await self.get_user_preferences()
        for key, value in preferences.items():
            if key not in params:
                params[key] = value
        return params
