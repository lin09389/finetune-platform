CREATE TABLE IF NOT EXISTS workflow_context_profiles (
    workflow_id TEXT PRIMARY KEY,
    project_path TEXT,
    chat_session_id TEXT,
    include_project_context INTEGER NOT NULL DEFAULT 1,
    include_chat_context INTEGER NOT NULL DEFAULT 0,
    include_memory INTEGER NOT NULL DEFAULT 1,
    max_context_chars INTEGER NOT NULL DEFAULT 6000,
    metadata TEXT DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (workflow_id) REFERENCES workflows(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS workflow_context_snapshots (
    id TEXT PRIMARY KEY,
    workflow_id TEXT NOT NULL,
    step_id TEXT,
    step_key TEXT,
    context_type TEXT NOT NULL DEFAULT 'runtime',
    content TEXT DEFAULT '',
    sources TEXT DEFAULT '[]',
    char_count INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    FOREIGN KEY (workflow_id) REFERENCES workflows(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_workflow_context_snapshots_workflow
    ON workflow_context_snapshots(workflow_id, created_at);

CREATE TABLE IF NOT EXISTS workflow_memory_entries (
    id TEXT PRIMARY KEY,
    workflow_id TEXT NOT NULL,
    source_step_id TEXT,
    memory_type TEXT NOT NULL DEFAULT 'workflow_retro',
    memory_key TEXT NOT NULL,
    memory_value TEXT DEFAULT '{}',
    content TEXT DEFAULT '',
    confidence REAL NOT NULL DEFAULT 0.6,
    status TEXT NOT NULL DEFAULT 'active',
    external_memory_id TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    reverted_at TEXT,
    FOREIGN KEY (workflow_id) REFERENCES workflows(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_workflow_memory_entries_workflow
    ON workflow_memory_entries(workflow_id, created_at);

CREATE TABLE IF NOT EXISTS workflow_memory_events (
    id TEXT PRIMARY KEY,
    workflow_id TEXT NOT NULL,
    memory_id TEXT,
    event_type TEXT NOT NULL,
    actor TEXT NOT NULL,
    message TEXT NOT NULL,
    payload TEXT DEFAULT '{}',
    created_at TEXT NOT NULL,
    FOREIGN KEY (workflow_id) REFERENCES workflows(id) ON DELETE CASCADE
);
