"""Memory API service backed only by long-term user memories."""

import logging
from datetime import datetime
from typing import Any

from memory.memory_service import get_memory_service

from .models import MemoryItem, MemorySearchResult, MemoryType

logger = logging.getLogger(__name__)


def _coerce_memory_type(value: str | MemoryType | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, MemoryType):
        return value.value
    return str(value)


def _map_memory_dict(memory: dict[str, Any]) -> MemoryItem:
    raw_type = _coerce_memory_type(memory.get("type")) or MemoryType.KNOWLEDGE.value
    try:
        memory_type = MemoryType(raw_type)
    except ValueError:
        memory_type = MemoryType.KNOWLEDGE

    created_at = memory.get("created_at")
    updated_at = memory.get("updated_at")
    if isinstance(created_at, str):
        created_at = datetime.fromisoformat(created_at)
    if isinstance(updated_at, str):
        updated_at = datetime.fromisoformat(updated_at)

    return MemoryItem(
        id=memory.get("id", ""),
        content=memory.get("content", ""),
        type=memory_type,
        importance=float(memory.get("importance", 0.5) or 0.5),
        source=memory.get("source", "memory_service"),
        created_at=created_at or datetime.now(),
        updated_at=updated_at or created_at or datetime.now(),
        access_count=int(memory.get("access_count", 0) or 0),
        metadata=memory.get("metadata", {}) or {},
        vector_state=memory.get("vector_state", "pending"),
        storage_mode=memory.get("storage_mode", "text_only"),
    )


class MemoryAPIService:
    """Compatibility wrapper for the long-term memory service."""

    def __init__(self):
        self._memory_service = get_memory_service()

    def _list_raw_memories(
        self,
        user_id: str,
        memory_type: MemoryType | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        raw_type = _coerce_memory_type(memory_type)
        return self._memory_service.list_memories(user_id=user_id, memory_type=raw_type, limit=limit)

    def create_memory(
        self,
        user_id: str,
        content: str,
        memory_type: MemoryType = MemoryType.KNOWLEDGE,
        importance: float = 0.5,
        metadata: dict[str, Any] | None = None,
    ) -> MemoryItem:
        memory_id = self._memory_service._store_memory(
            user_id,
            {
                "content": content,
                "type": memory_type.value,
                "importance": importance,
                "source": "api",
                "metadata": metadata or {},
            },
        )
        created = self._memory_service.get_memory(memory_id, user_id=user_id, increment_access=False)
        return _map_memory_dict(
            created
            or {
                "id": memory_id,
                "user_id": user_id,
                "content": content,
                "type": memory_type.value,
                "importance": importance,
                "source": "api",
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat(),
                "access_count": 0,
                "metadata": metadata or {},
            }
        )

    def get_memory(self, memory_id: str, user_id: str = "default") -> MemoryItem | None:
        memory = self._memory_service.get_memory(memory_id, user_id=user_id)
        return _map_memory_dict(memory) if memory else None

    def list_memories(
        self,
        user_id: str,
        memory_type: MemoryType | None = None,
        limit: int = 50,
    ) -> list[MemoryItem]:
        return [_map_memory_dict(memory) for memory in self._list_raw_memories(user_id, memory_type, limit)]

    def update_memory(
        self,
        memory_id: str,
        content: str | None = None,
        importance: float | None = None,
        metadata: dict[str, Any] | None = None,
        user_id: str = "default",
    ) -> MemoryItem | None:
        memory = self._memory_service.update_memory(
            memory_id=memory_id,
            user_id=user_id,
            content=content,
            importance=importance,
            metadata=metadata,
        )
        return _map_memory_dict(memory) if memory else None

    def delete_memory(self, memory_id: str, user_id: str = "default") -> bool:
        return self._memory_service.forget(user_id=user_id, memory_id=memory_id)

    def search_memories(
        self,
        user_id: str,
        query: str,
        top_k: int = 5,
        memory_type: MemoryType | None = None,
    ) -> list[MemorySearchResult]:
        memories = self._memory_service.recall(
            query=query,
            user_id=user_id,
            top_k=top_k,
            memory_type=_coerce_memory_type(memory_type),
        )
        return [
            MemorySearchResult(
                id=mapped.id,
                content=mapped.content,
                type=mapped.type,
                importance=mapped.importance,
                relevance=float(memory.get("relevance", 0.0) or 0.0),
                created_at=mapped.created_at,
                vector_state=mapped.vector_state,
                storage_mode=mapped.storage_mode,
            )
            for memory in memories
            for mapped in [_map_memory_dict(memory)]
        ]

    def get_stats(self, user_id: str) -> dict[str, Any]:
        stats = self._memory_service.get_stats(user_id)
        return {
            "total_memories": int(stats.get("total_memories", 0) or 0),
            "vector_collection_count": int(stats.get("vector_collection_count", 0) or 0),
            "collection_name": stats.get("collection_name", ""),
        }

    def clear_memories(self, user_id: str) -> int:
        count = len(self._list_raw_memories(user_id, limit=100000))
        self._memory_service.clear_all(user_id)
        return count

    def export_state(self, user_id: str) -> dict[str, Any]:
        return {
            "user_id": user_id,
            "memories": [memory.model_dump(mode="json") for memory in self.list_memories(user_id, limit=1000)],
        }

    def import_state(self, user_id: str, state: dict) -> bool:
        try:
            for memory in state.get("memories", []):
                raw_type = memory.get("type", MemoryType.KNOWLEDGE.value)
                try:
                    memory_type = MemoryType(raw_type)
                except ValueError:
                    memory_type = MemoryType.KNOWLEDGE
                self.create_memory(
                    user_id=user_id,
                    content=memory.get("content", ""),
                    memory_type=memory_type,
                    importance=float(memory.get("importance", 0.5) or 0.5),
                    metadata=memory.get("metadata", {}) or {},
                )
            return True
        except Exception as exc:
            logger.error("Failed to import memory state: %s", exc, exc_info=True)
            return False

    def get_summary(self, user_id: str) -> dict:
        return self._memory_service.get_user_summary(user_id)


_memory_api_service: MemoryAPIService | None = None


def get_memory_api_service() -> MemoryAPIService:
    """Get the memory API service singleton."""
    global _memory_api_service
    if _memory_api_service is None:
        _memory_api_service = MemoryAPIService()
    return _memory_api_service
