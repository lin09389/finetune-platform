from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path

import pytest

from agent_session.repository import AgentSessionRepository
from core import storage


MIGRATIONS_DIR = Path(__file__).resolve().parents[1] / "core" / "migrations"
PRESERVED_LEGACY_AGENT_TABLES = (
    "agent_sessions",
    "agent_parts",
    "agent_events",
    "agent_subtasks",
    "agent_subtask_events",
    "agent_training_links",
    "agent_frontend_diagnostics",
)
V2_TABLES = (
    "native_agent_sessions",
    "native_agent_events",
    "native_agent_commands",
    "native_agent_snapshots",
    "native_agent_pending_interactions",
    "native_agent_file_mutations",
    "native_agent_trace_candidates",
)


def _run_migrations_through(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    db_path: Path,
    last_version: int,
) -> dict[str, object]:
    """Run copied migrations through the production migration runner."""
    migration_dir = tmp_path / "migrations"
    migration_dir.mkdir(exist_ok=True)
    for source in sorted(MIGRATIONS_DIR.glob("*.sql")):
        if int(source.name.split("_", 1)[0]) <= last_version:
            shutil.copy2(source, migration_dir / source.name)
    monkeypatch.setattr(storage, "MIGRATIONS_DIR", migration_dir)
    return storage.run_schema_migrations(str(db_path))


def _rows(conn: sqlite3.Connection, table: str) -> list[tuple[object, ...]]:
    return conn.execute(f"SELECT * FROM {table} ORDER BY rowid").fetchall()


def _seed_preserved_product_data(conn: sqlite3.Connection) -> dict[str, list[tuple[object, ...]]]:
    conn.executescript(
        """
        CREATE TABLE workspace_registrations (id TEXT PRIMARY KEY, payload BLOB NOT NULL);
        CREATE TABLE model_records (id TEXT PRIMARY KEY, payload BLOB NOT NULL);
        CREATE TABLE dataset_records (id TEXT PRIMARY KEY, payload BLOB NOT NULL);
        CREATE TABLE inference_records (id TEXT PRIMARY KEY, payload BLOB NOT NULL);
        CREATE TABLE application_settings (key TEXT PRIMARY KEY, payload BLOB NOT NULL);
        CREATE TABLE desktop_user_data (key TEXT PRIMARY KEY, payload BLOB NOT NULL);
        """
    )
    preserved = {
        "workspace_registrations": [("workspace-1", b"workspace-bytes")],
        "model_records": [("model-1", b"model-bytes")],
        "dataset_records": [("dataset-1", b"dataset-bytes")],
        "inference_records": [("inference-1", b"inference-bytes")],
        "application_settings": [("theme", b"settings-bytes")],
        "desktop_user_data": [("window", b"desktop-bytes")],
    }
    for table, values in preserved.items():
        conn.executemany(f"INSERT INTO {table} VALUES (?, ?)", values)

    conn.execute(
        "INSERT INTO chat_sessions (id, title, message_count, metadata, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
        ("chat-1", "Keep chat", 1, "{\"outside_agent\":true}", "2026-07-17T00:00:00", "2026-07-17T00:00:00"),
    )
    conn.execute(
        "INSERT INTO chat_messages (id, session_id, role, content, metadata, created_at, ordinal) VALUES (?, ?, ?, ?, ?, ?, ?)",
        ("message-1", "chat-1", "user", "keep me", "{}", "2026-07-17T00:00:00", 1),
    )
    conn.execute(
        """INSERT INTO training_jobs
           (job_id, backend, priority, status, config_json, model_path, dataset_path, output_path, record_json,
            attempt, max_attempts, cancel_requested, created_at, queued_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            "training-1", "native", 2, "queued", "{}", "model", "dataset", "output", "{}", 0, 3, 0,
            "2026-07-17T00:00:00", "2026-07-17T00:00:00", "2026-07-17T00:00:00",
        ),
    )
    conn.execute(
        "INSERT INTO chat_agent_runs (id, chat_session_id, trigger_message_id, status, intent_type, summary, metadata, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ("chat-run-1", "chat-1", "message-1", "created", "agent_work", "keep run", "{}", "2026-07-17T00:00:00", "2026-07-17T00:00:00"),
    )
    conn.commit()
    table_names = (*preserved, "chat_sessions", "chat_messages", "training_jobs", "chat_agent_runs")
    return {table: _rows(conn, table) for table in table_names}


def test_migration_017_creates_v2_schema_with_idempotency_and_replay_constraints(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = tmp_path / "native-agent.db"
    assert _run_migrations_through(monkeypatch, tmp_path, db_path, 17)["applied"] == 17

    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        table_names = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        assert set(V2_TABLES) <= table_names
        conn.execute(
            "INSERT INTO native_agent_sessions (id, schema_version, runtime_kind, status, runtime_binding_json, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("native-1", 2, "native", "created", "{}", "2026-07-17T00:00:00", "2026-07-17T00:00:00"),
        )
        conn.execute(
            "INSERT INTO native_agent_events (id, session_id, sequence, schema_version, kind, payload_json, timestamp) VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("event-1", "native-1", 1, 2, "session.created", "{}", "2026-07-17T00:00:00"),
        )
        conn.execute(
            "INSERT INTO native_agent_commands (session_id, command_id, schema_version, kind, request_json, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ("native-1", "command-1", 2, "session.prompt", "{}", "accepted", "2026-07-17T00:00:00", "2026-07-17T00:00:00"),
        )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO native_agent_events (id, session_id, sequence, schema_version, kind, payload_json, timestamp) VALUES (?, ?, ?, ?, ?, ?, ?)",
                ("event-duplicate", "native-1", 1, 2, "session.started", "{}", "2026-07-17T00:00:00"),
            )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO native_agent_commands (session_id, command_id, schema_version, kind, request_json, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                ("native-1", "command-1", 2, "session.prompt", "{}", "accepted", "2026-07-17T00:00:00", "2026-07-17T00:00:00"),
            )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO native_agent_events (id, session_id, sequence, schema_version, kind, payload_json, timestamp) VALUES (?, ?, ?, ?, ?, ?, ?)",
                ("event-invalid", "missing", 2, 2, "session.started", "{}", "2026-07-17T00:00:00"),
            )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO native_agent_sessions (id, schema_version, runtime_kind, status, runtime_binding_json, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                ("invalid-version", 1, "native", "created", "{}", "2026-07-17T00:00:00", "2026-07-17T00:00:00"),
            )

        indexes = {row[1] for row in conn.execute("PRAGMA index_list(native_agent_events)")}
        assert "idx_native_agent_events_replay" in indexes
        assert "idx_native_agent_snapshots_recovery" in {
            row[1] for row in conn.execute("PRAGMA index_list(native_agent_snapshots)")
        }


def test_migration_017_preserves_legacy_agent_and_non_agent_data(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = tmp_path / "scoped-reset.db"
    _run_migrations_through(monkeypatch, tmp_path, db_path, 16)
    AgentSessionRepository(str(db_path))

    with sqlite3.connect(db_path) as conn:
        preserved_before = _seed_preserved_product_data(conn)
        conn.executescript(
            """
            INSERT INTO agent_sessions VALUES ('legacy-1', 'chat-1', 'build', 'completed', 'old agent', NULL, NULL, NULL, '{}', '2026-07-17T00:00:00', '2026-07-17T00:00:00');
            INSERT INTO agent_parts VALUES ('part-1', 'legacy-1', 'permission', 'pending', NULL, NULL, '{}', '2026-07-17T00:00:00', '2026-07-17T00:00:00');
            INSERT INTO agent_events VALUES ('legacy-event-1', 'legacy-1', 'done', 'old event', '{}', '2026-07-17T00:00:00');
            INSERT INTO agent_subtasks (id, parent_session_id, agent_name, status, created_at, updated_at) VALUES ('subtask-1', 'legacy-1', 'review', 'completed', '2026-07-17T00:00:00', '2026-07-17T00:00:00');
            INSERT INTO agent_subtask_events (id, task_id, parent_session_id, event_type, message, created_at) VALUES ('subtask-event-1', 'subtask-1', 'legacy-1', 'done', 'old subtask event', '2026-07-17T00:00:00');
            INSERT INTO agent_training_links (task_id, proposal_id, session_id, part_id, created_at, updated_at) VALUES ('training-1', 'proposal-1', 'legacy-1', 'part-1', '2026-07-17T00:00:00', '2026-07-17T00:00:00');
            INSERT INTO checkpoints VALUES ('agent_session:legacy-1:deepagents', '', 'checkpoint-1', NULL, NULL, X'01', X'02');
            INSERT INTO checkpoint_writes VALUES ('agent_session:legacy-1:deepagents', '', 'checkpoint-1', 'task-1', 0, 'channel', NULL, X'03');
            INSERT INTO checkpoints VALUES ('non-agent-thread', '', 'checkpoint-2', NULL, NULL, X'04', X'05');
            INSERT INTO checkpoint_writes VALUES ('non-agent-thread', '', 'checkpoint-2', 'task-2', 0, 'channel', NULL, X'06');
            INSERT INTO agent_frontend_diagnostics VALUES ('legacy-hash', 'v1', 1, 0, 0, 0, 0, 0, '{}', '2026-07-17T00:00:00', '2026-07-17T00:00:00');
            """
        )
        conn.commit()
        legacy_agent_before = {
            table: _rows(conn, table) for table in PRESERVED_LEGACY_AGENT_TABLES
        }
        checkpoint_before = {
            "checkpoints": _rows(conn, "checkpoints"),
            "checkpoint_writes": _rows(conn, "checkpoint_writes"),
        }

    result = _run_migrations_through(monkeypatch, tmp_path, db_path, 17)
    assert result == {"applied": 1, "skipped": 16, "failed": []}

    with sqlite3.connect(db_path) as conn:
        for table, before in legacy_agent_before.items():
            assert _rows(conn, table) == before
        for table, before in checkpoint_before.items():
            assert _rows(conn, table) == before
        for table, before in preserved_before.items():
            assert _rows(conn, table) == before
