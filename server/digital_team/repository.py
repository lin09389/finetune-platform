"""SQLite repository for Digital Team state."""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any

from core.db_manager import get_db_pool
from core.storage import APP_DB_PATH


def _now() -> str:
    return datetime.now().isoformat()


def _json(value: Any) -> str:
    return json.dumps(value if value is not None else {}, ensure_ascii=False)


def _load(value: str | None, default: Any = None) -> Any:
    if not value:
        return {} if default is None else default
    try:
        return json.loads(value)
    except Exception:
        return {} if default is None else default


class DigitalTeamRepository:
    def __init__(self, db_path: str = APP_DB_PATH):
        self.db_path = db_path
        self.ensure_schema()

    def ensure_schema(self) -> None:
        with get_db_pool(self.db_path).get_connection() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS digital_teams (
                    id TEXT PRIMARY KEY,
                    template_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    description TEXT DEFAULT '',
                    metadata TEXT DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS digital_team_projects (
                    id TEXT PRIMARY KEY,
                    team_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    goal TEXT NOT NULL,
                    template_id TEXT NOT NULL,
                    project_path TEXT,
                    provider TEXT NOT NULL,
                    model TEXT,
                    approval_mode TEXT NOT NULL,
                    status TEXT NOT NULL,
                    current_stage TEXT,
                    metadata TEXT DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    completed_at TEXT,
                    FOREIGN KEY (team_id) REFERENCES digital_teams(id)
                );

                CREATE TABLE IF NOT EXISTS digital_team_tasks (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    title TEXT NOT NULL,
                    description TEXT DEFAULT '',
                    status TEXT NOT NULL,
                    requires_approval INTEGER DEFAULT 1,
                    input TEXT DEFAULT '{}',
                    output TEXT DEFAULT '{}',
                    error TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    completed_at TEXT,
                    FOREIGN KEY (project_id) REFERENCES digital_team_projects(id)
                );

                CREATE TABLE IF NOT EXISTS digital_team_events (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    task_id TEXT,
                    event_type TEXT NOT NULL,
                    actor TEXT NOT NULL,
                    message TEXT NOT NULL,
                    payload TEXT DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (project_id) REFERENCES digital_team_projects(id)
                );

                CREATE TABLE IF NOT EXISTS digital_team_artifacts (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    task_id TEXT,
                    artifact_type TEXT NOT NULL,
                    title TEXT NOT NULL,
                    content TEXT DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (project_id) REFERENCES digital_team_projects(id)
                );

                CREATE TABLE IF NOT EXISTS digital_team_reviews (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    task_id TEXT NOT NULL,
                    approved INTEGER NOT NULL DEFAULT 0,
                    summary TEXT DEFAULT '',
                    risks TEXT DEFAULT '[]',
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (project_id) REFERENCES digital_team_projects(id),
                    FOREIGN KEY (task_id) REFERENCES digital_team_tasks(id)
                );
                """
            )

    def create_team(self, template_id: str, name: str, description: str) -> dict[str, Any]:
        team_id = f"team_{uuid.uuid4().hex[:8]}"
        now = _now()
        with get_db_pool(self.db_path).get_connection() as conn:
            conn.execute(
                """
                INSERT INTO digital_teams (id, template_id, name, description, metadata, created_at, updated_at)
                VALUES (?, ?, ?, ?, '{}', ?, ?)
                """,
                (team_id, template_id, name, description, now, now),
            )
        return {"id": team_id, "template_id": template_id, "name": name, "description": description}

    def create_project(self, data: dict[str, Any], team: dict[str, Any]) -> dict[str, Any]:
        project_id = f"dtp_{uuid.uuid4().hex[:8]}"
        now = _now()
        with get_db_pool(self.db_path).get_connection() as conn:
            conn.execute(
                """
                INSERT INTO digital_team_projects
                    (id, team_id, title, goal, template_id, project_path, provider, model,
                     approval_mode, status, current_stage, metadata, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'draft', 'draft', '{}', ?, ?)
                """,
                (
                    project_id,
                    team["id"],
                    data["title"],
                    data["goal"],
                    data["template_id"],
                    data.get("project_path"),
                    data["provider"],
                    data.get("model"),
                    data["approval_mode"],
                    now,
                    now,
                ),
            )
        self.add_event(project_id, None, "project_created", "user", "数字团队项目已创建", data)
        return self.get_project(project_id) or {}

    def list_projects(self) -> list[dict[str, Any]]:
        with get_db_pool(self.db_path).get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM digital_team_projects ORDER BY updated_at DESC"
            ).fetchall()
        return [self._project_from_row(row, include_tasks=True) for row in rows]

    def get_project(self, project_id: str) -> dict[str, Any] | None:
        with get_db_pool(self.db_path).get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM digital_team_projects WHERE id = ?",
                (project_id,),
            ).fetchone()
        return self._project_from_row(row, include_tasks=True) if row else None

    def update_project(self, project_id: str, **fields: Any) -> None:
        if not fields:
            return
        fields["updated_at"] = _now()
        assignments = ", ".join(f"{key} = ?" for key in fields)
        values = list(fields.values()) + [project_id]
        with get_db_pool(self.db_path).get_connection() as conn:
            conn.execute(
                f"UPDATE digital_team_projects SET {assignments} WHERE id = ?",
                values,
            )

    def create_task(
        self,
        project_id: str,
        role: str,
        title: str,
        description: str,
        status: str,
        input_data: dict[str, Any] | None = None,
        requires_approval: bool = True,
    ) -> dict[str, Any]:
        task_id = f"dtt_{uuid.uuid4().hex[:8]}"
        now = _now()
        with get_db_pool(self.db_path).get_connection() as conn:
            conn.execute(
                """
                INSERT INTO digital_team_tasks
                    (id, project_id, role, title, description, status, requires_approval,
                     input, output, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, '{}', ?, ?)
                """,
                (
                    task_id,
                    project_id,
                    role,
                    title,
                    description,
                    status,
                    1 if requires_approval else 0,
                    _json(input_data or {}),
                    now,
                    now,
                ),
            )
        return self.get_task(task_id) or {}

    def get_task(self, task_id: str) -> dict[str, Any] | None:
        with get_db_pool(self.db_path).get_connection() as conn:
            row = conn.execute("SELECT * FROM digital_team_tasks WHERE id = ?", (task_id,)).fetchone()
        return self._task_from_row(row) if row else None

    def get_tasks(self, project_id: str) -> list[dict[str, Any]]:
        with get_db_pool(self.db_path).get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM digital_team_tasks WHERE project_id = ? ORDER BY created_at ASC",
                (project_id,),
            ).fetchall()
        return [self._task_from_row(row) for row in rows]

    def update_task(self, task_id: str, **fields: Any) -> None:
        if "output" in fields:
            fields["output"] = _json(fields["output"])
        if "input" in fields:
            fields["input"] = _json(fields["input"])
        fields["updated_at"] = _now()
        assignments = ", ".join(f"{key} = ?" for key in fields)
        values = list(fields.values()) + [task_id]
        with get_db_pool(self.db_path).get_connection() as conn:
            conn.execute(f"UPDATE digital_team_tasks SET {assignments} WHERE id = ?", values)

    def add_event(
        self,
        project_id: str,
        task_id: str | None,
        event_type: str,
        actor: str,
        message: str,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        event_id = f"dte_{uuid.uuid4().hex[:8]}"
        now = _now()
        with get_db_pool(self.db_path).get_connection() as conn:
            conn.execute(
                """
                INSERT INTO digital_team_events
                    (id, project_id, task_id, event_type, actor, message, payload, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (event_id, project_id, task_id, event_type, actor, message, _json(payload), now),
            )
        return {"id": event_id, "project_id": project_id, "created_at": now}

    def add_artifact(
        self,
        project_id: str,
        task_id: str | None,
        artifact_type: str,
        title: str,
        content: dict[str, Any],
    ) -> dict[str, Any]:
        artifact_id = f"dta_{uuid.uuid4().hex[:8]}"
        now = _now()
        with get_db_pool(self.db_path).get_connection() as conn:
            conn.execute(
                """
                INSERT INTO digital_team_artifacts
                    (id, project_id, task_id, artifact_type, title, content, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (artifact_id, project_id, task_id, artifact_type, title, _json(content), now),
            )
        return {"id": artifact_id, "artifact_type": artifact_type, "title": title, "content": content}

    def add_review(
        self,
        project_id: str,
        task_id: str,
        approved: bool,
        summary: str,
        risks: list[str],
    ) -> None:
        with get_db_pool(self.db_path).get_connection() as conn:
            conn.execute(
                """
                INSERT INTO digital_team_reviews
                    (id, project_id, task_id, approved, summary, risks, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    f"dtr_{uuid.uuid4().hex[:8]}",
                    project_id,
                    task_id,
                    1 if approved else 0,
                    summary,
                    _json(risks),
                    _now(),
                ),
            )

    def list_events(self, project_id: str) -> list[dict[str, Any]]:
        with get_db_pool(self.db_path).get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM digital_team_events WHERE project_id = ? ORDER BY created_at ASC",
                (project_id,),
            ).fetchall()
        return [
            {
                **dict(row),
                "payload": _load(row["payload"]),
            }
            for row in rows
        ]

    def list_artifacts(self, project_id: str) -> list[dict[str, Any]]:
        with get_db_pool(self.db_path).get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM digital_team_artifacts WHERE project_id = ? ORDER BY created_at ASC",
                (project_id,),
            ).fetchall()
        return [
            {
                **dict(row),
                "content": _load(row["content"]),
            }
            for row in rows
        ]

    def _project_from_row(self, row: Any, include_tasks: bool = False) -> dict[str, Any]:
        data = dict(row)
        data["metadata"] = _load(data.get("metadata"))
        data["tasks"] = self.get_tasks(data["id"]) if include_tasks else []
        return data

    def _task_from_row(self, row: Any) -> dict[str, Any]:
        data = dict(row)
        data["requires_approval"] = bool(data.get("requires_approval"))
        data["input"] = _load(data.get("input"))
        data["output"] = _load(data.get("output"))
        return data

