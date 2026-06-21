-- 013_agent_frontend_diagnostics.sql
-- Anonymous aggregate diagnostics for the production Agent Workbench.

CREATE TABLE IF NOT EXISTS agent_frontend_diagnostics (
    session_hash TEXT PRIMARY KEY,
    protocol_version TEXT NOT NULL,
    unknown_events INTEGER NOT NULL DEFAULT 0,
    parse_failures INTEGER NOT NULL DEFAULT 0,
    reconnects INTEGER NOT NULL DEFAULT 0,
    recovery_requested INTEGER NOT NULL DEFAULT 0,
    recovery_succeeded INTEGER NOT NULL DEFAULT 0,
    recovery_failed INTEGER NOT NULL DEFAULT 0,
    attention_json TEXT NOT NULL DEFAULT '{}',
    first_seen_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_agent_frontend_diagnostics_updated
ON agent_frontend_diagnostics(updated_at DESC);
