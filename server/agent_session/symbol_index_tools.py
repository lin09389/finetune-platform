from __future__ import annotations

import json
import logging
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

from core.config import settings

from .tool_host import ToolHostProtocol
from .tool_types import ToolResult

AST_GREP_SYMBOL_RE = re.compile(r"^[A-Za-z_$][A-Za-z0-9_$]*$")
logger = logging.getLogger(__name__)


class SymbolIndexToolsMixin(ToolHostProtocol):
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
            except Exception as e:
                logger.debug(f"Failed to read file for symbol search {path}: {e}")
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
            except Exception as e:
                logger.debug(f"Failed to read file for reference search {path}: {e}")
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
        except Exception as e:
            logger.error(f"ast-grep symbol search failed: {e}")
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
        except Exception as e:
            logger.error(f"ast-grep reference search failed: {e}")
            return None
        return ToolResult(
            "completed",
            f"找到 {len(collected)} 个符号引用",
            {"symbol": symbol, "matches": collected, "touched_paths": [item["path"] for item in collected], "engine": "ast-grep"},
        )

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
            except Exception as e:
                logger.debug(f"Failed to resolve safe path for {value}: {e}")
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
