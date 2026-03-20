"""
API 速率限制模块 - 防止暴力破解�?DDoS 攻击

功能�?- 基于 IP 的速率限制
- 基于 API Key 的速率限制
- 基于用户的速率限制
- 滑动窗口算法
- 内存/Redis 存储后端
- 自动封禁机制

配置示例�?    RATE_LIMIT_ENABLED = True
    RATE_LIMIT_DEFAULT = "100/minute"  # 默认限制
    RATE_LIMIT_API = {
        "/api/login": "5/minute",      # 登录接口更严�?        "/api/chat": "30/minute",      # 聊天接口适中
        "/api/files": "20/minute",     # 文件接口
    }
    RATE_LIMIT_BAN = {
        "threshold": 10,               # 超过 10 次违�?        "duration": 3600,              # 封禁 1 小时
    }
"""
import time
import re
from typing import Dict, Optional, Tuple, List
from dataclasses import dataclass, field
from collections import defaultdict
from datetime import datetime, timedelta
import logging
import os

logger = logging.getLogger(__name__)


@dataclass
class RateLimitConfig:
    """速率限制配置"""
    requests: int  # 允许请求�?    window: int    # 时间窗口（秒�?    
    @classmethod
    def parse(cls, rate_str: str) -> 'RateLimitConfig':
        """
        解析速率限制字符�?        
        Args:
            rate_str: 格式�?"100/minute", "5/second", "1000/hour"
        
        Returns:
            RateLimitConfig 实例
        """
        match = re.match(r'(\d+)/(\w+)', rate_str.strip())
        if not match:
            raise ValueError(f"无效的速率限制格式：{rate_str}")
        
        count = int(match.group(1))
        unit = match.group(2).lower()
        
        unit_seconds = {
            'second': 1,
            'seconds': 1,
            'sec': 1,
            'minute': 60,
            'minutes': 60,
            'min': 60,
            'hour': 3600,
            'hours': 3600,
            'hr': 3600,
            'day': 86400,
            'days': 86400,
        }
        
        if unit not in unit_seconds:
            raise ValueError(f"无效的时间单位：{unit}")
        
        return cls(requests=count, window=unit_seconds[unit])


@dataclass
class RateLimitEntry:
    """速率限制条目"""
    timestamps: List[float] = field(default_factory=list)
    violations: int = 0
    banned_until: Optional[float] = None


class RateLimiter:
    """速率限制�?""

    def __init__(
        self,
        default_limit: str = "100/minute",
        api_limits: Optional[Dict[str, str]] = None,
        ban_threshold: int = 10,
        ban_duration: int = 3600,
        storage: Optional[Dict] = None
    ):
        """
        初始化速率限制�?
        Args:
            default_limit: 默认速率限制
            api_limits: API 端点特定限制
            ban_threshold: 封禁阈�?            ban_duration: 封禁时长（秒�?            storage: 存储后端（默认内存）
        """
        self.default_limit = RateLimitConfig.parse(default_limit)
        self.api_limits = {}
        
        if api_limits:
            for path, limit in api_limits.items():
                self.api_limits[path] = RateLimitConfig.parse(limit)
        
        self.ban_threshold = ban_threshold
        self.ban_duration = ban_duration
        
        # 存储：key -> RateLimitEntry
        self._storage: Dict[str, RateLimitEntry] = storage if storage is not None else {}
        
        logger.info(f"速率限制器已初始化，默认限制：{default_limit}")

    def _get_key(self, identifier: str, endpoint: str = "") -> str:
        """生成存储�?""
        if endpoint:
            return f"{identifier}:{endpoint}"
        return identifier

    def _get_limit(self, endpoint: str) -> RateLimitConfig:
        """获取端点的限制配�?""
        # 精确匹配
        if endpoint in self.api_limits:
            return self.api_limits[endpoint]
        
        # 前缀匹配
        for path, limit in self.api_limits.items():
            if endpoint.startswith(path):
                return limit
        
        # 默认限制
        return self.default_limit

    def _cleanup_old_timestamps(self, entry: RateLimitEntry, window: int):
        """清理过期时间�?""
        current_time = time.time()
        cutoff = current_time - window
        entry.timestamps = [ts for ts in entry.timestamps if ts > cutoff]

    def is_allowed(
        self,
        identifier: str,
        endpoint: str = "",
        cost: int = 1
    ) -> Tuple[bool, Dict]:
        """
        检查请求是否允�?
        Args:
            identifier: 标识符（IP/API Key/用户 ID�?            endpoint: API 端点路径
            cost: 请求成本（默�?1�?
        Returns:
            (是否允许，额外信�?
        """
        key = self._get_key(identifier, endpoint)
        limit = self._get_limit(endpoint)
        current_time = time.time()

        # 获取或创建条�?        if key not in self._storage:
            self._storage[key] = RateLimitEntry()
        
        entry = self._storage[key]

        # 检查是否被封禁
        if entry.banned_until:
            if current_time < entry.banned_until:
                remaining = int(entry.banned_until - current_time)
                return False, {
                    'error': 'rate_limit_banned',
                    'message': f'请求过于频繁，已被临时封�?,
                    'retry_after': remaining,
                    'banned_until': datetime.fromtimestamp(entry.banned_until).isoformat()
                }
            else:
                # 封禁已过期，重置
                entry.banned_until = None
                entry.violations = 0
                entry.timestamps = []

        # 清理过期时间�?        self._cleanup_old_timestamps(entry, limit.window)

        # 检查是否超过限�?        if len(entry.timestamps) + cost > limit.requests:
            # 违规
            entry.violations += 1
            
            # 检查是否需要封�?            if entry.violations >= self.ban_threshold:
                entry.banned_until = current_time + self.ban_duration
                logger.warning(f"标识�?{identifier} 已被封禁，时长：{self.ban_duration}�?)
                
                return False, {
                    'error': 'rate_limit_banned',
                    'message': f'请求过于频繁，已被封�?,
                    'retry_after': self.ban_duration,
                    'violations': entry.violations
                }
            
            # 计算等待时间
            if entry.timestamps:
                oldest = min(entry.timestamps)
                retry_after = int(oldest + limit.window - current_time) + 1
            else:
                retry_after = limit.window
            
            return False, {
                'error': 'rate_limit_exceeded',
                'message': f'请求过于频繁，限制：{limit.requests}�?{limit.window}�?,
                'retry_after': max(1, retry_after),
                'limit': limit.requests,
                'window': limit.window,
                'violations': entry.violations
            }

        # 允许请求，记录时间戳
        for _ in range(cost):
            entry.timestamps.append(current_time)
        
        # 计算剩余配额
        remaining = limit.requests - len(entry.timestamps)
        reset_time = int(current_time + limit.window)

        return True, {
            'limit': limit.requests,
            'remaining': remaining,
            'reset': reset_time,
            'window': limit.window
        }

    def get_status(self, identifier: str, endpoint: str = "") -> Dict:
        """
        获取速率限制状�?
        Args:
            identifier: 标识�?            endpoint: API 端点

        Returns:
            状态信�?        """
        key = self._get_key(identifier, endpoint)
        limit = self._get_limit(endpoint)
        current_time = time.time()

        if key not in self._storage:
            return {
                'limit': limit.requests,
                'remaining': limit.requests,
                'reset': int(current_time + limit.window),
                'banned': False
            }

        entry = self._storage[key]
        self._cleanup_old_timestamps(entry, limit.window)

        return {
            'limit': limit.requests,
            'remaining': max(0, limit.requests - len(entry.timestamps)),
            'reset': int(current_time + limit.window),
            'banned': entry.banned_until is not None and current_time < entry.banned_until,
            'violations': entry.violations,
            'used': len(entry.timestamps)
        }

    def reset(self, identifier: str, endpoint: str = ""):
        """重置标识符的速率限制"""
        key = self._get_key(identifier, endpoint)
        if key in self._storage:
            del self._storage[key]
            logger.info(f"已重置标识符 {identifier} 的速率限制")

    def ban(self, identifier: str, duration: Optional[int] = None, endpoint: str = ""):
        """
        手动封禁标识�?
        Args:
            identifier: 标识�?            duration: 封禁时长（秒�?            endpoint: 特定端点（可选）
        """
        key = self._get_key(identifier, endpoint)
        if key not in self._storage:
            self._storage[key] = RateLimitEntry()
        
        duration = duration or self.ban_duration
        self._storage[key].banned_until = time.time() + duration
        logger.warning(f"标识�?{identifier} 已被手动封禁，时长：{duration}�?)

    def get_stats(self) -> Dict:
        """获取速率限制统计信息"""
        total_keys = len(self._storage)
        banned_keys = sum(
            1 for entry in self._storage.values()
            if entry.banned_until and time.time() < entry.banned_until
        )
        total_violations = sum(entry.violations for entry in self._storage.values())

        return {
            'total_identifiers': total_keys,
            'banned_identifiers': banned_keys,
            'total_violations': total_violations,
            'api_limits': {
                path: f"{cfg.requests}/{cfg.window}s"
                for path, cfg in self.api_limits.items()
            },
            'default_limit': f"{self.default_limit.requests}/{self.default_limit.window}s"
        }

    def cleanup(self, max_age: int = 3600):
        """清理过期数据"""
        current_time = time.time()
        cutoff = current_time - max_age
        
        keys_to_delete = []
        for key, entry in self._storage.items():
            # 清理没有任何时间戳且封禁已过期的条目
            if not entry.timestamps:
                if not entry.banned_until or entry.banned_until < current_time:
                    keys_to_delete.append(key)
        
        for key in keys_to_delete:
            del self._storage[key]
        
        if keys_to_delete:
            logger.info(f"清理�?{len(keys_to_delete)} 个过期速率限制条目")


# 全局单例（默认配置）
_default_limiter: Optional[RateLimiter] = None


def get_rate_limiter() -> RateLimiter:
    """获取速率限制器单�?""
    global _default_limiter
    if _default_limiter is None:
        _default_limiter = RateLimiter(
            default_limit=os.environ.get('RATE_LIMIT_DEFAULT', '100/minute'),
            api_limits={
                '/api/login': '5/minute',
                '/api/register': '3/minute',
                '/api/chat': '30/minute',
                '/api/files': '20/minute',
                '/cloud/chat': '20/minute',
            },
            ban_threshold=int(os.environ.get('RATE_LIMIT_BAN_THRESHOLD', '10')),
            ban_duration=int(os.environ.get('RATE_LIMIT_BAN_DURATION', '3600'))
        )
    return _default_limiter


def init_rate_limiter(
    default_limit: str = "100/minute",
    api_limits: Optional[Dict[str, str]] = None,
    ban_threshold: int = 10,
    ban_duration: int = 3600
):
    """初始化速率限制�?""
    global _default_limiter
    _default_limiter = RateLimiter(
        default_limit=default_limit,
        api_limits=api_limits,
        ban_threshold=ban_threshold,
        ban_duration=ban_duration
    )
    return _default_limiter
