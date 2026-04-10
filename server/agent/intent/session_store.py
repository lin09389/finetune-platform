"""
会话存储模块
支持内存存储和 Redis 存储两种实现
"""
import json
import logging
import threading
import time
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class SessionData:
    """会话数据"""
    session_id: str
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    recent_messages: list[dict[str, Any]] = field(default_factory=list)
    recent_intents: list[str] = field(default_factory=list)
    mentioned_entities: dict[str, list[str]] = field(default_factory=dict)
    user_preferences: dict[str, Any] = field(default_factory=dict)
    current_task: str | None = None
    expecting_action: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SessionData":
        return cls(
            session_id=data.get("session_id", ""),
            created_at=data.get("created_at", time.time()),
            updated_at=data.get("updated_at", time.time()),
            recent_messages=data.get("recent_messages", []),
            recent_intents=data.get("recent_intents", []),
            mentioned_entities=data.get("mentioned_entities", {}),
            user_preferences=data.get("user_preferences", {}),
            current_task=data.get("current_task"),
            expecting_action=data.get("expecting_action"),
            metadata=data.get("metadata", {})
        )

    def add_message(self, role: str, content: str, intent: str | None = None, params: dict | None = None):
        self.recent_messages.append({
            "role": role,
            "content": content,
            "intent": intent,
            "params": params,
            "timestamp": time.time()
        })
        if len(self.recent_messages) > 20:
            self.recent_messages = self.recent_messages[-20:]
        self.updated_at = time.time()

    def add_intent(self, intent: str):
        self.recent_intents.append(intent)
        if len(self.recent_intents) > 10:
            self.recent_intents = self.recent_intents[-10:]
        self.updated_at = time.time()

    def add_entity(self, entity_type: str, entity_value: str):
        if entity_type not in self.mentioned_entities:
            self.mentioned_entities[entity_type] = []
        if entity_value not in self.mentioned_entities[entity_type]:
            self.mentioned_entities[entity_type].append(entity_value)
        self.updated_at = time.time()


class SessionStore(ABC):
    """会话存储抽象基类"""

    @abstractmethod
    def get(self, session_id: str) -> SessionData | None:
        pass

    @abstractmethod
    def set(self, session_id: str, data: SessionData, ttl: int = 3600) -> bool:
        pass

    @abstractmethod
    def delete(self, session_id: str) -> bool:
        pass

    @abstractmethod
    def exists(self, session_id: str) -> bool:
        pass

    @abstractmethod
    def update(self, session_id: str, updates: dict[str, Any]) -> bool:
        pass

    @abstractmethod
    def get_all_session_ids(self) -> list[str]:
        pass

    @abstractmethod
    def clear_expired(self) -> int:
        pass


class MemorySessionStore(SessionStore):
    """内存会话存储（默认实现，用于开发环境）"""

    def __init__(self, default_ttl: int = 3600):
        self._store: dict[str, dict[str, Any]] = {}
        self._expiry: dict[str, float] = {}
        self._lock = threading.RLock()
        self._default_ttl = default_ttl

    def get(self, session_id: str) -> SessionData | None:
        with self._lock:
            if session_id not in self._store:
                return None

            if session_id in self._expiry and time.time() > self._expiry[session_id]:
                del self._store[session_id]
                del self._expiry[session_id]
                return None

            data = self._store[session_id]
            return SessionData.from_dict(data)

    def set(self, session_id: str, data: SessionData, ttl: int = 3600) -> bool:
        with self._lock:
            self._store[session_id] = data.to_dict()
            self._expiry[session_id] = time.time() + (ttl or self._default_ttl)
            return True

    def delete(self, session_id: str) -> bool:
        with self._lock:
            if session_id in self._store:
                del self._store[session_id]
            if session_id in self._expiry:
                del self._expiry[session_id]
            return True

    def exists(self, session_id: str) -> bool:
        with self._lock:
            return session_id in self._store and (
                session_id not in self._expiry or time.time() <= self._expiry[session_id]
            )

    def update(self, session_id: str, updates: dict[str, Any]) -> bool:
        with self._lock:
            if session_id not in self._store:
                return False

            self._store[session_id].update(updates)
            self._store[session_id]["updated_at"] = time.time()
            return True

    def get_all_session_ids(self) -> list[str]:
        with self._lock:
            return list(self._store.keys())

    def clear_expired(self) -> int:
        with self._lock:
            current_time = time.time()
            expired = [
                sid for sid, expiry in self._expiry.items()
                if current_time > expiry
            ]
            for sid in expired:
                if sid in self._store:
                    del self._store[sid]
                del self._expiry[sid]
            return len(expired)

    def get_stats(self) -> dict[str, Any]:
        with self._lock:
            return {
                "total_sessions": len(self._store),
                "active_sessions": sum(
                    1 for sid in self._store
                    if sid not in self._expiry or time.time() <= self._expiry[sid]
                )
            }


class RedisSessionStore(SessionStore):
    """Redis 会话存储（生产环境推荐）"""

    def __init__(self, redis_client, prefix: str = "intent_session:", default_ttl: int = 3600):
        self.redis = redis_client
        self.prefix = prefix
        self._default_ttl = default_ttl

    def _get_key(self, session_id: str) -> str:
        return f"{self.prefix}{session_id}"

    def get(self, session_id: str) -> SessionData | None:
        try:
            data = self.redis.get(self._get_key(session_id))
            if data is None:
                return None
            return SessionData.from_dict(json.loads(data))
        except Exception as e:
            logger.error(f"Redis get 失败: {e}")
            return None

    def set(self, session_id: str, data: SessionData, ttl: int = 3600) -> bool:
        try:
            key = self._get_key(session_id)
            value = json.dumps(data.to_dict(), ensure_ascii=False)
            self.redis.setex(key, ttl or self._default_ttl, value)
            return True
        except Exception as e:
            logger.error(f"Redis set 失败: {e}")
            return False

    def delete(self, session_id: str) -> bool:
        try:
            self.redis.delete(self._get_key(session_id))
            return True
        except Exception as e:
            logger.error(f"Redis delete 失败: {e}")
            return False

    def exists(self, session_id: str) -> bool:
        try:
            return self.redis.exists(self._get_key(session_id)) > 0
        except Exception as e:
            logger.error(f"Redis exists 失败: {e}")
            return False

    def update(self, session_id: str, updates: dict[str, Any]) -> bool:
        try:
            data = self.get(session_id)
            if data is None:
                return False

            for key, value in updates.items():
                if hasattr(data, key):
                    setattr(data, key, value)
            data.updated_at = time.time()

            ttl = self.redis.ttl(self._get_key(session_id))
            if ttl > 0:
                return self.set(session_id, data, ttl)
            return self.set(session_id, data)
        except Exception as e:
            logger.error(f"Redis update 失败: {e}")
            return False

    def get_all_session_ids(self) -> list[str]:
        try:
            keys = self.redis.keys(f"{self.prefix}*")
            return [k.decode().replace(self.prefix, "") if isinstance(k, bytes) else k.replace(self.prefix, "") for k in keys]
        except Exception as e:
            logger.error(f"Redis get_all_session_ids 失败: {e}")
            return []

    def clear_expired(self) -> int:
        return 0


_store_instance: SessionStore | None = None
_store_lock = threading.Lock()


def get_session_store() -> SessionStore:
    """获取会话存储单例"""
    global _store_instance
    with _store_lock:
        if _store_instance is None:
            _store_instance = MemorySessionStore()
        return _store_instance


def set_session_store(store: SessionStore) -> None:
    """设置会话存储实现"""
    global _store_instance
    with _store_lock:
        _store_instance = store


def create_redis_session_store(redis_url: str = "redis://localhost:6379/0", **kwargs) -> RedisSessionStore:
    """创建 Redis 会话存储"""
    try:
        import redis
        client = redis.from_url(redis_url)
        return RedisSessionStore(client, **kwargs)
    except ImportError:
        logger.warning("Redis 库未安装，使用内存存储")
        return MemorySessionStore()
    except Exception as e:
        logger.warning(f"Redis 连接失败: {e}，使用内存存储")
        return MemorySessionStore()
