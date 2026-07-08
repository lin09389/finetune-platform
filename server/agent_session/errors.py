from __future__ import annotations


class AgentConfigurationError(ValueError):
    """Raised when an Agent run cannot start because required configuration is missing."""

    def __init__(self, message: str, *, failure_kind: str = "configuration_error") -> None:
        super().__init__(message)
        self.failure_kind = failure_kind
