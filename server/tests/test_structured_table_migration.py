from __future__ import annotations

import sqlite3
from pathlib import Path

from rag.structured.table_store import TableStore


def test_table_store_migrates_legacy_tables_db(tmp_path: Path):
    storage_path = tmp_path / "tables"
    storage_path.mkdir()
    legacy_db = storage_path / "tables.db"
    with sqlite3.connect(legacy_db) as conn:
        conn.execute(
            """
            CREATE TABLE table_registry (
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
            )
            """
        )
        conn.execute(
            """
            INSERT INTO table_registry
            VALUES ('tbl_legacy', 'legacy', '', NULL, 'csv', 1, 1, '[{"name":"value"}]', '2026-05-16T00:00:00', '2026-05-16T00:00:00', '[]')
            """
        )
        conn.execute('CREATE TABLE table_tbl_legacy ("value" TEXT)')
        conn.execute('INSERT INTO table_tbl_legacy ("value") VALUES ("hello")')

    store = TableStore(storage_path=str(storage_path), db_path=str(tmp_path / "app.db"))

    assert "tbl_legacy" in {table.table_id for table in store.list_tables()}
    assert store.query("tbl_legacy") == [{"value": "hello"}]
