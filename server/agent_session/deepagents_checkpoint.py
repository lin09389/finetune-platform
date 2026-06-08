"""DeepAgents checkpointer factory.

The DeepAgents checkpoint store uses its own SQLite file so workflow/session
execution does not contend with the application's main state database.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from core.storage import APP_DB_PATH

_cached_checkpointer: AsyncSqliteSaver | None = None
_cached_checkpointer_context = None


@lru_cache(maxsize=1)
def get_checkpoint_db_path() -> str:
    """Return the dedicated SQLite database path used for LangGraph checkpoints."""
    configured = os.getenv("LANGGRAPH_CHECKPOINT_DB", "").strip()
    if configured:
        path = Path(configured)
    else:
        app_db = Path(APP_DB_PATH)
        path = app_db.with_name("langgraph_checkpoints.db")
    path.parent.mkdir(parents=True, exist_ok=True)
    return str(path)


async def get_checkpointer() -> AsyncSqliteSaver:
    """Create and initialize the LangGraph SQLite checkpointer."""
    global _cached_checkpointer, _cached_checkpointer_context
    if _cached_checkpointer is None:
        _cached_checkpointer_context = AsyncSqliteSaver.from_conn_string(get_checkpoint_db_path())
        _cached_checkpointer = await _cached_checkpointer_context.__aenter__()
        conn = getattr(_cached_checkpointer, "conn", None) or getattr(_cached_checkpointer, "connection", None)
        if conn is not None:
            busy_timeout = int(os.environ.get("LANGGRAPH_SQLITE_BUSY_TIMEOUT", os.environ.get("SQLITE_BUSY_TIMEOUT", "30000")))
            await conn.execute(f"PRAGMA busy_timeout = {busy_timeout}")
            await conn.execute("PRAGMA journal_mode = WAL")
            await conn.execute("PRAGMA synchronous = NORMAL")
            await conn.commit()
    return _cached_checkpointer


__all__ = ["get_checkpoint_db_path", "get_checkpointer"]
