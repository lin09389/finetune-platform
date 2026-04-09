"""
KV Cache 优化模块
实现高效的键值缓存管理，减少推理延迟和内存占用
"""
import hashlib
import json
import logging
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class CacheStrategy(str, Enum):
    """缓存策略"""
    LRU = "lru"
    LFU = "lfu"
    FIFO = "fifo"
    TTL = "ttl"


@dataclass
class CacheEntry:
    """缓存条目"""
    key: str
    value: Any
    size: int
    created_at: float = field(default_factory=time.time)
    last_accessed: float = field(default_factory=time.time)
    access_count: int = 0
    ttl: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def is_expired(self) -> bool:
        """检查是否过期"""
        if self.ttl is None:
            return False
        return time.time() - self.created_at > self.ttl

    def touch(self):
        """更新访问信息"""
        self.last_accessed = time.time()
        self.access_count += 1


@dataclass
class CacheStats:
    """缓存统计"""
    total_entries: int = 0
    total_size: int = 0
    hits: int = 0
    misses: int = 0
    evictions: int = 0
    hit_rate: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_entries": self.total_entries,
            "total_size": self.total_size,
            "total_size_mb": round(self.total_size / (1024 * 1024), 2),
            "hits": self.hits,
            "misses": self.misses,
            "evictions": self.evictions,
            "hit_rate": round(self.hit_rate, 4),
        }


class KVCache:
    """
    键值缓存管理器

    功能：
    - 多种缓存策略（LRU/LFU/FIFO/TTL）
    - 内存限制和自动淘汰
    - 缓存预热
    - 统计信息
    """

    def __init__(
        self,
        max_size: int = 1024 * 1024 * 1024,
        max_entries: int = 10000,
        strategy: CacheStrategy = CacheStrategy.LRU,
        default_ttl: float | None = None,
    ):
        self.max_size = max_size
        self.max_entries = max_entries
        self.strategy = strategy
        self.default_ttl = default_ttl

        self._cache: OrderedDict[str, CacheEntry] = OrderedDict()
        self._lock = threading.RLock()
        self._stats = CacheStats()

        logger.info(f"KV缓存已初始化 (max_size={max_size // (1024*1024)}MB, strategy={strategy.value})")

    def _generate_key(self, *args, **kwargs) -> str:
        """生成缓存键"""
        key_data = json.dumps({"args": args, "kwargs": kwargs}, sort_keys=True)
        return hashlib.sha256(key_data.encode()).hexdigest()[:16]

    def _estimate_size(self, value: Any) -> int:
        """估算值的大小"""
        if isinstance(value, (str, bytes)):
            return len(value)
        elif isinstance(value, (list, tuple)):
            return sum(self._estimate_size(v) for v in value)
        elif isinstance(value, dict):
            return sum(self._estimate_size(k) + self._estimate_size(v) for k, v in value.items())
        elif isinstance(value, (int, float)):
            return 8
        else:
            try:
                return len(str(value))
            except:
                return 64

    def _evict(self, required_size: int = 0):
        """执行缓存淘汰"""
        while (
            (self._stats.total_size + required_size > self.max_size) or
            (len(self._cache) >= self.max_entries)
        ):
            if not self._cache:
                break

            if self.strategy == CacheStrategy.LRU:
                key = min(self._cache.keys(), key=lambda k: self._cache[k].last_accessed)
            elif self.strategy == CacheStrategy.LFU:
                key = min(self._cache.keys(), key=lambda k: self._cache[k].access_count)
            elif self.strategy == CacheStrategy.FIFO:
                key = next(iter(self._cache))
            elif self.strategy == CacheStrategy.TTL:
                expired = [k for k, v in self._cache.items() if v.is_expired()]
                if expired:
                    key = expired[0]
                else:
                    key = next(iter(self._cache))
            else:
                key = next(iter(self._cache))

            entry = self._cache.pop(key)
            self._stats.total_size -= entry.size
            self._stats.evictions += 1

            logger.debug(f"缓存淘汰: {key}, 大小: {entry.size}")

    def get(self, key: str) -> Any | None:
        """获取缓存值"""
        with self._lock:
            entry = self._cache.get(key)

            if entry is None:
                self._stats.misses += 1
                self._update_hit_rate()
                return None

            if entry.is_expired():
                self._cache.pop(key)
                self._stats.total_size -= entry.size
                self._stats.misses += 1
                self._update_hit_rate()
                return None

            entry.touch()
            self._stats.hits += 1
            self._update_hit_rate()

            if self.strategy == CacheStrategy.LRU:
                self._cache.move_to_end(key)

            return entry.value

    def set(
        self,
        key: str,
        value: Any,
        ttl: float | None = None,
        metadata: dict | None = None,
    ) -> bool:
        """设置缓存值"""
        size = self._estimate_size(value)

        if size > self.max_size:
            logger.warning(f"缓存值过大: {size} > {self.max_size}")
            return False

        with self._lock:
            if key in self._cache:
                old_entry = self._cache.pop(key)
                self._stats.total_size -= old_entry.size

            self._evict(required_size=size)

            entry = CacheEntry(
                key=key,
                value=value,
                size=size,
                ttl=ttl or self.default_ttl,
                metadata=metadata or {},
            )

            self._cache[key] = entry
            self._stats.total_size += size
            self._stats.total_entries = len(self._cache)

            return True

    def delete(self, key: str) -> bool:
        """删除缓存值"""
        with self._lock:
            if key in self._cache:
                entry = self._cache.pop(key)
                self._stats.total_size -= entry.size
                self._stats.total_entries = len(self._cache)
                return True
            return False

    def clear(self):
        """清空缓存"""
        with self._lock:
            self._cache.clear()
            self._stats.total_size = 0
            self._stats.total_entries = 0
            logger.info("缓存已清空")

    def contains(self, key: str) -> bool:
        """检查键是否存在"""
        with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                return False
            if entry.is_expired():
                self.delete(key)
                return False
            return True

    def get_or_set(
        self,
        key: str,
        factory: callable,
        ttl: float | None = None,
    ) -> Any:
        """获取或设置缓存值"""
        value = self.get(key)
        if value is not None:
            return value

        value = factory()
        if value is not None:
            self.set(key, value, ttl)
        return value

    def _update_hit_rate(self):
        """更新命中率"""
        total = self._stats.hits + self._stats.misses
        if total > 0:
            self._stats.hit_rate = self._stats.hits / total

    def get_stats(self) -> CacheStats:
        """获取缓存统计"""
        with self._lock:
            self._stats.total_entries = len(self._cache)
            return self._stats

    def warmup(self, items: list[tuple[str, Any]]):
        """缓存预热"""
        logger.info(f"开始缓存预热: {len(items)} 个项目")

        for key, value in items:
            self.set(key, value)

        logger.info(f"缓存预热完成: {len(items)} 个项目已缓存")

    def cleanup_expired(self) -> int:
        """清理过期条目"""
        with self._lock:
            expired_keys = [
                k for k, v in self._cache.items() if v.is_expired()
            ]

            for key in expired_keys:
                entry = self._cache.pop(key)
                self._stats.total_size -= entry.size
                self._stats.evictions += 1

            if expired_keys:
                logger.info(f"已清理 {len(expired_keys)} 个过期缓存条目")

            return len(expired_keys)

    def get_keys(self) -> list[str]:
        """获取所有缓存键"""
        with self._lock:
            return list(self._cache.keys())

    def get_size_info(self) -> dict[str, Any]:
        """获取大小信息"""
        with self._lock:
            return {
                "total_size": self._stats.total_size,
                "total_size_mb": round(self._stats.total_size / (1024 * 1024), 2),
                "max_size": self.max_size,
                "max_size_mb": self.max_size / (1024 * 1024),
                "usage_percent": round(self._stats.total_size / self.max_size * 100, 2),
                "entry_count": len(self._cache),
                "max_entries": self.max_entries,
            }


class KVCacheManager:
    """
    KV 缓存管理器

    管理多个命名缓存实例
    """

    def __init__(self):
        self._caches: dict[str, KVCache] = {}
        self._lock = threading.Lock()

    def create_cache(
        self,
        name: str,
        max_size: int = 1024 * 1024 * 1024,
        max_entries: int = 10000,
        strategy: CacheStrategy = CacheStrategy.LRU,
        default_ttl: float | None = None,
    ) -> KVCache:
        """创建命名缓存"""
        with self._lock:
            if name in self._caches:
                return self._caches[name]

            cache = KVCache(
                max_size=max_size,
                max_entries=max_entries,
                strategy=strategy,
                default_ttl=default_ttl,
            )
            self._caches[name] = cache
            return cache

    def get_cache(self, name: str) -> KVCache | None:
        """获取命名缓存"""
        return self._caches.get(name)

    def get_or_create(
        self,
        name: str,
        **kwargs,
    ) -> KVCache:
        """获取或创建命名缓存"""
        cache = self.get_cache(name)
        if cache is None:
            cache = self.create_cache(name, **kwargs)
        return cache

    def delete_cache(self, name: str) -> bool:
        """删除命名缓存"""
        with self._lock:
            if name in self._caches:
                self._caches[name].clear()
                del self._caches[name]
                return True
            return False

    def get_all_stats(self) -> dict[str, CacheStats]:
        """获取所有缓存统计"""
        return {name: cache.get_stats() for name, cache in self._caches.items()}

    def clear_all(self):
        """清空所有缓存"""
        for cache in self._caches.values():
            cache.clear()

    def cleanup_all_expired(self) -> int:
        """清理所有缓存的过期条目"""
        total = 0
        for cache in self._caches.values():
            total += cache.cleanup_expired()
        return total


_cache_manager: KVCacheManager | None = None
_manager_lock = threading.Lock()


def get_kv_cache_manager() -> KVCacheManager:
    """获取 KV 缓存管理器实例"""
    global _cache_manager
    with _manager_lock:
        if _cache_manager is None:
            _cache_manager = KVCacheManager()
        return _cache_manager


def get_kv_cache(name: str = "default", **kwargs) -> KVCache:
    """获取命名 KV 缓存实例"""
    manager = get_kv_cache_manager()
    return manager.get_or_create(name, **kwargs)
