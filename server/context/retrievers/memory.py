"""Memory retriever for Context Engine."""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from context.budget import ContextBuildOptions, estimate_tokens
from context.pack import ContextSource
from context.retrievers.base import BaseContextRetriever, RetrievalResult

logger = logging.getLogger(__name__)

MEMORY_TYPE_TO_FILE = {
    "personal": "preferences.md",
    "preference": "preferences.md",
    "habit": "preferences.md",
    "project": "projects.md",
    "skill": "projects.md",
    "knowledge": "facts.md",
    "history": "facts.md",
}


class MemoryRetriever(BaseContextRetriever):
    kind = "memory"

    def __init__(self, memory_service: Any | None = None):
        self._memory_service = memory_service

    def _get_memory_service(self):
        if self._memory_service is None:
            from memory.memory_service import get_memory_service

            self._memory_service = get_memory_service()
        return self._memory_service

    async def retrieve(
        self,
        query: str,
        user_id: str,
        session_id: str | None,
        options: ContextBuildOptions,
    ) -> RetrievalResult:
        start = time.time()
        try:
            service = self._get_memory_service()
            if hasattr(service, "search_files"):
                sources = await self._retrieve_file_memory(service, query, user_id, options)
            else:
                sources = await self._retrieve_legacy_memory(service, query, user_id, options)
            return RetrievalResult(sources=sources, duration=time.time() - start)
        except Exception as exc:
            logger.warning("文件记忆检索失败，尝试 legacy recall: %s", exc)
            try:
                service = self._get_memory_service()
                sources = await self._retrieve_legacy_memory(service, query, user_id, options)
                return RetrievalResult(
                    sources=sources,
                    warnings=[f"file_memory_retrieval_failed_used_legacy: {exc}"],
                    duration=time.time() - start,
                )
            except Exception as fallback_exc:
                logger.warning("记忆检索失败: %s", fallback_exc)
                return RetrievalResult(warnings=[f"memory_retrieval_failed: {fallback_exc}"], duration=time.time() - start)

    async def _retrieve_file_memory(
        self,
        service: Any,
        query: str,
        user_id: str,
        options: ContextBuildOptions,
    ) -> list[ContextSource]:
        results = await asyncio.to_thread(
            service.search_files,
            query,
            scope="user",
            namespace=user_id,
            user_id=user_id,
            top_k=options.memory_top_k,
        )
        allowed_files = self._allowed_files(options.memory_include_types)
        sources: list[ContextSource] = []
        for result in results:
            path = str(result.get("path") or "")
            if allowed_files and not any(path.endswith(file_name) for file_name in allowed_files):
                continue
            snippet = str(result.get("snippet") or "").strip()
            if not snippet:
                continue
            memory_type = self._memory_type_from_path(path)
            metadata = {
                **(result.get("metadata", {}) or {}),
                "source_type": "file_memory",
                "source": path,
                "title": path,
                "path": path,
                "memory_path": path,
                "scope": result.get("scope", "user"),
                "namespace": result.get("namespace", user_id),
                "version": result.get("version"),
                "updated_at": result.get("updated_at"),
                "memory_type": memory_type,
                "type": memory_type,
                "importance": self._importance_for_path(path),
            }
            sources.append(
                ContextSource(
                    id=str(result.get("file_id") or result.get("id") or path),
                    kind="memory",
                    content=snippet,
                    score=float(result.get("score", 0.5) or 0.5),
                    tokens=estimate_tokens(snippet),
                    metadata=metadata,
                )
            )
        return sources

    async def _retrieve_legacy_memory(
        self,
        service: Any,
        query: str,
        user_id: str,
        options: ContextBuildOptions,
    ) -> list[ContextSource]:
        memory_type = options.memory_include_types[0] if options.memory_include_types else None
        memories = await asyncio.to_thread(
            service.recall,
            query=query,
            user_id=user_id,
            top_k=options.memory_top_k,
            memory_type=memory_type,
        )
        return [
            ContextSource(
                id=str(memory.get("id", "")),
                kind="memory",
                content=str(memory.get("content", "")),
                score=float(memory.get("relevance", 0.5) or 0.5),
                tokens=estimate_tokens(str(memory.get("content", ""))),
                metadata={
                    **(memory.get("metadata", {}) or {}),
                    "source_type": "long_term_memory",
                    "memory_type": memory.get("type"),
                    "type": memory.get("type"),
                    "importance": float(memory.get("importance", 0.5) or 0.5),
                    "created_at": memory.get("created_at"),
                },
            )
            for memory in memories
            if memory.get("content")
        ]

    def _allowed_files(self, include_types: list[str] | None) -> set[str]:
        if not include_types:
            return set()
        return {MEMORY_TYPE_TO_FILE[item] for item in include_types if item in MEMORY_TYPE_TO_FILE}

    def _memory_type_from_path(self, path: str) -> str:
        if path.endswith("preferences.md"):
            return "preference"
        if path.endswith("projects.md"):
            return "project"
        return "knowledge"

    def _importance_for_path(self, path: str) -> float:
        if path.endswith("preferences.md"):
            return 0.8
        if path.endswith("projects.md"):
            return 0.7
        return 0.5
