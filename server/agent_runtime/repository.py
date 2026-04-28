"""SQLite repository for configurable workflow runtime state."""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from core.db_manager import get_db_pool
from core.storage import APP_DB_PATH

from .definitions import AgentDefinition, StepDefinition, WorkflowDefinition
from .models import WorkflowTemplateCreate, WorkflowTemplateUpdate
from .templates import SOFTWARE_DELIVERY_TEMPLATE

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


class WorkflowRuntimeRepository:
    def __init__(self, db_path: str = APP_DB_PATH):
        self.db_path = db_path
        self.ensure_schema()
        self.seed_builtin_templates()
        self.import_legacy_digital_team()

    def ensure_schema(self) -> None:
        migrations_dir = Path(__file__).resolve().parents[1] / "core" / "migrations"
        with get_db_pool(self.db_path).get_connection() as conn:
            conn.executescript((migrations_dir / "003_workflow_runtime.sql").read_text(encoding="utf-8"))
            conn.executescript((migrations_dir / "004_workflow_context_memory.sql").read_text(encoding="utf-8"))
            conn.executescript((migrations_dir / "005_workflow_observability_actions.sql").read_text(encoding="utf-8"))
            conn.executescript((migrations_dir / "006_chat_agent_runs.sql").read_text(encoding="utf-8"))

    def seed_builtin_templates(self) -> None:
        if self.get_template(SOFTWARE_DELIVERY_TEMPLATE.id):
            return
        self.upsert_template_definition(SOFTWARE_DELIVERY_TEMPLATE)

    def import_legacy_digital_team(self) -> None:
        with get_db_pool(self.db_path).get_connection() as conn:
            count = conn.execute("SELECT COUNT(*) AS count FROM workflows").fetchone()["count"]
            legacy_tables = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='digital_team_projects'"
            ).fetchone()
        if count or not legacy_tables:
            return

        role_map = {"ceo": "planner", "developer": "implementer", "reviewer": "reviewer"}
        step_map = {"ceo": "plan", "developer": "implement", "reviewer": "review"}
        with get_db_pool(self.db_path).get_connection() as conn:
            projects = conn.execute("SELECT * FROM digital_team_projects").fetchall()
            for project in projects:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO workflows
                        (id, title, goal, template_id, project_path, provider, model, approval_mode,
                         status, current_stage, metadata, created_at, updated_at, completed_at)
                    VALUES (?, ?, ?, 'software_delivery', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        project["id"],
                        project["title"],
                        project["goal"],
                        project["project_path"],
                        project["provider"],
                        project["model"],
                        project["approval_mode"],
                        project["status"],
                        project["current_stage"],
                        project["metadata"],
                        project["created_at"],
                        project["updated_at"],
                        project["completed_at"],
                    ),
                )
                tasks = conn.execute(
                    "SELECT * FROM digital_team_tasks WHERE project_id = ? ORDER BY created_at ASC",
                    (project["id"],),
                ).fetchall()
                for index, task in enumerate(tasks):
                    conn.execute(
                        """
                        INSERT OR IGNORE INTO workflow_steps
                            (id, workflow_id, step_key, agent_id, title, description, status,
                             requires_approval, input, output, error, sort_order, created_at,
                             updated_at, completed_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            task["id"],
                            task["project_id"],
                            step_map.get(task["role"], task["role"]),
                            role_map.get(task["role"], task["role"]),
                            task["title"],
                            task["description"],
                            task["status"],
                            task["requires_approval"],
                            task["input"],
                            task["output"],
                            task["error"],
                            index,
                            task["created_at"],
                            task["updated_at"],
                            task["completed_at"],
                        ),
                    )
                for event in conn.execute("SELECT * FROM digital_team_events WHERE project_id = ?", (project["id"],)):
                    conn.execute(
                        """
                        INSERT OR IGNORE INTO workflow_events
                            (id, workflow_id, step_id, event_type, actor, message, payload, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            event["id"],
                            event["project_id"],
                            event["task_id"],
                            event["event_type"],
                            event["actor"],
                            event["message"],
                            event["payload"],
                            event["created_at"],
                        ),
                    )
                for artifact in conn.execute("SELECT * FROM digital_team_artifacts WHERE project_id = ?", (project["id"],)):
                    conn.execute(
                        """
                        INSERT OR IGNORE INTO workflow_artifacts
                            (id, workflow_id, step_id, artifact_type, title, content, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            artifact["id"],
                            artifact["project_id"],
                            artifact["task_id"],
                            artifact["artifact_type"],
                            artifact["title"],
                            artifact["content"],
                            artifact["created_at"],
                        ),
                    )
                for review in conn.execute("SELECT * FROM digital_team_reviews WHERE project_id = ?", (project["id"],)):
                    conn.execute(
                        """
                        INSERT OR IGNORE INTO workflow_reviews
                            (id, workflow_id, step_id, approved, summary, risks, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            review["id"],
                            review["project_id"],
                            review["task_id"],
                            review["approved"],
                            review["summary"],
                            review["risks"],
                            review["created_at"],
                        ),
                    )

    def upsert_template_definition(self, workflow: WorkflowDefinition) -> None:
        now = _now()
        with get_db_pool(self.db_path).get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO workflow_templates
                    (id, name, description, is_builtin, is_enabled, default_provider, default_model,
                     default_approval_mode, metadata, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, '{}',
                    COALESCE((SELECT created_at FROM workflow_templates WHERE id = ?), ?), ?)
                """,
                (
                    workflow.id,
                    workflow.name,
                    workflow.description,
                    1 if workflow.is_builtin else 0,
                    1 if workflow.is_enabled else 0,
                    workflow.default_provider,
                    workflow.default_model,
                    workflow.default_approval_mode,
                    workflow.id,
                    now,
                    now,
                ),
            )
            conn.execute("DELETE FROM workflow_template_agents WHERE template_id = ?", (workflow.id,))
            conn.execute("DELETE FROM workflow_template_steps WHERE template_id = ?", (workflow.id,))
            for agent in workflow.agents:
                conn.execute(
                    """
                    INSERT INTO workflow_template_agents
                        (id, template_id, agent_id, name, description, system_prompt,
                         output_requirements, metadata, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, '{}', ?, ?)
                    """,
                    (
                        f"wta_{uuid.uuid4().hex[:8]}",
                        workflow.id,
                        agent.id,
                        agent.name,
                        agent.description,
                        agent.system_prompt,
                        agent.output_requirements,
                        now,
                        now,
                    ),
                )
            for index, step in enumerate(sorted(workflow.steps, key=lambda item: item.sort_order)):
                conn.execute(
                    """
                    INSERT INTO workflow_template_steps
                        (id, template_id, step_key, agent_id, title, description, artifact_type,
                         requires_approval, sort_order, metadata, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, '{}', ?, ?)
                    """,
                    (
                        f"wts_{uuid.uuid4().hex[:8]}",
                        workflow.id,
                        step.key,
                        step.agent_id,
                        step.title,
                        step.description,
                        step.artifact_type,
                        1 if step.requires_approval else 0,
                        index,
                        now,
                        now,
                    ),
                )

    def list_templates(self) -> list[WorkflowDefinition]:
        with get_db_pool(self.db_path).get_connection() as conn:
            rows = conn.execute("SELECT * FROM workflow_templates ORDER BY is_builtin DESC, updated_at DESC").fetchall()
        return [self._template_from_row(row) for row in rows]

    def get_template(self, template_id: str) -> WorkflowDefinition | None:
        with get_db_pool(self.db_path).get_connection() as conn:
            row = conn.execute("SELECT * FROM workflow_templates WHERE id = ?", (template_id,)).fetchone()
        return self._template_from_row(row) if row else None

    def create_template(self, request: WorkflowTemplateCreate) -> WorkflowDefinition:
        if self.get_template(request.id):
            raise ValueError("Workflow template already exists")
        workflow = self._definition_from_template_payload(request.id, request.model_dump(), is_builtin=False)
        self.upsert_template_definition(workflow)
        return self.get_template(request.id) or workflow

    def update_template(self, template_id: str, request: WorkflowTemplateUpdate) -> WorkflowDefinition:
        existing = self.get_template(template_id)
        if not existing:
            raise KeyError("Workflow template not found")
        if existing.is_builtin:
            raise PermissionError("Built-in workflow templates can only be copied before editing")
        payload = request.model_dump()
        workflow = self._definition_from_template_payload(template_id, payload, is_builtin=existing.is_builtin)
        self.upsert_template_definition(workflow)
        return self.get_template(template_id) or workflow

    def delete_template(self, template_id: str) -> None:
        template = self.get_template(template_id)
        if not template:
            raise KeyError("Workflow template not found")
        if template.is_builtin:
            raise PermissionError("Built-in workflow templates cannot be deleted")
        with get_db_pool(self.db_path).get_connection() as conn:
            conn.execute("DELETE FROM workflow_templates WHERE id = ?", (template_id,))

    def create_project(self, data: dict[str, Any], team: dict[str, Any] | None = None) -> dict[str, Any]:
        workflow_id = f"wf_{uuid.uuid4().hex[:8]}"
        now = _now()
        with get_db_pool(self.db_path).get_connection() as conn:
            conn.execute(
                """
                INSERT INTO workflows
                    (id, title, goal, template_id, project_path, provider, model, approval_mode,
                     status, current_stage, metadata, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'draft', 'draft', '{}', ?, ?)
                """,
                (
                    workflow_id,
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
        self.upsert_context_profile(
            workflow_id,
            {
                "project_path": data.get("project_path"),
                "chat_session_id": data.get("chat_session_id"),
                "include_project_context": data.get("include_project_context", True),
                "include_chat_context": data.get("include_chat_context", bool(data.get("chat_session_id"))),
                "include_memory": data.get("include_memory", True),
                "max_context_chars": data.get("max_context_chars", 6000),
                "metadata": data.get("context_metadata", {}),
            },
        )
        self.add_event(workflow_id, None, "workflow_created", "user", "工作流已创建", data)
        return self.get_project(workflow_id) or {}

    def list_projects(self) -> list[dict[str, Any]]:
        with get_db_pool(self.db_path).get_connection() as conn:
            rows = conn.execute("SELECT * FROM workflows ORDER BY updated_at DESC").fetchall()
        return [self._project_from_row(row, include_tasks=True) for row in rows]

    def get_project(self, project_id: str) -> dict[str, Any] | None:
        with get_db_pool(self.db_path).get_connection() as conn:
            row = conn.execute("SELECT * FROM workflows WHERE id = ?", (project_id,)).fetchone()
        return self._project_from_row(row, include_tasks=True) if row else None

    def update_project(self, project_id: str, **fields: Any) -> None:
        if not fields:
            return
        fields["updated_at"] = _now()
        assignments = ", ".join(f"{key} = ?" for key in fields)
        values = list(fields.values()) + [project_id]
        with get_db_pool(self.db_path).get_connection() as conn:
            conn.execute(f"UPDATE workflows SET {assignments} WHERE id = ?", values)

    def create_task(
        self,
        project_id: str,
        role: str,
        title: str,
        description: str,
        status: str,
        input_data: dict[str, Any] | None = None,
        requires_approval: bool = True,
        step_key: str | None = None,
        sort_order: int = 0,
    ) -> dict[str, Any]:
        task_id = f"wfs_{uuid.uuid4().hex[:8]}"
        now = _now()
        with get_db_pool(self.db_path).get_connection() as conn:
            conn.execute(
                """
                INSERT INTO workflow_steps
                    (id, workflow_id, step_key, agent_id, title, description, status,
                     requires_approval, input, output, error, sort_order, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, '{}', NULL, ?, ?, ?)
                """,
                (
                    task_id,
                    project_id,
                    step_key or role,
                    role,
                    title,
                    description,
                    status,
                    1 if requires_approval else 0,
                    _json(input_data or {}),
                    sort_order,
                    now,
                    now,
                ),
            )
        return self.get_task(task_id) or {}

    def get_task(self, task_id: str) -> dict[str, Any] | None:
        with get_db_pool(self.db_path).get_connection() as conn:
            row = conn.execute("SELECT * FROM workflow_steps WHERE id = ?", (task_id,)).fetchone()
        return self._task_from_row(row) if row else None

    def get_tasks(self, project_id: str) -> list[dict[str, Any]]:
        with get_db_pool(self.db_path).get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM workflow_steps WHERE workflow_id = ? ORDER BY sort_order ASC, created_at ASC",
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
            conn.execute(f"UPDATE workflow_steps SET {assignments} WHERE id = ?", values)

    def add_event(self, project_id: str, task_id: str | None, event_type: str, actor: str, message: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        event_id = f"wfe_{uuid.uuid4().hex[:8]}"
        now = _now()
        with get_db_pool(self.db_path).get_connection() as conn:
            conn.execute(
                """
                INSERT INTO workflow_events
                    (id, workflow_id, step_id, event_type, actor, message, payload, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (event_id, project_id, task_id, event_type, actor, message, _json(payload), now),
            )
        return {"id": event_id, "workflow_id": project_id, "created_at": now}

    def add_artifact(self, project_id: str, task_id: str | None, artifact_type: str, title: str, content: dict[str, Any]) -> dict[str, Any]:
        artifact_id = f"wfa_{uuid.uuid4().hex[:8]}"
        now = _now()
        with get_db_pool(self.db_path).get_connection() as conn:
            conn.execute(
                """
                INSERT INTO workflow_artifacts
                    (id, workflow_id, step_id, artifact_type, title, content, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (artifact_id, project_id, task_id, artifact_type, title, _json(content), now),
            )
        return {"id": artifact_id, "artifact_type": artifact_type, "title": title, "content": content}

    def add_review(self, project_id: str, task_id: str, approved: bool, summary: str, risks: list[str]) -> None:
        with get_db_pool(self.db_path).get_connection() as conn:
            conn.execute(
                """
                INSERT INTO workflow_reviews
                    (id, workflow_id, step_id, approved, summary, risks, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (f"wfr_{uuid.uuid4().hex[:8]}", project_id, task_id, 1 if approved else 0, summary, _json(risks), _now()),
            )

    def list_events(self, project_id: str) -> list[dict[str, Any]]:
        with get_db_pool(self.db_path).get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM workflow_events WHERE workflow_id = ? ORDER BY created_at ASC",
                (project_id,),
            ).fetchall()
        return [{**dict(row), "project_id": row["workflow_id"], "task_id": row["step_id"], "payload": _load(row["payload"])} for row in rows]

    def list_artifacts(self, project_id: str) -> list[dict[str, Any]]:
        with get_db_pool(self.db_path).get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM workflow_artifacts WHERE workflow_id = ? ORDER BY created_at ASC",
                (project_id,),
            ).fetchall()
        return [{**dict(row), "project_id": row["workflow_id"], "task_id": row["step_id"], "content": _load(row["content"])} for row in rows]

    def get_context_profile(self, workflow_id: str) -> dict[str, Any]:
        with get_db_pool(self.db_path).get_connection() as conn:
            row = conn.execute("SELECT * FROM workflow_context_profiles WHERE workflow_id = ?", (workflow_id,)).fetchone()
        if row:
            return self._context_profile_from_row(row)
        project = self.get_project(workflow_id)
        profile = {
            "project_path": project.get("project_path") if project else None,
            "chat_session_id": None,
            "include_project_context": True,
            "include_chat_context": False,
            "include_memory": True,
            "max_context_chars": 6000,
            "metadata": {},
        }
        self.upsert_context_profile(workflow_id, profile)
        return self.get_context_profile(workflow_id)

    def upsert_context_profile(self, workflow_id: str, data: dict[str, Any]) -> dict[str, Any]:
        now = _now()
        existing = None
        with get_db_pool(self.db_path).get_connection() as conn:
            existing = conn.execute(
                "SELECT created_at FROM workflow_context_profiles WHERE workflow_id = ?",
                (workflow_id,),
            ).fetchone()
            conn.execute(
                """
                INSERT OR REPLACE INTO workflow_context_profiles
                    (workflow_id, project_path, chat_session_id, include_project_context,
                     include_chat_context, include_memory, max_context_chars, metadata,
                     created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    workflow_id,
                    data.get("project_path"),
                    data.get("chat_session_id"),
                    1 if data.get("include_project_context", True) else 0,
                    1 if data.get("include_chat_context", False) else 0,
                    1 if data.get("include_memory", True) else 0,
                    int(data.get("max_context_chars") or 6000),
                    _json(data.get("metadata", {})),
                    existing["created_at"] if existing else now,
                    now,
                ),
            )
        return self.get_context_profile(workflow_id)

    def add_context_snapshot(
        self,
        workflow_id: str,
        step_id: str | None,
        step_key: str | None,
        content: str,
        sources: list[dict[str, Any]] | None = None,
        context_type: str = "runtime",
    ) -> dict[str, Any]:
        snapshot_id = f"wfc_{uuid.uuid4().hex[:8]}"
        now = _now()
        with get_db_pool(self.db_path).get_connection() as conn:
            conn.execute(
                """
                INSERT INTO workflow_context_snapshots
                    (id, workflow_id, step_id, step_key, context_type, content, sources, char_count, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (snapshot_id, workflow_id, step_id, step_key, context_type, content, _json(sources or []), len(content or ""), now),
            )
        return {
            "id": snapshot_id,
            "workflow_id": workflow_id,
            "step_id": step_id,
            "step_key": step_key,
            "context_type": context_type,
            "content": content,
            "sources": sources or [],
            "char_count": len(content or ""),
            "created_at": now,
        }

    def list_context_snapshots(self, workflow_id: str) -> list[dict[str, Any]]:
        with get_db_pool(self.db_path).get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM workflow_context_snapshots WHERE workflow_id = ? ORDER BY created_at ASC",
                (workflow_id,),
            ).fetchall()
        return [self._context_snapshot_from_row(row) for row in rows]

    def add_memory_entry(
        self,
        workflow_id: str,
        memory_type: str,
        memory_key: str,
        memory_value: dict[str, Any] | None,
        content: str,
        confidence: float = 0.6,
        source_step_id: str | None = None,
        external_memory_id: str | None = None,
    ) -> dict[str, Any]:
        memory_id = f"wfm_{uuid.uuid4().hex[:8]}"
        now = _now()
        with get_db_pool(self.db_path).get_connection() as conn:
            conn.execute(
                """
                INSERT INTO workflow_memory_entries
                    (id, workflow_id, source_step_id, memory_type, memory_key, memory_value,
                     content, confidence, status, external_memory_id, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, ?, ?)
                """,
                (
                    memory_id,
                    workflow_id,
                    source_step_id,
                    memory_type,
                    memory_key,
                    _json(memory_value or {}),
                    content,
                    confidence,
                    external_memory_id,
                    now,
                    now,
                ),
            )
        self.add_memory_event(workflow_id, memory_id, "memory_created", "system", "工作流记忆已自动写入")
        return self.get_memory_entry(memory_id) or {}

    def get_memory_entry(self, memory_id: str) -> dict[str, Any] | None:
        with get_db_pool(self.db_path).get_connection() as conn:
            row = conn.execute("SELECT * FROM workflow_memory_entries WHERE id = ?", (memory_id,)).fetchone()
        return self._memory_entry_from_row(row) if row else None

    def list_memory_entries(self, workflow_id: str) -> list[dict[str, Any]]:
        with get_db_pool(self.db_path).get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM workflow_memory_entries WHERE workflow_id = ? ORDER BY created_at ASC",
                (workflow_id,),
            ).fetchall()
        return [self._memory_entry_from_row(row) for row in rows]

    def revert_memory_entry(self, memory_id: str) -> dict[str, Any]:
        memory = self.get_memory_entry(memory_id)
        if not memory:
            raise KeyError("Workflow memory not found")
        now = _now()
        with get_db_pool(self.db_path).get_connection() as conn:
            conn.execute(
                "UPDATE workflow_memory_entries SET status = 'reverted', updated_at = ?, reverted_at = ? WHERE id = ?",
                (now, now, memory_id),
            )
        self.add_memory_event(memory["workflow_id"], memory_id, "memory_reverted", "user", "工作流记忆已撤销")
        return self.get_memory_entry(memory_id) or memory

    def add_memory_event(
        self,
        workflow_id: str,
        memory_id: str | None,
        event_type: str,
        actor: str,
        message: str,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        event_id = f"wfme_{uuid.uuid4().hex[:8]}"
        now = _now()
        with get_db_pool(self.db_path).get_connection() as conn:
            conn.execute(
                """
                INSERT INTO workflow_memory_events
                    (id, workflow_id, memory_id, event_type, actor, message, payload, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (event_id, workflow_id, memory_id, event_type, actor, message, _json(payload), now),
            )
        self.add_event(workflow_id, None, event_type, actor, message, payload)
        return {"id": event_id, "workflow_id": workflow_id, "memory_id": memory_id, "created_at": now}

    def add_step_log(
        self,
        workflow_id: str,
        step_id: str | None,
        step_key: str | None,
        agent_id: str | None,
        status: str,
        provider: str | None = None,
        model: str | None = None,
        input_summary: str = "",
        output_summary: str = "",
        error: str | None = None,
        started_at: str | None = None,
        completed_at: str | None = None,
        duration_ms: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        log_id = f"wfsl_{uuid.uuid4().hex[:8]}"
        now = _now()
        with get_db_pool(self.db_path).get_connection() as conn:
            conn.execute(
                """
                INSERT INTO workflow_step_logs
                    (id, workflow_id, step_id, step_key, agent_id, status, provider, model,
                     input_summary, output_summary, error, started_at, completed_at,
                     duration_ms, metadata, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    log_id,
                    workflow_id,
                    step_id,
                    step_key,
                    agent_id,
                    status,
                    provider,
                    model,
                    input_summary,
                    output_summary,
                    error,
                    started_at,
                    completed_at,
                    duration_ms,
                    _json(metadata or {}),
                    now,
                ),
            )
        return {
            "id": log_id,
            "workflow_id": workflow_id,
            "step_id": step_id,
            "step_key": step_key,
            "agent_id": agent_id,
            "status": status,
            "created_at": now,
        }

    def list_step_logs(self, workflow_id: str) -> list[dict[str, Any]]:
        with get_db_pool(self.db_path).get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM workflow_step_logs WHERE workflow_id = ? ORDER BY created_at ASC",
                (workflow_id,),
            ).fetchall()
        return [self._step_log_from_row(row) for row in rows]

    def add_action_proposal(
        self,
        workflow_id: str,
        step_id: str | None,
        action_type: str,
        title: str,
        description: str = "",
        payload: dict[str, Any] | None = None,
        created_by: str = "agent",
    ) -> dict[str, Any]:
        action_id = f"wfac_{uuid.uuid4().hex[:8]}"
        now = _now()
        with get_db_pool(self.db_path).get_connection() as conn:
            conn.execute(
                """
                INSERT INTO workflow_action_proposals
                    (id, workflow_id, step_id, action_type, title, description, payload,
                     status, created_by, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'pending_approval', ?, ?, ?)
                """,
                (action_id, workflow_id, step_id, action_type, title, description, _json(payload or {}), created_by, now, now),
            )
        self.add_event(workflow_id, step_id, "action_proposed", created_by, f"动作建议已生成：{title}", {"action_id": action_id, "action_type": action_type})
        return self.get_action_proposal(action_id) or {}

    def get_action_proposal(self, action_id: str) -> dict[str, Any] | None:
        with get_db_pool(self.db_path).get_connection() as conn:
            row = conn.execute("SELECT * FROM workflow_action_proposals WHERE id = ?", (action_id,)).fetchone()
        return self._action_from_row(row) if row else None

    def list_action_proposals(self, workflow_id: str) -> list[dict[str, Any]]:
        with get_db_pool(self.db_path).get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM workflow_action_proposals WHERE workflow_id = ? ORDER BY created_at ASC",
                (workflow_id,),
            ).fetchall()
        return [self._action_from_row(row) for row in rows]

    def update_action_status(self, action_id: str, status: str, **fields: Any) -> dict[str, Any]:
        fields["status"] = status
        fields["updated_at"] = _now()
        assignments = ", ".join(f"{key} = ?" for key in fields)
        values = list(fields.values()) + [action_id]
        with get_db_pool(self.db_path).get_connection() as conn:
            conn.execute(f"UPDATE workflow_action_proposals SET {assignments} WHERE id = ?", values)
        return self.get_action_proposal(action_id) or {}

    def add_action_execution(
        self,
        action_id: str,
        workflow_id: str,
        status: str,
        stdout: str = "",
        stderr: str = "",
        exit_code: int | None = None,
        duration_ms: int | None = None,
        error: str | None = None,
    ) -> dict[str, Any]:
        execution_id = f"wfae_{uuid.uuid4().hex[:8]}"
        now = _now()
        with get_db_pool(self.db_path).get_connection() as conn:
            conn.execute(
                """
                INSERT INTO workflow_action_executions
                    (id, action_id, workflow_id, status, stdout, stderr, exit_code,
                     duration_ms, error, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (execution_id, action_id, workflow_id, status, stdout, stderr, exit_code, duration_ms, error, now),
            )
        return {
            "id": execution_id,
            "action_id": action_id,
            "workflow_id": workflow_id,
            "status": status,
            "stdout": stdout,
            "stderr": stderr,
            "exit_code": exit_code,
            "duration_ms": duration_ms,
            "error": error,
            "created_at": now,
        }

    def list_action_executions(self, action_id: str) -> list[dict[str, Any]]:
        with get_db_pool(self.db_path).get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM workflow_action_executions WHERE action_id = ? ORDER BY created_at ASC",
                (action_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def _definition_from_template_payload(self, template_id: str, payload: dict[str, Any], is_builtin: bool) -> WorkflowDefinition:
        legacy_role_map = self._legacy_role_map(template_id)
        return WorkflowDefinition(
            id=template_id,
            name=payload["name"],
            description=payload.get("description", ""),
            legacy_template_id="software_dev_team" if template_id == "software_delivery" else template_id,
            is_builtin=is_builtin,
            is_enabled=payload.get("is_enabled", True),
            default_provider=payload.get("default_provider", "minimax"),
            default_model=payload.get("default_model"),
            default_approval_mode=payload.get("default_approval_mode", "manual"),
            agents=[
                AgentDefinition(
                    id=agent["agent_id"],
                    name=agent["name"],
                    description=agent.get("description", ""),
                    system_prompt=agent.get("system_prompt", ""),
                    output_requirements=agent.get("output_requirements", ""),
                )
                for agent in payload["agents"]
            ],
            steps=[
                StepDefinition(
                    key=step["step_key"],
                    agent_id=step["agent_id"],
                    legacy_role=legacy_role_map.get(step["step_key"], step["agent_id"]),
                    title=step["title"],
                    description=step.get("description", ""),
                    artifact_type=step["artifact_type"],
                    artifact_title=step["title"],
                    requires_approval=step.get("requires_approval", True),
                    sort_order=index,
                )
                for index, step in enumerate(sorted(payload["steps"], key=lambda item: item.get("sort_order", 0)))
            ],
        )

    def _template_from_row(self, row: Any) -> WorkflowDefinition:
        data = dict(row)
        legacy_role_map = self._legacy_role_map(data["id"])
        with get_db_pool(self.db_path).get_connection() as conn:
            agents = conn.execute(
                "SELECT * FROM workflow_template_agents WHERE template_id = ? ORDER BY created_at ASC",
                (data["id"],),
            ).fetchall()
            steps = conn.execute(
                "SELECT * FROM workflow_template_steps WHERE template_id = ? ORDER BY sort_order ASC, created_at ASC",
                (data["id"],),
            ).fetchall()
        return WorkflowDefinition(
            id=data["id"],
            name=data["name"],
            description=data["description"],
            legacy_template_id="software_dev_team" if data["id"] == "software_delivery" else data["id"],
            is_builtin=bool(data["is_builtin"]),
            is_enabled=bool(data["is_enabled"]),
            default_provider=data["default_provider"],
            default_model=data["default_model"],
            default_approval_mode=data["default_approval_mode"],
            agents=[
                AgentDefinition(
                    id=agent["agent_id"],
                    name=agent["name"],
                    description=agent["description"],
                    system_prompt=agent["system_prompt"],
                    output_requirements=agent["output_requirements"],
                )
                for agent in agents
            ],
            steps=[
                StepDefinition(
                    key=step["step_key"],
                    agent_id=step["agent_id"],
                    legacy_role=legacy_role_map.get(step["step_key"], step["agent_id"]),
                    title=step["title"],
                    description=step["description"],
                    artifact_type=step["artifact_type"],
                    artifact_title=step["title"],
                    requires_approval=bool(step["requires_approval"]),
                    sort_order=step["sort_order"],
                )
                for step in steps
            ],
        )

    def _project_from_row(self, row: Any, include_tasks: bool = False) -> dict[str, Any]:
        data = dict(row)
        data["metadata"] = _load(data.get("metadata"))
        data["tasks"] = self.get_tasks(data["id"]) if include_tasks else []
        return data

    def _task_from_row(self, row: Any) -> dict[str, Any]:
        data = dict(row)
        data["project_id"] = data["workflow_id"]
        data["role"] = data["agent_id"]
        data["requires_approval"] = bool(data.get("requires_approval"))
        data["input"] = _load(data.get("input"))
        data["output"] = _load(data.get("output"))
        return data

    def _context_profile_from_row(self, row: Any) -> dict[str, Any]:
        data = dict(row)
        data["include_project_context"] = bool(data.get("include_project_context"))
        data["include_chat_context"] = bool(data.get("include_chat_context"))
        data["include_memory"] = bool(data.get("include_memory"))
        data["metadata"] = _load(data.get("metadata"))
        return data

    def _context_snapshot_from_row(self, row: Any) -> dict[str, Any]:
        data = dict(row)
        data["sources"] = _load(data.get("sources"), [])
        return data

    def _memory_entry_from_row(self, row: Any) -> dict[str, Any]:
        data = dict(row)
        data["memory_value"] = _load(data.get("memory_value"))
        return data

    def _step_log_from_row(self, row: Any) -> dict[str, Any]:
        data = dict(row)
        data["metadata"] = _load(data.get("metadata"))
        return data

    def _action_from_row(self, row: Any) -> dict[str, Any]:
        data = dict(row)
        data["payload"] = _load(data.get("payload"))
        data["executions"] = self.list_action_executions(data["id"])
        return data

    def _legacy_role_map(self, template_id: str) -> dict[str, str]:
        if template_id == "software_delivery":
            return {"plan": "ceo", "implement": "developer", "review": "reviewer"}
        return {}
