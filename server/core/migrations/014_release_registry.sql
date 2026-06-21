CREATE TABLE IF NOT EXISTS release_runs (
    run_id TEXT PRIMARY KEY,
    kind TEXT NOT NULL CHECK (kind IN ('evaluation', 'deployment')),
    status TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_release_runs_kind_created
    ON release_runs(kind, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_release_runs_kind_status
    ON release_runs(kind, status, updated_at);

CREATE TABLE IF NOT EXISTS release_leases (
    resource_id TEXT PRIMARY KEY,
    lease_kind TEXT NOT NULL,
    owner_id TEXT NOT NULL,
    acquired_at TEXT NOT NULL,
    heartbeat_at TEXT NOT NULL,
    expires_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_release_leases_expires
    ON release_leases(expires_at);
