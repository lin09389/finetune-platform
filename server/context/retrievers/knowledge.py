"""Knowledge retriever for Context Engine."""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from context.budget import ContextBuildOptions, estimate_tokens
from context.pack import ContextSource
from context.retrievers.base import BaseContextRetriever, RetrievalResult

logger = logging.getLogger(__name__)


class KnowledgeRetriever(BaseContextRetriever):
    kind = "knowledge"

    def __init__(self, knowledge_integrator: Any | None = None):
        self._knowledge_integrator = knowledge_integrator

    def _get_knowledge_integrator(self):
        if self._knowledge_integrator is None:
            from context.knowledge_integration import get_knowledge_integrator

            self._knowledge_integrator = get_knowledge_integrator()
        return self._knowledge_integrator

    async def retrieve(
        self,
        query: str,
        user_id: str,
        session_id: str | None,
        options: ContextBuildOptions,
    ) -> RetrievalResult:
        start = time.time()
        try:
            if not options.knowledge_collection_id:
                return RetrievalResult(duration=time.time() - start)

            integrator = self._get_knowledge_integrator()
            should_retrieve, reason = await asyncio.to_thread(
                integrator.should_retrieve_knowledge,
                query=query,
                collection_id=options.knowledge_collection_id,
                force_retrieve=not options.knowledge_auto_retrieve,
            )
            if not should_retrieve:
                logger.debug("知识库检索跳过: %s", reason)
                return RetrievalResult(duration=time.time() - start)

            result = await asyncio.to_thread(
                integrator.retrieve_knowledge,
                query=query,
                collection_id=options.knowledge_collection_id,
                top_k=options.knowledge_top_k,
            )
            sources = [
                ContextSource(
                    id=str(source.id),
                    kind="knowledge",
                    content=str(source.content),
                    score=float(source.score or 0.0),
                    tokens=estimate_tokens(str(source.content)),
                    metadata={
                        **(source.metadata or {}),
                        "source": source.source,
                        "importance": 0.7,
                    },
                )
                for source in result.sources
                if source.content
            ]
            return RetrievalResult(sources=sources, duration=time.time() - start)
        except Exception as exc:
            logger.warning("知识库检索失败: %s", exc)
            return RetrievalResult(warnings=[f"knowledge_retrieval_failed: {exc}"], duration=time.time() - start)
