"""Bounded proposal storage with optional cross-process SQLite persistence."""

from __future__ import annotations

import json
import sqlite3
from collections import OrderedDict
from pathlib import Path
from threading import Lock

from agent_training.models import TrainingProposal


class TrainingProposalStore:
    """Thread-safe proposal storage; SQLite mode preserves approval state across workers."""

    def __init__(self, max_entries: int = 100, db_path: str | Path | None = None):
        if max_entries < 1:
            raise ValueError("max_entries must be at least 1")
        self._max_entries = max_entries
        self._items: OrderedDict[str, TrainingProposal] = OrderedDict()
        self._claimed_submission_ids: set[str] = set()
        self._lock = Lock()
        self._db_path = Path(db_path).resolve() if db_path else None

    def _connection(self) -> sqlite3.Connection:
        if self._db_path is None:  # pragma: no cover - guarded by callers
            raise RuntimeError("SQLite persistence is not configured")
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self._db_path, timeout=10, isolation_level=None)
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS agent_training_proposals (
                proposal_id TEXT PRIMARY KEY,
                payload TEXT NOT NULL,
                created_at TEXT NOT NULL,
                submission_claimed INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        return connection

    def add(self, proposal: TrainingProposal) -> TrainingProposal:
        if self._db_path is not None:
            payload = json.dumps(proposal.model_dump(mode="json"), ensure_ascii=False)
            with self._connection() as connection:
                connection.execute(
                    """
                    INSERT INTO agent_training_proposals(proposal_id, payload, created_at, submission_claimed)
                    VALUES (?, ?, ?, 0)
                    ON CONFLICT(proposal_id) DO UPDATE SET
                        payload=excluded.payload,
                        created_at=excluded.created_at
                    WHERE agent_training_proposals.submission_claimed = 0
                    """,
                    (proposal.proposal_id, payload, proposal.created_at.isoformat()),
                )
                connection.execute(
                    """
                    DELETE FROM agent_training_proposals
                    WHERE proposal_id IN (
                        SELECT proposal_id FROM agent_training_proposals
                        ORDER BY created_at DESC
                        LIMIT -1 OFFSET ?
                    )
                    """,
                    (self._max_entries,),
                )
            return proposal.model_copy(deep=True)
        with self._lock:
            self._items[proposal.proposal_id] = proposal.model_copy(deep=True)
            self._items.move_to_end(proposal.proposal_id)
            while len(self._items) > self._max_entries:
                proposal_id, _ = self._items.popitem(last=False)
                self._claimed_submission_ids.discard(proposal_id)
            return proposal.model_copy(deep=True)

    def get(self, proposal_id: str) -> TrainingProposal | None:
        if self._db_path is not None:
            with self._connection() as connection:
                row = connection.execute(
                    "SELECT payload FROM agent_training_proposals WHERE proposal_id = ?",
                    (proposal_id,),
                ).fetchone()
            return TrainingProposal.model_validate(json.loads(row[0])) if row else None
        with self._lock:
            proposal = self._items.get(proposal_id)
            return proposal.model_copy(deep=True) if proposal else None

    def claim_submission(self, proposal_id: str) -> bool:
        """Atomically reserve a known proposal so it cannot be submitted twice."""
        if self._db_path is not None:
            with self._connection() as connection:
                connection.execute("BEGIN IMMEDIATE")
                try:
                    result = connection.execute(
                        """
                        UPDATE agent_training_proposals
                        SET submission_claimed = 1
                        WHERE proposal_id = ? AND submission_claimed = 0
                        """,
                        (proposal_id,),
                    )
                    connection.execute("COMMIT")
                    return result.rowcount == 1
                except Exception:
                    connection.execute("ROLLBACK")
                    raise
        with self._lock:
            if proposal_id not in self._items or proposal_id in self._claimed_submission_ids:
                return False
            self._claimed_submission_ids.add(proposal_id)
            return True

    def release_submission(self, proposal_id: str) -> None:
        """Allow retry if the lower-level submission failed before task creation."""
        if self._db_path is not None:
            with self._connection() as connection:
                connection.execute(
                    "UPDATE agent_training_proposals SET submission_claimed = 0 WHERE proposal_id = ?",
                    (proposal_id,),
                )
            return
        with self._lock:
            self._claimed_submission_ids.discard(proposal_id)


__all__ = ["TrainingProposalStore"]
