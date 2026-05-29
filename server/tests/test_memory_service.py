"""Filesystem-backed memory service tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.storage import MemoryRepository
from memory import memory_service as memory_module
from memory.memory_service import MemoryService, decode_file_id


@pytest.fixture
def service(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_path = tmp_path / "app.db"
    monkeypatch.setattr(memory_module, "MemoryRepository", lambda: MemoryRepository(str(db_path)))
    return MemoryService(root_dir=tmp_path / "deep_memory")


def test_namespace_isolation(service: MemoryService):
    alice = service.list_files("user", "alice")
    bob = service.list_files("user", "bob")

    assert alice[0]["namespace"] == "alice"
    assert bob[0]["namespace"] == "bob"
    assert {file["id"] for file in alice}.isdisjoint({file["id"] for file in bob})


def test_org_policy_is_read_only(service: MemoryService):
    policy = service.list_files("org", "default-org")[0]

    with pytest.raises(PermissionError):
        service.update_file(policy["id"], "# Changed\n")


def test_file_write_increments_version_and_checksum(service: MemoryService):
    file = next(item for item in service.list_files("user", "default") if item["relative_path"] == "preferences.md")
    updated = service.update_file(file["id"], file["content"] + "- 用户偏好：回答简洁\n")

    assert updated["version"] == file["version"] + 1
    scope, namespace, relative_path = decode_file_id(updated["id"])
    path = service.store._resolve_file_path(scope, namespace, relative_path)
    meta = json.loads(path.with_name(f"{path.name}.meta.json").read_text(encoding="utf-8"))
    assert meta["checksum"]


def test_search_finds_memory_files(service: MemoryService):
    file = next(item for item in service.list_files("user", "default") if item["relative_path"] == "projects.md")
    service.update_file(file["id"], file["content"] + "- 项目使用 DeepAgents 文件记忆\n")

    results = service.search_files("DeepAgents 文件", scope="user", namespace="default")

    assert results
    assert results[0]["path"].endswith("projects.md")
    assert "DeepAgents" in results[0]["snippet"]


def test_migrate_from_items_is_idempotent(service: MemoryService):
    service.repository.create(
        {
            "id": "legacy-1",
            "user_id": "default",
            "content": "用户喜欢 QLoRA",
            "type": "preference",
            "importance": 0.8,
            "source": "test",
        }
    )

    first = service.migrate_from_items("default")
    second = service.migrate_from_items("default")

    assert first["migrated"] == 1
    assert second["migrated"] == 0
    assert second["skipped"] == 1


def test_episode_jsonl_order_is_stable(service: MemoryService):
    service.consolidator.record_episode("default", "s1", "user", "第一条")
    service.consolidator.record_episode("default", "s1", "assistant", "第二条")

    episodes = service.list_episodes("default", "s1")

    assert [event["content"] for event in episodes] == ["第一条", "第二条"]
