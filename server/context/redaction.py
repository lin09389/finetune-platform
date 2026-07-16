"""Secret redaction for Agent/context packs (Phase 3).

Unlike eval privacy sanitizers, this intentionally **keeps code paths and
structure** so the coding agent can still navigate the workspace. It only
masks credential-shaped material before content enters prompts or ``/context``
virtual files.
"""
from __future__ import annotations

import re
from typing import Any

# Assignment-style secrets: password=..., api_key: "..."
_SECRET_ASSIGNMENT = re.compile(
    r"(?i)\b(api[_-]?key|access[_-]?token|secret[_-]?key|client[_-]?secret|password|passwd|pwd|token|authorization)\b"
    r"(\s*[=:]\s*)(['\"]?)([^\s'\"\n\r,;]{4,})(\3?)"
)
_BEARER = re.compile(r"(?i)\b(authorization\s*:\s*bearer\s+)(\S+)")
_KNOWN_TOKEN = re.compile(
    r"\b(?:"
    r"sk-[A-Za-z0-9_-]{16,}"
    r"|gh[pousr]_[A-Za-z0-9_]{16,}"
    r"|xox[baprs]-[A-Za-z0-9-]{10,}"
    r"|hf_[A-Za-z0-9]{16,}"
    r"|AKIA[0-9A-Z]{16}"
    r")\b"
)
_PRIVATE_KEY = re.compile(
    r"-----BEGIN\s+(?:RSA\s+|EC\s+|OPENSSH\s+)?PRIVATE\s+KEY-----[\s\S]*?-----END\s+(?:RSA\s+|EC\s+|OPENSSH\s+)?PRIVATE\s+KEY-----",
    re.IGNORECASE,
)
_CONNECTION_STRING = re.compile(
    r"(?i)\b((?:postgres|postgresql|mysql|mongodb|redis|amqp|https?)://)([^:\s/@]+):([^@\s/]+)@"
)

REDACTED = "[REDACTED_SECRET]"


def redact_secrets(text: str | None) -> str:
    """Return text with credential-shaped spans replaced."""
    if not text:
        return ""
    result = str(text)
    result = _PRIVATE_KEY.sub(f"-----BEGIN PRIVATE KEY-----\n{REDACTED}\n-----END PRIVATE KEY-----", result)
    result = _CONNECTION_STRING.sub(rf"\1\2:{REDACTED}@", result)
    result = _BEARER.sub(rf"\1{REDACTED}", result)
    result = _KNOWN_TOKEN.sub(REDACTED, result)

    def _assign(match: re.Match[str]) -> str:
        key, sep, quote, _value, end_quote = match.group(1), match.group(2), match.group(3), match.group(4), match.group(5)
        return f"{key}{sep}{quote}{REDACTED}{end_quote or quote}"

    result = _SECRET_ASSIGNMENT.sub(_assign, result)
    return result


def redact_mapping_values(data: dict[str, Any] | None, keys: tuple[str, ...] = ("content", "text", "snippet")) -> dict[str, Any]:
    """Return a shallow copy with selected string fields redacted."""
    if not isinstance(data, dict):
        return {}
    out = dict(data)
    for key in keys:
        if key in out and isinstance(out[key], str):
            out[key] = redact_secrets(out[key])
    return out


def count_redactions(original: str, redacted: str) -> int:
    if not original or original == redacted:
        return 0
    return max(0, redacted.count(REDACTED) - original.count(REDACTED))
