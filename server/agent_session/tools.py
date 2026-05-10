from __future__ import annotations

import json
import re
import shutil
import subprocess
import time
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from fastapi import HTTPException

from agent_runtime.command_policy import command_allowed, normalize_command, resolve_command_cwd, run_git, summarize_failure
from agent_runtime.patch_engine import SafePatchEngine
from core.config import settings
from workspace.local_paths import get_allowed_workspace_roots
from .parser import parse_tool_request


DEV_SERVER_PROCESSES: dict[str, dict[str, Any]] = {}
AST_GREP_SYMBOL_RE = re.compile(r"^[A-Za-z_$][A-Za-z0-9_$]*$")
LOCAL_HTTP_HOSTS = {"localhost", "127.0.0.1", "::1"}


class LocalPageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._title_active = False
        self._heading_tag: str | None = None
        self.title = ""
        self.headings: list[dict[str, str]] = []
        self.links: list[str] = []
        self.text_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        lowered = tag.lower()
        if lowered == "title":
            self._title_active = True
        if lowered in {"h1", "h2", "h3"}:
            self._heading_tag = lowered
        if lowered == "a":
            href = dict(attrs).get("href")
            if href and len(self.links) < 12:
                self.links.append(href)

    def handle_endtag(self, tag: str) -> None:
        lowered = tag.lower()
        if lowered == "title":
            self._title_active = False
        if lowered == self._heading_tag:
            self._heading_tag = None

    def handle_data(self, data: str) -> None:
        text = " ".join(data.split())
        if not text:
            return
        if self._title_active and not self.title:
            self.title = text[:200]
        if self._heading_tag and len(self.headings) < 8:
            self.headings.append({"tag": self._heading_tag, "text": text[:200]})
        if len(" ".join(self.text_parts)) < 4000:
            self.text_parts.append(text[:400])


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
    def __init__(self, repository: Any | None = None):
        self._tools: dict[str, ToolDefinition] = {}
        self.repository = repository
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
        self.register(ToolDefinition("find_symbol", "查找符号定义", "read", {"symbol": "string"}, self._find_symbol))
        self.register(ToolDefinition("find_references", "查找符号引用", "read", {"symbol": "string"}, self._find_references))
        self.register(ToolDefinition("glob", "列出文件", "read", {"path_glob": "string"}, self._glob))
        self.register(ToolDefinition("collect_context", "批量收集上下文", "read", {}, self._collect_context))
        self.register(ToolDefinition("detect_project_commands", "识别验证命令", "read", {}, self._detect_project_commands))
        self.register(ToolDefinition("git_status", "读取 Git 状态", "read", {}, self._git_status))
        self.register(ToolDefinition("git_diff", "读取 Git 差异", "read", {}, self._git_diff))
        self.register(ToolDefinition("list_changed_files", "列出变更文件", "read", {}, self._list_changed_files))
        self.register(ToolDefinition("read_logs", "读取日志", "read", {}, self._read_logs))
        self.register(ToolDefinition("http_probe", "探测本地 HTTP 服务", "read", {"url": "string"}, self._http_probe))
        self.register(ToolDefinition("probe_json_endpoint", "探测本地 JSON 接口", "read", {"url": "string"}, self._probe_json_endpoint))
        self.register(ToolDefinition("read_local_page", "读取本地页面摘要", "read", {"url": "string"}, self._read_local_page))
        self.register(ToolDefinition("browser_validate_page", "使用浏览器验证本地页面", "read", {"url": "string"}, self._browser_validate_page))
        self.register(ToolDefinition("capture_network_errors", "捕获本地页面网络错误", "read", {"url": "string"}, self._capture_network_errors))
        self.register(ToolDefinition("browser_click", "使用浏览器点击本地页面元素", "read", {"url": "string", "selector": "string"}, self._browser_click))
        self.register(ToolDefinition("browser_fill", "使用浏览器填写本地页面表单", "read", {"url": "string", "selector": "string", "value": "string"}, self._browser_fill))
        self.register(ToolDefinition("browser_wait_for", "等待本地页面元素或文本出现", "read", {"url": "string"}, self._browser_wait_for))
        self.register(ToolDefinition("run_targeted_test", "精准运行测试目标", "command", {}, self._run_targeted_test))
        self.register(ToolDefinition("summarize_test_results", "汇总最近测试结果", "read", {}, self._summarize_test_results))
        self.register(ToolDefinition("collect_test_failures", "汇总最近测试失败信息", "read", {}, self._collect_test_failures))
        self.register(ToolDefinition("run_dev_server", "启动开发服务器", "command", {}, self._run_dev_server))
        self.register(ToolDefinition("stop_dev_server", "停止开发服务器", "command", {}, self._stop_dev_server))
        self.register(ToolDefinition("get_server_status", "查看开发服务器状态", "read", {}, self._get_server_status))
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
        return get_allowed_workspace_roots({Path.cwd().resolve(), settings.base_dir.resolve(), self._workspace_root()})

    def _read(self, args: dict[str, Any], context: dict[str, Any]) -> ToolResult:
        root = self._root(context)
        raw_paths = args.get("paths")
        if isinstance(raw_paths, list):
            files: list[dict[str, Any]] = []
            touched: list[str] = []
            failures: list[dict[str, str]] = []
            for raw_item in raw_paths[:8]:
                result = self._read({"path": raw_item}, context)
                if result.status == "completed":
                    files.append(result.payload)
                    touched.append(str(result.payload.get("path") or ""))
                else:
                    failures.append({"path": str(raw_item), "error": result.error or result.summary})
            status = "completed" if files else "failed"
            summary = f"已读取 {len(files)} 个文件" if files else "批量读取失败"
            return ToolResult(
                status,
                summary,
                {"files": files, "touched_paths": [path for path in touched if path], "failures": failures},
                None if files else "no files read",
            )

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

    def _find_symbol(self, args: dict[str, Any], context: dict[str, Any]) -> ToolResult:
        root = self._root(context)
        symbol = str(args.get("symbol") or args.get("name") or args.get("query") or "").strip()
        if not symbol:
            return ToolResult("failed", "缺少符号名", {}, "symbol is required")
        requested_kind = str(args.get("kind") or "").strip().lower()
        limit = int(args.get("limit") or 20)
        scope_paths = self._tool_scope_paths(root, args)
        ast_result = self._find_symbol_with_ast_grep(root, symbol, requested_kind, limit, scope_paths=scope_paths)
        if ast_result is not None:
            return ast_result
        return self._find_symbol_builtin(root, symbol, requested_kind, limit, scope_paths=scope_paths)

    def _find_references(self, args: dict[str, Any], context: dict[str, Any]) -> ToolResult:
        root = self._root(context)
        symbol = str(args.get("symbol") or args.get("name") or args.get("query") or "").strip()
        if not symbol:
            return ToolResult("failed", "缺少符号名", {}, "symbol is required")
        include_definitions = bool(args.get("include_definitions"))
        limit = int(args.get("limit") or 50)
        scope_paths = self._tool_scope_paths(root, args)
        ast_result = self._find_references_with_ast_grep(root, symbol, include_definitions, limit, scope_paths=scope_paths)
        if ast_result is not None:
            return ast_result
        return self._find_references_builtin(root, symbol, include_definitions, limit, scope_paths=scope_paths)

    def _find_symbol_builtin(self, root: Path, symbol: str, requested_kind: str, limit: int, scope_paths: list[str] | None = None) -> ToolResult:
        matches: list[dict[str, Any]] = []
        patterns = self._symbol_definition_patterns(symbol)
        for path in self._candidate_files(root):
            if not self._is_searchable_code_file(path):
                continue
            rel = path.relative_to(root).as_posix()
            if scope_paths and not self._path_in_scope(rel, scope_paths):
                continue
            try:
                lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
            except Exception:
                continue
            for line_no, line in enumerate(lines, 1):
                definition = self._match_symbol_definition(line, symbol, patterns)
                if not definition:
                    continue
                if requested_kind and definition["kind"] != requested_kind:
                    continue
                matches.append({
                    "path": rel,
                    "line": line_no,
                    "kind": definition["kind"],
                    "preview": line.strip()[:300],
                })
                if len(matches) >= limit:
                    return ToolResult(
                        "completed",
                        f"找到 {len(matches)} 个符号定义",
                        {"symbol": symbol, "matches": matches, "touched_paths": [item["path"] for item in matches], "engine": "builtin"},
                    )
        return ToolResult(
            "completed",
            f"找到 {len(matches)} 个符号定义",
            {"symbol": symbol, "matches": matches, "touched_paths": [item["path"] for item in matches], "engine": "builtin"},
        )

    def _find_references_builtin(self, root: Path, symbol: str, include_definitions: bool, limit: int, scope_paths: list[str] | None = None) -> ToolResult:
        ref_pattern = re.compile(rf"(?<![\w$]){re.escape(symbol)}(?![\w$])")
        definition_patterns = self._symbol_definition_patterns(symbol)
        matches: list[dict[str, Any]] = []
        for path in self._candidate_files(root):
            if not self._is_searchable_code_file(path):
                continue
            rel = path.relative_to(root).as_posix()
            if scope_paths and not self._path_in_scope(rel, scope_paths):
                continue
            try:
                lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
            except Exception:
                continue
            for line_no, line in enumerate(lines, 1):
                if not ref_pattern.search(line):
                    continue
                definition = self._match_symbol_definition(line, symbol, definition_patterns)
                if definition and not include_definitions:
                    continue
                matches.append({
                    "path": rel,
                    "line": line_no,
                    "is_definition": bool(definition),
                    "preview": line.strip()[:300],
                })
                if len(matches) >= limit:
                    return ToolResult(
                        "completed",
                        f"找到 {len(matches)} 个符号引用",
                        {"symbol": symbol, "matches": matches, "touched_paths": [item["path"] for item in matches], "engine": "builtin"},
                    )
        return ToolResult(
            "completed",
            f"找到 {len(matches)} 个符号引用",
            {"symbol": symbol, "matches": matches, "touched_paths": [item["path"] for item in matches], "engine": "builtin"},
        )

    def _find_symbol_with_ast_grep(self, root: Path, symbol: str, requested_kind: str, limit: int, scope_paths: list[str] | None = None) -> ToolResult | None:
        if not AST_GREP_SYMBOL_RE.match(symbol):
            return None
        collected: list[dict[str, Any]] = []
        try:
            for spec in self._ast_grep_symbol_specs(symbol, requested_kind):
                matches = self._run_ast_grep(
                    root=root,
                    pattern=spec["pattern"],
                    lang=spec["lang"],
                    globs=spec["globs"],
                    limit=max(limit - len(collected), 1),
                    scope_paths=scope_paths,
                )
                for match in matches:
                    item = {
                        "path": match["path"],
                        "line": match["line"],
                        "kind": self._ast_grep_match_kind(spec["kind"], match["preview"]),
                        "preview": match["preview"],
                    }
                    if item not in collected:
                        collected.append(item)
                    if len(collected) >= limit:
                        return ToolResult(
                            "completed",
                            f"找到 {len(collected)} 个符号定义",
                            {"symbol": symbol, "matches": collected, "touched_paths": [item["path"] for item in collected], "engine": "ast-grep"},
                        )
        except Exception:
            return None
        return ToolResult(
            "completed",
            f"找到 {len(collected)} 个符号定义",
            {"symbol": symbol, "matches": collected, "touched_paths": [item["path"] for item in collected], "engine": "ast-grep"},
        )

    def _find_references_with_ast_grep(self, root: Path, symbol: str, include_definitions: bool, limit: int, scope_paths: list[str] | None = None) -> ToolResult | None:
        if not AST_GREP_SYMBOL_RE.match(symbol):
            return None
        definitions = self._find_symbol_with_ast_grep(root, symbol, "", limit=200, scope_paths=scope_paths)
        definition_locations = {
            (item["path"], int(item["line"]))
            for item in (definitions.payload.get("matches") or [])
        } if definitions is not None else set()
        collected: list[dict[str, Any]] = []
        try:
            for spec in self._ast_grep_reference_specs(symbol):
                matches = self._run_ast_grep(
                    root=root,
                    pattern=spec["pattern"],
                    lang=spec["lang"],
                    globs=spec["globs"],
                    limit=max(limit * 2, 20),
                    scope_paths=scope_paths,
                )
                for match in matches:
                    key = (match["path"], match["line"])
                    is_definition = key in definition_locations
                    if is_definition and not include_definitions:
                        continue
                    item = {
                        "path": match["path"],
                        "line": match["line"],
                        "is_definition": is_definition,
                        "preview": match["preview"],
                    }
                    if item not in collected:
                        collected.append(item)
                    if len(collected) >= limit:
                        return ToolResult(
                            "completed",
                            f"找到 {len(collected)} 个符号引用",
                            {"symbol": symbol, "matches": collected, "touched_paths": [item["path"] for item in collected], "engine": "ast-grep"},
                        )
        except Exception:
            return None
        return ToolResult(
            "completed",
            f"找到 {len(collected)} 个符号引用",
            {"symbol": symbol, "matches": collected, "touched_paths": [item["path"] for item in collected], "engine": "ast-grep"},
        )

    def _collect_context(self, args: dict[str, Any], context: dict[str, Any]) -> ToolResult:
        root = self._root(context)
        goal = str(args.get("goal") or (context.get("session") or {}).get("metadata", {}).get("current_goal") or (context.get("session") or {}).get("title") or "")
        markers = self._project_markers(root)
        matches: list[dict[str, Any]] = []
        files: list[dict[str, Any]] = []
        touched: list[str] = []
        explicit_reads = list(args.get("read") or args.get("files") or [])
        explicit_queries = list(args.get("search") or args.get("queries") or [])
        explicit_symbols = list(args.get("symbols") or [])
        single_symbol = str(args.get("symbol") or "").strip()
        if single_symbol:
            explicit_symbols.append(single_symbol)
        should_infer_targets = not explicit_reads and not explicit_queries and not explicit_symbols
        inferred_reads, inferred_queries = self._infer_context_targets(root, goal) if should_infer_targets else ([], [])
        reads = list(dict.fromkeys([*explicit_reads, *inferred_reads]))
        queries = list(dict.fromkeys([*explicit_queries, *inferred_queries]))
        for query in queries[:8]:
            result = self._search({"query": query, "limit": 10, "path_glob": args.get("path_glob") or "**/*"}, context)
            matches.extend(result.payload.get("matches") or [])
        should_expand_symbols = bool(explicit_symbols) or bool(queries) or not explicit_reads
        symbols = self._infer_symbol_candidates(goal, queries, reads, explicit_symbols) if should_expand_symbols else []
        symbol_hits: list[dict[str, Any]] = []
        symbol_reads: list[str] = []
        symbol_scope_paths = list(
            dict.fromkeys(
                [
                    *reads,
                    *[str(item.get("path")) for item in matches if item.get("path")],
                ]
            )
        )
        for symbol in symbols[:4]:
            definition_result = self._find_symbol({"symbol": symbol, "limit": 4, "scope_paths": symbol_scope_paths}, context)
            reference_result = self._find_references({"symbol": symbol, "limit": 6, "scope_paths": symbol_scope_paths}, context)
            if not (definition_result.payload.get("matches") or []) and not (reference_result.payload.get("matches") or []):
                definition_result = self._find_symbol({"symbol": symbol, "limit": 4}, context)
                reference_result = self._find_references({"symbol": symbol, "limit": 6}, context)
            definitions = definition_result.payload.get("matches") or []
            references = reference_result.payload.get("matches") or []
            if not definitions and not references:
                continue
            engine = definition_result.payload.get("engine") or reference_result.payload.get("engine")
            symbol_hits.append(
                {
                    "symbol": symbol,
                    "engine": engine,
                    "definitions": definitions[:4],
                    "references": references[:6],
                }
            )
            for item in definitions[:2]:
                path = item.get("path")
                if path:
                    symbol_reads.append(str(path))
            touched.extend(item.get("path") for item in definitions if item.get("path"))
            touched.extend(item.get("path") for item in references if item.get("path"))
        reads = list(dict.fromkeys([*reads, *symbol_reads]))
        for raw_path in reads[:8]:
            result = self._read({"path": raw_path}, context)
            if result.status == "completed":
                files.append(result.payload)
                touched.append(result.payload["path"])
        touched.extend(match.get("path") for match in matches if match.get("path"))
        commands = self._detect_project_commands({}, context).payload.get("commands") or []
        return ToolResult(
            "completed",
            f"已收集上下文：读取 {len(files)} 个文件，找到 {len(matches)} 条匹配，命中 {len(symbol_hits)} 个符号，识别 {len(commands)} 个验证命令",
            {
                "goal": goal,
                "markers": markers,
                "matches": matches,
                "symbols": symbol_hits,
                "files": files,
                "commands": commands,
                "inferred_queries": queries,
                "inferred_symbols": symbols,
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
            if "build" in scripts:
                commands.append({"kind": "build", "command": ["npm", "run", "build"], "cwd_hint": cwd_hint, "source": pkg.relative_to(root).as_posix()})
            if "lint" in scripts:
                commands.append({"kind": "lint", "command": ["npm", "run", "lint"], "cwd_hint": cwd_hint, "source": pkg.relative_to(root).as_posix()})
            if any("vitest" in str(value).lower() for value in scripts.values()):
                commands.append({"kind": "vitest", "command": ["npx", "vitest", "run"], "cwd_hint": cwd_hint, "source": pkg.relative_to(root).as_posix()})
            if (pkg.parent / "tsconfig.json").exists():
                commands.append({"kind": "tsc", "command": ["tsc", "--noEmit"], "cwd_hint": cwd_hint, "source": pkg.relative_to(root).as_posix()})
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

    def _http_probe(self, args: dict[str, Any], context: dict[str, Any]) -> ToolResult:
        url = str(args.get("url") or args.get("server_url") or "").strip()
        if not url:
            return ToolResult("failed", "缺少页面地址", {}, "url is required")
        timeout_seconds = int(args.get("timeout_seconds") or 10)
        method = str(args.get("method") or "GET").strip().upper()
        try:
            response = self._fetch_local_url(url, timeout_seconds=timeout_seconds, method=method)
        except ValueError as exc:
            return ToolResult("blocked", "页面探测被阻断", {"url": url}, str(exc))
        status = "completed" if response["ok"] else "failed"
        summary = f"页面探测成功：{response['status_code']}" if response["ok"] else f"页面探测失败：{response['status_code']}"
        return ToolResult(
            status,
            summary,
            {
                "url": response["url"],
                "final_url": response["final_url"],
                "method": method,
                "status_code": response["status_code"],
                "ok": response["ok"],
                "content_type": response["content_type"],
                "title": self._extract_html_title(response["body"]),
                "body_excerpt": response["body"][:1200],
            },
            None if response["ok"] else f"unexpected status: {response['status_code']}",
        )

    def _probe_json_endpoint(self, args: dict[str, Any], context: dict[str, Any]) -> ToolResult:
        url = str(args.get("url") or args.get("server_url") or "").strip()
        if not url:
            return ToolResult("failed", "缺少接口地址", {}, "url is required")
        timeout_seconds = int(args.get("timeout_seconds") or 10)
        method = str(args.get("method") or "GET").strip().upper()
        try:
            response = self._fetch_local_url(url, timeout_seconds=timeout_seconds, method=method)
        except ValueError as exc:
            return ToolResult("blocked", "接口探测被阻断", {"url": url}, str(exc))
        try:
            parsed = json.loads(response["body"] or "null")
            parse_error = None
        except json.JSONDecodeError as exc:
            parsed = None
            parse_error = str(exc)
        ok = bool(response["ok"] and parse_error is None and isinstance(parsed, (dict, list)))
        preview = parsed if isinstance(parsed, dict) else parsed[:5] if isinstance(parsed, list) else None
        return ToolResult(
            "completed" if ok else "failed",
            "JSON 接口探测成功" if ok else f"JSON 接口探测失败：{response['status_code']}",
            {
                "url": response["url"],
                "final_url": response["final_url"],
                "method": method,
                "status_code": response["status_code"],
                "ok": ok,
                "content_type": response["content_type"],
                "json_type": type(parsed).__name__ if parsed is not None else "",
                "json_preview": preview,
                "body_excerpt": response["body"][:1200],
                "parse_error": parse_error,
            },
            None if ok else (parse_error or f"unexpected status: {response['status_code']}"),
        )

    def _read_local_page(self, args: dict[str, Any], context: dict[str, Any]) -> ToolResult:
        url = str(args.get("url") or args.get("server_url") or "").strip()
        if not url:
            return ToolResult("failed", "缺少页面地址", {}, "url is required")
        timeout_seconds = int(args.get("timeout_seconds") or 10)
        try:
            response = self._fetch_local_url(url, timeout_seconds=timeout_seconds, method="GET")
        except ValueError as exc:
            return ToolResult("blocked", "页面读取被阻断", {"url": url}, str(exc))
        parser = LocalPageParser()
        parser.feed(response["body"])
        text_excerpt = " ".join(parser.text_parts)[:1600]
        return ToolResult(
            "completed" if response["ok"] else "failed",
            "页面摘要读取完成" if response["ok"] else f"页面读取失败：{response['status_code']}",
            {
                "url": response["url"],
                "final_url": response["final_url"],
                "status_code": response["status_code"],
                "ok": response["ok"],
                "content_type": response["content_type"],
                "title": parser.title,
                "headings": parser.headings,
                "links": parser.links,
                "text_excerpt": text_excerpt,
            },
            None if response["ok"] else f"unexpected status: {response['status_code']}",
        )

    def _browser_validate_page(self, args: dict[str, Any], context: dict[str, Any]) -> ToolResult:
        url = str(args.get("url") or args.get("server_url") or "").strip()
        if not url:
            return ToolResult("failed", "缺少页面地址", {}, "url is required")
        selectors = [str(item).strip() for item in (args.get("selectors") or []) if str(item).strip()][:8]
        required_text = [str(item).strip() for item in (args.get("required_text") or []) if str(item).strip()][:8]
        timeout_seconds = int(args.get("timeout_seconds") or 15)
        try:
            payload = self._run_browser_validation(
                url=url,
                selectors=selectors,
                required_text=required_text,
                timeout_seconds=timeout_seconds,
                root=self._root(context),
            )
        except ValueError as exc:
            return ToolResult("blocked", "浏览器验证被阻断", {"url": url}, str(exc))
        ok = bool(payload.get("ok"))
        return ToolResult(
            "completed" if ok else "failed",
            "浏览器验证通过" if ok else "浏览器验证失败",
            payload,
            None if ok else str(payload.get("error") or "browser validation failed"),
        )

    def _capture_network_errors(self, args: dict[str, Any], context: dict[str, Any]) -> ToolResult:
        url = str(args.get("url") or args.get("server_url") or "").strip()
        if not url:
            return ToolResult("failed", "缺少页面地址", {}, "url is required")
        timeout_seconds = int(args.get("timeout_seconds") or 15)
        try:
            payload = self._run_network_capture(
                root=self._root(context),
                url=url,
                timeout_seconds=timeout_seconds,
            )
        except ValueError as exc:
            return ToolResult("blocked", "网络错误捕获被阻断", {"url": url}, str(exc))
        ok = bool(payload.get("ok"))
        return ToolResult(
            "completed" if ok else "failed",
            "网络请求检查通过" if ok else "检测到网络错误",
            payload,
            None if ok else str(payload.get("error") or "network errors detected"),
        )

    def _browser_click(self, args: dict[str, Any], context: dict[str, Any]) -> ToolResult:
        url = str(args.get("url") or args.get("server_url") or "").strip()
        selector = str(args.get("selector") or "").strip()
        if not url or not selector:
            return ToolResult("failed", "缺少页面地址或选择器", {}, "url and selector are required")
        timeout_seconds = int(args.get("timeout_seconds") or 15)
        try:
            payload = self._run_browser_action(
                root=self._root(context),
                action="click",
                url=url,
                selector=selector,
                value="",
                wait_for=str(args.get("wait_for") or "").strip(),
                required_text=[str(item).strip() for item in (args.get("required_text") or []) if str(item).strip()][:8],
                timeout_seconds=timeout_seconds,
            )
        except ValueError as exc:
            return ToolResult("blocked", "浏览器点击被阻断", {"url": url, "selector": selector}, str(exc))
        return ToolResult("completed" if payload.get("ok") else "failed", "浏览器点击完成" if payload.get("ok") else "浏览器点击失败", payload, None if payload.get("ok") else str(payload.get("error") or "browser click failed"))

    def _browser_fill(self, args: dict[str, Any], context: dict[str, Any]) -> ToolResult:
        url = str(args.get("url") or args.get("server_url") or "").strip()
        selector = str(args.get("selector") or "").strip()
        value = str(args.get("value") or "").strip()
        if not url or not selector:
            return ToolResult("failed", "缺少页面地址或选择器", {}, "url and selector are required")
        timeout_seconds = int(args.get("timeout_seconds") or 15)
        try:
            payload = self._run_browser_action(
                root=self._root(context),
                action="fill",
                url=url,
                selector=selector,
                value=value,
                wait_for=str(args.get("wait_for") or "").strip(),
                required_text=[str(item).strip() for item in (args.get("required_text") or []) if str(item).strip()][:8],
                timeout_seconds=timeout_seconds,
            )
        except ValueError as exc:
            return ToolResult("blocked", "浏览器填写被阻断", {"url": url, "selector": selector}, str(exc))
        return ToolResult("completed" if payload.get("ok") else "failed", "浏览器填写完成" if payload.get("ok") else "浏览器填写失败", payload, None if payload.get("ok") else str(payload.get("error") or "browser fill failed"))

    def _browser_wait_for(self, args: dict[str, Any], context: dict[str, Any]) -> ToolResult:
        url = str(args.get("url") or args.get("server_url") or "").strip()
        wait_for = str(args.get("wait_for") or args.get("selector") or "").strip()
        required_text = [str(item).strip() for item in (args.get("required_text") or []) if str(item).strip()][:8]
        if not url:
            return ToolResult("failed", "缺少页面地址", {}, "url is required")
        if not wait_for and not required_text:
            return ToolResult("failed", "缺少等待条件", {}, "wait_for or required_text is required")
        timeout_seconds = int(args.get("timeout_seconds") or 15)
        try:
            payload = self._run_browser_action(
                root=self._root(context),
                action="wait_for",
                url=url,
                selector="",
                value="",
                wait_for=wait_for,
                required_text=required_text,
                timeout_seconds=timeout_seconds,
            )
        except ValueError as exc:
            return ToolResult("blocked", "浏览器等待被阻断", {"url": url}, str(exc))
        return ToolResult("completed" if payload.get("ok") else "failed", "浏览器等待完成" if payload.get("ok") else "浏览器等待失败", payload, None if payload.get("ok") else str(payload.get("error") or "browser wait failed"))

    def _run_targeted_test(self, args: dict[str, Any], context: dict[str, Any]) -> ToolResult:
        root = self._root(context)
        payload = args.get("payload") if isinstance(args.get("payload"), dict) else dict(args)
        framework = str(payload.get("framework") or "").strip().lower()
        target = str(payload.get("target") or payload.get("path") or "").strip()
        test_name = str(payload.get("test_name") or payload.get("name") or "").strip()
        if not framework:
            framework = self._infer_test_framework(root, target)
        if framework not in {"pytest", "vitest", "npm_test"}:
            return ToolResult("blocked", "无法识别测试框架", {"framework": framework, "target": target}, "unsupported test framework")
        command = self._build_targeted_test_command(root, framework, target, test_name)
        if not command_allowed(command):
            return ToolResult("blocked", "精准测试命令不在白名单内", {"command": command, "framework": framework, "target": target}, "command is not allowlisted")
        return ToolResult(
            "completed",
            "已生成精准测试命令",
            {
                "command": command,
                "framework": framework,
                "target": target,
                "test_name": test_name or None,
                "cwd": str(resolve_command_cwd(root, command)),
            },
        )

    def _summarize_test_results(self, args: dict[str, Any], context: dict[str, Any]) -> ToolResult:
        stdout = str(args.get("stdout") or "")
        stderr = str(args.get("stderr") or "")
        exit_code = args.get("exit_code")
        framework = str(args.get("framework") or "").strip().lower()
        session = context.get("session") or {}
        if (not stdout and not stderr and exit_code is None) and self.repository is not None and session.get("id"):
            parts = self.repository.list_parts(str(session["id"]))
            latest_command = next((part for part in reversed(parts) if part.get("type") == "command"), None)
            payload = (latest_command or {}).get("payload") if isinstance((latest_command or {}).get("payload"), dict) else {}
            stdout = str(payload.get("stdout") or "")
            stderr = str(payload.get("stderr") or "")
            exit_code = payload.get("exit_code")
            framework = framework or self._infer_test_framework(self._root(context), " ".join(payload.get("command") or []))
        summary = self._parse_test_result_summary(stdout, stderr, framework)
        summary["exit_code"] = exit_code
        summary["framework"] = framework or summary.get("framework") or ""
        return ToolResult(
            "completed" if (stdout or stderr or exit_code is not None) else "failed",
            "测试结果已汇总" if (stdout or stderr or exit_code is not None) else "未找到测试结果",
            summary,
            None if (stdout or stderr or exit_code is not None) else "no test output available",
        )

    def _collect_test_failures(self, args: dict[str, Any], context: dict[str, Any]) -> ToolResult:
        stdout = str(args.get("stdout") or "")
        stderr = str(args.get("stderr") or "")
        failure_summary = str(args.get("failure_summary") or "")
        session = context.get("session") or {}
        if not stdout and not stderr and self.repository is not None and session.get("id"):
            parts = self.repository.list_parts(str(session["id"]))
            latest_command = next((part for part in reversed(parts) if part.get("type") == "command"), None)
            payload = (latest_command or {}).get("payload") if isinstance((latest_command or {}).get("payload"), dict) else {}
            stdout = str(payload.get("stdout") or "")
            stderr = str(payload.get("stderr") or "")
            failure_summary = failure_summary or str(payload.get("failure_summary") or "")
        failures = self._parse_test_failures(stdout, stderr)
        return ToolResult(
            "completed" if (failures or failure_summary or stdout or stderr) else "failed",
            f"提取到 {len(failures)} 条测试失败信息" if (failures or failure_summary or stdout or stderr) else "未找到测试失败信息",
            self._normalize_tool_payload(
                {
                    "failure_summary": failure_summary,
                    "failures": failures[:12],
                    "stdout_excerpt": stdout[-1600:],
                    "stderr_excerpt": stderr[-1600:],
                }
            ),
            None if (failures or failure_summary or stdout or stderr) else "no test failure information available",
        )

    def _patch(self, args: dict[str, Any], context: dict[str, Any]) -> ToolResult:
        payload = args.get("payload") if isinstance(args.get("payload"), dict) else args
        return ToolResult("completed", "已生成补丁建议", self._normalize_tool_payload({"payload": payload, "diff": payload.get("diff"), "files": payload.get("files") or []}))

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

    def _server_key(self, args: dict[str, Any], context: dict[str, Any]) -> str:
        session = context.get("session") or {}
        return f"{session.get('id') or 'default'}:{args.get('name') or 'dev'}"

    def _run_dev_server(self, args: dict[str, Any], context: dict[str, Any]) -> ToolResult:
        payload = args.get("payload") if isinstance(args.get("payload"), dict) else args
        command = payload.get("command") or ["npm", "run", "dev"]
        try:
            argv = normalize_command(command)
        except HTTPException as exc:
            return ToolResult("blocked", "开发服务器启动被阻断", {"command": command}, str(exc.detail))
        if not command_allowed(argv):
            return ToolResult("blocked", "开发服务器命令不在白名单内", {"command": argv}, "command is not allowlisted")
        root = self._root(context)
        command_root = resolve_command_cwd(root, argv)
        key = self._server_key(payload, context)
        existing = DEV_SERVER_PROCESSES.get(key)
        process = existing.get("process") if existing else None
        if process is not None and process.poll() is None:
            return ToolResult("completed", "开发服务器已在运行", {k: v for k, v in existing.items() if k not in {"process", "log_file"}})
        log_dir = root / "tmp" / "agent-dev-servers"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / f"{re.sub(r'[^a-zA-Z0-9_.-]+', '_', key)}.log"
        log_file = log_path.open("a", encoding="utf-8", errors="ignore")
        log_file.write(f"\n[{time.strftime('%Y-%m-%dT%H:%M:%S')}] starting: {' '.join(argv)}\n")
        log_file.flush()
        process = subprocess.Popen(argv, cwd=str(command_root), text=True, stdout=log_file, stderr=subprocess.STDOUT, shell=False)
        server_url = str(payload.get("server_url") or payload.get("url") or "http://localhost:5173")
        record = {
            "name": payload.get("name") or "dev",
            "command": argv,
            "cwd": str(command_root),
            "pid": process.pid,
            "server_url": server_url,
            "log_path": log_path.relative_to(root).as_posix(),
            "started_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "process": process,
            "log_file": log_file,
        }
        DEV_SERVER_PROCESSES[key] = record
        return ToolResult("completed", f"开发服务器已启动：{server_url}", {k: v for k, v in record.items() if k not in {"process", "log_file"}})

    def _stop_dev_server(self, args: dict[str, Any], context: dict[str, Any]) -> ToolResult:
        payload = args.get("payload") if isinstance(args.get("payload"), dict) else args
        key = self._server_key(payload, context)
        record = DEV_SERVER_PROCESSES.get(key)
        process = record.get("process") if record else None
        if process is None:
            return ToolResult("completed", "没有正在运行的开发服务器", {"running": False})
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
        log_file = record.get("log_file")
        if log_file:
            try:
                log_file.close()
            except Exception:
                pass
        DEV_SERVER_PROCESSES.pop(key, None)
        return ToolResult("completed", "开发服务器已停止", {"running": False, "pid": record.get("pid")})

    def _get_server_status(self, args: dict[str, Any], context: dict[str, Any]) -> ToolResult:
        payload = args.get("payload") if isinstance(args.get("payload"), dict) else args
        key = self._server_key(payload, context)
        record = DEV_SERVER_PROCESSES.get(key)
        process = record.get("process") if record else None
        running = bool(process is not None and process.poll() is None)
        if not record:
            return ToolResult("completed", "开发服务器未启动", {"running": False})
        data = {k: v for k, v in record.items() if k not in {"process", "log_file"}}
        data["running"] = running
        data["exit_code"] = None if running else process.poll()
        return ToolResult("completed", "开发服务器正在运行" if running else "开发服务器已退出", data)

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

    def _finalize(self, args: dict[str, Any], context: dict[str, Any]) -> ToolResult:
        content = str(args.get("summary") or args.get("content") or "任务已完成。")
        return ToolResult("completed", content, self._normalize_tool_payload({"summary": content, **args}))

    def apply_patch_payload(self, payload: dict[str, Any], context: dict[str, Any]) -> ToolResult:
        root = self._root(context)
        try:
            result = SafePatchEngine(root).apply_payload(payload)
            return ToolResult(
                "completed",
                result.stdout,
                self._normalize_tool_payload({"changed_files": result.changed_files, "applied_hunks": len(result.summaries), "patch_summaries": result.summaries}),
            )
        except Exception as exc:
            return ToolResult("failed", "补丁执行失败", self._normalize_tool_payload({}), str(exc))

    def _normalize_tool_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        normalized = dict(payload)
        if "changed_files" in normalized and "artifacts" not in normalized:
            normalized["artifacts"] = {"changed_files": normalized.get("changed_files") or []}
        if "patch_summaries" in normalized and "details" not in normalized:
            normalized["details"] = normalized.get("patch_summaries") or []
        if "failure_summary" in normalized and "next_action" not in normalized:
            normalized["next_action"] = normalized.get("failure_summary") or ""
        return normalized

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
            "路由": ["APIRouter", "router", "routes"],
            "接口": ["apiClient", "APIRouter", "response_model"],
        }
        for keyword, mapped in keyword_map.items():
            if keyword.lower() in goal.lower():
                queries.extend(mapped)
        for candidate in self._likely_files(root, queries):
            reads.append(candidate)
        for candidate in self._related_test_files(root, reads, queries):
            reads.append(candidate)
        return list(dict.fromkeys(reads)), list(dict.fromkeys(query for query in queries if query))

    def _related_test_files(self, root: Path, reads: list[str], queries: list[str]) -> list[str]:
        candidates: list[str] = []
        stems = {Path(path).stem for path in reads if Path(path).stem}
        stems.update(query for query in queries if len(query) >= 4)
        test_roots = [root / "server" / "tests", root / "client" / "src" / "test", root / "client" / "src" / "__tests__"]
        for base in test_roots:
            if not base.exists():
                continue
            for path in base.rglob("*"):
                if not path.is_file():
                    continue
                rel = path.relative_to(root).as_posix()
                haystack = rel.lower()
                if any(stem.lower().replace("_", "").replace("-", "") in haystack.replace("_", "").replace("-", "") for stem in stems):
                    candidates.append(rel)
                if len(candidates) >= 6:
                    return candidates
        return candidates

    def _infer_symbol_candidates(
        self,
        goal: str,
        queries: list[str],
        reads: list[str],
        explicit_symbols: list[str] | None = None,
    ) -> list[str]:
        candidates: list[str] = []
        stop_words = {
            "react",
            "fastapi",
            "python",
            "typescript",
            "typecheck",
            "pytest",
            "vitest",
            "server",
            "client",
            "route",
            "routes",
            "router",
            "test",
            "tests",
            "feature",
            "styles",
            "module",
            "api",
        }
        for symbol in explicit_symbols or []:
            normalized = str(symbol or "").strip()
            if AST_GREP_SYMBOL_RE.match(normalized):
                candidates.append(normalized)
        for token in re.findall(r"\b[A-Z][A-Za-z0-9_]{2,}\b|\b[a-zA-Z_][A-Za-z0-9_]{3,}\b", goal):
            if token.lower() not in stop_words:
                candidates.append(token)
        for query in queries:
            if AST_GREP_SYMBOL_RE.match(query) and query.lower() not in stop_words:
                candidates.append(query)
        for path in reads:
            stem = Path(path).stem
            if AST_GREP_SYMBOL_RE.match(stem) and stem.lower() not in stop_words:
                candidates.append(stem)
        return list(dict.fromkeys(candidates))

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

    def _is_searchable_code_file(self, path: Path) -> bool:
        suffix = path.suffix.lower()
        return suffix in {".py", ".ts", ".tsx", ".js", ".jsx", ".json", ".css", ".scss", ".md", ".sql", ".yaml", ".yml"}

    def _symbol_definition_patterns(self, symbol: str) -> list[tuple[str, re.Pattern[str]]]:
        escaped = re.escape(symbol)
        return [
            ("function", re.compile(rf"^\s*(?:export\s+)?(?:async\s+)?function\s+{escaped}\b")),
            ("class", re.compile(rf"^\s*(?:export\s+)?class\s+{escaped}\b")),
            ("interface", re.compile(rf"^\s*(?:export\s+)?interface\s+{escaped}\b")),
            ("type", re.compile(rf"^\s*(?:export\s+)?type\s+{escaped}\b")),
            ("enum", re.compile(rf"^\s*(?:export\s+)?enum\s+{escaped}\b")),
            ("variable", re.compile(rf"^\s*(?:export\s+)?(?:const|let|var)\s+{escaped}\b")),
            ("function", re.compile(rf"^\s*(?:export\s+)?(?:const|let|var)\s+{escaped}\s*=\s*(?:async\s*)?(?:\([^)]*\)|[A-Za-z_][A-Za-z0-9_]*)\s*=>")),
            ("function", re.compile(rf"^\s*def\s+{escaped}\b")),
            ("class", re.compile(rf"^\s*class\s+{escaped}\b")),
        ]

    def _match_symbol_definition(
        self,
        line: str,
        symbol: str,
        patterns: list[tuple[str, re.Pattern[str]]] | None = None,
    ) -> dict[str, Any] | None:
        for kind, pattern in (patterns or self._symbol_definition_patterns(symbol)):
            if pattern.search(line):
                return {"kind": kind}
        return None

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

    def _ast_grep_executable(self, root: Path) -> str | None:
        candidates = [
            root / "server" / ".venv" / "Scripts" / "sg.exe",
            root / ".venv" / "Scripts" / "sg.exe",
            settings.base_dir.resolve() / ".venv" / "Scripts" / "sg.exe",
        ]
        for candidate in candidates:
            if candidate.exists():
                return str(candidate)
        return shutil.which("sg") or shutil.which("ast-grep")

    def _ast_grep_scope_paths(self, root: Path) -> list[str]:
        candidates = [
            root / "client" / "src",
            root / "server",
            root / "tmp",
            root / "docs",
        ]
        paths = [path.relative_to(root).as_posix() for path in candidates if path.exists()]
        return paths or ["."]

    def _ast_grep_symbol_specs(self, symbol: str, requested_kind: str) -> list[dict[str, Any]]:
        specs = [
            {"kind": "function", "lang": "ts", "pattern": f"function {symbol}($$$) {{ $$$ }}", "globs": ["**/*.ts"]},
            {"kind": "function", "lang": "tsx", "pattern": f"function {symbol}($$$) {{ $$$ }}", "globs": ["**/*.tsx"]},
            {"kind": "function", "lang": "js", "pattern": f"function {symbol}($$$) {{ $$$ }}", "globs": ["**/*.js"]},
            {"kind": "function", "lang": "jsx", "pattern": f"function {symbol}($$$) {{ $$$ }}", "globs": ["**/*.jsx"]},
            {"kind": "class", "lang": "ts", "pattern": f"class {symbol} {{ $$$ }}", "globs": ["**/*.ts"]},
            {"kind": "class", "lang": "tsx", "pattern": f"class {symbol} {{ $$$ }}", "globs": ["**/*.tsx"]},
            {"kind": "class", "lang": "js", "pattern": f"class {symbol} {{ $$$ }}", "globs": ["**/*.js"]},
            {"kind": "class", "lang": "jsx", "pattern": f"class {symbol} {{ $$$ }}", "globs": ["**/*.jsx"]},
            {"kind": "interface", "lang": "ts", "pattern": f"interface {symbol} {{ $$$ }}", "globs": ["**/*.ts"]},
            {"kind": "interface", "lang": "tsx", "pattern": f"interface {symbol} {{ $$$ }}", "globs": ["**/*.tsx"]},
            {"kind": "type", "lang": "ts", "pattern": f"type {symbol} = $$$", "globs": ["**/*.ts"]},
            {"kind": "type", "lang": "tsx", "pattern": f"type {symbol} = $$$", "globs": ["**/*.tsx"]},
            {"kind": "enum", "lang": "ts", "pattern": f"enum {symbol} {{ $$$ }}", "globs": ["**/*.ts"]},
            {"kind": "enum", "lang": "tsx", "pattern": f"enum {symbol} {{ $$$ }}", "globs": ["**/*.tsx"]},
            {"kind": "variable", "lang": "ts", "pattern": f"const {symbol} = $$$", "globs": ["**/*.ts"]},
            {"kind": "variable", "lang": "tsx", "pattern": f"const {symbol} = $$$", "globs": ["**/*.tsx"]},
            {"kind": "variable", "lang": "js", "pattern": f"const {symbol} = $$$", "globs": ["**/*.js"]},
            {"kind": "variable", "lang": "jsx", "pattern": f"const {symbol} = $$$", "globs": ["**/*.jsx"]},
            {"kind": "variable", "lang": "ts", "pattern": f"let {symbol} = $$$", "globs": ["**/*.ts"]},
            {"kind": "variable", "lang": "tsx", "pattern": f"let {symbol} = $$$", "globs": ["**/*.tsx"]},
            {"kind": "variable", "lang": "js", "pattern": f"let {symbol} = $$$", "globs": ["**/*.js"]},
            {"kind": "variable", "lang": "jsx", "pattern": f"let {symbol} = $$$", "globs": ["**/*.jsx"]},
            {"kind": "variable", "lang": "ts", "pattern": f"var {symbol} = $$$", "globs": ["**/*.ts"]},
            {"kind": "variable", "lang": "tsx", "pattern": f"var {symbol} = $$$", "globs": ["**/*.tsx"]},
            {"kind": "variable", "lang": "js", "pattern": f"var {symbol} = $$$", "globs": ["**/*.js"]},
            {"kind": "variable", "lang": "jsx", "pattern": f"var {symbol} = $$$", "globs": ["**/*.jsx"]},
            {"kind": "function", "lang": "python", "pattern": f"def {symbol}($$$):\n    $$$", "globs": ["**/*.py"]},
            {"kind": "class", "lang": "python", "pattern": f"class {symbol}:\n    $$$", "globs": ["**/*.py"]},
            {"kind": "class", "lang": "python", "pattern": f"class {symbol}($$$):\n    $$$", "globs": ["**/*.py"]},
        ]
        if requested_kind:
            return [spec for spec in specs if spec["kind"] == requested_kind]
        return specs

    def _ast_grep_reference_specs(self, symbol: str) -> list[dict[str, Any]]:
        return [
            {"lang": "ts", "pattern": symbol, "globs": ["**/*.ts"]},
            {"lang": "tsx", "pattern": symbol, "globs": ["**/*.tsx"]},
            {"lang": "js", "pattern": symbol, "globs": ["**/*.js"]},
            {"lang": "jsx", "pattern": symbol, "globs": ["**/*.jsx"]},
            {"lang": "python", "pattern": symbol, "globs": ["**/*.py"]},
        ]

    def _ast_grep_match_kind(self, default_kind: str, preview: str) -> str:
        stripped = preview.strip()
        if default_kind == "variable" and ("=>" in stripped or "function" in stripped):
            return "function"
        return default_kind

    def _tool_scope_paths(self, root: Path, args: dict[str, Any]) -> list[str] | None:
        raw_scope_paths = args.get("scope_paths") or args.get("paths") or []
        if isinstance(raw_scope_paths, str):
            raw_scope_paths = [raw_scope_paths]
        paths: list[str] = []
        for raw_path in raw_scope_paths:
            value = str(raw_path or "").strip()
            if not value:
                continue
            try:
                rel = self._safe_path(root, value).relative_to(root).as_posix()
            except Exception:
                rel = value.replace("\\", "/").lstrip("./")
            paths.append(rel)
        return list(dict.fromkeys(paths)) or None

    def _path_in_scope(self, rel_path: str, scope_paths: list[str]) -> bool:
        normalized = rel_path.replace("\\", "/")
        for scope in scope_paths:
            candidate = str(scope or "").replace("\\", "/").rstrip("/")
            if not candidate:
                continue
            if normalized == candidate or normalized.startswith(f"{candidate}/"):
                return True
        return False

    def _run_ast_grep(
        self,
        *,
        root: Path,
        pattern: str,
        lang: str,
        globs: list[str],
        limit: int,
        scope_paths: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        executable = self._ast_grep_executable(root)
        if not executable:
            raise FileNotFoundError("ast-grep executable not found")
        command = [executable, "run", "--pattern", pattern, "--lang", lang, "--json=compact", "--no-ignore", "vcs"]
        for glob in globs:
            command.extend(["--globs", glob])
        command.extend(scope_paths or self._ast_grep_scope_paths(root))
        completed = subprocess.run(
            command,
            cwd=str(root),
            text=True,
            capture_output=True,
            timeout=30,
            shell=False,
        )
        if completed.returncode != 0 and completed.stdout.strip() in {"", "[]"}:
            return []
        try:
            data = json.loads(completed.stdout.strip() or "[]")
        except json.JSONDecodeError:
            return []
        results: list[dict[str, Any]] = []
        for item in data:
            path = str(item.get("file") or "").replace("\\", "/")
            if not path:
                continue
            preview = str(item.get("lines") or item.get("text") or "").strip()
            line = int((((item.get("range") or {}).get("start") or {}).get("line")) or 0) + 1
            results.append({"path": path, "line": line, "preview": preview[:300]})
            if len(results) >= limit:
                break
        return results

    def _validate_local_url(self, raw_url: str) -> str:
        parsed = urlparse(raw_url)
        if parsed.scheme not in {"http", "https"}:
            raise ValueError("only http/https local URLs are allowed")
        if (parsed.hostname or "").lower() not in LOCAL_HTTP_HOSTS:
            raise ValueError("only localhost URLs are allowed")
        return raw_url

    def _fetch_local_url(self, raw_url: str, *, timeout_seconds: int, method: str) -> dict[str, Any]:
        url = self._validate_local_url(raw_url)
        request = Request(url, method=method, headers={"User-Agent": "finetune-platform-agent/1.0"})
        try:
            with urlopen(request, timeout=timeout_seconds) as response:
                body = response.read().decode("utf-8", errors="ignore")
                status_code = int(getattr(response, "status", 200))
                final_url = str(response.geturl())
                content_type = str(response.headers.get("content-type") or "")
        except HTTPError as exc:
            body = exc.read().decode("utf-8", errors="ignore")
            status_code = int(exc.code)
            final_url = str(exc.geturl() or url)
            content_type = str(exc.headers.get("content-type") or "")
        except URLError as exc:
            return {
                "url": url,
                "final_url": url,
                "status_code": 0,
                "ok": False,
                "content_type": "",
                "body": str(exc.reason),
            }
        return {
            "url": url,
            "final_url": final_url,
            "status_code": status_code,
            "ok": 200 <= status_code < 400,
            "content_type": content_type,
            "body": body,
        }

    def _extract_html_title(self, body: str) -> str:
        match = re.search(r"<title[^>]*>(.*?)</title>", body, flags=re.IGNORECASE | re.DOTALL)
        if not match:
            return ""
        return " ".join(match.group(1).split())[:200]

    def _run_browser_validation(
        self,
        *,
        url: str,
        selectors: list[str],
        required_text: list[str],
        timeout_seconds: int,
        root: Path,
    ) -> dict[str, Any]:
        validated_url = self._validate_local_url(url)
        node_executable = shutil.which("node")
        if not node_executable:
            return {
                "url": validated_url,
                "final_url": validated_url,
                "ok": False,
                "status_code": 0,
                "title": "",
                "headings": [],
                "console_errors": [],
                "page_errors": [],
                "selector_results": [],
                "text_results": [],
                "body_excerpt": "",
                "error": "node executable not found",
                "engine": "playwright",
            }
        client_root = root / "client"
        script = """
const { chromium } = require('playwright');

async function main() {
  const input = JSON.parse(process.argv[1]);
  const consoleErrors = [];
  const pageErrors = [];
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();
  page.on('console', (msg) => {
    if (msg.type() === 'error' && consoleErrors.length < 12) {
      consoleErrors.push(msg.text());
    }
  });
  page.on('pageerror', (error) => {
    if (pageErrors.length < 12) {
      pageErrors.push(String(error));
    }
  });
  let response = null;
  try {
    response = await page.goto(input.url, { waitUntil: 'networkidle', timeout: input.timeoutMs });
    const title = await page.title();
    const headings = await page.$$eval('h1,h2,h3', (nodes) =>
      nodes.slice(0, 8).map((node) => ({
        tag: node.tagName.toLowerCase(),
        text: (node.textContent || '').trim().slice(0, 200),
      }))
    );
    const bodyText = await page.locator('body').innerText().catch(() => '');
    const selectorResults = [];
    for (const selector of input.selectors) {
      const count = await page.locator(selector).count().catch(() => 0);
      selectorResults.push({ selector, found: count > 0, count });
    }
    const textResults = [];
    for (const text of input.requiredText) {
      const found = await page.locator('body').evaluate((node, value) => (node.innerText || '').includes(value), text).catch(() => false);
      textResults.push({ text, found });
    }
    const statusCode = response ? response.status() : 0;
    const ok =
      statusCode >= 200 &&
      statusCode < 400 &&
      consoleErrors.length === 0 &&
      pageErrors.length === 0 &&
      selectorResults.every((item) => item.found) &&
      textResults.every((item) => item.found);
    const payload = {
      url: input.url,
      final_url: page.url(),
      ok,
      status_code: statusCode,
      title,
      headings,
      console_errors: consoleErrors,
      page_errors: pageErrors,
      selector_results: selectorResults,
      text_results: textResults,
      body_excerpt: bodyText.slice(0, 1600),
      engine: 'playwright',
    };
    console.log(JSON.stringify(payload));
  } catch (error) {
    const payload = {
      url: input.url,
      final_url: page.url() || input.url,
      ok: false,
      status_code: response ? response.status() : 0,
      title: '',
      headings: [],
      console_errors: consoleErrors,
      page_errors: pageErrors,
      selector_results: [],
      text_results: [],
      body_excerpt: '',
      error: String(error),
      engine: 'playwright',
    };
    console.log(JSON.stringify(payload));
  } finally {
    await browser.close().catch(() => {});
  }
}

main().catch((error) => {
  console.log(JSON.stringify({
    url: '',
    final_url: '',
    ok: false,
    status_code: 0,
    title: '',
    headings: [],
    console_errors: [],
    page_errors: [String(error)],
    selector_results: [],
    text_results: [],
    body_excerpt: '',
    error: String(error),
    engine: 'playwright',
  }));
  process.exit(0);
});
"""
        input_payload = json.dumps(
            {
                "url": validated_url,
                "selectors": selectors,
                "requiredText": required_text,
                "timeoutMs": timeout_seconds * 1000,
            },
            ensure_ascii=False,
        )
        completed = subprocess.run(
            [node_executable, "-e", script, input_payload],
            cwd=str(client_root if client_root.exists() else root),
            text=True,
            capture_output=True,
            timeout=max(timeout_seconds + 10, 20),
            shell=False,
        )
        output = (completed.stdout or "").strip().splitlines()
        raw = output[-1] if output else "{}"
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            payload = {
                "url": validated_url,
                "final_url": validated_url,
                "ok": False,
                "status_code": 0,
                "title": "",
                "headings": [],
                "console_errors": [],
                "page_errors": [],
                "selector_results": [],
                "text_results": [],
                "body_excerpt": "",
                "error": completed.stderr.strip() or raw or "invalid browser validation output",
                "engine": "playwright",
            }
        payload.setdefault("url", validated_url)
        payload.setdefault("final_url", validated_url)
        payload.setdefault("engine", "playwright")
        payload.setdefault("console_errors", [])
        payload.setdefault("page_errors", [])
        payload.setdefault("selector_results", [])
        payload.setdefault("text_results", [])
        payload.setdefault("headings", [])
        payload.setdefault("title", "")
        payload.setdefault("body_excerpt", "")
        payload.setdefault("status_code", 0)
        payload.setdefault("ok", False)
        if completed.returncode != 0 and not payload.get("error"):
            payload["error"] = completed.stderr.strip() or "browser validation command failed"
        return payload

    def _run_browser_action(
        self,
        *,
        root: Path,
        action: str,
        url: str,
        selector: str,
        value: str,
        wait_for: str,
        required_text: list[str],
        timeout_seconds: int,
    ) -> dict[str, Any]:
        validated_url = self._validate_local_url(url)
        node_executable = shutil.which("node")
        if not node_executable:
            return {
                "url": validated_url,
                "final_url": validated_url,
                "ok": False,
                "status_code": 0,
                "title": "",
                "headings": [],
                "console_errors": [],
                "page_errors": [],
                "selector_results": [],
                "text_results": [],
                "body_excerpt": "",
                "error": "node executable not found",
                "engine": "playwright",
                "action": action,
            }
        client_root = root / "client"
        script = """
const { chromium } = require('playwright');
async function main() {
  const input = JSON.parse(process.argv[1]);
  const consoleErrors = [];
  const pageErrors = [];
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();
  page.on('console', (msg) => {
    if (msg.type() === 'error' && consoleErrors.length < 12) consoleErrors.push(msg.text());
  });
  page.on('pageerror', (error) => {
    if (pageErrors.length < 12) pageErrors.push(String(error));
  });
  let response = null;
  try {
    response = await page.goto(input.url, { waitUntil: 'networkidle', timeout: input.timeoutMs });
    if (input.action === 'click') {
      await page.locator(input.selector).click({ timeout: input.timeoutMs });
    } else if (input.action === 'fill') {
      await page.locator(input.selector).fill(input.value, { timeout: input.timeoutMs });
    }
    if (input.waitFor) {
      if (input.waitFor.startsWith('text=')) {
        await page.getByText(input.waitFor.slice(5), { exact: false }).waitFor({ timeout: input.timeoutMs });
      } else {
        await page.locator(input.waitFor).waitFor({ timeout: input.timeoutMs });
      }
    }
    const selectorResults = [];
    if (input.selector) {
      const count = await page.locator(input.selector).count().catch(() => 0);
      selectorResults.push({ selector: input.selector, found: count > 0, count });
    }
    const textResults = [];
    for (const text of input.requiredText) {
      const found = await page.locator('body').evaluate((node, value) => (node.innerText || '').includes(value), text).catch(() => false);
      textResults.push({ text, found });
    }
    const title = await page.title();
    const headings = await page.$$eval('h1,h2,h3', (nodes) =>
      nodes.slice(0, 8).map((node) => ({ tag: node.tagName.toLowerCase(), text: (node.textContent || '').trim().slice(0, 200) }))
    );
    const bodyText = await page.locator('body').innerText().catch(() => '');
    const statusCode = response ? response.status() : 0;
    const ok = statusCode >= 200 && statusCode < 400 && consoleErrors.length === 0 && pageErrors.length === 0 && textResults.every((item) => item.found);
    console.log(JSON.stringify({
      url: input.url,
      final_url: page.url(),
      ok,
      status_code: statusCode,
      title,
      headings,
      console_errors: consoleErrors,
      page_errors: pageErrors,
      selector_results: selectorResults,
      text_results: textResults,
      body_excerpt: bodyText.slice(0, 1600),
      engine: 'playwright',
      action: input.action,
    }));
  } catch (error) {
    console.log(JSON.stringify({
      url: input.url,
      final_url: page.url() || input.url,
      ok: false,
      status_code: response ? response.status() : 0,
      title: '',
      headings: [],
      console_errors: consoleErrors,
      page_errors: pageErrors,
      selector_results: input.selector ? [{ selector: input.selector, found: false, count: 0 }] : [],
      text_results: input.requiredText.map((text) => ({ text, found: false })),
      body_excerpt: '',
      error: String(error),
      engine: 'playwright',
      action: input.action,
    }));
  } finally {
    await browser.close().catch(() => {});
  }
}
main().catch((error) => {
  console.log(JSON.stringify({
    url: '',
    final_url: '',
    ok: false,
    status_code: 0,
    title: '',
    headings: [],
    console_errors: [],
    page_errors: [String(error)],
    selector_results: [],
    text_results: [],
    body_excerpt: '',
    error: String(error),
    engine: 'playwright',
    action: 'unknown',
  }));
  process.exit(0);
});
"""
        input_payload = json.dumps(
            {
                "url": validated_url,
                "action": action,
                "selector": selector,
                "value": value,
                "waitFor": wait_for,
                "requiredText": required_text,
                "timeoutMs": timeout_seconds * 1000,
            },
            ensure_ascii=False,
        )
        completed = subprocess.run(
            [node_executable, "-e", script, input_payload],
            cwd=str(client_root if client_root.exists() else root),
            text=True,
            capture_output=True,
            timeout=max(timeout_seconds + 10, 20),
            shell=False,
        )
        output = (completed.stdout or "").strip().splitlines()
        raw = output[-1] if output else "{}"
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            payload = {
                "url": validated_url,
                "final_url": validated_url,
                "ok": False,
                "status_code": 0,
                "title": "",
                "headings": [],
                "console_errors": [],
                "page_errors": [],
                "selector_results": [],
                "text_results": [],
                "body_excerpt": "",
                "error": completed.stderr.strip() or raw or "invalid browser action output",
                "engine": "playwright",
                "action": action,
            }
        payload.setdefault("url", validated_url)
        payload.setdefault("final_url", validated_url)
        payload.setdefault("engine", "playwright")
        payload.setdefault("action", action)
        payload.setdefault("console_errors", [])
        payload.setdefault("page_errors", [])
        payload.setdefault("selector_results", [])
        payload.setdefault("text_results", [])
        payload.setdefault("headings", [])
        payload.setdefault("title", "")
        payload.setdefault("body_excerpt", "")
        payload.setdefault("status_code", 0)
        payload.setdefault("ok", False)
        if completed.returncode != 0 and not payload.get("error"):
            payload["error"] = completed.stderr.strip() or "browser action command failed"
        return payload

    def _run_network_capture(
        self,
        *,
        root: Path,
        url: str,
        timeout_seconds: int,
    ) -> dict[str, Any]:
        validated_url = self._validate_local_url(url)
        node_executable = shutil.which("node")
        if not node_executable:
            return {
                "url": validated_url,
                "final_url": validated_url,
                "ok": False,
                "request_failures": [],
                "error_responses": [],
                "console_errors": [],
                "page_errors": [],
                "engine": "playwright",
                "error": "node executable not found",
            }
        client_root = root / "client"
        script = """
const { chromium } = require('playwright');
async function main() {
  const input = JSON.parse(process.argv[1]);
  const requestFailures = [];
  const errorResponses = [];
  const consoleErrors = [];
  const pageErrors = [];
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();
  page.on('console', (msg) => {
    if (msg.type() === 'error' && consoleErrors.length < 12) consoleErrors.push(msg.text());
  });
  page.on('pageerror', (error) => {
    if (pageErrors.length < 12) pageErrors.push(String(error));
  });
  page.on('requestfailed', (request) => {
    if (requestFailures.length < 12) {
      requestFailures.push({
        url: request.url(),
        method: request.method(),
        failure: request.failure() ? request.failure().errorText : 'requestfailed',
      });
    }
  });
  page.on('response', async (response) => {
    if (response.status() >= 400 && errorResponses.length < 12) {
      errorResponses.push({
        url: response.url(),
        status: response.status(),
        method: response.request().method(),
      });
    }
  });
  try {
    const response = await page.goto(input.url, { waitUntil: 'networkidle', timeout: input.timeoutMs });
    console.log(JSON.stringify({
      url: input.url,
      final_url: page.url(),
      ok: requestFailures.length === 0 && errorResponses.length === 0 && consoleErrors.length === 0 && pageErrors.length === 0 && !!response && response.status() < 400,
      status_code: response ? response.status() : 0,
      request_failures: requestFailures,
      error_responses: errorResponses,
      console_errors: consoleErrors,
      page_errors: pageErrors,
      engine: 'playwright',
    }));
  } catch (error) {
    console.log(JSON.stringify({
      url: input.url,
      final_url: page.url() || input.url,
      ok: false,
      status_code: 0,
      request_failures: requestFailures,
      error_responses: errorResponses,
      console_errors: consoleErrors,
      page_errors: [...pageErrors, String(error)].slice(0, 12),
      engine: 'playwright',
      error: String(error),
    }));
  } finally {
    await browser.close().catch(() => {});
  }
}
main().catch((error) => {
  console.log(JSON.stringify({
    url: '',
    final_url: '',
    ok: false,
    status_code: 0,
    request_failures: [],
    error_responses: [],
    console_errors: [],
    page_errors: [String(error)],
    engine: 'playwright',
    error: String(error),
  }));
  process.exit(0);
});
"""
        input_payload = json.dumps({"url": validated_url, "timeoutMs": timeout_seconds * 1000}, ensure_ascii=False)
        completed = subprocess.run(
            [node_executable, "-e", script, input_payload],
            cwd=str(client_root if client_root.exists() else root),
            text=True,
            capture_output=True,
            timeout=max(timeout_seconds + 10, 20),
            shell=False,
        )
        output = (completed.stdout or "").strip().splitlines()
        raw = output[-1] if output else "{}"
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            payload = {
                "url": validated_url,
                "final_url": validated_url,
                "ok": False,
                "status_code": 0,
                "request_failures": [],
                "error_responses": [],
                "console_errors": [],
                "page_errors": [],
                "engine": "playwright",
                "error": completed.stderr.strip() or raw or "invalid network capture output",
            }
        payload.setdefault("url", validated_url)
        payload.setdefault("final_url", validated_url)
        payload.setdefault("status_code", 0)
        payload.setdefault("ok", False)
        payload.setdefault("request_failures", [])
        payload.setdefault("error_responses", [])
        payload.setdefault("console_errors", [])
        payload.setdefault("page_errors", [])
        payload.setdefault("engine", "playwright")
        if completed.returncode != 0 and not payload.get("error"):
            payload["error"] = completed.stderr.strip() or "network capture command failed"
        return payload

    def _parse_test_failures(self, stdout: str, stderr: str) -> list[dict[str, Any]]:
        text = "\n".join(part for part in (stdout, stderr) if part).splitlines()
        failures: list[dict[str, Any]] = []
        current: dict[str, Any] | None = None
        for line in text:
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.startswith("FAILED ") or stripped.startswith("ERROR "):
                current = {"headline": stripped[:300], "details": []}
                failures.append(current)
                continue
            if current is not None and len(current["details"]) < 6:
                if stripped.startswith(("E ", "AssertionError", "RuntimeError", "TypeError", "ValueError", "Expected ", "Received ")):
                    current["details"].append(stripped[:300])
        return failures

    def _infer_test_framework(self, root: Path, target: str) -> str:
        normalized = target.replace("\\", "/").lower()
        if normalized.endswith(".py") or normalized.startswith("server/tests"):
            return "pytest"
        if any(normalized.endswith(ext) for ext in (".ts", ".tsx", ".js", ".jsx")) or normalized.startswith("client/"):
            if (root / "client" / "package.json").exists():
                return "vitest"
        if (root / "server" / "tests").exists():
            return "pytest"
        if (root / "client" / "package.json").exists():
            return "vitest"
        return ""

    def _build_targeted_test_command(self, root: Path, framework: str, target: str, test_name: str) -> list[str]:
        if framework == "pytest":
            command = ["python", "-m", "pytest"]
            if target:
                command.append(self._safe_path(root, target).relative_to(root).as_posix())
            if test_name:
                command.extend(["-k", test_name])
            return command
        if framework == "vitest":
            command = ["npx", "vitest", "run"]
            if target:
                command.append(self._safe_path(root, target).relative_to(root).as_posix())
            if test_name:
                command.extend(["-t", test_name])
            return command
        command = ["npm", "test"]
        if target:
            command.extend(["--", self._safe_path(root, target).relative_to(root).as_posix()])
        return command

    def _parse_test_result_summary(self, stdout: str, stderr: str, framework: str) -> dict[str, Any]:
        text = "\n".join(part for part in (stdout, stderr) if part)
        summary: dict[str, Any] = {
            "framework": framework,
            "passed": 0,
            "failed": 0,
            "skipped": 0,
            "collected": 0,
            "duration": "",
            "headline": "",
        }
        for line in reversed([item.strip() for item in text.splitlines() if item.strip()]):
            if not summary["headline"] and any(token in line.lower() for token in ("passed", "failed", "error", "collected", "duration", "warnings")):
                summary["headline"] = line[:300]
            passed = re.search(r"(\d+)\s+passed", line, flags=re.IGNORECASE)
            failed = re.search(r"(\d+)\s+failed", line, flags=re.IGNORECASE)
            skipped = re.search(r"(\d+)\s+skipped", line, flags=re.IGNORECASE)
            collected = re.search(r"collected\s+(\d+)\s+items", line, flags=re.IGNORECASE)
            duration = re.search(r"in\s+([0-9.]+s|\d+:\d+\.\d+)", line, flags=re.IGNORECASE)
            if passed:
                summary["passed"] = int(passed.group(1))
            if failed:
                summary["failed"] = int(failed.group(1))
            if skipped:
                summary["skipped"] = int(skipped.group(1))
            if collected:
                summary["collected"] = int(collected.group(1))
            if duration and not summary["duration"]:
                summary["duration"] = duration.group(1)
        if not summary["headline"]:
            summary["headline"] = summarize_failure(stdout, stderr, limit=300)
        return summary
