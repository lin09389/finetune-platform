CREATE TABLE IF NOT EXISTS workflow_tool_calls (
    id TEXT PRIMARY KEY,
    workflow_id TEXT NOT NULL,
    step_id TEXT,
    agent_id TEXT,
    tool_name TEXT NOT NULL,
    arguments TEXT NOT NULL DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'running',
    result_summary TEXT NOT NULL DEFAULT '',
    result_payload TEXT NOT NULL DEFAULT '{}',
    error TEXT,
    started_at TEXT,
    completed_at TEXT,
    duration_ms INTEGER,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (workflow_id) REFERENCES workflows(id) ON DELETE CASCADE,
    FOREIGN KEY (step_id) REFERENCES workflow_steps(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_workflow_tool_calls_workflow
    ON workflow_tool_calls(workflow_id, created_at);

CREATE INDEX IF NOT EXISTS idx_workflow_tool_calls_step
    ON workflow_tool_calls(step_id, created_at);
