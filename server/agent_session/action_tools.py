from __future__ import annotations

import logging
import subprocess
from typing import Any

from fastapi import HTTPException

from .command_policy import command_allowed, normalize_command, resolve_command_cwd, summarize_failure
from .patch_engine import SafePatchEngine

from .tool_host import ToolHostProtocol
from .tool_types import ToolResult

logger = logging.getLogger(__name__)


class ActionToolsMixin(ToolHostProtocol):
    def _patch(self, args: dict[str, Any], context: dict[str, Any]) -> ToolResult:
        payload = args.get("payload") if isinstance(args.get("payload"), dict) else args
        files = list(payload.get("files") or payload.get("file_changes") or [])
        if not files and payload.get("file_path"):
            files = [{
                "path": str(payload["file_path"]),
                "content": str(payload.get("new_string") or ""),
                "old_string": str(payload.get("old_string") or ""),
                "create": bool(payload.get("create") or payload.get("new_file")),
                "patch_mode": "string_replace",
            }]
        return ToolResult("completed", "已生成补丁建议", self._normalize_tool_payload({"payload": payload, "diff": payload.get("diff"), "files": files}))

    def _command(self, args: dict[str, Any], context: dict[str, Any]) -> ToolResult:
        payload = args.get("payload") if isinstance(args.get("payload"), dict) else args
        command = payload.get("command")
        if isinstance(command, str):
            return ToolResult("blocked", "命令被阻断", self._normalize_tool_payload({"command": command}), "command must be argv array")
        try:
            argv = normalize_command(command)
        except HTTPException as exc:
            return ToolResult("blocked", "命令被阻断", self._normalize_tool_payload({"command": command}), str(exc.detail))
        if not command_allowed(argv):
            return ToolResult("blocked", "命令不在白名单内", self._normalize_tool_payload({"command": argv}), "command is not allowlisted")
        root = self._root(context)
        command_root = resolve_command_cwd(root, argv)
        completed = subprocess.run(argv, cwd=str(command_root), text=True, capture_output=True, timeout=int(payload.get("timeout_seconds") or 120), shell=False)
        failure = summarize_failure(completed.stdout, completed.stderr) if completed.returncode else ""
        return ToolResult(
            "completed" if completed.returncode == 0 else "failed",
            "命令执行完成" if completed.returncode == 0 else "命令执行失败",
            self._normalize_tool_payload({"command": argv, "cwd": str(command_root), "stdout": completed.stdout, "stderr": completed.stderr, "exit_code": completed.returncode, "failure_summary": failure}),
            failure or None,
        )

    def _read_execution(self, args: dict[str, Any], context: dict[str, Any]) -> ToolResult:
        session = context.get("session") or {}
        session_id = str(session.get("id") or "")
        if not session_id or self.repository is None:
            return ToolResult("completed", "执行结果已在会话 parts 中记录", {})
        parts = self.repository.list_parts(session_id)
        latest_command = next((part for part in reversed(parts) if part.get("type") == "command"), None)
        latest_diff = next((part for part in reversed(parts) if part.get("type") == "diff"), None)
        latest_summary = next((part for part in reversed(parts) if part.get("type") == "summary"), None)
        latest_error = next((part for part in reversed(parts) if part.get("status") in {"failed", "blocked"}), None)
        payload = self._normalize_tool_payload(
            {
                "latest_command": self._part_snapshot(latest_command),
                "latest_diff": self._part_snapshot(latest_diff),
                "latest_summary": self._part_snapshot(latest_summary),
                "latest_error": self._part_snapshot(latest_error),
            }
        )
        command_failure = ((latest_command or {}).get("payload") or {}).get("failure_summary")
        if command_failure:
            payload["failure_summary"] = command_failure
            payload["next_action"] = command_failure
        return ToolResult("completed", "已读取最近执行结果", payload)

    def apply_patch_payload_with_decisions(self, payload: dict[str, Any], context: dict[str, Any], hunk_decisions: dict[str, str]) -> "ToolResult":
        """Like apply_patch_payload but filters hunks based on hunk_decisions mapping."""
        diff = str(payload.get("diff") or "")
        if not diff or not hunk_decisions:
            return self.apply_patch_payload(payload, context)
        root = self._root(context)
        rejected_keys = {k for k, v in hunk_decisions.items() if v == "rejected"}
        try:
            result = SafePatchEngine(root).apply_partial_diff(diff, rejected_keys)
            self._refresh_context_index(root, result.changed_files)
            return ToolResult(
                "completed",
                result.stdout,
                self._normalize_tool_payload({"changed_files": result.changed_files, "applied_hunks": len(result.summaries), "patch_summaries": result.summaries}),
            )
        except Exception as exc:
            return ToolResult("failed", "部分补丁执行失败", self._normalize_tool_payload({}), str(exc))
    def apply_patch_payload(self, payload: dict[str, Any], context: dict[str, Any]) -> ToolResult:
        root = self._root(context)
        try:
            result = SafePatchEngine(root).apply_payload(payload)
            self._refresh_context_index(root, result.changed_files)
            return ToolResult(
                "completed",
                result.stdout,
                self._normalize_tool_payload({"changed_files": result.changed_files, "applied_hunks": len(result.summaries), "patch_summaries": result.summaries}),
            )
        except Exception as exc:
            return ToolResult("failed", "补丁执行失败", self._normalize_tool_payload({}), str(exc))

    def _refresh_context_index(self, root: Any, changed_files: list[str]) -> None:
        try:
            from context.service import get_context_service
            get_context_service().refresh_changed_files(str(root), changed_files)
        except Exception:
            logger.debug("context index refresh after patch failed", exc_info=True)

    def _part_snapshot(self, part: dict[str, Any] | None) -> dict[str, Any] | None:
        if not part:
            return None
        payload = part.get("payload") if isinstance(part.get("payload"), dict) else {}
        return {
            "id": part.get("id"),
            "type": part.get("type"),
            "status": part.get("status"),
            "title": part.get("title"),
            "content": part.get("content"),
            "command": payload.get("command"),
            "changed_files": payload.get("changed_files"),
            "failure_summary": payload.get("failure_summary"),
            "server_url": payload.get("server_url"),
        }
