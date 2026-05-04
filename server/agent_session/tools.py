from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from fastapi import HTTPException

from agent_runtime.command_policy import command_allowed, normalize_command, summarize_failure
from agent_runtime.patch_engine import SafePatchEngine
from core.config import settings


@dataclass
class ToolResult:
    status: str
    summary: str
    payload: dict[str, Any]
    error: str | None = None


@dataclass
class ToolDefinition:
    name: str
    description: str
    permission: str
    input_schema: dict[str, Any]
    execute: Callable[[dict[str, Any], dict[str, Any]], ToolResult]


class AgentToolRegistry:
    def __init__(self):
        self._tools: dict[str, ToolDefinition] = {}
        self.register_defaults()

    def register(self, tool: ToolDefinition) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> ToolDefinition | None:
        return self._tools.get(name)

    def list(self) -> list[ToolDefinition]:
        return list(self._tools.values())

    def register_defaults(self) -> None:
        self.register(ToolDefinition("read", "读取文件", "read", {"path": "string"}, self._read))
        self.register(ToolDefinition("search", "搜索代码", "read", {"query": "string"}, self._search))
        self.register(ToolDefinition("glob", "列出文件", "read", {"path_glob": "string"}, self._glob))
        self.register(ToolDefinition("collect_context", "批量收集上下文", "read", {}, self._collect_context))
        self.register(ToolDefinition("patch", "提出或应用补丁", "patch", {}, self._patch))
        self.register(ToolDefinition("bash_command", "运行白名单命令", "command", {}, self._command))
        self.register(ToolDefinition("read_execution", "读取执行结果", "read", {}, self._read_execution))
        self.register(ToolDefinition("finalize", "完成总结", "read", {}, self._finalize))

    def _root(self, context: dict[str, Any]) -> Path:
        raw = context.get("project_path") or self._workspace_root()
        root = Path(raw).resolve()
        if not any(root == allowed or root.is_relative_to(allowed) for allowed in self._workspace_roots()):
            raise ValueError("project_path must stay inside workspace")
        return root

    def _safe_path(self, root: Path, raw_path: str) -> Path:
        target = Path(raw_path)
        if not target.is_absolute():
            target = root / target
        target = target.resolve()
        if not (target == root or target.is_relative_to(root)):
            raise ValueError("path must stay inside project path")
        return target

    def _workspace_root(self) -> Path:
        base_dir = settings.base_dir.resolve()
        return base_dir.parent if base_dir.name == "server" else base_dir

    def _workspace_roots(self) -> set[Path]:
        return {Path.cwd().resolve(), settings.base_dir.resolve(), self._workspace_root()}

    def _read(self, args: dict[str, Any], context: dict[str, Any]) -> ToolResult:
        root = self._root(context)
        raw_path = str(args.get("path") or args.get("file_path") or "").strip()
        if not raw_path:
            return ToolResult("failed", "缺少文件路径", {}, "path is required")
        target = self._safe_path(root, raw_path)
        if not target.exists() or not target.is_file():
            return ToolResult("failed", "文件不存在", {"path": raw_path}, "file not found")
        content = target.read_text(encoding="utf-8", errors="ignore")
        truncated = len(content) > 20_000
        if truncated:
            content = content[:20_000]
        rel = target.relative_to(root).as_posix()
        return ToolResult("completed", f"已读取 {rel}", {"path": rel, "content": content, "truncated": truncated})

    def _search(self, args: dict[str, Any], context: dict[str, Any]) -> ToolResult:
        root = self._root(context)
        query = str(args.get("query") or "").strip()
        if not query:
            return ToolResult("failed", "缺少搜索关键词", {}, "query is required")
        path_glob = str(args.get("path_glob") or "**/*")
        limit = int(args.get("limit") or 20)
        matches: list[dict[str, Any]] = []
        lowered = query.lower()
        for path in root.rglob("*"):
            if not path.is_file() or any(part in {".git", "node_modules", "dist", "build", ".venv", "__pycache__"} for part in path.parts):
                continue
            rel = path.relative_to(root).as_posix()
            if path_glob and not path.match(path_glob):
                continue
            try:
                lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
            except Exception:
                continue
            for line_no, line in enumerate(lines, 1):
                if lowered in line.lower():
                    matches.append({"path": rel, "line": line_no, "preview": line.strip()[:300]})
                    if len(matches) >= limit:
                        return ToolResult("completed", f"找到 {len(matches)} 条匹配", {"query": query, "matches": matches, "touched_paths": [m["path"] for m in matches]})
        return ToolResult("completed", f"找到 {len(matches)} 条匹配", {"query": query, "matches": matches, "touched_paths": [m["path"] for m in matches]})

    def _glob(self, args: dict[str, Any], context: dict[str, Any]) -> ToolResult:
        root = self._root(context)
        pattern = str(args.get("path_glob") or "**/*")
        files = [path.relative_to(root).as_posix() for path in root.glob(pattern) if path.is_file()][:200]
        return ToolResult("completed", f"列出 {len(files)} 个文件", {"files": files})

    def _collect_context(self, args: dict[str, Any], context: dict[str, Any]) -> ToolResult:
        markers = {
            "package_json": (self._root(context) / "package.json").exists(),
            "client_package_json": (self._root(context) / "client" / "package.json").exists(),
            "server_dir": (self._root(context) / "server").exists(),
            "client_dir": (self._root(context) / "client").exists(),
        }
        matches: list[dict[str, Any]] = []
        files: list[dict[str, Any]] = []
        touched: list[str] = []
        for query in args.get("search") or args.get("queries") or []:
            result = self._search({"query": query, "limit": 10, "path_glob": args.get("path_glob") or "**/*"}, context)
            matches.extend(result.payload.get("matches") or [])
        for raw_path in args.get("read") or args.get("files") or []:
            result = self._read({"path": raw_path}, context)
            if result.status == "completed":
                files.append(result.payload)
                touched.append(result.payload["path"])
        touched.extend(match.get("path") for match in matches if match.get("path"))
        return ToolResult(
            "completed",
            f"已收集上下文：读取 {len(files)} 个文件，找到 {len(matches)} 条匹配",
            {"markers": markers, "matches": matches, "files": files, "touched_paths": list(dict.fromkeys(touched))},
        )

    def _patch(self, args: dict[str, Any], context: dict[str, Any]) -> ToolResult:
        payload = args.get("payload") if isinstance(args.get("payload"), dict) else args
        return ToolResult("completed", "已生成补丁建议", {"payload": payload, "diff": payload.get("diff"), "files": payload.get("files") or []})

    def _command(self, args: dict[str, Any], context: dict[str, Any]) -> ToolResult:
        payload = args.get("payload") if isinstance(args.get("payload"), dict) else args
        command = payload.get("command")
        if isinstance(command, str):
            return ToolResult("blocked", "命令被阻断", {"command": command}, "command must be argv array")
        try:
            argv = normalize_command(command)
        except HTTPException as exc:
            return ToolResult("blocked", "命令被阻断", {"command": command}, str(exc.detail))
        if not command_allowed(argv):
            return ToolResult("blocked", "命令不在白名单内", {"command": argv}, "command is not allowlisted")
        root = self._root(context)
        completed = subprocess.run(argv, cwd=str(root), text=True, capture_output=True, timeout=int(payload.get("timeout_seconds") or 120), shell=False)
        failure = summarize_failure(completed.stdout, completed.stderr) if completed.returncode else ""
        return ToolResult(
            "completed" if completed.returncode == 0 else "failed",
            "命令执行完成" if completed.returncode == 0 else "命令执行失败",
            {"command": argv, "stdout": completed.stdout, "stderr": completed.stderr, "exit_code": completed.returncode, "failure_summary": failure},
            failure or None,
        )

    def _read_execution(self, args: dict[str, Any], context: dict[str, Any]) -> ToolResult:
        return ToolResult("completed", "执行结果已在会话 parts 中记录", {})

    def _finalize(self, args: dict[str, Any], context: dict[str, Any]) -> ToolResult:
        content = str(args.get("summary") or args.get("content") or "任务已完成。")
        return ToolResult("completed", content, {"summary": content, **args})

    def apply_patch_payload(self, payload: dict[str, Any], context: dict[str, Any]) -> ToolResult:
        root = self._root(context)
        try:
            result = SafePatchEngine(root).apply_payload(payload)
            return ToolResult("completed", result.stdout, {"changed_files": result.changed_files, "applied_hunks": len(result.summaries), "patch_summaries": result.summaries})
        except Exception as exc:
            return ToolResult("failed", "补丁执行失败", {}, str(exc))


def parse_tool_request(raw: str) -> dict[str, Any] | None:
    text = raw.strip()
    if not text:
        return None
    if text.startswith("```"):
        import re

        match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
        if match:
            text = match.group(1)
    try:
        payload = json.loads(text)
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None
    tool = payload.get("tool") or payload.get("name") or payload.get("tool_name")
    if not tool:
        return None
    arguments = payload.get("arguments") or payload.get("args") or payload.get("parameters") or {}
    return {"tool": str(tool), "arguments": arguments if isinstance(arguments, dict) else {}}

