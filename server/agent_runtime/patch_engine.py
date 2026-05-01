"""Safe text patch application for workflow action proposals."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from fastapi import HTTPException

logger = logging.getLogger(__name__)


MAX_PATCH_FILES = 3
MAX_FILE_CHARS = 80_000
MAX_DIFF_CHARS = 120_000


@dataclass
class PatchApplyResult:
    changed_files: list[str] = field(default_factory=list)
    summaries: list[dict[str, Any]] = field(default_factory=list)

    @property
    def stdout(self) -> str:
        return "\n".join(self.changed_files)


class SafePatchEngine:
    def __init__(self, root: Path):
        self.root = root.resolve()
        # In-memory backup: {resolved_path_str: original_content_or_None}
        self._backup: dict[str, str | None] = {}

    def apply_payload(self, payload: dict[str, Any]) -> PatchApplyResult:
        if payload.get("format") == "unified_diff" or payload.get("diff"):
            return self.apply_unified_diff(str(payload.get("diff") or ""))
        files = payload.get("files") or payload.get("file_changes") or []
        return self.apply_file_writes(files)

    def apply_file_writes(self, files: Any) -> PatchApplyResult:
        if not isinstance(files, list) or not files:
            raise HTTPException(status_code=400, detail="Patch action requires files/file_changes")
        if len(files) > MAX_PATCH_FILES:
            raise HTTPException(status_code=400, detail="Patch changes too many files")
        result = PatchApplyResult()
        for item in files:
            if not isinstance(item, dict):
                raise HTTPException(status_code=400, detail="Each patch file must be an object")
            relative_path = item.get("path") or item.get("file_path")
            content = item.get("content")
            if not relative_path or content is None:
                raise HTTPException(status_code=400, detail="Each patch file requires path and content")
            content_text = str(content)
            if len(content_text) > MAX_FILE_CHARS:
                raise HTTPException(status_code=400, detail="Patch file content is too large")
            target = self._safe_path(str(relative_path))
            # Backup original content before write
            self._backup_file(target)
            before = target.read_text(encoding="utf-8", errors="ignore") if target.exists() else ""
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content_text, encoding="utf-8")
            rel = target.relative_to(self.root).as_posix()
            result.changed_files.append(rel)
            result.summaries.append(
                {
                    "path": rel,
                    "before_chars": len(before),
                    "after_chars": len(content_text),
                    "mode": "write_file",
                }
            )
        return result

    def apply_unified_diff(self, diff: str) -> PatchApplyResult:
        if not diff.strip():
            raise HTTPException(status_code=400, detail="Unified diff payload is empty")
        if len(diff) > MAX_DIFF_CHARS:
            raise HTTPException(status_code=400, detail="Unified diff is too large")
        if "Binary files " in diff or "\nrename from " in diff or "\nrename to " in diff:
            raise HTTPException(status_code=400, detail="Binary or rename patches are not supported")
        file_patches = self._parse_unified_diff(diff)
        if len(file_patches) > MAX_PATCH_FILES:
            raise HTTPException(status_code=400, detail="Patch changes too many files")
        result = PatchApplyResult()
        for patch in file_patches:
            target = self._safe_path(patch["new_path"])
            if patch["new_path"] == "/dev/null":
                raise HTTPException(status_code=400, detail="Deleting files is not supported")
            # Backup before applying diff
            self._backup_file(target)
            if patch["old_path"] == "/dev/null":
                original_lines: list[str] = []
            else:
                if not target.exists():
                    raise HTTPException(status_code=400, detail=f"Patch target does not exist: {patch['new_path']}")
                original = target.read_text(encoding="utf-8", errors="ignore")
                original_lines = original.splitlines()
            new_lines = self._apply_hunks(original_lines, patch["hunks"], patch["new_path"])
            new_text = "\n".join(new_lines)
            if original_lines or diff.endswith("\n"):
                new_text += "\n"
            if len(new_text) > MAX_FILE_CHARS:
                raise HTTPException(status_code=400, detail="Patched file content is too large")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(new_text, encoding="utf-8")
            rel = target.relative_to(self.root).as_posix()
            result.changed_files.append(rel)
            result.summaries.append(
                {
                    "path": rel,
                    "before_lines": len(original_lines),
                    "after_lines": len(new_lines),
                    "mode": "unified_diff",
                }
            )
        return result

    def _parse_unified_diff(self, diff: str) -> list[dict[str, Any]]:
        lines = diff.splitlines()
        patches: list[dict[str, Any]] = []
        index = 0
        while index < len(lines):
            line = lines[index]
            if line.startswith("diff --git ") or line.startswith("index "):
                index += 1
                continue
            if not line.startswith("--- "):
                index += 1
                continue
            old_path = self._clean_diff_path(line[4:].strip())
            index += 1
            if index >= len(lines) or not lines[index].startswith("+++ "):
                raise HTTPException(status_code=400, detail="Malformed unified diff")
            new_path = self._clean_diff_path(lines[index][4:].strip())
            if new_path == "/dev/null":
                raise HTTPException(status_code=400, detail="Deleting files is not supported")
            index += 1
            hunks: list[dict[str, Any]] = []
            while index < len(lines) and not lines[index].startswith("--- "):
                if lines[index].startswith("@@ "):
                    header = lines[index]
                    index += 1
                    hunk_lines: list[str] = []
                    while index < len(lines) and not lines[index].startswith("@@ ") and not lines[index].startswith("--- "):
                        hunk_lines.append(lines[index])
                        index += 1
                    hunks.append({"header": header, "lines": hunk_lines})
                else:
                    index += 1
            patches.append({"old_path": old_path, "new_path": new_path, "hunks": hunks})
        if not patches:
            raise HTTPException(status_code=400, detail="No file patch found in unified diff")
        return patches

    def _apply_hunks(self, original: list[str], hunks: list[dict[str, Any]], path: str) -> list[str]:
        output: list[str] = []
        cursor = 0
        for hunk in hunks:
            old_start = self._old_start(hunk["header"])
            target_index = max(old_start - 1, 0)
            if target_index < cursor:
                raise HTTPException(status_code=400, detail=f"Overlapping patch hunk in {path}")
            output.extend(original[cursor:target_index])
            cursor = target_index
            for line in hunk["lines"]:
                if line == "\\ No newline at end of file":
                    continue
                marker = line[:1]
                text = line[1:]
                if marker == " ":
                    if cursor >= len(original) or original[cursor] != text:
                        raise HTTPException(status_code=400, detail=f"Patch conflict in {path}")
                    output.append(original[cursor])
                    cursor += 1
                elif marker == "-":
                    if cursor >= len(original) or original[cursor] != text:
                        raise HTTPException(status_code=400, detail=f"Patch conflict in {path}")
                    cursor += 1
                elif marker == "+":
                    output.append(text)
                else:
                    raise HTTPException(status_code=400, detail=f"Unsupported diff line in {path}")
        output.extend(original[cursor:])
        return output

    def _old_start(self, header: str) -> int:
        try:
            old_range = header.split(" ")[1]
            start = old_range.split(",")[0].lstrip("-")
            return int(start or "0")
        except Exception as exc:
            raise HTTPException(status_code=400, detail="Malformed hunk header") from exc

    def _clean_diff_path(self, value: str) -> str:
        path = value.split("\t")[0].strip()
        if path == "/dev/null":
            return path
        if path.startswith("a/") or path.startswith("b/"):
            path = path[2:]
        return path

    def _backup_file(self, target: Path) -> None:
        """Store original file content in memory for potential rollback."""
        key = str(target.resolve())
        if key in self._backup:
            return  # already backed up
        if target.exists() and target.is_file():
            try:
                self._backup[key] = target.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                self._backup[key] = None
        else:
            self._backup[key] = None  # file did not exist

    def rollback(self) -> list[str]:
        """Restore all backed-up files to their original content.

        Returns a list of paths that were restored.
        """
        restored: list[str] = []
        for path_str, original_content in self._backup.items():
            target = Path(path_str)
            try:
                if original_content is None:
                    # File did not exist before — remove it
                    if target.exists():
                        target.unlink()
                        restored.append(path_str)
                else:
                    target.write_text(original_content, encoding="utf-8")
                    restored.append(path_str)
            except Exception as exc:
                logger.warning("Rollback failed for %s: %s", path_str, exc)
        self._backup.clear()
        return restored

    def clear_backup(self) -> None:
        """Discard all backed-up content (e.g. after successful commit)."""
        self._backup.clear()

    @property
    def has_backup(self) -> bool:
        """Return True if there are any backed-up files."""
        return bool(self._backup)

    def _safe_path(self, raw_path: str) -> Path:
        if raw_path == "/dev/null":
            raise HTTPException(status_code=400, detail="Deleting files is not supported")
        target = Path(raw_path)
        if target.is_absolute():
            candidate = target.resolve()
        else:
            candidate = (self.root / target).resolve()
        if not (candidate == self.root or candidate.is_relative_to(self.root)):
            raise HTTPException(status_code=400, detail="Patch target must stay inside workflow project path")
        return candidate
