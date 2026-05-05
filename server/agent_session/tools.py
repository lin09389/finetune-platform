from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from fastapi import HTTPException

from agent_runtime.command_policy import command_allowed, normalize_command, summarize_failure
from agent_runtime.patch_engine import SafePatchEngine
from core.config import settings
from .parser import parse_tool_request


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
        self.register(ToolDefinition("detect_project_commands", "识别验证命令", "read", {}, self._detect_project_commands))
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
        scanned = 0
        for path in self._candidate_files(root):
            scanned += 1
            if scanned > 3000:
                break
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
        root = self._root(context)
        goal = str(args.get("goal") or (context.get("session") or {}).get("metadata", {}).get("current_goal") or (context.get("session") or {}).get("title") or "")
        markers = self._project_markers(root)
        matches: list[dict[str, Any]] = []
        files: list[dict[str, Any]] = []
        touched: list[str] = []
        explicit_reads = list(args.get("read") or args.get("files") or [])
        explicit_queries = list(args.get("search") or args.get("queries") or [])
        inferred_reads, inferred_queries = self._infer_context_targets(root, goal)
        reads = list(dict.fromkeys([*explicit_reads, *inferred_reads]))
        queries = list(dict.fromkeys([*explicit_queries, *inferred_queries]))
        for query in queries[:8]:
            result = self._search({"query": query, "limit": 10, "path_glob": args.get("path_glob") or "**/*"}, context)
            matches.extend(result.payload.get("matches") or [])
        for raw_path in reads[:8]:
            result = self._read({"path": raw_path}, context)
            if result.status == "completed":
                files.append(result.payload)
                touched.append(result.payload["path"])
        touched.extend(match.get("path") for match in matches if match.get("path"))
        commands = self._detect_project_commands({}, context).payload.get("commands") or []
        return ToolResult(
            "completed",
            f"已收集上下文：读取 {len(files)} 个文件，找到 {len(matches)} 条匹配，识别 {len(commands)} 个验证命令",
            {
                "goal": goal,
                "markers": markers,
                "matches": matches,
                "files": files,
                "commands": commands,
                "inferred_queries": queries,
                "touched_paths": list(dict.fromkeys(touched)),
            },
        )

    def _detect_project_commands(self, args: dict[str, Any], context: dict[str, Any]) -> ToolResult:
        root = self._root(context)
        commands: list[dict[str, Any]] = []
        client_pkg = root / "client" / "package.json"
        root_pkg = root / "package.json"
        for pkg, cwd_hint in ((client_pkg, "client"), (root_pkg, ".")):
            if not pkg.exists():
                continue
            try:
                data = json.loads(pkg.read_text(encoding="utf-8", errors="ignore"))
            except Exception:
                continue
            scripts = data.get("scripts") if isinstance(data, dict) else {}
            if not isinstance(scripts, dict):
                continue
            if "typecheck" in scripts:
                commands.append({"kind": "typecheck", "command": ["npm", "run", "typecheck"], "cwd_hint": cwd_hint, "source": pkg.relative_to(root).as_posix()})
            if "test" in scripts:
                commands.append({"kind": "test", "command": ["npm", "test"], "cwd_hint": cwd_hint, "source": pkg.relative_to(root).as_posix()})
        if (root / "pytest.ini").exists() or (root / "server" / "pytest.ini").exists() or (root / "server" / "tests").exists():
            commands.append({"kind": "python_tests", "command": ["python", "-m", "pytest"], "cwd_hint": ".", "source": "pytest"})
        commands.append({"kind": "python_compile", "command": ["python", "-m", "py_compile"], "cwd_hint": ".", "source": "python"})
        unique: list[dict[str, Any]] = []
        seen: set[tuple[str, ...]] = set()
        for item in commands:
            key = tuple(item["command"])
            if key not in seen:
                seen.add(key)
                unique.append(item)
        return ToolResult("completed", f"识别 {len(unique)} 个可用验证命令", {"commands": unique})

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

    def _project_markers(self, root: Path) -> dict[str, bool]:
        return {
            "package_json": (root / "package.json").exists(),
            "client_package_json": (root / "client" / "package.json").exists(),
            "server_dir": (root / "server").exists(),
            "client_dir": (root / "client").exists(),
            "tests_dir": (root / "server" / "tests").exists() or (root / "client" / "src" / "test").exists(),
        }

    def _infer_context_targets(self, root: Path, goal: str) -> tuple[list[str], list[str]]:
        reads: list[str] = []
        queries: list[str] = []
        for token in re.findall(r"[\w./\\-]+\.(?:py|ts|tsx|css|md|json)", goal):
            reads.append(token.replace("\\", "/"))
        for token in re.findall(r"`([^`]+)`", goal):
            if "/" in token or "." in token:
                reads.append(token.replace("\\", "/"))
            elif len(token) >= 3:
                queries.append(token)
        identifiers = re.findall(r"\b[A-Z][A-Za-z0-9_]{2,}\b|\b[a-zA-Z_][a-zA-Z0-9_]{3,}\b", goal)
        queries.extend(identifiers[:6])
        keyword_map = {
            "聊天": ["ChatNew", "ChatInput", "ChatMessage"],
            "对话": ["ChatNew", "ChatInput", "ChatMessage"],
            "Agent": ["AgentPartMessage", "AgentRunCard", "AgentSession"],
            "卡片": ["AgentRunCard", "AgentPartMessage"],
            "样式": ["module.css", "styles"],
            "typecheck": ["typecheck", "tsconfig"],
            "测试": ["pytest", "vitest", "test"],
            "前端": ["client/src", "React"],
            "后端": ["server", "FastAPI"],
        }
        for keyword, mapped in keyword_map.items():
            if keyword.lower() in goal.lower():
                queries.extend(mapped)
        for candidate in self._likely_files(root, queries):
            reads.append(candidate)
        return list(dict.fromkeys(reads)), list(dict.fromkeys(query for query in queries if query))

    def _likely_files(self, root: Path, queries: list[str]) -> list[str]:
        if not queries:
            return []
        lowered_queries = [query.lower() for query in queries if len(query) >= 3]
        if not lowered_queries:
            return []
        candidates: list[str] = []
        scanned = 0
        for path in self._candidate_files(root):
            scanned += 1
            if scanned > 2500:
                break
            if len(candidates) >= 6:
                break
            rel = path.relative_to(root).as_posix()
            haystack = rel.lower()
            if any(query.lower().replace("/", "") in haystack.replace("/", "") or query.lower() in haystack for query in lowered_queries):
                candidates.append(rel)
        return candidates

    def _candidate_files(self, root: Path):
        preferred = [
            root / "client" / "src",
            root / "server" / "agent_session",
            root / "server" / "chat_agent",
            root / "server" / "api",
            root / "server" / "tests",
            root / "docs",
            root / "tmp",
        ]
        ignored = {".git", "node_modules", "dist", "build", ".venv", "__pycache__"}
        seen: set[Path] = set()
        for base in preferred:
            if not base.exists():
                continue
            for path in base.rglob("*"):
                if path in seen or not path.is_file() or any(part in ignored for part in path.parts):
                    continue
                seen.add(path)
                yield path
        for path in root.glob("*"):
            if path in seen or not path.is_file() or any(part in ignored for part in path.parts):
                continue
            seen.add(path)
            yield path
