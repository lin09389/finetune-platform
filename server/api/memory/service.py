"""API facade for file-backed memory."""

from __future__ import annotations

from typing import Any

from memory.memory_service import get_memory_service


class MemoryAPIService:
    def __init__(self):
        self._memory_service = get_memory_service()

    def list_files(self, scope: str = "user", namespace: str = "default") -> list[dict[str, Any]]:
        return self._memory_service.list_files(scope=scope, namespace=namespace)

    def get_file(self, file_id: str) -> dict[str, Any]:
        return self._memory_service.get_file(file_id)

    def update_file(self, file_id: str, content: str, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        return self._memory_service.update_file(file_id=file_id, content=content, metadata=metadata)

    def search(self, query: str, scope: str | None, namespace: str | None, user_id: str, top_k: int) -> list[dict[str, Any]]:
        return self._memory_service.search_files(query, scope=scope, namespace=namespace, user_id=user_id, top_k=top_k)

    def consolidate(self, user_id: str, session_id: str | None = None) -> dict[str, Any]:
        return self._memory_service.consolidate(user_id=user_id, session_id=session_id)

    def list_episodes(self, user_id: str = "default", session_id: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        return self._memory_service.list_episodes(user_id=user_id, session_id=session_id, limit=limit)

    def migrate_from_items(self, user_id: str = "default") -> dict[str, Any]:
        return self._memory_service.migrate_from_items(user_id=user_id)


_memory_api_service: MemoryAPIService | None = None


def get_memory_api_service() -> MemoryAPIService:
    global _memory_api_service
    if _memory_api_service is None:
        _memory_api_service = MemoryAPIService()
    return _memory_api_service
