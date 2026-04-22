from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from core.db_manager import close_all_pools, get_db_connection
from core.storage import (
    ChatRepository,
    MemoryRepository,
    StorageOutboxRepository,
    init_storage,
    process_json_outbox,
    storage_status,
)


@dataclass
class DummySession:
    id: str = "session_1"

    def to_dict(self) -> dict:
        now = datetime.now().isoformat()
        return {
            "id": self.id,
            "title": "Test Session",
            "message_count": 0,
            "created_at": now,
            "updated_at": now,
            "metadata": {},
            "messages": [],
        }


def test_db_manager_rolls_back_and_releases_file(tmp_path: Path):
    db_path = str(tmp_path / "app.db")
    init_storage(db_path)

    try:
        with get_db_connection(db_path) as conn:
            conn.execute("CREATE TABLE rollback_probe (id TEXT PRIMARY KEY)")
            conn.execute("INSERT INTO rollback_probe (id) VALUES ('a')")
            raise RuntimeError("force rollback")
    except RuntimeError:
        pass

    with get_db_connection(db_path) as conn:
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='rollback_probe'"
        ).fetchone()
    assert row is None

    close_all_pools()
    (tmp_path / "app.db").unlink()


def test_chat_append_messages_are_ordered_under_concurrency(tmp_path: Path):
    db_path = str(tmp_path / "app.db")
    repo = ChatRepository(db_path)
    repo.save_session(DummySession())

    def append(index: int) -> None:
        repo.append_message(
            "session_1",
            {
                "id": f"msg_{index}",
                "role": "user",
                "content": f"message {index}",
                "created_at": datetime.now().isoformat(),
                "metadata": {},
            },
        )

    threads = [threading.Thread(target=append, args=(index,)) for index in range(20)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    session = repo.get_session("session_1")
    assert session is not None
    assert session["message_count"] == 20
    assert len(session["messages"]) == 20
    assert len({message["id"] for message in session["messages"]}) == 20

    close_all_pools()


def test_outbox_survives_and_processes_json_shadow_write(tmp_path: Path):
    db_path = str(tmp_path / "app.db")
    target = tmp_path / "shadow" / "session.json"
    outbox = StorageOutboxRepository(db_path)
    outbox.enqueue(
        "json_shadow_write",
        str(target),
        {"id": "session_1", "messages": []},
        task_id="json_session_1",
    )

    result = process_json_outbox(db_path, limit=10)

    assert result["attempted"] == 1
    assert result["done"] == 1
    assert target.exists()
    assert outbox.counts().get("done") == 1

    close_all_pools()


def test_memory_text_search_uses_sqlite_fallback_path(tmp_path: Path):
    db_path = str(tmp_path / "app.db")
    repo = MemoryRepository(db_path)
    repo.create({
        "id": "mem_1",
        "user_id": "user_1",
        "content": "SQLite durable memory search",
        "type": "knowledge",
        "importance": 0.8,
    })

    results = repo.search_text("durable", user_id="user_1", top_k=5)

    assert results
    assert results[0]["id"] == "mem_1"
    assert storage_status(db_path)["tables"]["memory_items"] == 1

    close_all_pools()
