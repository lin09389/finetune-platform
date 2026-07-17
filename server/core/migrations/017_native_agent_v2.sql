-- Native Agent v2 persistence scaffolding.
--
-- These tables are intentionally repositories, rather than projections: the
-- event log is authoritative and snapshots are disposable recovery aids.

CREATE TABLE IF NOT EXISTS native_agent_sessions (
    id TEXT PRIMARY KEY,
    schema_version INTEGER NOT NULL DEFAULT 2 CHECK (schema_version = 2),
    runtime_kind TEXT NOT NULL CHECK (runtime_kind = 'native'),
    status TEXT NOT NULL CHECK (
        status IN ('created', 'queued', 'running', 'waiting_approval', 'waiting_permission',
                   'paused', 'completed', 'failed', 'cancelled')
    ),
    workspace_id TEXT,
    branch_id TEXT,
    runtime_binding_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_native_agent_sessions_status_updated
ON native_agent_sessions(status, updated_at DESC);

CREATE TABLE IF NOT EXISTS native_agent_events (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    sequence INTEGER NOT NULL CHECK (sequence > 0),
    schema_version INTEGER NOT NULL DEFAULT 2 CHECK (schema_version = 2),
    turn_id TEXT,
    command_id TEXT,
    causation_id TEXT,
    kind TEXT NOT NULL,
    payload_json TEXT NOT NULL DEFAULT '{}',
    timestamp TEXT NOT NULL,
    FOREIGN KEY (session_id) REFERENCES native_agent_sessions(id) ON DELETE RESTRICT,
    UNIQUE (session_id, sequence)
);

CREATE INDEX IF NOT EXISTS idx_native_agent_events_replay
ON native_agent_events(session_id, sequence);
CREATE INDEX IF NOT EXISTS idx_native_agent_events_turn_sequence
ON native_agent_events(session_id, turn_id, sequence);
CREATE INDEX IF NOT EXISTS idx_native_agent_events_command
ON native_agent_events(session_id, command_id, sequence);

CREATE TABLE IF NOT EXISTS native_agent_commands (
    session_id TEXT NOT NULL,
    command_id TEXT NOT NULL,
    schema_version INTEGER NOT NULL DEFAULT 2 CHECK (schema_version = 2),
    kind TEXT NOT NULL,
    request_json TEXT NOT NULL DEFAULT '{}',
    response_json TEXT,
    status TEXT NOT NULL CHECK (status IN ('accepted', 'completed', 'rejected', 'failed')),
    accepted_sequence INTEGER CHECK (accepted_sequence IS NULL OR accepted_sequence >= 0),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (session_id, command_id),
    FOREIGN KEY (session_id) REFERENCES native_agent_sessions(id) ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS idx_native_agent_commands_status_updated
ON native_agent_commands(session_id, status, updated_at DESC);

CREATE TABLE IF NOT EXISTS native_agent_snapshots (
    session_id TEXT NOT NULL,
    sequence INTEGER NOT NULL CHECK (sequence >= 0),
    schema_version INTEGER NOT NULL DEFAULT 2 CHECK (schema_version = 2),
    projector_version INTEGER NOT NULL CHECK (projector_version > 0),
    state_json TEXT NOT NULL,
    checksum TEXT NOT NULL CHECK (length(checksum) = 64),
    created_at TEXT NOT NULL,
    PRIMARY KEY (session_id, sequence),
    FOREIGN KEY (session_id) REFERENCES native_agent_sessions(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_native_agent_snapshots_recovery
ON native_agent_snapshots(session_id, sequence DESC);

CREATE TABLE IF NOT EXISTS native_agent_pending_interactions (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    schema_version INTEGER NOT NULL DEFAULT 2 CHECK (schema_version = 2),
    turn_id TEXT,
    opened_sequence INTEGER NOT NULL CHECK (opened_sequence > 0),
    kind TEXT NOT NULL CHECK (kind IN ('approval', 'permission')),
    status TEXT NOT NULL CHECK (status IN ('pending', 'approved', 'rejected', 'cancelled', 'expired')),
    request_json TEXT NOT NULL DEFAULT '{}',
    resolution_json TEXT,
    resolved_sequence INTEGER CHECK (resolved_sequence IS NULL OR resolved_sequence > 0),
    created_at TEXT NOT NULL,
    resolved_at TEXT,
    FOREIGN KEY (session_id) REFERENCES native_agent_sessions(id) ON DELETE CASCADE,
    CHECK ((status = 'pending' AND resolved_at IS NULL) OR status <> 'pending')
);

CREATE INDEX IF NOT EXISTS idx_native_agent_pending_interactions_open
ON native_agent_pending_interactions(session_id, status, opened_sequence);

CREATE TABLE IF NOT EXISTS native_agent_file_mutations (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    schema_version INTEGER NOT NULL DEFAULT 2 CHECK (schema_version = 2),
    branch_id TEXT NOT NULL,
    event_sequence INTEGER NOT NULL CHECK (event_sequence > 0),
    causation_id TEXT,
    operation TEXT NOT NULL CHECK (operation IN ('write', 'edit', 'delete', 'rename')),
    path_token TEXT NOT NULL,
    destination_path_token TEXT,
    base_hash TEXT,
    result_hash TEXT,
    preimage_blob BLOB,
    encoding TEXT,
    restore_status TEXT NOT NULL DEFAULT 'not_requested' CHECK (
        restore_status IN ('not_requested', 'eligible', 'restored', 'conflict', 'manual_resolution', 'failed')
    ),
    restore_json TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (session_id) REFERENCES native_agent_sessions(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_native_agent_file_mutations_rewind
ON native_agent_file_mutations(session_id, branch_id, event_sequence DESC);
CREATE INDEX IF NOT EXISTS idx_native_agent_file_mutations_path
ON native_agent_file_mutations(session_id, path_token, event_sequence DESC);

CREATE TABLE IF NOT EXISTS native_agent_trace_candidates (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    branch_id TEXT,
    schema_version INTEGER NOT NULL DEFAULT 2 CHECK (schema_version = 2),
    event_sequence INTEGER NOT NULL CHECK (event_sequence > 0),
    redaction_version INTEGER NOT NULL CHECK (redaction_version > 0),
    state TEXT NOT NULL DEFAULT 'candidate' CHECK (state IN ('candidate', 'selected', 'rejected', 'exported')),
    facts_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (session_id) REFERENCES native_agent_sessions(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_native_agent_trace_candidates_selection
ON native_agent_trace_candidates(state, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_native_agent_trace_candidates_session
ON native_agent_trace_candidates(session_id, event_sequence);
