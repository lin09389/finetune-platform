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
            memory_type = options.memory_include_types[0] if options.memory_include_types else None
            memories = await asyncio.to_thread(
                service.recall,
                query=query,
                user_id=user_id,
                top_k=options.memory_top_k,
                memory_type=memory_type,
            )
            sources = [
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
            return RetrievalResult(sources=sources, duration=time.time() - start)
        except Exception as exc:
            logger.warning("记忆检索失败: %s", exc)
            return RetrievalResult(warnings=[f"memory_retrieval_failed: {exc}"], duration=time.time() - start)
