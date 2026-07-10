"""Bounded, process-local storage for unsubmitted training proposals."""

from __future__ import annotations

from collections import OrderedDict
from threading import Lock

from agent_training.models import TrainingProposal


class TrainingProposalStore:
    """Thread-safe proposal storage; its contents intentionally do not survive restarts."""

    def __init__(self, max_entries: int = 100):
        if max_entries < 1:
            raise ValueError("max_entries must be at least 1")
        self._max_entries = max_entries
        self._items: OrderedDict[str, TrainingProposal] = OrderedDict()
        self._claimed_submission_ids: set[str] = set()
        self._lock = Lock()

    def add(self, proposal: TrainingProposal) -> TrainingProposal:
        with self._lock:
            self._items[proposal.proposal_id] = proposal.model_copy(deep=True)
            self._items.move_to_end(proposal.proposal_id)
            while len(self._items) > self._max_entries:
                proposal_id, _ = self._items.popitem(last=False)
                self._claimed_submission_ids.discard(proposal_id)
            return proposal.model_copy(deep=True)

    def get(self, proposal_id: str) -> TrainingProposal | None:
        with self._lock:
            proposal = self._items.get(proposal_id)
            return proposal.model_copy(deep=True) if proposal else None

    def claim_submission(self, proposal_id: str) -> bool:
        """Atomically reserve a known proposal so it cannot be submitted twice."""
        with self._lock:
            if proposal_id not in self._items or proposal_id in self._claimed_submission_ids:
                return False
            self._claimed_submission_ids.add(proposal_id)
            return True

    def release_submission(self, proposal_id: str) -> None:
        """Allow retry if the lower-level submission failed before task creation."""
        with self._lock:
            self._claimed_submission_ids.discard(proposal_id)


__all__ = ["TrainingProposalStore"]
