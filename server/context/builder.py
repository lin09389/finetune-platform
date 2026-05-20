"""Context Engine builder."""
from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from collections.abc import Iterable

from context.budget import ContextBuildOptions, TokenBudget, estimate_tokens
from context.formatter import ContextFormatter
from context.pack import ContextConflict, ContextDecision, ContextPack, ContextSource, ContextTrace
from context.retrievers.base import BaseContextRetriever, RetrievalResult
from context.retrievers.knowledge import KnowledgeRetriever
from context.retrievers.memory import MemoryRetriever
from context.retrievers.project import ProjectRetriever

logger = logging.getLogger(__name__)


class ContextBuilder:
    """Build a ContextPack from memory, knowledge, and project retrievers."""

    def __init__(
        self,
        memory_retriever: BaseContextRetriever | None = None,
        knowledge_retriever: BaseContextRetriever | None = None,
        project_retriever: BaseContextRetriever | None = None,
        formatter: ContextFormatter | None = None,
    ):
        self.memory_retriever = memory_retriever or MemoryRetriever()
        self.knowledge_retriever = knowledge_retriever or KnowledgeRetriever()
        self.project_retriever = project_retriever or ProjectRetriever()
        self.formatter = formatter or ContextFormatter()

    async def build(
        self,
        query: str,
        user_id: str = "default",
        session_id: str | None = None,
        options: ContextBuildOptions | None = None,
    ) -> ContextPack:
        start = time.time()
        options = options or ContextBuildOptions()
        session_id = session_id or "default"

        tasks: list[tuple[str, asyncio.Task[RetrievalResult]]] = []
        for name, retriever in self._enabled_retrievers(options):
            tasks.append((
                name,
                asyncio.create_task(retriever.retrieve(query, user_id, session_id, options)),
            ))

        raw_sources: list[ContextSource] = []
        warnings: list[str] = []
        timings: dict[str, float] = {}

        if tasks:
            results = await asyncio.gather(*(task for _, task in tasks), return_exceptions=True)
            for (name, _), result in zip(tasks, results, strict=False):
                if isinstance(result, Exception):
                    logger.warning("%s retriever failed: %s", name, result)
                    warnings.append(f"{name}_retrieval_failed: {result}")
                    timings[name] = 0.0
                    continue
                raw_sources.extend(result.sources)
                warnings.extend(result.warnings)
                timings[name] = result.duration

        ranked_sources = self._rank_sources(raw_sources)
        candidates, decisions, conflicts = self._prepare_candidates(ranked_sources, options)
        limited_sources = candidates[: max(0, options.max_total_sources)]
        selected_sources, budget = TokenBudget(
            max_tokens=max(0, options.max_context_tokens),
            reserved_tokens=options.reserved_output_tokens,
        ).select(limited_sources)
        self._finalize_decisions(
            decisions=decisions,
            candidates=candidates,
            selected_sources=selected_sources,
            budget_dropped_ids=set(budget.dropped_sources),
            max_total_sources=max(0, options.max_total_sources),
        )

        sections = self.formatter.build_sections(selected_sources)
        context_text = self.formatter.build_context_text(sections)
        retrieval_time = time.time() - start
        timings["total"] = retrieval_time

        return ContextPack(
            query=query,
            user_id=user_id,
            session_id=session_id,
            sources=selected_sources,
            sections=sections,
            context_text=context_text,
            budget=budget,
            timings=timings,
            warnings=warnings,
            trace=ContextTrace(
                decisions=list(decisions.values()),
                conflicts=conflicts,
            ),
            retrieval_time=retrieval_time,
        )

    def _enabled_retrievers(
        self,
        options: ContextBuildOptions,
    ) -> Iterable[tuple[str, BaseContextRetriever]]:
        if options.use_memory:
            yield "memory", self.memory_retriever
        if options.use_knowledge and options.knowledge_collection_id:
            yield "knowledge", self.knowledge_retriever
        if options.use_project_context and options.project_path:
            yield "project", self.project_retriever

    def _rank_sources(self, sources: list[ContextSource]) -> list[ContextSource]:
        for source in sources:
            if source.tokens <= 0:
                source.tokens = estimate_tokens(source.content)

        return sorted(sources, key=lambda source: source.score * source.importance, reverse=True)

    def _prepare_candidates(
        self,
        ranked_sources: list[ContextSource],
        options: ContextBuildOptions,
    ) -> tuple[list[ContextSource], dict[str, ContextDecision], list[ContextConflict]]:
        decisions: dict[str, ContextDecision] = {}
        conflicts: list[ContextConflict] = []
        seen_by_content: dict[str, ContextSource] = {}
        seen_by_fact: dict[str, ContextSource] = {}
        candidates: list[ContextSource] = []

        for index, source in enumerate(ranked_sources, 1):
            decisions[source.id] = ContextDecision(
                source_id=source.id,
                kind=source.kind,
                selected=False,
                reason=self._selection_reason(source),
                score=source.score,
                importance=source.importance,
                tokens=source.tokens,
                rank=index,
            )

            content_key = self._content_key(source.content)
            existing = seen_by_content.get(content_key)
            if existing is not None:
                conflict = self._make_conflict(
                    conflict_type="duplicate_content",
                    source_ids=[existing.id, source.id],
                    description="来源内容归一化后相同。",
                    resolution=f"保留排名更高的来源 {existing.id}，丢弃 {source.id}。",
                )
                conflicts.append(conflict)
                decisions[source.id].dropped_reason = "duplicate_content"
                decisions[source.id].conflict_ids.append(conflict.id)
                decisions[existing.id].conflict_ids.append(conflict.id)
                continue
            seen_by_content[content_key] = source

            fact_key = self._fact_key(source)
            if fact_key:
                fact_peer = seen_by_fact.get(fact_key)
                if fact_peer is not None and self._content_key(fact_peer.content) != content_key:
                    conflict = self._make_conflict(
                        conflict_type="fact_conflict",
                        source_ids=[fact_peer.id, source.id],
                        description=f"多个来源声明同一事实键 {fact_key}，但内容不同。",
                        resolution="保留所有未超预算来源，并在 trace 中标记冲突，交由上层或模型谨慎处理。",
                    )
                    conflicts.append(conflict)
                    decisions[source.id].conflict_ids.append(conflict.id)
                    decisions[fact_peer.id].conflict_ids.append(conflict.id)
                else:
                    seen_by_fact[fact_key] = source

            candidates.append(source)

        max_total_sources = max(0, options.max_total_sources)
        for source in candidates[max_total_sources:]:
            decisions[source.id].dropped_reason = "max_total_sources_exceeded"

        return candidates, decisions, conflicts

    def _finalize_decisions(
        self,
        decisions: dict[str, ContextDecision],
        candidates: list[ContextSource],
        selected_sources: list[ContextSource],
        budget_dropped_ids: set[str],
        max_total_sources: int,
    ):
        selected_ids = {source.id for source in selected_sources}
        limited_ids = {source.id for source in candidates[:max_total_sources]}

        for source in candidates:
            decision = decisions[source.id]
            if source.id in selected_ids:
                decision.selected = True
                decision.reason = f"{decision.reason}; 排名进入候选集并符合 token 预算。"
            elif source.id in budget_dropped_ids:
                decision.dropped_reason = "token_budget_exceeded"
                decision.reason = f"{decision.reason}; 因 token 预算不足未进入 prompt。"
            elif source.id not in limited_ids and decision.dropped_reason is None:
                decision.dropped_reason = "max_total_sources_exceeded"
                decision.reason = f"{decision.reason}; 超过 max_total_sources 限制。"

    def _selection_reason(self, source: ContextSource) -> str:
        return (
            f"{source.kind} retriever 返回；按 score({source.score:.3f}) "
            f"* importance({source.importance:.3f}) 排序。"
        )

    def _fact_key(self, source: ContextSource) -> str | None:
        value = (
            source.metadata.get("fact_key")
            or source.metadata.get("claim_key")
            or source.metadata.get("entity_key")
        )
        return str(value) if value else None

    def _make_conflict(
        self,
        conflict_type: str,
        source_ids: list[str],
        description: str,
        resolution: str,
    ) -> ContextConflict:
        raw = f"{conflict_type}:{':'.join(source_ids)}:{description}"
        return ContextConflict(
            id=hashlib.md5(raw.encode("utf-8")).hexdigest(),
            source_ids=source_ids,
            conflict_type=conflict_type,
            description=description,
            resolution=resolution,
        )

    def _rank_and_deduplicate(self, sources: list[ContextSource]) -> list[ContextSource]:
        ranked = self._rank_sources(sources)
        seen: set[str] = set()
        unique: list[ContextSource] = []
        for source in ranked:
            key = self._content_key(source.content)
            if key in seen:
                continue
            seen.add(key)
            unique.append(source)
        return unique

    @staticmethod
    def _content_key(content: str) -> str:
        normalized = " ".join(content.split()).strip().lower()
        return hashlib.md5(normalized.encode("utf-8")).hexdigest()


_builder_instance: ContextBuilder | None = None


def get_context_builder() -> ContextBuilder:
    global _builder_instance
    if _builder_instance is None:
        _builder_instance = ContextBuilder()
    return _builder_instance
