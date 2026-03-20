"""
模型调度�?- 参�?Ollama sched.go 设计模式
负责模型加载、卸载、缓存管理和并发控制
"""
import asyncio
import logging
import time
from typing import Dict, Optional, Any, List
from datetime import datetime
from dataclasses import dataclass
from enum import Enum
import threading

from core.state import get_state_manager, ModelState
from core.config import get_settings
from api.errors import ModelNotFoundError, ModelLoadFailedError
from api.inference.backends.base import BaseBackend
from api.inference.backends.huggingface import HuggingFaceBackend
from api.inference.backends.ollama import OllamaBackend

logger = logging.getLogger(__name__)


class BackendType(str, Enum):
    HUGGINGFACE = "huggingface"
    OLLAMA = "ollama"
    CLOUD = "cloud"


@dataclass
class LoadRequest:
    """模型加载请求"""
    model_id: str
    backend: BackendType
    priority: int = 0
    callback: Optional[Any] = None


class ModelScheduler:
    """
    模型调度�?    
    参�?Ollama sched.go 的设计：
    - 模型加载/卸载管理
    - LRU 缓存策略
    - 并发控制
    - 后端抽象
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
            self.settings = get_settings()
            self.state = get_state_manager()
            
            self._backends: Dict[str, BaseBackend] = {}
            self._loading: Dict[str, asyncio.Event] = {}
            self._load_queue: asyncio.Queue = None
            
            self._max_models = getattr(self.settings, 'max_cached_models', 3)
            self._default_backend = getattr(self.settings, 'inference_backend', 'huggingface')
            
            self._initialized = True
            logger.info(f"ModelScheduler 初始化完成，最大缓存模型数: {self._max_models}")
    
    def _get_backend(self, backend_type: str) -> BaseBackend:
        """获取后端实例"""
        if backend_type not in self._backends:
            if backend_type == BackendType.HUGGINGFACE.value:
                self._backends[backend_type] = HuggingFaceBackend()
            elif backend_type == BackendType.OLLAMA.value:
                self._backends[backend_type] = OllamaBackend()
            else:
                raise ValueError(f"不支持的后端类型: {backend_type}")
        return self._backends[backend_type]
    
    async def get_model(
        self,
        model_id: str,
        backend: Optional[str] = None
    ) -> ModelState:
        """
        获取模型（自动加载）
        
        参�?Ollama sched.go �?GetModel 方法
        """
        backend_type = backend or self._default_backend
        
        if model_id in self._loading:
            logger.info(f"等待模型加载: {model_id}")
            await self._loading[model_id].wait()
        
        model_state = self.state.get_model(model_id)
        if model_state:
            model_state.touch()
            logger.debug(f"模型命中缓存: {model_id}")
            return model_state
        
        return await self._load_model(model_id, backend_type)
    
    async def _load_model(
        self,
        model_id: str,
        backend_type: str
    ) -> ModelState:
        """加载模型"""
        load_event = asyncio.Event()
        self._loading[model_id] = load_event
        
        try:
            await self._ensure_capacity()
            
            logger.info(f"开始加载模�? {model_id} (backend: {backend_type})")
            start_time = time.time()
            
            backend = self._get_backend(backend_type)
            model_data = await backend.load_model(model_id)
            
            model_state = ModelState(
                model_id=model_id,
                model=model_data.get("model"),
                tokenizer=model_data.get("tokenizer"),
                loaded_at=datetime.now(),
                last_used=datetime.now(),
                use_count=1,
                backend=backend_type,
                device=model_data.get("device", "unknown")
            )
            
            self.state.set_model(model_id, model_state)
            
            elapsed = time.time() - start_time
            logger.info(f"模型加载完成: {model_id}, 耗时: {elapsed:.2f}s")
            
            return model_state
            
        except Exception as e:
            logger.error(f"模型加载失败: {model_id}: {e}")
            raise
        finally:
            del self._loading[model_id]
            load_event.set()
    
    async def _ensure_capacity(self):
        """确保缓存容量"""
        models = self.state.list_models()
        
        while len(models) >= self._max_models:
            oldest_id = min(
                models,
                key=lambda x: self.state.get_model(x).last_used
            )
            logger.info(f"LRU 淘汰模型: {oldest_id}")
            await self.unload_model(oldest_id)
            models = self.state.list_models()
    
    async def unload_model(self, model_id: str) -> bool:
        """卸载模型"""
        model_state = self.state.get_model(model_id)
        if not model_state:
            return False
        
        try:
            backend = self._get_backend(model_state.backend)
            await backend.unload_model(model_id)
            self.state.remove_model(model_id)
            logger.info(f"模型已卸�? {model_id}")
            return True
        except Exception as e:
            logger.error(f"卸载模型失败: {model_id}: {e}")
            return False
    
    async def unload_all(self):
        """卸载所有模�?""
        models = self.state.list_models()
        for model_id in list(models):
            await self.unload_model(model_id)
        logger.info("所有模型已卸载")
    
    async def get_backend(self, backend_type: Optional[str] = None) -> BaseBackend:
        """获取后端实例"""
        return self._get_backend(backend_type or self._default_backend)
    
    async def list_models(self, backend: Optional[str] = None) -> List[Dict[str, Any]]:
        """列出可用模型"""
        if backend:
            backend_instance = self._get_backend(backend)
            return await backend_instance.list_models()
        
        all_models = []
        for backend_type in [BackendType.HUGGINGFACE.value, BackendType.OLLAMA.value]:
            try:
                backend_instance = self._get_backend(backend_type)
                models = await backend_instance.list_models()
                all_models.extend(models)
            except Exception as e:
                logger.warning(f"获取 {backend_type} 模型列表失败: {e}")
        
        return all_models
    
    async def is_backend_available(self, backend_type: str) -> bool:
        """检查后端是否可�?""
        try:
            backend = self._get_backend(backend_type)
            return await backend.is_available()
        except Exception:
            return False
    
    async def get_stats(self) -> Dict[str, Any]:
        """获取调度器统�?""
        models = self.state.list_models()
        model_stats = []
        
        for model_id in models:
            state = self.state.get_model(model_id)
            if state:
                model_stats.append({
                    "model_id": model_id,
                    "backend": state.backend,
                    "loaded_at": state.loaded_at.isoformat(),
                    "last_used": state.last_used.isoformat(),
                    "use_count": state.use_count,
                    "device": state.device,
                })
        
        backend_status = {}
        for backend_type in [BackendType.HUGGINGFACE.value, BackendType.OLLAMA.value]:
            backend_status[backend_type] = await self.is_backend_available(backend_type)
        
        return {
            "cached_models": len(models),
            "max_models": self._max_models,
            "default_backend": self._default_backend,
            "models": model_stats,
            "backend_status": backend_status,
        }
    
    def set_default_backend(self, backend: str):
        """设置默认后端"""
        if backend in [b.value for b in BackendType]:
            self._default_backend = backend
            self.settings.inference_backend = backend
            logger.info(f"默认后端已切换到: {backend}")
        else:
            raise ValueError(f"不支持的后端类型: {backend}")


_scheduler: Optional[ModelScheduler] = None


def get_scheduler() -> ModelScheduler:
    """获取调度器单�?""
    global _scheduler
    if _scheduler is None:
        _scheduler = ModelScheduler()
    return _scheduler
