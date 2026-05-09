-- 009_langgraph_checkpoints.sql
-- LangGraph checkpoint 持久化表，与现有业务表共存于 app.db
-- 由 AsyncSqliteSaver.setup() 创建，此处手动定义以确保与迁移系统一致
-- 参考: langgraph-checkpoint-sqlite 3.0.3

CREATE TABLE IF NOT EXISTS checkpoints (
    thread_id TEXT NOT NULL,
    checkpoint_ns TEXT NOT NULL DEFAULT '',
    checkpoint_id TEXT NOT NULL,
    parent_checkpoint_id TEXT,
    type TEXT,
    checkpoint BLOB,
    metadata BLOB,
    PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id)
);

CREATE TABLE IF NOT EXISTS checkpoint_writes (
    thread_id TEXT NOT NULL,
    checkpoint_ns TEXT NOT NULL DEFAULT '',
    checkpoint_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    idx INTEGER NOT NULL,
    channel TEXT NOT NULL,
    type TEXT,
    value BLOB,
    PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id, task_id, idx)
);

-- 性能索引
CREATE INDEX IF NOT EXISTS idx_checkpoints_thread ON checkpoints(thread_id, checkpoint_ns);
CREATE INDEX IF NOT EXISTS idx_checkpoints_parent ON checkpoints(parent_checkpoint_id);
CREATE INDEX IF NOT EXISTS idx_checkpoint_writes_lookup ON checkpoint_writes(thread_id, checkpoint_ns, checkpoint_id);