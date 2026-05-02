"""本地推理离线缓存。"""
from __future__ import annotations

import hashlib
import json
import threading
import time
from dataclasses import dataclass
from typing import Any


@dataclass
class OfflineCacheEntry:
    value: Any
    created_at: float
    ttl_seconds: int

    @property
    def expired(self) -> bool:
        return (time.time() - self.created_at) > self.ttl_seconds


class OfflineCache:
    def __init__(self, default_ttl_seconds: int = 600, max_entries: int = 1024):
        self.default_ttl_seconds = default_ttl_seconds
        self.max_entries = max_entries
        self._entries: dict[str, OfflineCacheEntry] = {}
        self._lock = threading.Lock()
        self._hits = 0
        self._misses = 0

    def build_key(self, namespace: str, payload: dict[str, Any]) -> str:
        canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        digest = hashlib.sha256(f"{namespace}:{canonical}".encode("utf-8")).hexdigest()
        return digest

    def get(self, key: str) -> Any | None:
        with self._lock:
            entry = self._entries.get(key)
            if not entry:
                self._misses += 1
                return None
            if entry.expired:
                self._entries.pop(key, None)
                self._misses += 1
                return None
            self._hits += 1
            return entry.value

    def set(self, key: str, value: Any, ttl_seconds: int | None = None) -> None:
        with self._lock:
            if len(self._entries) >= self.max_entries:
                oldest_key = min(self._entries.items(), key=lambda item: item[1].created_at)[0]
                self._entries.pop(oldest_key, None)
            self._entries[key] = OfflineCacheEntry(
                value=value,
                created_at=time.time(),
                ttl_seconds=ttl_seconds or self.default_ttl_seconds,
            )

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()
            self._hits = 0
            self._misses = 0

    def get_stats(self) -> dict[str, Any]:
        with self._lock:
            return {
                "entries": len(self._entries),
                "hits": self._hits,
                "misses": self._misses,
                "hit_rate": round(self._hits / max(self._hits + self._misses, 1), 4),
                "default_ttl_seconds": self.default_ttl_seconds,
            }


_offline_cache: OfflineCache | None = None


def get_offline_cache() -> OfflineCache:
    global _offline_cache
    if _offline_cache is None:
        from core.config import get_settings

        settings = get_settings()
        _offline_cache = OfflineCache(default_ttl_seconds=settings.offline_cache_ttl_seconds)
    return _offline_cache
