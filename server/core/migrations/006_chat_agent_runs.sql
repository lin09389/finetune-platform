CREATE TABLE IF NOT EXISTS chat_agent_runs (
    id TEXT PRIMARY KEY,
    chat_session_id TEXT,
    trigger_message_id TEXT,
    workflow_id TEXT,
    status TEXT NOT NULL DEFAULT 'created',
    intent_type TEXT NOT NULL DEFAULT 'agent_work',
    summary TEXT NOT NULL DEFAULT '',
    metadata TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_chat_agent_runs_session
    ON chat_agent_runs(chat_session_id, created_at);

CREATE INDEX IF NOT EXISTS idx_chat_agent_runs_workflow
    ON chat_agent_runs(workflow_id);

CREATE TABLE IF NOT EXISTS chat_agent_run_messages (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    chat_message_id TEXT,
    message_type TEXT NOT NULL,
    workflow_event_id TEXT,
    action_id TEXT,
    metadata TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    FOREIGN KEY(run_id) REFERENCES chat_agent_runs(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_chat_agent_run_messages_run
    ON chat_agent_run_messages(run_id, created_at);
