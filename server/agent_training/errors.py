"""Domain errors exposed by the agent training application service."""

from __future__ import annotations

from typing import Any


class AgentTrainingError(RuntimeError):
    """A stable, tool-safe error for a rejected agent training action."""

    def __init__(self, code: str, message: str, *, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}

    def as_dict(self) -> dict[str, Any]:
        """Return a serializable error payload for a future tool adapter."""
        return {"code": self.code, "message": self.message, "details": self.details}
