CREATE TABLE IF NOT EXISTS workflow_step_logs (
    id TEXT PRIMARY KEY,
    workflow_id TEXT NOT NULL,
    step_id TEXT,
    step_key TEXT,
    agent_id TEXT,
    status TEXT NOT NULL,
    provider TEXT,
    model TEXT,
    input_summary TEXT DEFAULT '',
    output_summary TEXT DEFAULT '',
    error TEXT,
    started_at TEXT,
    completed_at TEXT,
    duration_ms INTEGER,
    metadata TEXT DEFAULT '{}',
    created_at TEXT NOT NULL,
    FOREIGN KEY (workflow_id) REFERENCES workflows(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_workflow_step_logs_workflow
    ON workflow_step_logs(workflow_id, created_at);

CREATE TABLE IF NOT EXISTS workflow_action_proposals (
    id TEXT PRIMARY KEY,
    workflow_id TEXT NOT NULL,
    step_id TEXT,
    action_type TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT DEFAULT '',
    payload TEXT DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'pending_approval',
    created_by TEXT DEFAULT 'agent',
    approved_at TEXT,
    rejected_at TEXT,
    executed_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (workflow_id) REFERENCES workflows(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_workflow_action_proposals_workflow
    ON workflow_action_proposals(workflow_id, created_at);

CREATE TABLE IF NOT EXISTS workflow_action_executions (
    id TEXT PRIMARY KEY,
    action_id TEXT NOT NULL,
    workflow_id TEXT NOT NULL,
    status TEXT NOT NULL,
    stdout TEXT DEFAULT '',
    stderr TEXT DEFAULT '',
    exit_code INTEGER,
    duration_ms INTEGER,
    error TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (workflow_id) REFERENCES workflows(id) ON DELETE CASCADE,
    FOREIGN KEY (action_id) REFERENCES workflow_action_proposals(id) ON DELETE CASCADE
);
