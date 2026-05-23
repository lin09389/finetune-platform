from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

from .symbol_index_tools import AST_GREP_SYMBOL_RE
from .tool_host import ToolHostProtocol
from .tool_types import ToolResult

logger = logging.getLogger(__name__)


class FileToolsMixin(ToolHostProtocol):
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
            except Exception as e:
                logger.debug(f"Failed to read file for search {path}: {e}")
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
        explicit_symbols = list(args.get("symbols") or [])
        single_symbol = str(args.get("symbol") or "").strip()
        if single_symbol:
            explicit_symbols.append(single_symbol)
        should_infer_targets = not explicit_reads and not explicit_queries and not explicit_symbols
        inferred_reads, inferred_queries = self._infer_context_targets(root, goal) if should_infer_targets else ([], [])
        reads = list(dict.fromkeys([*explicit_reads, *inferred_reads]))
        queries = list(dict.fromkeys([*explicit_queries, *inferred_queries]))
        
        # 优化：采用单次扫描与文件缓存对多个查询进行批量检索，避免多次遍历磁盘带来的严重 I/O 阻塞
        if queries:
            lowered_queries = [q.lower() for q in queries[:8]]
            scanned = 0
            candidate_files_list = list(self._candidate_files(root))
            query_matches = {q: [] for q in lowered_queries}
            path_glob = args.get("path_glob") or "**/*"
            
            for path in candidate_files_list:
                scanned += 1
                if scanned > 3000:
                    break
                if path_glob and not path.match(path_glob):
                    continue
                rel = path.relative_to(root).as_posix()
                try:
                    content = path.read_text(encoding="utf-8", errors="ignore")
                    lowered_content = content.lower()
                except Exception:
                    continue
                
                for lq in lowered_queries:
                    if len(query_matches[lq]) >= 10:
                        continue
                    if lq in lowered_content:
                        lines = content.splitlines()
                        for line_no, line in enumerate(lines, 1):
                            if lq in line.lower():
                                query_matches[lq].append({"path": rel, "line": line_no, "preview": line.strip()[:300]})
                                if len(query_matches[lq]) >= 10:
                                    break
            for lq in lowered_queries:
                matches.extend(query_matches[lq])
        
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
            except Exception as e:
                logger.debug(f"Failed to parse {pkg}: {e}")
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
            "react", "fastapi", "python", "typescript", "typecheck", "pytest",
            "vitest", "server", "client", "route", "routes", "router", "test",
            "tests", "feature", "styles", "module", "api",
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

    def _is_searchable_code_file(self, path: Path) -> bool:
        suffix = path.suffix.lower()
        return suffix in {".py", ".ts", ".tsx", ".js", ".jsx", ".json", ".css", ".scss", ".md", ".sql", ".yaml", ".yml"}

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
