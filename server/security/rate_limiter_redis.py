"""
Redis 速率限制器
使用 Redis 实现持久化的速率限制
"""
import logging
import time
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
            _redis_client = await redis.from_url(redis_url)
            logger.info("Redis 连接成功")
        except Exception as e:
            logger.warning(f"Redis 连接失败，使用内存存储: {e}")
            _redis_client = None
    return _redis_client


class RedisRateLimiter:
    """基于 Redis 的速率限制器"""

    def __init__(
        self,
        redis_url: str = "redis://localhost:6379/0",
        max_requests: int = 100,
        window_seconds: int = 60,
        ban_threshold: int = 10,
        ban_duration: int = 3600
    ):
        self.redis_url = redis_url
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.ban_threshold = ban_threshold
        self.ban_duration = ban_duration
        self._redis: Any = None
        self._memory_store: dict[str, list] = {}
        self._memory_bans: dict[str, float] = {}

    async def init(self):
        try:
            import redis.asyncio as redis
            self._redis = await redis.from_url(self.redis_url)
            logger.info("Redis 速率限制器初始化成功")
        except Exception as e:
            logger.warning(f"Redis 初始化失败，使用内存存储: {e}")
            self._redis = None

    async def is_allowed(
        self,
        key: str,
        max_requests: int | None = None,
        window_seconds: int | None = None
    ) -> tuple[bool, dict[str, Any]]:
        max_requests = max_requests or self.max_requests
        window_seconds = window_seconds or self.window_seconds
        now = time.time()

        if self._redis:
            return await self._redis_check(key, max_requests, window_seconds, now)
        else:
            return self._memory_check(key, max_requests, window_seconds, now)

    async def _redis_check(
        self,
        key: str,
        max_requests: int,
        window_seconds: int,
        now: float
    ) -> tuple[bool, dict[str, Any]]:
        try:
            window_start = now - window_seconds

            pipe = self._redis.pipeline()
            pipe.zremrangebyscore(key, 0, window_start)
            pipe.zcard(key)
            pipe.zadd(key, {str(now): now})
            pipe.expire(key, window_seconds)

            results = await pipe.execute()
            current_count = results[1]

            is_allowed = current_count < max_requests

            return is_allowed, {
                "current": current_count + 1,
                "limit": max_requests,
                "reset_at": int(now + window_seconds),
                "remaining": max(0, max_requests - current_count - 1),
                "source": "redis"
            }
        except Exception as e:
            logger.error(f"Redis 速率检查失败: {e}")
            return self._memory_check(key, max_requests, window_seconds, now)

    def _memory_check(
        self,
        key: str,
        max_requests: int,
        window_seconds: int,
        now: float
    ) -> tuple[bool, dict[str, Any]]:
        window_start = now - window_seconds

        if key not in self._memory_store:
            self._memory_store[key] = []

        self._memory_store[key] = [
            t for t in self._memory_store[key] if t > window_start
        ]

        current_count = len(self._memory_store[key])

        if current_count >= max_requests:
            return False, {
                "current": current_count,
                "limit": max_requests,
                "reset_at": int(window_start + window_seconds),
                "remaining": 0,
                "source": "memory"
            }

        self._memory_store[key].append(now)

        return True, {
            "current": current_count + 1,
            "limit": max_requests,
            "reset_at": int(now + window_seconds),
            "remaining": max_requests - current_count - 1,
            "source": "memory"
        }

    async def ban(self, key: str, duration_seconds: int | None = None):
        duration = duration_seconds or self.ban_duration

        if self._redis:
            try:
                await self._redis.setex(f"banned:{key}", duration, "1")
                logger.info(f"已封禁 {key}，持续 {duration} 秒")
            except Exception as e:
                logger.error(f"Redis 封禁失败: {e}")
                self._memory_bans[key] = time.time() + duration
        else:
            self._memory_bans[key] = time.time() + duration

    async def is_banned(self, key: str) -> bool:
        if self._redis:
            try:
                return bool(await self._redis.exists(f"banned:{key}") > 0)
            except Exception as e:
                logger.error(f"Redis 检查封禁失败: {e}")
                return self._check_memory_ban(key)
        else:
            return self._check_memory_ban(key)

    def _check_memory_ban(self, key: str) -> bool:
        if key in self._memory_bans:
            if time.time() < self._memory_bans[key]:
                return True
            else:
                del self._memory_bans[key]
        return False

    async def unban(self, key: str):
        if self._redis:
            try:
                await self._redis.delete(f"banned:{key}")
            except Exception as e:
                logger.error(f"Redis 解封失败: {e}")
        if key in self._memory_bans:
            del self._memory_bans[key]

    async def get_stats(self) -> dict[str, Any]:
        stats = {
            "backend": "redis" if self._redis else "memory",
            "max_requests": self.max_requests,
            "window_seconds": self.window_seconds,
            "ban_threshold": self.ban_threshold,
            "ban_duration": self.ban_duration,
        }

        if self._redis:
            try:
                info = await self._redis.info()
                stats["redis_connected"] = True
                stats["redis_used_memory"] = info.get("used_memory_human", "unknown")
            except Exception:
                stats["redis_connected"] = False
        else:
            stats["memory_keys"] = len(self._memory_store)
            stats["memory_bans"] = len(self._memory_bans)

        return stats


_redis_rate_limiter: RedisRateLimiter | None = None


def get_redis_rate_limiter() -> RedisRateLimiter:
    global _redis_rate_limiter
    if _redis_rate_limiter is None:
        from core.config import get_settings
        settings = get_settings()
        redis_url = getattr(settings, 'redis_url', 'redis://localhost:6379/0')
        _redis_rate_limiter = RedisRateLimiter(
            redis_url=redis_url,
            max_requests=settings.rate_limit,
            window_seconds=settings.rate_window
        )
    return _redis_rate_limiter
