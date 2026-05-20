"""Project context retriever for Context Engine."""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from context.budget import ContextBuildOptions, estimate_tokens
from context.pack import ContextSource
from context.retrievers.base import BaseContextRetriever, RetrievalResult

logger = logging.getLogger(__name__)


class ProjectRetriever(BaseContextRetriever):
    kind = "project"

    def __init__(self, context_service: Any | None = None):
        self._context_service = context_service

    def _get_context_service(self):
        if self._context_service is None:
            from context.service import get_context_service
            from rag.embedder import get_embedder
            from rag.vector_store import get_vector_store

            embedder = get_embedder()
            vector_store = get_vector_store()
            self._context_service = get_context_service(embedder=embedder, vector_store=vector_store)
        return self._context_service

    async def retrieve(
        self,
        query: str,
        user_id: str,
        session_id: str | None,
        options: ContextBuildOptions,
    ) -> RetrievalResult:
        start = time.time()
        try:
            if not options.project_path:
                return RetrievalResult(duration=time.time() - start)

            service = self._get_context_service()
            context_text = await asyncio.to_thread(
                service.get_context_for_chat,
                query=query,
                project_path=options.project_path,
                max_length=options.project_max_tokens,
            )
            if not context_text:
                return RetrievalResult(duration=time.time() - start)

            source = ContextSource(
                id=f"project:{options.project_path}",
                kind="project",
                content=context_text,
                score=0.8,
                tokens=estimate_tokens(context_text),
                metadata={
                    "source_type": "project_info",
                    "path": options.project_path,
                    "importance": 0.6,
                },
            )
            return RetrievalResult(sources=[source], duration=time.time() - start)
        except Exception as exc:
            logger.warning("项目上下文检索失败: %s", exc)
            return RetrievalResult(warnings=[f"project_retrieval_failed: {exc}"], duration=time.time() - start)
