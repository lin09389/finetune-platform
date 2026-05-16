-- 010: 将 tables.db 的 table_registry 表合并到主应用数据库
-- 从此版本起，TableStore 使用 app.db 而非独立的 tables.db

CREATE TABLE IF NOT EXISTS table_registry (
    table_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    source_file TEXT,
    source_type TEXT,
    row_count INTEGER,
    column_count INTEGER,
    columns_json TEXT,
    created_at TEXT,
    updated_at TEXT,
    tags_json TEXT
);
