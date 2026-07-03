CREATE TABLE IF NOT EXISTS training_jobs (
    job_id TEXT PRIMARY KEY,
    backend TEXT NOT NULL DEFAULT 'native',
    priority INTEGER NOT NULL DEFAULT 2,
    status TEXT NOT NULL,
    config_json TEXT NOT NULL,
    model_path TEXT NOT NULL,
    dataset_path TEXT NOT NULL,
    output_path TEXT NOT NULL,
    record_json TEXT NOT NULL,
    attempt INTEGER NOT NULL DEFAULT 0,
    max_attempts INTEGER NOT NULL DEFAULT 3,
    cancel_requested INTEGER NOT NULL DEFAULT 0,
    error TEXT,
    created_at TEXT NOT NULL,
    queued_at TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_training_jobs_claim
ON training_jobs(status, priority, queued_at);

CREATE INDEX IF NOT EXISTS idx_training_jobs_updated
ON training_jobs(updated_at DESC);

CREATE TABLE IF NOT EXISTS training_job_leases (
    job_id TEXT PRIMARY KEY,
    owner_id TEXT NOT NULL,
    acquired_at TEXT NOT NULL,
    heartbeat_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    FOREIGN KEY (job_id) REFERENCES training_jobs(job_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_training_job_leases_expires
ON training_job_leases(expires_at);

CREATE TABLE IF NOT EXISTS training_events (
    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT NOT NULL UNIQUE,
    version TEXT NOT NULL DEFAULT 'v2',
    ts TEXT NOT NULL,
    task_id TEXT NOT NULL,
    phase TEXT NOT NULL,
    kind TEXT NOT NULL,
    payload_json TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_training_events_task_sequence
ON training_events(task_id, sequence);

CREATE TABLE IF NOT EXISTS training_workers (
    worker_id TEXT PRIMARY KEY,
    pid INTEGER NOT NULL,
    hostname TEXT NOT NULL,
    status TEXT NOT NULL,
    started_at TEXT NOT NULL,
    heartbeat_at TEXT NOT NULL,
    stopped_at TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_training_workers_heartbeat
ON training_workers(heartbeat_at DESC);
