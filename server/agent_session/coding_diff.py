"""Bounded, snapshot-based review payloads for Coding Agent writes.

This module deliberately has no repository or runtime dependency.  The
trajectory middleware owns the write boundary and persists the payload only
after its post-write static validation has succeeded.
"""

from __future__ import annotations

import difflib
from pathlib import PurePosixPath, PureWindowsPath
from typing import Any

CODING_DIFF_CONTRACT_VERSION = 1
MAX_INLINE_DIFF_BYTES = 64 * 1024
MAX_INLINE_DIFF_LINES = 1_000
MAX_DIFF_SOURCE_BYTES = 512 * 1024


def workspace_relative_path(value: str) -> str:
    """Return a safe workspace-relative POSIX path without leaking local paths."""
    raw = str(value or "").strip().replace("\\", "/")
    if raw.startswith("/workspace/"):
        raw = raw.removeprefix("/workspace/")
    elif raw == "/workspace":
        raw = ""
    if not raw or raw.startswith("/") or PureWindowsPath(raw).drive:
        raise ValueError("Diff paths must be workspace-relative")

    parts = PurePosixPath(raw).parts
    if any(part in {"", ".", "..", "/"} for part in parts):
        raise ValueError("Diff paths must not contain traversal segments")
    return "/".join(parts)


def build_coding_diff_payload(
    *,
    path: str,
    before_existed: bool,
    before_content: bytes,
    after_existed: bool,
    after_content: bytes,
    write_sequence: int,
) -> dict[str, Any]:
    """Build the versioned, bounded review payload for one successful write."""
    relative_path = workspace_relative_path(path)
    if int(write_sequence) <= 0:
        raise ValueError("write_sequence must be positive")

    change_type = _change_type(before_existed, after_existed)
    binary = _is_binary(before_content) or _is_binary(after_content)
    additions = 0
    deletions = 0
    diff = ""
    truncated = False

    if not binary:
        before_text, after_text = _decode_text(before_content), _decode_text(after_content)
        if before_text is None or after_text is None:
            binary = True
        elif len(before_content) > MAX_DIFF_SOURCE_BYTES or len(after_content) > MAX_DIFF_SOURCE_BYTES:
            # Keep both the persisted payload and the computation bounded.  The
            # resulting record still proves review coverage, but intentionally
            # does not pretend to offer an inline patch for a huge file.
            truncated = True
        else:
            # ``unified_diff(..., lineterm="")`` expects line values without
            # terminators.  Keeping them would make joining the emitted hunks
            # double-count physical lines and violate the payload line bound.
            before_lines = before_text.splitlines()
            after_lines = after_text.splitlines()
            additions, deletions = _line_changes(before_lines, after_lines)
            diff, truncated = _bounded_unified_diff(
                before_lines,
                after_lines,
                relative_path=relative_path,
                added=change_type == "added",
                deleted=change_type == "deleted",
            )

    return {
        "contract_version": CODING_DIFF_CONTRACT_VERSION,
        "path": relative_path,
        # Retained for existing timeline consumers while the review card uses
        # the single-file `path` field above.
        "changed_files": [relative_path],
        "change_type": change_type,
        "diff": diff,
        "additions": additions,
        "deletions": deletions,
        "binary": binary,
        "truncated": truncated,
        "write_sequence": int(write_sequence),
        "review_status": "ready",
    }


def _change_type(before_existed: bool, after_existed: bool) -> str:
    if not before_existed and after_existed:
        return "added"
    if before_existed and not after_existed:
        return "deleted"
    return "modified"


def _is_binary(content: bytes) -> bool:
    return b"\x00" in content


def _decode_text(content: bytes) -> str | None:
    try:
        return content.decode("utf-8")
    except UnicodeDecodeError:
        return None


def _line_changes(before_lines: list[str], after_lines: list[str]) -> tuple[int, int]:
    additions = deletions = 0
    matcher = difflib.SequenceMatcher(a=before_lines, b=after_lines, autojunk=False)
    for tag, old_start, old_end, new_start, new_end in matcher.get_opcodes():
        if tag in {"replace", "delete"}:
            deletions += old_end - old_start
        if tag in {"replace", "insert"}:
            additions += new_end - new_start
    return additions, deletions


def _bounded_unified_diff(
    before_lines: list[str],
    after_lines: list[str],
    *,
    relative_path: str,
    added: bool,
    deleted: bool,
) -> tuple[str, bool]:
    from_file = "/dev/null" if added else f"a/{relative_path}"
    to_file = "/dev/null" if deleted else f"b/{relative_path}"
    lines: list[str] = []
    encoded_bytes = 0
    truncated = False
    for line in difflib.unified_diff(before_lines, after_lines, fromfile=from_file, tofile=to_file, lineterm=""):
        encoded = line.encode("utf-8")
        if len(lines) >= MAX_INLINE_DIFF_LINES or encoded_bytes + len(encoded) + (1 if lines else 0) > MAX_INLINE_DIFF_BYTES:
            truncated = True
            break
        lines.append(line)
        encoded_bytes += len(encoded) + (1 if len(lines) > 1 else 0)
    return "\n".join(lines), truncated


__all__ = [
    "CODING_DIFF_CONTRACT_VERSION",
    "MAX_DIFF_SOURCE_BYTES",
    "MAX_INLINE_DIFF_BYTES",
    "MAX_INLINE_DIFF_LINES",
    "build_coding_diff_payload",
    "workspace_relative_path",
]
