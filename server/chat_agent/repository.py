from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from core.db_manager import get_db_pool
from core.storage import APP_DB_PATH


def _now() -> str:
    return datetime.now().isoformat()


def _json(value: Any) -> str:
    return json.dumps(value if value is not None else {}, ensure_ascii=False)


def _load(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    try:
        loaded = json.loads(value)
        return loaded if isinstance(loaded, dict) else {}
    except Exception:
        return {}


class ChatAgentRepository:
    def __init__(self, db_path: str = APP_DB_PATH):
        self.db_path = db_path
        self.ensure_schema()

    def ensure_schema(self) -> None:
        migrations_dir = Path(__file__).resolve().parents[1] / "core" / "migrations"
        with get_db_pool(self.db_path).get_connection() as conn:
            conn.executescript((migrations_dir / "006_chat_agent_runs.sql").read_text(encoding="utf-8"))

    def create_run(
        self,
        *,
        chat_session_id: str | None,
        trigger_message_id: str | None,
        workflow_id: str,
        intent_type: str,
        summary: str,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        run_id = f"car_{uuid.uuid4().hex[:8]}"
        now = _now()
        with get_db_pool(self.db_path).get_connection() as conn:
            conn.execute(
                """
                INSERT INTO chat_agent_runs
                    (id, chat_session_id, trigger_message_id, workflow_id, status,
                     intent_type, summary, metadata, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    chat_session_id,
                    trigger_message_id,
                    workflow_id,
                    "created",
                    intent_type,
                    summary,
                    _json(metadata),
                    now,
                    now,
                ),
            )
        return self.get_run(run_id) or {}

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        with get_db_pool(self.db_path).get_connection() as conn:
            row = conn.execute("SELECT * FROM chat_agent_runs WHERE id = ?", (run_id,)).fetchone()
        return self._run_from_row(row) if row else None

    def get_run_by_workflow(self, workflow_id: str) -> dict[str, Any] | None:
        with get_db_pool(self.db_path).get_connection() as conn:
            row = conn.execute("SELECT * FROM chat_agent_runs WHERE workflow_id = ?", (workflow_id,)).fetchone()
        return self._run_from_row(row) if row else None

    def update_run(self, run_id: str, **fields: Any) -> dict[str, Any]:
        if not fields:
            return self.get_run(run_id) or {}
        fields["updated_at"] = _now()
        assignments = ", ".join(f"{key} = ?" for key in fields)
        values = [_json(value) if key == "metadata" else value for key, value in fields.items()]
        values.append(run_id)
        with get_db_pool(self.db_path).get_connection() as conn:
            conn.execute(f"UPDATE chat_agent_runs SET {assignments} WHERE id = ?", values)
        return self.get_run(run_id) or {}

    def add_run_message(
        self,
        run_id: str,
        message_type: str,
        *,
        chat_message_id: str | None = None,
        workflow_event_id: str | None = None,
        action_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        message_id = f"cam_{uuid.uuid4().hex[:8]}"
        now = _now()
        with get_db_pool(self.db_path).get_connection() as conn:
            conn.execute(
                """
                INSERT INTO chat_agent_run_messages
                    (id, run_id, chat_message_id, message_type, workflow_event_id,
                     action_id, metadata, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (message_id, run_id, chat_message_id, message_type, workflow_event_id, action_id, _json(metadata), now),
            )
        return {
            "id": message_id,
            "run_id": run_id,
            "chat_message_id": chat_message_id,
            "message_type": message_type,
            "workflow_event_id": workflow_event_id,
            "action_id": action_id,
            "metadata": metadata or {},
            "created_at": now,
        }

    def _run_from_row(self, row: Any) -> dict[str, Any]:
        data = dict(row)
        data["metadata"] = _load(data.get("metadata"))
        return data
