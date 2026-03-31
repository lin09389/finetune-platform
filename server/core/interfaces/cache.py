"""
缓存接口 - 用于模型和嵌入缓存
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Generic, TypeVar

T = TypeVar('T')


@dataclass
class CacheEntry(Generic[T]):
    """缓存条目"""
    key: str
    value: T
    created_at: datetime
    last_accessed: datetime
    access_count: int = 0
    size_bytes: int = 0
    metadata: dict[str, Any] = None


class CacheInterface(ABC, Generic[T]):
    """
    缓存接口
    
    支持多种缓存策略：
    - LRU (Least Recently Used)
    - LFU (Least Frequently Used)
    - TTL (Time To Live)
    """

    @abstractmethod
    def get(self, key: str) -> T | None:
        """
        获取缓存值
        
        Args:
            key: 缓存键
            
        Returns:
            缓存值，不存在返回 None
        """
        pass

    @abstractmethod
    def set(self, key: str, value: T, ttl: int | None = None) -> bool:
        """
        设置缓存值
        
        Args:
            key: 缓存键
            value: 缓存值
            ttl: 过期时间（秒）
            
        Returns:
            是否成功
        """
        pass

    @abstractmethod
    def delete(self, key: str) -> bool:
        """
        删除缓存
        
        Args:
            key: 缓存键
            
        Returns:
            是否成功
        """
        pass

    @abstractmethod
    def exists(self, key: str) -> bool:
        """
        检查缓存是否存在
        
        Args:
            key: 缓存键
            
        Returns:
            是否存在
        """
        pass

    @abstractmethod
    def clear(self) -> bool:
        """
        清空缓存
        
        Returns:
            是否成功
        """
        pass

    @abstractmethod
    def size(self) -> int:
        """
        获取缓存大小
        
        Returns:
            缓存条目数量
        """
        pass

    @abstractmethod
    def get_keys(self) -> list[str]:
        """
        获取所有缓存键
        
        Returns:
            缓存键列表
        """
        pass

    def get_stats(self) -> dict[str, Any]:
        """
        获取缓存统计信息
        
        Returns:
            统计信息
        """
        return {
            "size": self.size(),
            "keys": self.get_keys(),
        }
