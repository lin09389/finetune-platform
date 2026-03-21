# -*- coding: utf-8 -*-
"""
统一状态管理器 - 参考 Ollama sched.go 设计模式
管理所有运行时状态：模型缓存、会话状态、记忆状态
"""
import asyncio
import threading
import time
import gc
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from datetime import datetime
from collections import OrderedDict
import logging

logger = logging.getLogger(__name__)


@dataclass
class ModelState:
    """模型状态"""
    model_id: str
    model: Any
    tokenizer: Any
    loaded_at: datetime
    last_used: datetime
    use_count: int = 0
    memory_usage: int = 0
    backend: str = "huggingface"
    device: str = "cuda"
    
    def touch(self):
        """更新最后使用时间"""
        self.last_used = datetime.now()
        self.use_count += 1


@dataclass
class SessionState:
    """会话状态"""
    session_id: str
    messages: List[Dict[str, Any]] = field(default_factory=list)
    context: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def add_message(self, role: str, content: str, **kwargs):
        """添加消息"""
        message = {
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat(),
            **kwargs
        }
        self.messages.append(message)
        self.updated_at = datetime.now()
        return message
    
    def get_context_window(self, max_tokens: int = 4000) -> List[Dict[str, Any]]:
        """获取上下文窗口"""
        return self.messages[-max_tokens:]
    
    def clear(self):
        """清空会话"""
        self.messages.clear()
        self.context.clear()
        self.updated_at = datetime.now()


@dataclass
class MemoryState:
    """记忆状态"""
    user_id: str
    short_term: List[Dict[str, Any]] = field(default_factory=list)
    entities: Dict[str, Any] = field(default_factory=dict)
    last_updated: datetime = field(default_factory=datetime.now)


class ModelCache:
    """
    模型缓存 - LRU 策略
    
    参考 Ollama sched.go 的模型管理设计
    """
    
    def __init__(self, max_size: int = 3, ttl_seconds: int = 3600):
        self.max_size = max_size
        self.ttl_seconds = ttl_seconds
        self._cache: OrderedDict[str, ModelState] = OrderedDict()
        self._lock = threading.RLock()
    
    def get(self, model_id: str) -> Optional[ModelState]:
        """获取模型（更新LRU顺序）"""
        with self._lock:
            if model_id in self._cache:
                state = self._cache[model_id]
                if self._is_expired(state):
                    self._remove(model_id)
                    return None
                self._cache.move_to_end(model_id)
                state.touch()
                return state
            return None
    
    def set(self, model_id: str, state: ModelState) -> None:
        """设置模型"""
        with self._lock:
            if model_id in self._cache:
                self._cache.move_to_end(model_id)
                self._cache[model_id] = state
            else:
                while len(self._cache) >= self.max_size:
                    self._evict_lru()
                self._cache[model_id] = state
    
    def remove(self, model_id: str) -> bool:
        """移除模型"""
        with self._lock:
            return self._remove(model_id)
    
    def _remove(self, model_id: str) -> bool:
        """内部移除方法"""
        if model_id in self._cache:
            state = self._cache.pop(model_id)
            self._cleanup_model(state)
            return True
        return False
    
    def _evict_lru(self):
        """淘汰最久未使用的模型"""
        if self._cache:
            model_id, state = self._cache.popitem(last=False)
            logger.info(f"LRU 淘汰模型: {model_id}")
            self._cleanup_model(state)
    
    def _is_expired(self, state: ModelState) -> bool:
        """检查是否过期"""
        if self.ttl_seconds <= 0:
            return False
        elapsed = (datetime.now() - state.last_used).total_seconds()
        return elapsed > self.ttl_seconds
    
    def _cleanup_model(self, state: ModelState):
        """清理模型资源"""
        try:
            if hasattr(state.model, 'cpu'):
                state.model.cpu()
            del state.model
            del state.tokenizer
            gc.collect()
            
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                torch.cuda.synchronize()
        except Exception as e:
            logger.warning(f"清理模型资源失败: {e}")
    
    def clear(self):
        """清空缓存"""
        with self._lock:
            for model_id in list(self._cache.keys()):
                self._remove(model_id)
    
    def size(self) -> int:
        """获取缓存大小"""
        return len(self._cache)
    
    def list_cached(self) -> List[str]:
        """列出缓存的模型"""
        return list(self._cache.keys())
    
    def get_stats(self) -> Dict[str, Any]:
        """获取缓存统计"""
        with self._lock:
            return {
                "size": len(self._cache),
                "max_size": self.max_size,
                "ttl_seconds": self.ttl_seconds,
                "models": [
                    {
                        "model_id": model_id,
                        "loaded_at": state.loaded_at.isoformat(),
                        "last_used": state.last_used.isoformat(),
                        "use_count": state.use_count,
                        "backend": state.backend,
                    }
                    for model_id, state in self._cache.items()
                ]
            }


class SessionManager:
    """
    会话管理器
    
    统一管理所有会话状态
    """
    
    def __init__(self, max_sessions: int = 100):
        self.max_sessions = max_sessions
        self._sessions: Dict[str, SessionState] = {}
        self._lock = threading.RLock()
    
    def get(self, session_id: str) -> Optional[SessionState]:
        """获取会话"""
        with self._lock:
            return self._sessions.get(session_id)
    
    def create(self, session_id: str, **kwargs) -> SessionState:
        """创建会话"""
        with self._lock:
            if session_id in self._sessions:
                return self._sessions[session_id]
            
            if len(self._sessions) >= self.max_sessions:
                self._evict_oldest()
            
            session = SessionState(session_id=session_id, **kwargs)
            self._sessions[session_id] = session
            return session
    
    def get_or_create(self, session_id: str) -> SessionState:
        """获取或创建会话"""
        session = self.get(session_id)
        if session is None:
            session = self.create(session_id)
        return session
    
    def delete(self, session_id: str) -> bool:
        """删除会话"""
        with self._lock:
            if session_id in self._sessions:
                del self._sessions[session_id]
                return True
            return False
    
    def _evict_oldest(self):
        """淘汰最旧的会话"""
        if self._sessions:
            oldest_id = min(
                self._sessions.keys(),
                key=lambda x: self._sessions[x].updated_at
            )
            del self._sessions[oldest_id]
            logger.info(f"淘汰旧会话: {oldest_id}")
    
    def list_sessions(self) -> List[str]:
        """列出所有会话"""
        return list(self._sessions.keys())
    
    def clear(self):
        """清空所有会话"""
        with self._lock:
            self._sessions.clear()
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        with self._lock:
            return {
                "total_sessions": len(self._sessions),
                "max_sessions": self.max_sessions,
                "sessions": [
                    {
                        "session_id": session_id,
                        "message_count": len(session.messages),
                        "created_at": session.created_at.isoformat(),
                        "updated_at": session.updated_at.isoformat(),
                    }
                    for session_id, session in self._sessions.items()
                ]
            }


class StateManager:
    """
    统一状态管理器
    
    管理所有运行时状态：
    - 模型缓存
    - 会话状态
    - 记忆状态
    """
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if not hasattr(self, '_initialized'):
            self.model_cache = ModelCache(max_size=3, ttl_seconds=3600)
            self.session_manager = SessionManager(max_sessions=100)
            self._memory_states: Dict[str, MemoryState] = {}
            self._memory_lock = threading.RLock()
            self._initialized = True
            logger.info("StateManager 初始化完成")
    
    def get_model(self, model_id: str) -> Optional[ModelState]:
        """获取模型状态"""
        return self.model_cache.get(model_id)
    
    def set_model(self, model_id: str, state: ModelState) -> None:
        """设置模型状态"""
        self.model_cache.set(model_id, state)
    
    def remove_model(self, model_id: str) -> bool:
        """移除模型"""
        return self.model_cache.remove(model_id)
    
    def list_models(self) -> List[str]:
        """列出缓存的模型"""
        return self.model_cache.list_cached()
    
    def get_model_stats(self) -> Dict[str, Any]:
        """获取模型缓存统计"""
        return self.model_cache.get_stats()
    
    def get_session(self, session_id: str) -> Optional[SessionState]:
        """获取会话"""
        return self.session_manager.get(session_id)
    
    def create_session(self, session_id: str) -> SessionState:
        """创建会话"""
        return self.session_manager.create(session_id)
    
    def get_or_create_session(self, session_id: str) -> SessionState:
        """获取或创建会话"""
        return self.session_manager.get_or_create(session_id)
    
    def delete_session(self, session_id: str) -> bool:
        """删除会话"""
        return self.session_manager.delete(session_id)
    
    def list_sessions(self) -> List[str]:
        """列出所有会话"""
        return self.session_manager.list_sessions()
    
    def get_session_stats(self) -> Dict[str, Any]:
        """获取会话统计"""
        return self.session_manager.get_stats()
    
    def get_memory_state(self, user_id: str) -> MemoryState:
        """获取记忆状态"""
        with self._memory_lock:
            if user_id not in self._memory_states:
                self._memory_states[user_id] = MemoryState(user_id=user_id)
            return self._memory_states[user_id]
    
    def update_memory_state(self, user_id: str, **kwargs) -> None:
        """更新记忆状态"""
        with self._memory_lock:
            state = self.get_memory_state(user_id)
            for key, value in kwargs.items():
                if hasattr(state, key):
                    setattr(state, key, value)
            state.last_updated = datetime.now()
    
    def clear_memory_state(self, user_id: str) -> bool:
        """清空记忆状态"""
        with self._memory_lock:
            if user_id in self._memory_states:
                del self._memory_states[user_id]
                return True
            return False
    
    def clear_all(self):
        """清空所有状态"""
        self.model_cache.clear()
        self.session_manager.clear()
        with self._memory_lock:
            self._memory_states.clear()
        logger.info("所有状态已清空")
    
    def get_full_stats(self) -> Dict[str, Any]:
        """获取完整统计"""
        return {
            "models": self.get_model_stats(),
            "sessions": self.get_session_stats(),
            "memory_users": len(self._memory_states),
        }


_state_manager: Optional[StateManager] = None


def get_state_manager() -> StateManager:
    """获取状态管理器单例"""
    global _state_manager
    if _state_manager is None:
        _state_manager = StateManager()
    return _state_manager


def get_model_cache() -> ModelCache:
    """获取模型缓存"""
    return get_state_manager().model_cache


def get_session_manager() -> SessionManager:
    """获取会话管理器"""
    return get_state_manager().session_manager
