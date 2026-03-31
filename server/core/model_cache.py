"""
模型缓存模块 - 带有 LRU 淘汰策略
"""
import logging
import threading
from collections import OrderedDict
from typing import Any

logger = logging.getLogger(__name__)


class ModelCache:
    """
    带有 LRU 淘汰策略的模型缓存
    
    特性：
    - 最大容量限制
    - LRU 淘汰策略
    - 线程安全
    - 自动清理 GPU 内存
    """

    def __init__(self, max_size: int = 3):
        self._cache: OrderedDict[str, dict[str, Any]] = OrderedDict()
        self._max_size = max_size
        self._lock = threading.Lock()

    def get(self, model_id: str) -> dict[str, Any] | None:
        """获取缓存项（会更新访问顺序）"""
        with self._lock:
            if model_id in self._cache:
                self._cache.move_to_end(model_id)
                return self._cache[model_id]
            return None

    def set(self, model_id: str, value: dict[str, Any]) -> None:
        """设置缓存项"""
        with self._lock:
            if model_id in self._cache:
                self._cache.move_to_end(model_id)
                self._cache[model_id] = value
            else:
                while len(self._cache) >= self._max_size:
                    self._evict_oldest()
                self._cache[model_id] = value

    def _evict_oldest(self) -> None:
        """淘汰最旧的缓存项"""
        if not self._cache:
            return

        oldest_id, oldest_item = next(iter(self._cache.items()))

        try:
            if "model" in oldest_item:
                model = oldest_item["model"]
                if hasattr(model, "cpu"):
                    model.cpu()
                del model

            from core.utils import cleanup_gpu_memory
            cleanup_gpu_memory()
            logger.info(f"淘汰缓存模型：{oldest_id}")
        except Exception as e:
            logger.warning(f"清理模型资源失败：{e}")

        del self._cache[oldest_id]

    def remove(self, model_id: str) -> bool:
        """移除指定缓存项"""
        with self._lock:
            if model_id in self._cache:
                item = self._cache.pop(model_id)
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
        """清空所有缓存"""
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
            logger.info("模型缓存已清空")

    def size(self) -> int:
        """获取缓存大小"""
        with self._lock:
            return len(self._cache)

    def list_cached(self) -> list[str]:
        """获取已缓存的模型列表"""
        with self._lock:
            return list(self._cache.keys())

    def contains(self, model_id: str) -> bool:
        """检查是否包含指定模型"""
        with self._lock:
            return model_id in self._cache


_model_cache: ModelCache | None = None
_cache_lock = threading.Lock()


def get_model_cache(max_size: int = 3) -> ModelCache:
    """获取模型缓存实例"""
    global _model_cache
    with _cache_lock:
        if _model_cache is None:
            _model_cache = ModelCache(max_size=max_size)
        return _model_cache
