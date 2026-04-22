"""
Memory API service backed by the real memory, short-term memory, and graph systems.
"""
import logging
from datetime import datetime
from typing import Any

from memory.knowledge_graph import get_knowledge_graph
from memory.memory_service import get_memory_service
from memory.short_term_memory import get_short_term_memory, get_stm_manager

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
    """Compatibility wrapper for the real memory subsystems."""

    def __init__(self):
        self._memory_service = get_memory_service()
        self._knowledge_graph = get_knowledge_graph()
        self._stm_manager = get_stm_manager()

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
        created = self._memory_service.get_memory(memory_id, user_id=user_id, increment_access=False) or {
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
        return _map_memory_dict(created)

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
        raw_type = _coerce_memory_type(memory_type)
        memories = self._memory_service.recall(
            query=query,
            user_id=user_id,
            top_k=top_k,
            memory_type=raw_type,
        )
        results: list[MemorySearchResult] = []
        for memory in memories:
            mapped = _map_memory_dict(memory)
            results.append(
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
            )
        return results

    def get_stats(self, user_id: str) -> dict[str, Any]:
        return {
            "total_memories": self._memory_service.get_stats(user_id).get("total_memories", 0),
            "knowledge_graph": self._knowledge_graph.get_stats(),
            "short_term_memory": get_short_term_memory("default").summarize(),
        }

    def clear_memories(self, user_id: str) -> int:
        count = len(self._list_raw_memories(user_id, limit=100000))
        self._memory_service.clear_all(user_id)
        return count

    def export_state(self, user_id: str) -> dict[str, Any]:
        return {
            "user_id": user_id,
            "memories": [memory.model_dump(mode="json") for memory in self.list_memories(user_id, limit=1000)],
            "knowledge_graph": self._knowledge_graph.to_dict(),
            "sessions": {
                session_id: get_short_term_memory(session_id).export_state()
                for session_id in self._stm_manager.get_all_sessions()
            },
        }

    def import_state(self, user_id: str, state: dict) -> bool:
        try:
            for memory in state.get("memories", []):
                self.create_memory(
                    user_id=user_id,
                    content=memory.get("content", ""),
                    memory_type=MemoryType(memory.get("type", MemoryType.KNOWLEDGE.value)),
                    importance=float(memory.get("importance", 0.5) or 0.5),
                    metadata=memory.get("metadata", {}) or {},
                )

            if state.get("knowledge_graph"):
                self._knowledge_graph.from_dict(state["knowledge_graph"])

            for session_id, session_state in (state.get("sessions") or {}).items():
                get_short_term_memory(session_id).import_state(session_state)

            return True
        except Exception as exc:
            logger.error("Failed to import memory state: %s", exc, exc_info=True)
            return False

    def get_summary(self, user_id: str) -> dict:
        return {
            "total_count": len(self._list_raw_memories(user_id, limit=100000)),
            "by_type": self._memory_service.get_user_summary(user_id).get("by_type", {}),
            "knowledge_graph": self._knowledge_graph.get_stats(),
        }

    def get_context(self, user_id: str, query: str, session_id: str | None = None) -> str:
        session = get_short_term_memory(session_id or "default")
        short_term_context = session.get_context(max_tokens=1500)
        long_term_context = self._memory_service.get_context_with_memory(query=query, user_id=user_id, max_memories=5)
        parts = [part for part in [short_term_context, long_term_context] if part]
        return "\n\n".join(parts)

    def list_sessions(self) -> list[str]:
        return self._stm_manager.get_all_sessions()

    def get_session_context(self, session_id: str, max_tokens: int = 4000) -> dict:
        session = get_short_term_memory(session_id)
        return {
            "context": session.get_context(max_tokens=max_tokens),
            "summary": session.summarize(),
        }

    def add_session_message(self, session_id: str, role: str, content: str, entities: list[str] | None = None) -> bool:
        self._stm_manager.add_message(role=role, content=content, session_id=session_id, entities=entities)
        return True

    def clear_session(self, session_id: str) -> bool:
        self._stm_manager.clear_session(session_id)
        return True

    def get_active_entities(self, session_id: str, threshold: float = 0.3) -> list[str]:
        return get_short_term_memory(session_id).get_active_entities(threshold=threshold)

    def add_entity(self, name: str, entity_type: str, attributes: dict | None = None, confidence: float = 0.5) -> tuple:
        return self._knowledge_graph.add_entity(name, entity_type, attributes or {}, confidence)

    def add_relation(self, source_name: str, target_name: str, relation_type: str, evidence: str = "") -> str | None:
        return self._knowledge_graph.add_relation(source_name, target_name, relation_type, evidence=evidence)

    def get_entity(self, entity_id: str) -> dict | None:
        entity = self._knowledge_graph.get_entity(entity_id)
        return entity.to_dict() if entity else None

    def get_entity_context(self, entity_id: str, depth: int = 2) -> dict:
        return self._knowledge_graph.get_entity_context(entity_id, depth)

    def find_path(self, source_id: str, target_id: str, max_depth: int = 4) -> list:
        return self._knowledge_graph.find_path(source_id, target_id, max_depth)

    def search_graph(self, query: str, entity_types: list[str] | None = None, limit: int = 10) -> list:
        entities = self._knowledge_graph.get_all_entities()
        if entity_types:
            entities = [entity for entity in entities if entity.entity_type in entity_types]
        if query:
            query_lower = query.lower()
            entities = [
                entity for entity in entities
                if query_lower in entity.name.lower()
                or query_lower in str(entity.attributes).lower()
            ]
        return [entity.to_dict() for entity in entities[:limit]]

    def get_graph_stats(self) -> dict:
        return self._knowledge_graph.get_stats()

    def delete_entity(self, entity_id: str) -> bool:
        return self._knowledge_graph.delete_entity(entity_id)

    def list_relations(self) -> list:
        return [relation.to_dict() for relation in self._knowledge_graph.get_all_relations()]


_memory_api_service: MemoryAPIService | None = None


def get_memory_api_service() -> MemoryAPIService:
    """Get the memory API service singleton."""
    global _memory_api_service
    if _memory_api_service is None:
        _memory_api_service = MemoryAPIService()
    return _memory_api_service
