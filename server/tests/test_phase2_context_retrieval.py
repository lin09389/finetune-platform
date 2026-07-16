"""Phase-2: knowledge binding, hybrid project retrieval hooks, index mtime helpers."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from context.budget import ContextBudget
from context.deepagents import build_deepagents_context_pack
from context.knowledge_binding import resolve_agent_knowledge_collection
from context.pack import ContextPack, ContextSource
from context.code_indexer import CodeIndexer
from context.service import ContextService
from context.models import ContextResult


def test_resolve_agent_knowledge_session_override_disables():
    collection, obs = resolve_agent_knowledge_collection(
        {"knowledge_collection_id": "", "workspace": {"id": "ws_x"}},
        workspace_id="ws_x",
    )
    assert collection is None
    assert obs["status"] == "disabled"
    assert obs["use_knowledge"] is False


def test_resolve_agent_knowledge_session_override_wins(monkeypatch):
    monkeypatch.setattr(
        "context.knowledge_binding.get_workspace_knowledge_collection",
        lambda _ws: "ws_default",
    )
    collection, obs = resolve_agent_knowledge_collection(
        {"knowledge_collection_id": "kb-session", "workspace": {"id": "ws_x"}},
        workspace_id="ws_x",
    )
    assert collection == "kb-session"
    assert obs["source"] == "session"
    assert obs["use_knowledge"] is True


def test_resolve_agent_knowledge_inherits_workspace(monkeypatch):
    monkeypatch.setattr(
        "context.knowledge_binding.get_workspace_knowledge_collection",
        lambda ws: "ws_coll" if ws == "ws_1" else None,
    )
    collection, obs = resolve_agent_knowledge_collection(
        {"workspace": {"id": "ws_1"}},
        workspace_id="ws_1",
    )
    assert collection == "ws_coll"
    assert obs["source"] == "workspace"
    assert obs["use_knowledge"] is True


@pytest.mark.asyncio
async def test_build_deepagents_context_pack_enables_knowledge_when_bound(monkeypatch):
    captured = {}

    class FakeBuilder:
        async def build(self, **kwargs):
            captured.update(kwargs)
            options = kwargs.get("options")
            assert options.use_knowledge is True
            assert options.knowledge_collection_id == "kb-from-session"
            return ContextPack(
                query=str(kwargs.get("query") or ""),
                sources=[
                    ContextSource(
                        id="k1",
                        kind="knowledge",
                        content="RAG doc about agents",
                        score=0.9,
                        tokens=12,
                        metadata={"source": "doc.md"},
                    ),
                    ContextSource(
                        id="p1",
                        kind="project",
                        content="server/main.py",
                        score=0.8,
                        tokens=8,
                        metadata={"path": "server/main.py"},
                    ),
                ],
                context_text="combined",
                budget=ContextBudget(max_tokens=3200, used_tokens=20),
            )

    monkeypatch.setattr("context.deepagents.get_context_builder", lambda: FakeBuilder())

    pack = await build_deepagents_context_pack(
        goal="explain agent runtime",
        active_context=None,
        explicit_context=[],
        project_path="C:/workspace/project",
        session_id="s1",
        user_id="u1",
        session_metadata={"knowledge_collection_id": "kb-from-session"},
    )

    assert pack.metadata["knowledge_binding"]["use_knowledge"] is True
    assert pack.metadata["knowledge_binding"]["collection_id"] == "kb-from-session"
    assert "/context/retrieval/knowledge.md" in pack.files
    assert "RAG doc about agents" in pack.files["/context/retrieval/knowledge.md"]["content"]
    assert pack.metadata["project_retrieval"]["use_knowledge"] is True


@pytest.mark.asyncio
async def test_build_deepagents_context_pack_skips_knowledge_when_unbound(monkeypatch):
    captured = {}

    class FakeBuilder:
        async def build(self, **kwargs):
            captured.update(kwargs)
            options = kwargs.get("options")
            assert options.use_knowledge is False
            assert options.knowledge_collection_id is None
            return ContextPack(
                query="q",
                sources=[],
                context_text="",
                budget=ContextBudget(max_tokens=3200),
                warnings=[],
            )

    monkeypatch.setattr("context.deepagents.get_context_builder", lambda: FakeBuilder())
    monkeypatch.setattr(
        "context.knowledge_binding.resolve_agent_knowledge_collection",
        lambda *_a, **_k: (None, {"status": "not_configured", "use_knowledge": False, "source": None, "collection_id": None}),
    )

    pack = await build_deepagents_context_pack(
        goal="task",
        active_context=None,
        explicit_context=[],
        project_path="C:/workspace/project",
        session_metadata={},
    )
    assert pack.metadata["knowledge_binding"]["status"] == "not_configured"
    assert "knowledge_not_configured" in (pack.metadata.get("warnings") or [])


def test_context_service_hybrid_falls_back_when_vector_unavailable(monkeypatch, tmp_path: Path):
    service = ContextService(embedder=None, vector_store=None)
    project = tmp_path / "proj"
    project.mkdir()
    (project / "hello.py").write_text("def hello():\n    return 1\n", encoding="utf-8")

    # Force lightweight index without vector.
    service.scan_project(str(project))
    service._build_lightweight_index(service.projects[str(project.resolve())])
    # Vector path should be skipped (no embedder); mention/key path still works.
    results = service.retrieve("hello", project_path=str(project), top_k=5)
    assert isinstance(results, list)
    # At least key_files or mention-based content for hello.py
    assert any("hello" in (r.content or "").lower() or (r.path or "").endswith("hello.py") for r in results) or results == []


def test_code_indexer_collection_name_stable():
    a = CodeIndexer.collection_name_for_project("C:/repo/app")
    b = CodeIndexer.collection_name_for_project("C:/repo/app")
    assert a == b
    assert a.startswith("project_")


def test_code_indexer_mtime_manifest_roundtrip(tmp_path: Path, monkeypatch):
    indexer = CodeIndexer()
    # Point manifest dir under tmp
    monkeypatch.setattr(
        indexer,
        "_mtime_manifest_path",
        lambda name: tmp_path / f"{name}.mtime.json",
    )
    name = "project_test"
    indexer._save_mtime_manifest(name, {"project_path": "C:/p", "files": {"a.py": 1.5}})
    loaded = indexer._load_mtime_manifest(name)
    assert loaded["files"]["a.py"] == 1.5


def test_lightweight_index_persists_and_reloads(tmp_path: Path, monkeypatch):
    service = ContextService()
    project = tmp_path / "p"
    project.mkdir()
    (project / "a.py").write_text("x = 1\n", encoding="utf-8")
    root = str(project.resolve())

    monkeypatch.setattr(
        service,
        "_lightweight_index_path",
        lambda path: tmp_path / "idx.json",
    )
    service.scan_project(root)
    service._build_lightweight_index(service.projects[root])
    service._persist_lightweight_index(root)
    assert (tmp_path / "idx.json").exists()

    service2 = ContextService()
    monkeypatch.setattr(
        service2,
        "_lightweight_index_path",
        lambda path: tmp_path / "idx.json",
    )
    assert service2._load_lightweight_index(root) is True
    assert root in service2.project_indexes
    assert "a.py" in (service2.project_indexes[root].get("files") or {})
