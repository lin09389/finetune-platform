from __future__ import annotations

from pathlib import Path
from typing import Any

from .tool_host import ToolHostProtocol
from .tool_types import ToolResult


class LogToolsMixin(ToolHostProtocol):
    def _read_logs(self, args: dict[str, Any], context: dict[str, Any]) -> ToolResult:
        root = self._root(context)
        limit = int(args.get("limit") or 12_000)
        candidates: list[Path] = []
        raw_path = str(args.get("path") or "").strip()
        if raw_path:
            candidates.append(self._safe_path(root, raw_path))
        else:
            for base in (root / "logs", root / "tmp"):
                if base.exists():
                    candidates.extend(path for path in base.rglob("*.log") if path.is_file())
            candidates.extend(path for path in root.glob("*.log") if path.is_file())
        entries: list[dict[str, Any]] = []
        for path in sorted(set(candidates), key=lambda item: item.stat().st_mtime if item.exists() else 0, reverse=True)[:5]:
            if not path.exists() or not path.is_file():
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            tail = text[-limit:]
            entries.append({"path": path.relative_to(root).as_posix(), "content": tail, "truncated": len(text) > len(tail)})
        return ToolResult(
            "completed" if entries else "failed",
            f"读取 {len(entries)} 个日志文件" if entries else "未找到日志文件",
            {"logs": entries, "touched_paths": [item["path"] for item in entries]},
            None if entries else "log file not found",
        )
