"""Configurable tool-result size limits and offload detection (Scheme A).

DeepAgents FilesystemMiddleware already offloads oversized tool results to
``/large_tool_results/`` when ``tool_token_limit_before_evict`` is exceeded.
This module:

1. Reads platform settings for execute-output bytes and tool-token eviction.
2. Applies those defaults when constructing DeepAgents graphs (patch once).
3. Detects offload markers in tool message text for UI / session metadata.
"""
from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

# DeepAgents default (filesystem middleware).
_DEEPAGENTS_DEFAULT_TOOL_TOKEN_LIMIT = 20_000

_OFFLOAD_PATH_RE = re.compile(
    r"(?P<path>/large_tool_results/[^\s`\"']+)",
    re.IGNORECASE,
)
_OFFLOAD_HINT_RE = re.compile(
    r"Tool result too large|offloaded into the filesystem|Output was truncated due to size",
    re.IGNORECASE,
)
_EXEC_TRUNCATED_RE = re.compile(
    r"Output truncated at\s+(\d+)\s+bytes",
    re.IGNORECASE,
)

_PATCHED = False


def get_execute_max_output_bytes() -> int:
    try:
        from core.config import settings

        return max(8_192, int(getattr(settings, "agent_execute_max_output_bytes", 200_000) or 200_000))
    except Exception:
        return 200_000


def get_tool_token_limit_before_evict() -> int:
    """Token budget before DeepAgents evicts a tool result to the VFS."""
    try:
        from core.config import settings

        value = getattr(settings, "agent_tool_token_limit_before_evict", 12_000)
        if value is None:
            return _DEEPAGENTS_DEFAULT_TOOL_TOKEN_LIMIT
        return max(1_000, int(value))
    except Exception:
        return 12_000


def get_tool_result_ui_max_chars() -> int:
    try:
        from core.config import settings

        return max(2_000, int(getattr(settings, "agent_tool_result_ui_max_chars", 12_000) or 12_000))
    except Exception:
        return 12_000


def apply_deepagents_tool_eviction_defaults() -> None:
    """Patch FilesystemMiddleware so create_deep_agent uses platform token limit.

    Safe to call multiple times; only patches once per process.
    """
    global _PATCHED
    if _PATCHED:
        return
    try:
        from deepagents.middleware.filesystem import FilesystemMiddleware
    except Exception as exc:
        logger.debug("DeepAgents FilesystemMiddleware unavailable for limit patch: %s", exc)
        return

    limit = get_tool_token_limit_before_evict()
    original_init = FilesystemMiddleware.__init__
    if getattr(original_init, "_finetune_tool_limit_patched", False):
        _PATCHED = True
        return

    def _patched_init(self, *args: Any, tool_token_limit_before_evict: int | None = None, **kwargs: Any) -> None:
        # Only override the library default when the caller did not pass an explicit value.
        if tool_token_limit_before_evict is None or tool_token_limit_before_evict == _DEEPAGENTS_DEFAULT_TOOL_TOKEN_LIMIT:
            tool_token_limit_before_evict = limit
        original_init(self, *args, tool_token_limit_before_evict=tool_token_limit_before_evict, **kwargs)

    _patched_init._finetune_tool_limit_patched = True  # type: ignore[attr-defined]
    FilesystemMiddleware.__init__ = _patched_init  # type: ignore[method-assign]
    _PATCHED = True
    logger.info(
        "DeepAgents tool result eviction limit set to %s tokens (execute max output %s bytes)",
        limit,
        get_execute_max_output_bytes(),
    )


def detect_tool_result_offload(content: str | None) -> dict[str, Any]:
    """Return offload/truncation facts for UI and session metadata."""
    text = str(content or "")
    path_match = _OFFLOAD_PATH_RE.search(text)
    exec_match = _EXEC_TRUNCATED_RE.search(text)
    hinted = bool(_OFFLOAD_HINT_RE.search(text))
    offloaded = bool(path_match) or hinted
    truncated = bool(exec_match) or ("truncated" in text.lower() and len(text) > 200)
    return {
        "offloaded": offloaded,
        "truncated": truncated or offloaded,
        "path": path_match.group("path") if path_match else None,
        "execute_truncated_bytes": int(exec_match.group(1)) if exec_match else None,
    }


def truncate_tool_result_for_ui(content: str | None, *, max_chars: int | None = None) -> tuple[str, bool]:
    """Bound part content stored for timeline UI (full text may live in VFS)."""
    text = str(content or "")
    limit = max_chars if max_chars is not None else get_tool_result_ui_max_chars()
    if len(text) <= limit:
        return text, False
    head = max(512, limit // 2)
    tail = max(512, limit - head - 80)
    marker = f"\n\n... [UI truncated {len(text) - head - tail} chars; full output may be under /large_tool_results/] ...\n\n"
    return text[:head] + marker + text[-tail:], True


def record_tool_offload_in_metadata(
    metadata: dict[str, Any] | None,
    *,
    tool: str,
    detection: dict[str, Any],
) -> dict[str, Any]:
    """Accumulate offload counters under metadata.context_refresh for UI."""
    next_meta = dict(metadata or {})
    refresh = dict(next_meta.get("context_refresh") or {})
    offloads = int(refresh.get("tool_offload_count") or 0)
    truncations = int(refresh.get("tool_truncate_count") or 0)
    if detection.get("offloaded"):
        offloads += 1
    if detection.get("truncated"):
        truncations += 1
    refresh["tool_offload_count"] = offloads
    refresh["tool_truncate_count"] = truncations
    recent = [item for item in (refresh.get("recent_offloads") or []) if isinstance(item, dict)]
    if detection.get("offloaded") or detection.get("truncated"):
        recent.append(
            {
                "tool": tool,
                "path": detection.get("path"),
                "offloaded": bool(detection.get("offloaded")),
                "truncated": bool(detection.get("truncated")),
            }
        )
        refresh["recent_offloads"] = recent[-12:]
    next_meta["context_refresh"] = refresh
    return next_meta
