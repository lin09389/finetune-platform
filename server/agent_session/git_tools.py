from __future__ import annotations

from pathlib import Path
from typing import Any

from .command_policy import run_git

from .tool_host import ToolHostProtocol
from .tool_types import ToolResult


class GitToolsMixin(ToolHostProtocol):
    def _git_status(self, args: dict[str, Any], context: dict[str, Any]) -> ToolResult:
        root = self._root(context)
        result = run_git(["status", "--short"], root)
        files = [line[3:].strip() for line in result["stdout"].splitlines() if len(line) > 3]
        return ToolResult(
            result["status"],
            f"发现 {len(files)} 个变更文件" if result["status"] == "completed" else "读取 Git 状态失败",
            {**result, "files": files},
            result["stderr"] if result["status"] == "failed" else None,
        )

    def _git_diff(self, args: dict[str, Any], context: dict[str, Any]) -> ToolResult:
        root = self._root(context)
        raw_path = str(args.get("path") or "").strip()
        if raw_path:
            target = self._safe_path(root, raw_path)
            rel = target.relative_to(root).as_posix()
            result = run_git(["diff", "--", rel], root)
        else:
            result = run_git(["diff", "--"], root)
        stdout = result["stdout"][:30_000]
        return ToolResult(
            result["status"],
            "已读取 Git diff" if result["status"] == "completed" else "读取 Git diff 失败",
            {**result, "stdout": stdout, "truncated": len(result["stdout"]) > len(stdout)},
            result["stderr"] if result["status"] == "failed" else None,
        )

    def _list_changed_files(self, args: dict[str, Any], context: dict[str, Any]) -> ToolResult:
        status = self._git_status(args, context)
        return ToolResult(status.status, status.summary, {"files": status.payload.get("files") or [], **status.payload}, status.error)
