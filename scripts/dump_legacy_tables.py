"""
Pre-drop backup: dump all legacy workflow/digital_team tables to JSON.

Run this BEFORE applying migration 012_drop_legacy_tables.sql.

Usage:
    cd server
    python ../scripts/dump_legacy_tables.py [--db data/app.db] [--out data/backups]
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

LEGACY_TABLES = [
    # digital_team (002)
    "digital_teams",
    "digital_team_projects",
    "digital_team_tasks",
    "digital_team_events",
    "digital_team_artifacts",
    "digital_team_reviews",
    # workflow runtime (003)
    "workflow_templates",
    "workflow_template_agents",
    "workflow_template_steps",
    "workflows",
    "workflow_steps",
    "workflow_events",
    "workflow_artifacts",
    "workflow_reviews",
    # workflow context/memory (004)
    "workflow_context_profiles",
    "workflow_context_snapshots",
    "workflow_memory_entries",
    "workflow_memory_events",
    # workflow observability/actions (005)
    "workflow_step_logs",
    "workflow_action_proposals",
    "workflow_action_executions",
    # tool calls (007)
    "workflow_tool_calls",
]


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone()
    return row is not None


def dump(db_path: str, out_dir: str) -> Path:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    dest = out / f"legacy_tables_dump_{stamp}.json"

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    result: dict[str, list[dict]] = {}
    stats: dict[str, int] = {}

    try:
        for table in LEGACY_TABLES:
            if not _table_exists(conn, table):
                print(f"  SKIP  {table} (not found)")
                stats[table] = -1
                continue
            rows = conn.execute(f"SELECT * FROM {table}").fetchall()  # noqa: S608
            result[table] = [dict(r) for r in rows]
            stats[table] = len(rows)
            print(f"  DUMP  {table}: {len(rows)} rows")
    finally:
        conn.close()

    dest.write_text(
        json.dumps({"dumped_at": stamp, "tables": result}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    total = sum(v for v in stats.values() if v >= 0)
    print(f"\nWrote {total} total rows → {dest}")
    return dest


def main() -> None:
    parser = argparse.ArgumentParser(description="Dump legacy tables before dropping them")
    parser.add_argument("--db", default="data/app.db", help="Path to app.db")
    parser.add_argument("--out", default="data/backups", help="Output directory")
    args = parser.parse_args()

    db_path = Path(args.db)
    if not db_path.exists():
        print(f"ERROR: database not found at {db_path}", file=sys.stderr)
        sys.exit(1)

    dump(str(db_path), args.out)


if __name__ == "__main__":
    main()
