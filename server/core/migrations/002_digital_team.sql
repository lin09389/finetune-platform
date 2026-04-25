CREATE TABLE IF NOT EXISTS digital_teams (
    id TEXT PRIMARY KEY,
    template_id TEXT NOT NULL,
    name TEXT NOT NULL,
    description TEXT DEFAULT '',
    metadata TEXT DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS digital_team_projects (
    id TEXT PRIMARY KEY,
    team_id TEXT NOT NULL,
    title TEXT NOT NULL,
    goal TEXT NOT NULL,
    template_id TEXT NOT NULL,
    project_path TEXT,
    provider TEXT NOT NULL,
    model TEXT,
    approval_mode TEXT NOT NULL,
    status TEXT NOT NULL,
    current_stage TEXT,
    metadata TEXT DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    completed_at TEXT,
    FOREIGN KEY (team_id) REFERENCES digital_teams(id)
);

CREATE INDEX IF NOT EXISTS idx_digital_team_projects_updated
ON digital_team_projects(updated_at DESC);

CREATE TABLE IF NOT EXISTS digital_team_tasks (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    role TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT DEFAULT '',
    status TEXT NOT NULL,
    requires_approval INTEGER DEFAULT 1,
    input TEXT DEFAULT '{}',
    output TEXT DEFAULT '{}',
    error TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    completed_at TEXT,
    FOREIGN KEY (project_id) REFERENCES digital_team_projects(id)
);

CREATE INDEX IF NOT EXISTS idx_digital_team_tasks_project
ON digital_team_tasks(project_id, created_at);

CREATE TABLE IF NOT EXISTS digital_team_events (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    task_id TEXT,
    event_type TEXT NOT NULL,
    actor TEXT NOT NULL,
    message TEXT NOT NULL,
    payload TEXT DEFAULT '{}',
    created_at TEXT NOT NULL,
    FOREIGN KEY (project_id) REFERENCES digital_team_projects(id)
);

CREATE INDEX IF NOT EXISTS idx_digital_team_events_project
ON digital_team_events(project_id, created_at);

CREATE TABLE IF NOT EXISTS digital_team_artifacts (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    task_id TEXT,
    artifact_type TEXT NOT NULL,
    title TEXT NOT NULL,
    content TEXT DEFAULT '{}',
    created_at TEXT NOT NULL,
    FOREIGN KEY (project_id) REFERENCES digital_team_projects(id)
);

CREATE INDEX IF NOT EXISTS idx_digital_team_artifacts_project
ON digital_team_artifacts(project_id, created_at);

CREATE TABLE IF NOT EXISTS digital_team_reviews (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    approved INTEGER NOT NULL DEFAULT 0,
    summary TEXT DEFAULT '',
    risks TEXT DEFAULT '[]',
    created_at TEXT NOT NULL,
    FOREIGN KEY (project_id) REFERENCES digital_team_projects(id),
    FOREIGN KEY (task_id) REFERENCES digital_team_tasks(id)
);
