"""
分布式缓存模块
支持 Redis 和内存缓存双模式
"""
import hashlib
import logging
import pickle
import time
from collections.abc import Callable
from functools import wraps
from typing import Any

logger = logging.getLogger(__name__)

_redis_client = None


async def get_redis_client():
    global _redis_client
    if _redis_client is None:
        try:
            import redis.asyncio as redis

            from core.config import get_settings
            settings = get_settings()
            redis_url = getattr(settings, 'redis_url', 'redis://localhost:6379/0')
            _redis_client = await redis.from_url(
                redis_url,
                encoding="utf-8",
                decode_responses=False
            )
            logger.info("Redis 缓存连接成功")
        except Exception as e:
            logger.warning(f"Redis 连接失败，使用内存缓存: {e}")
            _redis_client = None
    return _redis_client


class DistributedCache:
    """分布式缓存，支持 Redis 和内存双模式"""

    def __init__(
        self,
        redis_url: str = "redis://localhost:6379/0",
        default_ttl: int = 3600,
        max_memory_items: int = 1000
    ):
        self.redis_url = redis_url
        self.default_ttl = default_ttl
        self.max_memory_items = max_memory_items

        self._redis = None
        self._memory_cache: dict[str, tuple] = {}
        self._access_order: list[str] = []
        self._stats = {
            "hits": 0,
            "misses": 0,
            "sets": 0,
            "deletes": 0,
            "errors": 0
        }

    async def init(self):
        try:
            import redis.asyncio as redis
            self._redis = await redis.from_url(
                self.redis_url,
                encoding="utf-8",
                decode_responses=False
            )
            logger.info("分布式缓存初始化成功 (Redis模式)")
        except Exception as e:
            logger.warning(f"Redis 初始化失败，使用内存缓存: {e}")
            self._redis = None

    def _generate_key(self, *args, **kwargs) -> str:
        key_data = str(args) + str(sorted(kwargs.items()))
        return hashlib.sha256(key_data.encode()).hexdigest()[:32]

    async def get(self, key: str) -> Any | None:
        if self._redis:
            try:
                data = await self._redis.get(key)
                if data:
                    self._stats["hits"] += 1
                    return pickle.loads(data)
                self._stats["misses"] += 1
                return None
            except Exception as e:
                logger.error(f"Redis 读取失败: {e}")
                self._stats["errors"] += 1
                return self._memory_get(key)
        else:
            return self._memory_get(key)

    def _memory_get(self, key: str) -> Any | None:
        if key in self._memory_cache:
            data, expire_at = self._memory_cache[key]
            if time.time() < expire_at:
                self._stats["hits"] += 1
                if key in self._access_order:
                    self._access_order.remove(key)
                self._access_order.append(key)
                return data
            else:
                del self._memory_cache[key]
                if key in self._access_order:
                    self._access_order.remove(key)
        self._stats["misses"] += 1
        return None

    async def set(
        self,
        key: str,
        value: Any,
        ttl: int | None = None
    ) -> bool:
        ttl = ttl or self.default_ttl
        self._stats["sets"] += 1

        if self._redis:
            try:
                data = pickle.dumps(value)
                await self._redis.setex(key, ttl, data)
                return True
            except Exception as e:
                logger.error(f"Redis 写入失败: {e}")
                self._stats["errors"] += 1
                return self._memory_set(key, value, ttl)
        else:
            return self._memory_set(key, value, ttl)

    def _memory_set(self, key: str, value: Any, ttl: int) -> bool:
        if len(self._memory_cache) >= self.max_memory_items:
            self._evict_lru()

        expire_at = time.time() + ttl
        self._memory_cache[key] = (value, expire_at)

        if key in self._access_order:
            self._access_order.remove(key)
        self._access_order.append(key)

        return True

    def _evict_lru(self):
        if self._access_order:
            oldest_key = self._access_order.pop(0)
            if oldest_key in self._memory_cache:
                del self._memory_cache[oldest_key]

    async def delete(self, key: str) -> bool:
        self._stats["deletes"] += 1

        if self._redis:
            try:
                await self._redis.delete(key)
            except Exception as e:
                logger.error(f"Redis 删除失败: {e}")

        if key in self._memory_cache:
            del self._memory_cache[key]
        if key in self._access_order:
            self._access_order.remove(key)

        return True

    async def exists(self, key: str) -> bool:
        if self._redis:
            try:
                return await self._redis.exists(key) > 0
            except Exception as e:
                logger.error(f"Redis 检查失败: {e}")

        return key in self._memory_cache

    async def invalidate_pattern(self, pattern: str):
        """批量失效缓存"""
        if self._redis:
            try:
                keys = await self._redis.keys(pattern)
                if keys:
                    await self._redis.delete(*keys)
                    logger.info(f"Redis 批量删除 {len(keys)} 个缓存")
            except Exception as e:
                logger.error(f"Redis 批量删除失败: {e}")

        import fnmatch
        keys_to_delete = [
            k for k in self._memory_cache
            if fnmatch.fnmatch(k, pattern)
        ]
        for key in keys_to_delete:
            del self._memory_cache[key]
            if key in self._access_order:
                self._access_order.remove(key)

        if keys_to_delete:
            logger.info(f"内存缓存批量删除 {len(keys_to_delete)} 个")

    def get_stats(self) -> dict[str, Any]:
        total = self._stats["hits"] + self._stats["misses"]
        hit_rate = self._stats["hits"] / total if total > 0 else 0

        return {
            **self._stats,
            "hit_rate": f"{hit_rate:.2%}",
            "memory_items": len(self._memory_cache),
            "backend": "redis" if self._redis else "memory"
        }

    async def health_check(self) -> dict[str, Any]:
        health = {
            "status": "healthy",
            "backend": "memory",
            "redis_connected": False
        }

        if self._redis:
            try:
                await self._redis.ping()
                health["backend"] = "redis"
                health["redis_connected"] = True
            except Exception as e:
                health["status"] = "degraded"
                health["error"] = str(e)

        return health


_cache: DistributedCache | None = None


def get_cache() -> DistributedCache:
    global _cache
    if _cache is None:
        from core.config import get_settings
        settings = get_settings()
        redis_url = getattr(settings, 'redis_url', 'redis://localhost:6379/0')
        _cache = DistributedCache(redis_url=redis_url)
    return _cache


def cached(
    key_prefix: str,
    ttl: int = 3600,
    key_builder: Callable | None = None
):
    """
    缓存装饰器

    Args:
        key_prefix: 缓存键前缀
        ttl: 过期时间（秒）
        key_builder: 自定义键生成函数
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            cache = get_cache()

            if key_builder:
                cache_key = key_builder(*args, **kwargs)
            else:
                cache_key = f"{key_prefix}:{cache._generate_key(*args, **kwargs)}"

            cached_result = await cache.get(cache_key)
            if cached_result is not None:
                logger.debug(f"缓存命中: {cache_key}")
                return cached_result

            result = await func(*args, **kwargs)

            if result is not None:
                await cache.set(cache_key, result, ttl)
                logger.debug(f"缓存写入: {cache_key}")

            return result
        return wrapper
    return decorator
