"""Typed, transport-safe Native Agent errors."""

from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict, Field, field_validator

MAX_ERROR_MESSAGE_CHARS = 512

_WINDOWS_PATH = re.compile(r"(?<![\w])(?:[A-Za-z]:\\)[^\s\"']+")
_POSIX_PATH = re.compile(r"(?<![\w])/(?:[^\s\"']+)")
_SECRET_VALUE = re.compile(
    r"(?i)\b(api[_-]?key|access[_-]?token|token|password|secret|authorization)\s*[:=]\s*"
    r"(?:bearer\s+)?[^\s,;]+"
)


def redact_error_message(message: str) -> str:
    """Return a bounded summary that cannot expose common paths or credentials."""

    redacted = _WINDOWS_PATH.sub("[path]", message)
    redacted = _POSIX_PATH.sub("[path]", redacted)
    redacted = _SECRET_VALUE.sub(lambda match: f"{match.group(1)}=[redacted]", redacted)
    return " ".join(redacted.split())[:MAX_ERROR_MESSAGE_CHARS]


class NativeAgentError(Exception):
    """Base error with a stable code suitable for protocol error envelopes."""

    code = "native_agent_error"

    def __init__(self, message: str) -> None:
        super().__init__(redact_error_message(message))


class UnknownCommandError(NativeAgentError):
    code = "unknown_command"


class ErrorPayload(BaseModel):
    """Public error fields. Raw exception objects and tracebacks never cross this boundary."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    code: str = Field(pattern=r"^[a-z][a-z0-9_]{0,63}$")
    message: str = Field(min_length=1, max_length=MAX_ERROR_MESSAGE_CHARS)
    retryable: bool = False
    retry_after_ms: int | None = Field(default=None, ge=0, le=300_000)

    @field_validator("message")
    @classmethod
    def redact_message(cls, value: str) -> str:
        redacted = redact_error_message(value)
        if not redacted:
            raise ValueError("error message must contain safe summary text")
        return redacted
