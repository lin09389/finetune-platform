CREATE TABLE IF NOT EXISTS chat_sessions (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    message_count INTEGER DEFAULT 0,
    metadata TEXT DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    deleted_at TEXT
);

CREATE TABLE IF NOT EXISTS chat_messages (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    metadata TEXT DEFAULT '{}',
    created_at TEXT NOT NULL,
    ordinal INTEGER NOT NULL,
    FOREIGN KEY (session_id) REFERENCES chat_sessions(id) ON DELETE CASCADE
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_chat_messages_session_id
ON chat_messages(session_id, id);

CREATE UNIQUE INDEX IF NOT EXISTS idx_chat_messages_session_ordinal_unique
ON chat_messages(session_id, ordinal);

CREATE INDEX IF NOT EXISTS idx_chat_sessions_updated
ON chat_sessions(updated_at DESC);

CREATE TABLE IF NOT EXISTS chat_branches (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    parent_message_id TEXT,
    title TEXT,
    metadata TEXT DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (session_id) REFERENCES chat_sessions(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_chat_branches_session
ON chat_branches(session_id);

CREATE TABLE IF NOT EXISTS chat_shares (
    share_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    title TEXT NOT NULL,
    messages TEXT NOT NULL,
    created_at TEXT NOT NULL,
    expires_at TEXT,
    view_count INTEGER DEFAULT 0,
    is_public INTEGER DEFAULT 1,
    FOREIGN KEY (session_id) REFERENCES chat_sessions(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_chat_shares_session
ON chat_shares(session_id);

CREATE TABLE IF NOT EXISTS memory_items (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL DEFAULT 'default',
    content TEXT NOT NULL,
    type TEXT NOT NULL DEFAULT 'knowledge',
    importance REAL DEFAULT 0.5,
    source TEXT DEFAULT 'unknown',
    metadata TEXT DEFAULT '{}',
    vector_state TEXT DEFAULT 'pending',
    access_count INTEGER DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    deleted_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_memory_items_user_type
ON memory_items(user_id, type, deleted_at);

CREATE INDEX IF NOT EXISTS idx_memory_vector_state
ON memory_items(vector_state, updated_at);

CREATE TABLE IF NOT EXISTS audit_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT UNIQUE,
    trace_id TEXT,
    user_id TEXT,
    session_id TEXT,
    agent_id TEXT,
    source_ip TEXT,
    event_type TEXT,
    severity TEXT,
    resource_type TEXT,
    resource_id TEXT,
    action TEXT,
    details TEXT DEFAULT '{}',
    params TEXT,
    status TEXT,
    result TEXT,
    latency REAL,
    error TEXT,
    error_message TEXT,
    duration_ms REAL,
    metadata TEXT DEFAULT '{}',
    timestamp TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_audit_logs_event_type
ON audit_logs(event_type);

CREATE INDEX IF NOT EXISTS idx_audit_logs_user_id
ON audit_logs(user_id);

CREATE INDEX IF NOT EXISTS idx_audit_logs_timestamp
ON audit_logs(timestamp);

CREATE TABLE IF NOT EXISTS storage_outbox (
    id TEXT PRIMARY KEY,
    type TEXT NOT NULL,
    target TEXT NOT NULL,
    payload TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    retry_count INTEGER NOT NULL DEFAULT 0,
    max_retries INTEGER NOT NULL DEFAULT 5,
    next_retry_at TEXT,
    error TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_storage_outbox_status_next
ON storage_outbox(status, next_retry_at, updated_at);
