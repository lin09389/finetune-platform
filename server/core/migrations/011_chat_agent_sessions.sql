ALTER TABLE chat_agent_runs ADD COLUMN agent_session_id TEXT;

CREATE INDEX IF NOT EXISTS idx_chat_agent_runs_agent_session
    ON chat_agent_runs(agent_session_id);
