from __future__ import annotations

import asyncio
import sqlite3
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
    APP_DB_PATH,
    ChatRepository,
    backup_all,
    backup_storage,
    cleanup_langgraph_checkpoints,
    check_storage,
    get_langgraph_checkpoint_db_path,
    import_legacy_agent_session_database,
    migrate_json_state,
    resolve_storage_path,
    storage_status,
)
from core.config import settings
from agent_session.repository import AgentSessionRepository
from core.storage_worker import StorageOutboxWorker


class FakeContextManager:
    def add_message(self, *args, **kwargs):
        return None

    def clear_context(self, *args, **kwargs):
        return None


def test_storage_paths_are_absolute_and_relative_values_use_server_base_dir():
    resolved = Path(resolve_storage_path("data/path-resolution-test.db"))

    assert Path(APP_DB_PATH).is_absolute()
    assert resolved == (settings.base_dir / "data" / "path-resolution-test.db").resolve()


def test_checkpoint_path_uses_canonical_configured_storage_location(monkeypatch, tmp_path: Path):
    configured = tmp_path / "nested" / "checkpoints.db"
    monkeypatch.setenv("LANGGRAPH_CHECKPOINT_DB", str(configured))

    assert Path(get_langgraph_checkpoint_db_path()) == configured.resolve()


def test_backup_all_uses_canonical_checkpoint_path(monkeypatch, tmp_path: Path):
    app_db = tmp_path / "app.db"
    checkpoint_db = tmp_path / "checkpoints" / "langgraph.db"
    checkpoint_db.parent.mkdir()
    sqlite3.connect(app_db).close()
    sqlite3.connect(checkpoint_db).close()
    monkeypatch.setenv("LANGGRAPH_CHECKPOINT_DB", str(checkpoint_db))
    monkeypatch.setattr("core.storage.APP_DB_PATH", str(app_db))

    result = backup_all(tmp_path / "backups")

    sources = {item["source"] for item in result["backed_up"]}
    assert str(app_db) in sources
    assert str(checkpoint_db.resolve()) in sources


def test_checkpoint_cleanup_keeps_active_and_unknown_threads_for_supported_schemas(tmp_path: Path):
    app_db = tmp_path / "app.db"
    old_timestamp = "2020-01-01T00:00:00"
    now_timestamp = datetime.now().isoformat()
    with sqlite3.connect(app_db) as conn:
        conn.execute(
            "CREATE TABLE agent_sessions (id TEXT PRIMARY KEY, status TEXT NOT NULL, updated_at TEXT NOT NULL)"
        )
        conn.executemany(
            "INSERT INTO agent_sessions (id, status, updated_at) VALUES (?, ?, ?)",
            [
                ("expired", "completed", old_timestamp),
                ("active", "running", old_timestamp),
                ("recent", "completed", now_timestamp),
            ],
        )

    for write_table in ("writes", "checkpoint_writes"):
        checkpoint_db = tmp_path / f"{write_table}.db"
        with sqlite3.connect(checkpoint_db) as conn:
            conn.execute("CREATE TABLE checkpoints (thread_id TEXT PRIMARY KEY, payload BLOB)")
            conn.execute(f"CREATE TABLE {write_table} (thread_id TEXT NOT NULL, payload BLOB)")
            conn.execute("CREATE TABLE blobs (thread_id TEXT NOT NULL, payload BLOB)")
            for session_id in ("expired", "active", "recent", "unknown"):
                thread_id = f"agent_session:{session_id}:deepagents"
                conn.execute("INSERT INTO checkpoints (thread_id, payload) VALUES (?, ?)", (thread_id, b"checkpoint"))
                conn.execute(f"INSERT INTO {write_table} (thread_id, payload) VALUES (?, ?)", (thread_id, b"write"))
                conn.execute("INSERT INTO blobs (thread_id, payload) VALUES (?, ?)", (thread_id, b"blob"))

        result = cleanup_langgraph_checkpoints(
            checkpoint_db_path=checkpoint_db,
            app_db_path=app_db,
            max_age_days=1,
        )

        assert result["deleted_threads"] == 1
        assert result["deleted_checkpoints"] == 1
        assert result["deleted_writes"] == 1
        assert result["deleted_blobs"] == 1
        with sqlite3.connect(checkpoint_db) as conn:
            remaining = {
                row[0]
                for row in conn.execute("SELECT thread_id FROM checkpoints")
            }
            assert f"agent_session:expired:deepagents" not in remaining
            assert {
                f"agent_session:active:deepagents",
                f"agent_session:recent:deepagents",
                f"agent_session:unknown:deepagents",
            } <= remaining
            assert conn.execute(f"SELECT COUNT(*) FROM {write_table}").fetchone()[0] == 3
            assert conn.execute("SELECT COUNT(*) FROM blobs").fetchone()[0] == 3


def test_explicit_legacy_agent_database_import_is_transactional_and_idempotent(tmp_path: Path):
    legacy_path = tmp_path / "legacy.db"
    destination_path = tmp_path / "destination.db"
    legacy = AgentSessionRepository(str(legacy_path))
    destination = AgentSessionRepository(str(destination_path))
    now = datetime.now().isoformat()

    legacy.create_session(
        {
            "id": "imported-session",
            "agent_id": "build",
            "status": "completed",
            "title": "legacy import",
            "metadata": {},
            "created_at": now,
            "updated_at": now,
        }
    )
    legacy_part = legacy.add_part(
        "imported-session", "summary", status="completed", title="legacy", content="import me"
    )
    legacy_event = legacy.add_event("imported-session", "session_completed", "legacy event")
    # A same-id destination session must not receive source child records.
    legacy.create_session(
        {
            "id": "colliding-session",
            "agent_id": "build",
            "status": "completed",
            "title": "source collision",
            "metadata": {},
            "created_at": now,
            "updated_at": now,
        }
    )
    legacy.add_part("colliding-session", "summary", status="completed", title="source", content="must not mix")
    destination.create_session(
        {
            "id": "colliding-session",
            "agent_id": "build",
            "status": "idle",
            "title": "destination wins",
            "metadata": {},
            "created_at": now,
            "updated_at": now,
        }
    )
    close_all_pools()

    first = import_legacy_agent_session_database(legacy_path, destination_db_path=destination_path)
    second = import_legacy_agent_session_database(legacy_path, destination_db_path=destination_path)

    assert first["imported"]["agent_sessions"] == 1
    assert first["imported"]["agent_parts"] == 1
    assert first["imported"]["agent_events"] == 1
    assert second["imported"]["agent_sessions"] == 0
    assert second["imported"]["agent_parts"] == 0
    assert second["imported"]["agent_events"] == 0
    with sqlite3.connect(destination_path) as conn:
        imported = conn.execute("SELECT title FROM agent_sessions WHERE id = 'imported-session'").fetchone()
        collision = conn.execute("SELECT title FROM agent_sessions WHERE id = 'colliding-session'").fetchone()
        parts = conn.execute("SELECT id FROM agent_parts WHERE session_id = 'imported-session'").fetchall()
        events = conn.execute("SELECT id FROM agent_events WHERE session_id = 'imported-session'").fetchall()
        collision_parts = conn.execute("SELECT id FROM agent_parts WHERE session_id = 'colliding-session'").fetchall()
    assert imported == ("legacy import",)
    assert collision == ("destination wins",)
    assert parts == [(legacy_part["id"],)]
    assert events == [(legacy_event["id"],)]
    assert collision_parts == []


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
