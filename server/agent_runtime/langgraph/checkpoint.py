"""LangGraph checkpointer factory.

Phase 1 keeps the checkpointer isolated from the legacy SQLite connection pool
while sharing the same underlying ``app.db`` file.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from core.db_manager import get_db_pool

_cached_checkpointer: AsyncSqliteSaver | None = None
_cached_checkpointer_context = None


@lru_cache(maxsize=1)
def get_checkpoint_db_path() -> str:
    """Return the SQLite database path used by the application."""
    return str(Path(get_db_pool()._db_path))


async def get_checkpointer() -> AsyncSqliteSaver:
    """Create and initialize the LangGraph SQLite checkpointer."""
    global _cached_checkpointer, _cached_checkpointer_context
    if _cached_checkpointer is None:
        _cached_checkpointer_context = AsyncSqliteSaver.from_conn_string(get_checkpoint_db_path())
        _cached_checkpointer = await _cached_checkpointer_context.__aenter__()
    return _cached_checkpointer
