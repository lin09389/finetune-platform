from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.chat import routes as chat_routes
from api.chat.session import SessionManager
from api import chat_share
from core.db_manager import close_all_pools
from core.storage import (
    ChatRepository,
    backup_storage,
    check_storage,
    migrate_json_state,
    storage_status,
)
from core.storage_worker import StorageOutboxWorker


class FakeContextManager:
    def add_message(self, *args, **kwargs):
        return None

    def clear_context(self, *args, **kwargs):
        return None


def test_runtime_storage_check_and_backup(tmp_path: Path):
    db_path = str(tmp_path / "app.db")
    repo = ChatRepository(db_path)
    repo.save_session(DummySession())

    check = check_storage(db_path)
    backup = backup_storage(db_path, backup_dir=tmp_path / "backups")

    assert check["status"] == "ok"
    assert backup["integrity"]["status"] == "ok"
    assert Path(backup["backup_path"]).exists()
    assert storage_status(db_path)["last_backup"] is None
    close_all_pools()


def test_json_data_migration_is_manual_and_idempotent(tmp_path: Path):
    db_path = str(tmp_path / "app.db")
    data_dir = tmp_path / "data"
    sessions_dir = data_dir / "sessions"
    sessions_dir.mkdir(parents=True)
    now = datetime.now().isoformat()
    (sessions_dir / "session_1.json").write_text(
        """
        {
          "id": "session_1",
          "title": "Migrated",
          "messages": [],
          "message_count": 0,
          "created_at": "%s",
          "updated_at": "%s",
          "metadata": {}
        }
        """
        % (now, now),
        encoding="utf-8",
    )

    first = migrate_json_state(db_path=db_path, base_dir=data_dir)
    second = migrate_json_state(db_path=db_path, base_dir=data_dir)

    assert first["sessions"] == 1
    assert second["sessions"] == 0
    assert ChatRepository(db_path).get_session("session_1") is not None
    close_all_pools()


def test_session_manager_bootstraps_legacy_json_when_sqlite_is_empty(tmp_path: Path):
    db_path = str(tmp_path / "app.db")
    sessions_dir = tmp_path / "sessions"
    sessions_dir.mkdir()
    now = datetime.now().isoformat()
    (sessions_dir / "session_legacy.json").write_text(
        """
        {
          "id": "session_legacy",
          "title": "Legacy",
          "messages": [],
          "message_count": 0,
          "created_at": "%s",
          "updated_at": "%s",
          "metadata": {}
        }
        """
        % (now, now),
        encoding="utf-8",
    )

    manager = SessionManager(storage_path=sessions_dir, db_path=db_path)

    assert manager.get_session("session_legacy") is not None
    assert ChatRepository(db_path).get_session("session_legacy") is not None
    close_all_pools()


def test_chat_share_lazy_migrates_legacy_json(tmp_path: Path, monkeypatch):
    db_path = str(tmp_path / "app.db")
    share_dir = tmp_path / "share"
    share_dir.mkdir()
    monkeypatch.setattr(chat_share, "SHARE_DIR", share_dir)
    monkeypatch.setattr(chat_share, "share_repository", chat_share.ChatShareRepository(db_path))
    ChatRepository(db_path).save_session(DummySession())
    payload = {
        "share_id": "legacy_share",
        "session_id": "session_1",
        "title": "Legacy Share",
        "messages": [],
        "created_at": datetime.now().isoformat(),
        "expires_at": None,
        "view_count": 0,
        "is_public": True,
    }
    (share_dir / "share_legacy_share.json").write_text(
        __import__("json").dumps(payload),
        encoding="utf-8",
    )

    share = chat_share.load_share("legacy_share")

    assert share is not None
    assert share.share_id == "legacy_share"
    assert chat_share.share_repository.get_share("legacy_share") is not None
    close_all_pools()


def test_storage_outbox_worker_process_once(monkeypatch, tmp_path: Path):
    calls: list[dict] = []

    def fake_process_storage_outbox(db_path: str, limit: int):
        calls.append({"db_path": db_path, "limit": limit})
        return {"json": {"attempted": 1, "done": 1, "failed": 0}, "vector": {"attempted": 0}}

    monkeypatch.setattr("core.storage_worker.process_storage_outbox", fake_process_storage_outbox)
    worker = StorageOutboxWorker(db_path=str(tmp_path / "app.db"), interval_seconds=60, batch_size=7)

    result = asyncio.run(worker.process_once())

    assert result["json"]["done"] == 1
    assert calls == [{"db_path": str(tmp_path / "app.db"), "limit": 7}]


def test_chat_messages_api_concurrent_append(monkeypatch, tmp_path: Path):
    db_path = str(tmp_path / "app.db")
    manager = SessionManager(storage_path=str(tmp_path / "sessions"), db_path=db_path)
    session = manager.create_session("API concurrent")

    monkeypatch.setattr(chat_routes, "get_session_manager", lambda: manager)
    monkeypatch.setattr(chat_routes, "get_context_manager", lambda: FakeContextManager())

    app = FastAPI()
    app.include_router(chat_routes.router)
    client = TestClient(app)

    def post_message(index: int) -> dict:
        response = client.post(
            f"/chat/sessions/{session.id}/messages",
            json={"role": "user", "content": f"message {index}", "metadata": {}},
        )
        assert response.status_code == 200
        return response.json()

    with ThreadPoolExecutor(max_workers=10) as executor:
        created = list(executor.map(post_message, range(50)))

    messages_response = client.get(f"/chat/sessions/{session.id}/messages?limit=100")
    messages = messages_response.json()["messages"]

    assert len(created) == 50
    assert len(messages) == 50
    assert len({message["id"] for message in messages}) == 50
    close_all_pools()


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
