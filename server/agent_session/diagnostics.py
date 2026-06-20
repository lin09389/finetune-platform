from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from core.db_manager import get_db_pool
from core.storage import APP_DB_PATH, init_storage


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class AgentFrontendDiagnosticsRepository:
    def __init__(self, db_path: str = APP_DB_PATH):
        self.db_path = db_path
        init_storage(db_path)

    @staticmethod
    def session_hash(session_id: str, user_id: str) -> str:
        return hashlib.sha256(f"{user_id}:{session_id}".encode("utf-8")).hexdigest()

    def upsert(self, report: dict[str, Any], user_id: str) -> None:
        session_id = str(report.get("sessionId") or "").strip()
        if not session_id:
            return
        now = str(report.get("updatedAt") or _utcnow())
        session_hash = self.session_hash(session_id, user_id)
        with get_db_pool(self.db_path).get_connection() as conn:
            conn.execute(
                """
                INSERT INTO agent_frontend_diagnostics (
                    session_hash, protocol_version, unknown_events, parse_failures,
                    reconnects, recovery_requested, recovery_succeeded, recovery_failed,
                    attention_json, first_seen_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(session_hash) DO UPDATE SET
                    protocol_version = excluded.protocol_version,
                    unknown_events = MAX(agent_frontend_diagnostics.unknown_events, excluded.unknown_events),
                    parse_failures = MAX(agent_frontend_diagnostics.parse_failures, excluded.parse_failures),
                    reconnects = MAX(agent_frontend_diagnostics.reconnects, excluded.reconnects),
                    recovery_requested = MAX(agent_frontend_diagnostics.recovery_requested, excluded.recovery_requested),
                    recovery_succeeded = MAX(agent_frontend_diagnostics.recovery_succeeded, excluded.recovery_succeeded),
                    recovery_failed = MAX(agent_frontend_diagnostics.recovery_failed, excluded.recovery_failed),
                    attention_json = excluded.attention_json,
                    updated_at = excluded.updated_at
                """,
                (
                    session_hash,
                    str(report.get("protocolVersion") or "agent.session.v1"),
                    max(0, int(report.get("unknownEvents") or 0)),
                    max(0, int(report.get("parseFailures") or 0)),
                    max(0, int(report.get("reconnects") or 0)),
                    max(0, int(report.get("recoveryRequested") or 0)),
                    max(0, int(report.get("recoverySucceeded") or 0)),
                    max(0, int(report.get("recoveryFailed") or 0)),
                    json.dumps(report.get("attentionByKind") or {}, ensure_ascii=False),
                    now,
                    now,
                ),
            )

    def summary(self) -> dict[str, Any]:
        with get_db_pool(self.db_path).get_readonly_connection() as conn:
            row = conn.execute(
                """
                SELECT
                    COUNT(*) AS sessions,
                    COALESCE(SUM(unknown_events), 0) AS unknown_events,
                    COALESCE(SUM(parse_failures), 0) AS parse_failures,
                    COALESCE(SUM(reconnects), 0) AS reconnects,
                    COALESCE(SUM(recovery_requested), 0) AS recovery_requested,
                    COALESCE(SUM(recovery_succeeded), 0) AS recovery_succeeded,
                    COALESCE(SUM(recovery_failed), 0) AS recovery_failed,
                    MAX(updated_at) AS updated_at
                FROM agent_frontend_diagnostics
                """
            ).fetchone()
        result = dict(row) if row else {}
        requested = int(result.get("recovery_requested") or 0)
        succeeded = int(result.get("recovery_succeeded") or 0)
        result["recovery_success_rate"] = round(succeeded / requested, 4) if requested else None
        return result
