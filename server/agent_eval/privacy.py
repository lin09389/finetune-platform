"""Bounded redaction for persisted evaluation summaries."""

from __future__ import annotations

import re
from collections.abc import Iterable

MAX_SUMMARY_LENGTH = 512

_CODE_FENCE = re.compile(r"```.*?```", re.DOTALL)
_AUTHORIZATION = re.compile(r"(?i)authorization\s*[:=]\s*(?:bearer\s+)?\S+")
_SECRET_ASSIGNMENT = re.compile(
    r"(?i)\b(api[_-]?key|access[_-]?token|secret|password)\b\s*[:=]\s*['\"]?[^\s,'\"]+"
)
_KNOWN_TOKEN = re.compile(r"\b(?:sk-[A-Za-z0-9_-]{8,}|gh[pousr]_[A-Za-z0-9_]{8,}|xox[baprs]-\S+|hf_[A-Za-z0-9]{8,})\b")
_WINDOWS_PATH = re.compile(r"(?i)(?<![A-Za-z0-9])(?:[A-Z]:\\|\\\\)[^\r\n\t<>|\"]+")
_POSIX_PATH = re.compile(r"(?<![A-Za-z0-9:/])/(?:[^\s/]+/)*[^\s,;:]*")
_LONG_QUOTED_VALUE = re.compile(r"(['\"])[^'\"\r\n]{80,}\1")


def sanitize_summary(
    value: str | None,
    *,
    sensitive_values: Iterable[str] = (),
) -> str | None:
    """Remove paths, credentials, prompts, and code-shaped bulk content."""

    if value is None:
        return None
    result = _CODE_FENCE.sub("[REDACTED_CODE]", value)
    for sensitive in sorted((item for item in sensitive_values if item), key=len, reverse=True):
        result = re.sub(re.escape(sensitive), "[REDACTED_CONTENT]", result, flags=re.IGNORECASE)
    result = _AUTHORIZATION.sub("Authorization: [REDACTED]", result)
    result = _SECRET_ASSIGNMENT.sub(lambda match: f"{match.group(1)}=[REDACTED]", result)
    result = _KNOWN_TOKEN.sub("[REDACTED_SECRET]", result)
    result = _WINDOWS_PATH.sub("[REDACTED_PATH]", result)
    result = _POSIX_PATH.sub("[REDACTED_PATH]", result)
    result = _LONG_QUOTED_VALUE.sub("[REDACTED_CONTENT]", result)
    result = " ".join(result.split())
    if not result:
        return None
    if len(result) > MAX_SUMMARY_LENGTH:
        result = f"{result[: MAX_SUMMARY_LENGTH - 1]}…"
    return result
