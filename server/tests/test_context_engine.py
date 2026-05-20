import asyncio
import os
import sys
from dataclasses import dataclass

import pytest

server_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, server_dir)

from context.budget import ContextBuildOptions
from context.builder import ContextBuilder
from context.pack import ContextSource
from context.retrievers.base import BaseContextRetriever, RetrievalResult
from context.retrievers.knowledge import KnowledgeRetriever
from context.retrievers.memory import MemoryRetriever
from context.retrievers.project import ProjectRetriever


class FakeMemoryService:
    def recall(self, query, user_id, top_k, memory_type=None):
        assert query == "query"
        assert user_id == "u1"
        assert top_k == 2
        assert memory_type == "preference"
        return [
            {
                "id": "mem-1",
                "content": "用户喜欢简洁回答",
                "type": "preference",
                "relevance": 0.9,
                "importance": 0.8,
                "metadata": {"source": "profile"},
            }
        ]


@dataclass
class FakeKnowledgeItem:
    id: str
    content: str
    source: str
    score: float
    metadata: dict


@dataclass
class FakeKnowledgeResult:
    sources: list[FakeKnowledgeItem]


class FakeKnowledgeIntegrator:
    def should_retrieve_knowledge(self, query, collection_id, force_retrieve=False):
        assert collection_id == "docs"
        return True, "forced"

    def retrieve_knowledge(self, query, collection_id, top_k):
        assert top_k == 1
        return FakeKnowledgeResult(
            sources=[
                FakeKnowledgeItem(
                    id="doc-1",
                    content="RAG reference content",
                    source="guide.md",
                    score=0.91,
                    metadata={"chapter": "intro"},
                )
            ]
        )


class FakeProjectService:
    def get_context_for_chat(self, query, project_path=None, max_length=2000):
        assert project_path == "C:/repo"
        assert max_length == 128
        return "[app.py]\ndef main(): pass"


@pytest.mark.asyncio
async def test_retrievers_return_context_sources():
    options = ContextBuildOptions(
        memory_top_k=2,
        memory_include_types=["preference"],
        knowledge_collection_id="docs",
        knowledge_top_k=1,
        project_path="C:/repo",
        project_max_tokens=128,
    )

    memory = await MemoryRetriever(FakeMemoryService()).retrieve("query", "u1", "s1", options)
    knowledge = await KnowledgeRetriever(FakeKnowledgeIntegrator()).retrieve("query", "u1", "s1", options)
    project = await ProjectRetriever(FakeProjectService()).retrieve("query", "u1", "s1", options)

    assert memory.sources[0].kind == "memory"
    assert memory.sources[0].memory_type == "preference"
    assert knowledge.sources[0].kind == "knowledge"
    assert knowledge.sources[0].source == "guide.md"
    assert project.sources[0].kind == "project"
    assert project.sources[0].path == "C:/repo"


class FakeRetriever(BaseContextRetriever):
    def __init__(self, kind, sources, delay=0.0):
        self.kind = kind
        self._sources = sources
        self._delay = delay

    async def retrieve(self, query, user_id, session_id, options):
        if self._delay:
            await asyncio.sleep(self._delay)
        return RetrievalResult(sources=self._sources, duration=self._delay)


@pytest.mark.asyncio
async def test_builder_merges_deduplicates_and_formats_sections():
    duplicate_content = "same useful content"
    builder = ContextBuilder(
        memory_retriever=FakeRetriever(
            "memory",
            [
                ContextSource("mem-1", "memory", "用户偏好中文", score=0.9, metadata={"importance": 0.9}),
                ContextSource("mem-dup", "memory", duplicate_content, score=0.6, metadata={"importance": 0.5}),
            ],
        ),
        knowledge_retriever=FakeRetriever(
            "knowledge",
            [
                ContextSource("doc-1", "knowledge", duplicate_content, score=0.8, metadata={"source": "guide.md"}),
            ],
        ),
        project_retriever=FakeRetriever(
            "project",
            [
                ContextSource("proj-1", "project", "项目使用 FastAPI", score=0.7, metadata={"path": "server/main.py"}),
            ],
        ),
    )

    pack = await builder.build(
        "query",
        "u1",
        "s1",
        ContextBuildOptions(
            use_memory=True,
            use_knowledge=True,
            use_project_context=True,
            knowledge_collection_id="docs",
            project_path="C:/repo",
            max_context_tokens=1000,
        ),
    )

    assert pack.total_sources == 3
    assert {source.id for source in pack.sources} == {"mem-1", "doc-1", "proj-1"}
    system_prompt = pack.build_system_prompt("base")
    assert "【用户记忆】" in system_prompt
    assert "【参考资料】" in system_prompt
    assert "【项目上下文】" in system_prompt
    assert "请根据以上上下文信息回答用户问题" in system_prompt
    assert pack.trace.prompt_artifact is not None
    assert pack.trace.prompt_artifact.system_prompt == system_prompt
    assert pack.trace.prompt_artifact.prompt_hash

    duplicate_conflicts = [conflict for conflict in pack.trace.conflicts if conflict.conflict_type == "duplicate_content"]
    assert duplicate_conflicts
    assert {decision.source_id: decision for decision in pack.trace.decisions}["mem-dup"].dropped_reason == "duplicate_content"
    assert {decision.source_id: decision for decision in pack.trace.decisions}["doc-1"].selected is True


@pytest.mark.asyncio
async def test_builder_token_budget_drops_sources():
    builder = ContextBuilder(
        memory_retriever=FakeRetriever(
            "memory",
            [
                ContextSource("short", "memory", "短内容", score=1.0, metadata={"importance": 1.0}),
                ContextSource("long", "memory", "很长的内容" * 200, score=0.9, metadata={"importance": 1.0}),
            ],
        )
    )

    pack = await builder.build(
        "query",
        options=ContextBuildOptions(
            use_memory=True,
            use_knowledge=False,
            use_project_context=False,
            max_context_tokens=20,
        ),
    )

    assert [source.id for source in pack.sources] == ["short"]
    assert "long" in pack.budget.dropped_sources
    assert pack.budget.dropped_tokens > 0
    decisions = {decision.source_id: decision for decision in pack.trace.decisions}
    assert decisions["short"].selected is True
    assert decisions["short"].reason
    assert decisions["long"].dropped_reason == "token_budget_exceeded"


@pytest.mark.asyncio
async def test_builder_marks_fact_conflicts_without_dropping_sources():
    builder = ContextBuilder(
        memory_retriever=FakeRetriever(
            "memory",
            [
                ContextSource("mem-old", "memory", "用户偏好英文回答", score=0.9, metadata={"fact_key": "reply_language"}),
                ContextSource("mem-new", "memory", "用户偏好中文回答", score=0.8, metadata={"fact_key": "reply_language"}),
            ],
        )
    )

    pack = await builder.build(
        "query",
        options=ContextBuildOptions(use_memory=True, max_context_tokens=1000),
    )

    assert {source.id for source in pack.sources} == {"mem-old", "mem-new"}
    assert [conflict.conflict_type for conflict in pack.trace.conflicts] == ["fact_conflict"]
    decisions = {decision.source_id: decision for decision in pack.trace.decisions}
    assert decisions["mem-old"].conflict_ids
    assert decisions["mem-new"].conflict_ids


@pytest.mark.asyncio
async def test_retriever_failure_becomes_warning():
    class FailingMemoryService:
        def recall(self, **kwargs):
            raise RuntimeError("boom")

    result = await MemoryRetriever(FailingMemoryService()).retrieve(
        "query",
        "u1",
        "s1",
        ContextBuildOptions(),
    )

    assert result.sources == []
    assert result.warnings
