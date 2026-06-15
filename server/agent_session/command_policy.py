"""Terminal output helpers.

Historically this module enforced a command allowlist and shell-operator
rejection for agent commands. That gating is no longer performed by the
platform: agent commands now run through the DeepAgents sandbox execute
tool (see AGENTS.md "核心设计模式 13"), so the allowlist had no production
callers and was removed to avoid implying a safety control that does not
exist. Only :func:`summarize_failure` survives, reused by
``terminal_manager`` to truncate failed-command output.

The module name is intentionally kept (renaming would force import changes
across callers without functional benefit).
"""

from __future__ import annotations


def summarize_failure(stdout: str = "", stderr: str = "", error: str | None = None, limit: int = 1600) -> str:
    text = "\n".join(part for part in [error or "", stderr or "", stdout or ""] if part).strip()
    if not text:
        return ""
    lines = [line.rstrip() for line in text.splitlines() if line.strip()]
    selected = lines[-20:]
    summary = "\n".join(selected)
    return summary[:limit]


__all__ = ["summarize_failure"]
