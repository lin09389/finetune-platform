"""
技能执行结果缓存模�?
功能�?- 基于参数哈希的缓存键生成
- LRU 缓存淘汰策略
- 缓存过期时间控制
- 缓存命中率统�?- 持久化缓存支�?"""
import asyncio
import hashlib
import json
import pickle
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from threading import Lock
from typing import Any, Callable, Dict, List, Optional, Tuple

from .models import SkillResult


@dataclass
class CacheEntry:
    """缓存条目"""
    key: str
    skill_name: str
    parameters_hash: str
    result: SkillResult
    created_at: datetime
    expires_at: Optional[datetime]
    hit_count: int = 0
    last_accessed_at: datetime = field(default_factory=datetime.now)
    size_bytes: int = 0


@dataclass
class CacheStats:
    """缓存统计信息"""
    total_entries: int = 0
    total_hits: int = 0
    total_misses: int = 0
    total_evictions: int = 0
    total_size_bytes: int = 0
    skill_stats: Dict[str, Dict[str, int]] = field(default_factory=dict)
    
    @property
    def hit_rate(self) -> float:
        total = self.total_hits + self.total_misses
        return self.total_hits / total if total > 0 else 0.0


class SkillExecutionCache:
    """技能执行结果缓�?""
    
    DEFAULT_MAX_SIZE = 1000
    DEFAULT_TTL_SECONDS = 3600
    DEFAULT_MAX_MEMORY_MB = 100
    
    def __init__(
        self,
        max_size: int = DEFAULT_MAX_SIZE,
        default_ttl: int = DEFAULT_TTL_SECONDS,
        max_memory_mb: int = DEFAULT_MAX_MEMORY_MB,
        persist_dir: Optional[Path] = None,
    ):
        self._cache: OrderedDict[str, CacheEntry] = OrderedDict()
        self._skill_index: Dict[str, set] = {}
        self._lock = Lock()
        self._stats = CacheStats()
        
        self._max_size = max_size
        self._default_ttl = default_ttl
        self._max_memory_bytes = max_memory_mb * 1024 * 1024
        self._persist_dir = persist_dir
        
        self._on_evict: Optional[Callable[[CacheEntry], None]] = None
        
        if persist_dir:
            self._load_from_disk()
    
    def _generate_key(self, skill_name: str, parameters: Dict[str, Any]) -> str:
        """生成缓存�?""
        params_str = json.dumps(parameters, sort_keys=True, default=str)
        params_hash = hashlib.sha256(params_str.encode()).hexdigest()[:16]
        return f"{skill_name}:{params_hash}"
    
    def _calculate_size(self, result: SkillResult) -> int:
        """计算结果大小"""
        try:
            return len(pickle.dumps(result))
        except Exception:
            return 0
    
    def _is_expired(self, entry: CacheEntry) -> bool:
        """检查缓存是否过�?""
        if entry.expires_at is None:
            return False
        return datetime.now() > entry.expires_at
    
    def _evict_lru(self) -> Optional[CacheEntry]:
        """LRU 淘汰"""
        if not self._cache:
            return None
        
        oldest_key = next(iter(self._cache))
        entry = self._cache.pop(oldest_key)
        
        if entry.skill_name in self._skill_index:
            self._skill_index[entry.skill_name].discard(entry.key)
        
        self._stats.total_evictions += 1
        self._stats.total_size_bytes -= entry.size_bytes
        
        if self._on_evict:
            self._on_evict(entry)
        
        return entry
    
    def _evict_expired(self) -> int:
        """清理过期缓存"""
        expired_keys = []
        
        for key, entry in self._cache.items():
            if self._is_expired(entry):
                expired_keys.append(key)
        
        for key in expired_keys:
            self._remove_entry(key)
        
        return len(expired_keys)
    
    def _remove_entry(self, key: str) -> Optional[CacheEntry]:
        """移除缓存条目"""
        if key not in self._cache:
            return None
        
        entry = self._cache.pop(key)
        
        if entry.skill_name in self._skill_index:
            self._skill_index[entry.skill_name].discard(entry.key)
            if not self._skill_index[entry.skill_name]:
                del self._skill_index[entry.skill_name]
        
        self._stats.total_size_bytes -= entry.size_bytes
        
        return entry
    
    def _update_skill_stats(self, skill_name: str, hit: bool):
        """更新技能统�?""
        if skill_name not in self._stats.skill_stats:
            self._stats.skill_stats[skill_name] = {
                "hits": 0,
                "misses": 0,
                "entries": 0,
            }
        
        if hit:
            self._stats.skill_stats[skill_name]["hits"] += 1
        else:
            self._stats.skill_stats[skill_name]["misses"] += 1
    
    def get(
        self,
        skill_name: str,
        parameters: Dict[str, Any],
    ) -> Optional[SkillResult]:
        """获取缓存结果"""
        key = self._generate_key(skill_name, parameters)
        
        with self._lock:
            if key not in self._cache:
                self._stats.total_misses += 1
                self._update_skill_stats(skill_name, hit=False)
                return None
            
            entry = self._cache[key]
            
            if self._is_expired(entry):
                self._remove_entry(key)
                self._stats.total_misses += 1
                self._update_skill_stats(skill_name, hit=False)
                return None
            
            self._cache.move_to_end(key)
            entry.hit_count += 1
            entry.last_accessed_at = datetime.now()
            
            self._stats.total_hits += 1
            self._update_skill_stats(skill_name, hit=True)
            
            return entry.result
    
    def set(
        self,
        skill_name: str,
        parameters: Dict[str, Any],
        result: SkillResult,
        ttl: Optional[int] = None,
    ) -> str:
        """设置缓存结果"""
        key = self._generate_key(skill_name, parameters)
        params_hash = key.split(":")[1]
        
        now = datetime.now()
        expires_at = now + timedelta(seconds=ttl or self._default_ttl)
        
        size_bytes = self._calculate_size(result)
        
        entry = CacheEntry(
            key=key,
            skill_name=skill_name,
            parameters_hash=params_hash,
            result=result,
            created_at=now,
            expires_at=expires_at,
            size_bytes=size_bytes,
        )
        
        with self._lock:
            while (
                len(self._cache) >= self._max_size
                or self._stats.total_size_bytes + size_bytes > self._max_memory_bytes
            ):
                if not self._evict_lru():
                    break
            
            if key in self._cache:
                old_entry = self._cache[key]
                self._stats.total_size_bytes -= old_entry.size_bytes
            else:
                self._stats.total_entries += 1
                if skill_name not in self._stats.skill_stats:
                    self._stats.skill_stats[skill_name] = {
                        "hits": 0,
                        "misses": 0,
                        "entries": 0,
                    }
                self._stats.skill_stats[skill_name]["entries"] += 1
            
            self._cache[key] = entry
            self._cache.move_to_end(key)
            
            if skill_name not in self._skill_index:
                self._skill_index[skill_name] = set()
            self._skill_index[skill_name].add(key)
            
            self._stats.total_size_bytes += size_bytes
        
        return key
    
    def invalidate(
        self,
        skill_name: str,
        parameters: Optional[Dict[str, Any]] = None,
    ) -> int:
        """使缓存失�?""
        with self._lock:
            if parameters:
                key = self._generate_key(skill_name, parameters)
                if key in self._cache:
                    self._remove_entry(key)
                    return 1
                return 0
            
            if skill_name not in self._skill_index:
                return 0
            
            keys_to_remove = list(self._skill_index[skill_name])
            for key in keys_to_remove:
                self._remove_entry(key)
            
            return len(keys_to_remove)
    
    def clear(self):
        """清空缓存"""
        with self._lock:
            self._cache.clear()
            self._skill_index.clear()
            self._stats = CacheStats()
    
    def cleanup(self) -> int:
        """清理过期缓存"""
        with self._lock:
            return self._evict_expired()
    
    def get_stats(self) -> CacheStats:
        """获取缓存统计"""
        with self._lock:
            return CacheStats(
                total_entries=self._stats.total_entries,
                total_hits=self._stats.total_hits,
                total_misses=self._stats.total_misses,
                total_evictions=self._stats.total_evictions,
                total_size_bytes=self._stats.total_size_bytes,
                skill_stats=dict(self._stats.skill_stats),
            )
    
    def get_entry_info(self, skill_name: str, parameters: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """获取缓存条目信息"""
        key = self._generate_key(skill_name, parameters)
        
        with self._lock:
            if key not in self._cache:
                return None
            
            entry = self._cache[key]
            return {
                "key": entry.key,
                "skill_name": entry.skill_name,
                "created_at": entry.created_at.isoformat(),
                "expires_at": entry.expires_at.isoformat() if entry.expires_at else None,
                "hit_count": entry.hit_count,
                "last_accessed_at": entry.last_accessed_at.isoformat(),
                "size_bytes": entry.size_bytes,
                "is_expired": self._is_expired(entry),
            }
    
    def list_entries(self, skill_name: Optional[str] = None) -> List[Dict[str, Any]]:
        """列出缓存条目"""
        with self._lock:
            entries = []
            
            if skill_name:
                keys = self._skill_index.get(skill_name, set())
            else:
                keys = self._cache.keys()
            
            for key in keys:
                if key in self._cache:
                    entry = self._cache[key]
                    entries.append({
                        "key": entry.key,
                        "skill_name": entry.skill_name,
                        "created_at": entry.created_at.isoformat(),
                        "expires_at": entry.expires_at.isoformat() if entry.expires_at else None,
                        "hit_count": entry.hit_count,
                        "size_bytes": entry.size_bytes,
                    })
            
            return entries
    
    def set_on_evict(self, callback: Callable[[CacheEntry], None]):
        """设置淘汰回调"""
        self._on_evict = callback
    
    def _load_from_disk(self):
        """从磁盘加载缓�?""
        if not self._persist_dir:
            return
        
        cache_file = self._persist_dir / "skill_cache.pkl"
        if not cache_file.exists():
            return
        
        try:
            with open(cache_file, "rb") as f:
                data = pickle.load(f)
            
            for entry in data.get("entries", []):
                if isinstance(entry, CacheEntry) and not self._is_expired(entry):
                    self._cache[entry.key] = entry
                    if entry.skill_name not in self._skill_index:
                        self._skill_index[entry.skill_name] = set()
                    self._skill_index[entry.skill_name].add(entry.key)
                    self._stats.total_entries += 1
                    self._stats.total_size_bytes += entry.size_bytes
        
        except Exception:
            pass
    
    def save_to_disk(self):
        """保存缓存到磁�?""
        if not self._persist_dir:
            return
        
        self._persist_dir.mkdir(parents=True, exist_ok=True)
        cache_file = self._persist_dir / "skill_cache.pkl"
        
        with self._lock:
            self._evict_expired()
            
            data = {
                "entries": list(self._cache.values()),
                "saved_at": datetime.now().isoformat(),
            }
        
        try:
            with open(cache_file, "wb") as f:
                pickle.dump(data, f)
        except Exception:
            pass


class CachedSkillExecutor:
    """带缓存的技能执行器包装"""
    
    def __init__(
        self,
        cache: Optional[SkillExecutionCache] = None,
        cacheable_skills: Optional[set] = None,
        non_cacheable_skills: Optional[set] = None,
    ):
        self._cache = cache or SkillExecutionCache()
        self._cacheable_skills = cacheable_skills
        self._non_cacheable_skills = non_cacheable_skills or set()
    
    def _should_cache(self, skill_name: str, result: SkillResult) -> bool:
        """判断是否应该缓存"""
        if not result.success:
            return False
        
        if skill_name in self._non_cacheable_skills:
            return False
        
        if self._cacheable_skills is not None:
            return skill_name in self._cacheable_skills
        
        return True
    
    async def execute_with_cache(
        self,
        skill_name: str,
        parameters: Dict[str, Any],
        executor: Callable[[Dict[str, Any]], SkillResult],
        ttl: Optional[int] = None,
        force_refresh: bool = False,
    ) -> Tuple[SkillResult, bool]:
        """带缓存的执行"""
        if not force_refresh:
            cached_result = self._cache.get(skill_name, parameters)
            if cached_result is not None:
                return cached_result, True
        
        result = await executor(parameters)
        
        if self._should_cache(skill_name, result):
            self._cache.set(skill_name, parameters, result, ttl)
        
        return result, False
    
    def invalidate(self, skill_name: str, parameters: Optional[Dict[str, Any]] = None) -> int:
        """使缓存失�?""
        return self._cache.invalidate(skill_name, parameters)
    
    def get_cache_stats(self) -> CacheStats:
        """获取缓存统计"""
        return self._cache.get_stats()


_skill_cache: Optional[SkillExecutionCache] = None


def get_skill_cache() -> SkillExecutionCache:
    """获取全局技能缓存实�?""
    global _skill_cache
    if _skill_cache is None:
        _skill_cache = SkillExecutionCache()
    return _skill_cache


def create_skill_cache(
    max_size: int = SkillExecutionCache.DEFAULT_MAX_SIZE,
    default_ttl: int = SkillExecutionCache.DEFAULT_TTL_SECONDS,
    max_memory_mb: int = SkillExecutionCache.DEFAULT_MAX_MEMORY_MB,
    persist_dir: Optional[Path] = None,
) -> SkillExecutionCache:
    """创建技能缓存实�?""
    return SkillExecutionCache(
        max_size=max_size,
        default_ttl=default_ttl,
        max_memory_mb=max_memory_mb,
        persist_dir=persist_dir,
    )
