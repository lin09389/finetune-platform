"""
模型缓存模块 - 带有 LRU 淘汰策略
"""
import threading
import time
import logging
from collections import OrderedDict
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)


class ModelCache:
    """
    带有 LRU 淘汰策略的模型缓�?    
    特性：
    - 最大容量限�?    - LRU 淘汰策略
    - 线程安全
    - 自动清理 GPU 内存
    """
    
    def __init__(self, max_size: int = 3):
        self._cache: OrderedDict[str, Dict[str, Any]] = OrderedDict()
        self._max_size = max_size
        self._lock = threading.Lock()
    
    def get(self, model_id: str) -> Optional[Dict[str, Any]]:
        """获取缓存项（会更新访问顺序）"""
        with self._lock:
            if model_id in self._cache:
                # 移动到末尾（最近使用）
                self._cache.move_to_end(model_id)
                return self._cache[model_id]
            return None
    
    def set(self, model_id: str, value: Dict[str, Any]) -> None:
        """设置缓存�?""
        with self._lock:
            if model_id in self._cache:
                # 更新已存在的�?                self._cache.move_to_end(model_id)
                self._cache[model_id] = value
            else:
                # 检查是否需要淘�?                while len(self._cache) >= self._max_size:
                    self._evict_oldest()
                self._cache[model_id] = value
    
    def _evict_oldest(self) -> None:
        """淘汰最旧的缓存�?""
        if not self._cache:
            return
        
        # 获取最旧的项（第一个）
        oldest_id, oldest_item = next(iter(self._cache.items()))
        
        # 清理模型资源
        try:
            if "model" in oldest_item:
                model = oldest_item["model"]
                if hasattr(model, "cpu"):
                    model.cpu()
                del model
            
            # 清理 GPU 内存
            from core.utils import cleanup_gpu_memory
            cleanup_gpu_memory()
            logger.info(f"淘汰缓存模型：{oldest_id}")
        except Exception as e:
            logger.warning(f"清理模型资源失败：{e}")
        
        # 从缓存中移除
        del self._cache[oldest_id]
    
    def remove(self, model_id: str) -> bool:
        """移除指定缓存�?""
        with self._lock:
            if model_id in self._cache:
                item = self._cache.pop(model_id)
                # 清理资源
                try:
                    if "model" in item:
                        model = item["model"]
                        if hasattr(model, "cpu"):
                            model.cpu()
                        del model
                    
                    from core.utils import cleanup_gpu_memory
                    cleanup_gpu_memory()
                except Exception as e:
                    logger.warning(f"清理模型资源失败：{e}")
                return True
            return False
    
    def clear(self) -> None:
        """清空所有缓�?""
        with self._lock:
            for model_id, item in list(self._cache.items()):
                try:
                    if "model" in item:
                        model = item["model"]
                        if hasattr(model, "cpu"):
                            model.cpu()
                        del model
                except Exception as e:
                    logger.warning(f"清理模型 {model_id} 失败：{e}")
            self._cache.clear()
            
            from core.utils import cleanup_gpu_memory
            cleanup_gpu_memory()
            logger.info("模型缓存已清�?)
    
    def size(self) -> int:
        """获取缓存大小"""
        with self._lock:
            return len(self._cache)
    
    def list_cached(self) -> List[str]:
        """获取已缓存的模型列表"""
        with self._lock:
            return list(self._cache.keys())
    
    def contains(self, model_id: str) -> bool:
        """检查是否包含指定模�?""
        with self._lock:
            return model_id in self._cache


# 全局模型缓存实例
_model_cache: Optional[ModelCache] = None
_cache_lock = threading.Lock()


def get_model_cache(max_size: int = 3) -> ModelCache:
    """获取模型缓存实例"""
    global _model_cache
    with _cache_lock:
        if _model_cache is None:
            _model_cache = ModelCache(max_size=max_size)
        return _model_cache
