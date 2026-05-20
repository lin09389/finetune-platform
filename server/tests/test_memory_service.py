"""Long-term memory service tests."""

from pathlib import Path

import pytest

from core.storage import MemoryRepository
from memory import memory_service as memory_module


@pytest.fixture
def service(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_path = tmp_path / "app.db"

    monkeypatch.setattr(memory_module, "MemoryRepository", lambda: MemoryRepository(str(db_path)))
    monkeypatch.setattr(
        "rag.embedder.get_embedder",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("embedding disabled")),
    )

    service = memory_module.MemoryService(vector_db_path=str(tmp_path / "vectors"))
    service._embedding_available = False
    service.embedder = None
    service.vector_store = None
    return service


def test_store_memory_writes_to_sqlite(service):
    memory_id = service._store_memory(
        "default",
        {
            "content": "用户喜欢低显存 LoRA 微调流程",
            "type": "preference",
            "importance": 0.8,
            "source": "test",
        },
    )

    memory = service.get_memory(memory_id, increment_access=False)

    assert memory is not None
    assert memory["content"] == "用户喜欢低显存 LoRA 微调流程"
    assert memory["type"] == "preference"
    assert memory["vector_state"] == "failed"


def test_recall_uses_text_fallback_when_vectors_are_disabled(service):
    service._store_memory(
        "default",
        {
            "content": "SQLite durable memory search",
            "type": "knowledge",
            "importance": 0.7,
            "source": "test",
        },
    )

    results = service.recall("durable memory", user_id="default", top_k=5)

    assert len(results) == 1
    assert results[0]["content"] == "SQLite durable memory search"
    assert results[0]["storage_mode"] == "text_only"


def test_forget_hides_memory_from_get_list_and_search(service):
    memory_id = service._store_memory(
        "default",
        {
            "content": "临时测试记忆",
            "type": "knowledge",
            "importance": 0.5,
            "source": "test",
        },
    )

    assert service.forget("default", memory_id) is True
    assert service.get_memory(memory_id, increment_access=False) is None
    assert service.list_memories("default") == []
    assert service.recall("临时测试", user_id="default") == []


def test_update_content_marks_vector_state(service):
    memory_id = service._store_memory(
        "default",
        {
            "content": "旧内容",
            "type": "knowledge",
            "importance": 0.5,
            "source": "test",
        },
    )

    updated = service.update_memory(memory_id, user_id="default", content="新内容")

    assert updated is not None
    assert updated["content"] == "新内容"
    assert updated["vector_state"] == "failed"
    assert updated["storage_mode"] == "text_only"


def test_get_stats_reports_total_memories(service):
    service._store_memory(
        "default",
        {
            "content": "统计测试",
            "type": "knowledge",
            "importance": 0.5,
            "source": "test",
        },
    )

    stats = service.get_stats("default")

    assert stats["total_memories"] == 1
