"""Lightweight workspace inventory for Agent kickoff (Phase B1).

Works without embeddings/indexes: shallow tree + keyword file ranking.
Respects optional task_scope (B0) so inventory does not advertise out-of-scope paths.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from agent_session.task_scope import normalize_rel_path, path_in_scope

# Keep scans cheap on large trees.
_MAX_DEPTH = 3
_MAX_TREE_ENTRIES = 48
_MAX_MATCHED_FILES = 8
_MAX_SCANNED_FILES = 400
_MAX_PREVIEW_CHARS = 280
_MAX_MARKDOWN_CHARS = 8_000

_SKIP_DIR_NAMES = frozenset(
    {
        ".git",
        ".hg",
        ".svn",
        ".venv",
        "venv",
        "node_modules",
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        ".tox",
        "dist",
        "build",
        "coverage",
        ".next",
        ".nuxt",
        ".turbo",
        ".cache",
        "modelscope_cache",
        "outputs",
        "logs",
        "data",
        "tmp",
        "temp",
        ".idea",
        ".vscode",
    }
)

_CODE_SUFFIXES = frozenset(
    {
        ".py",
        ".pyi",
        ".ts",
        ".tsx",
        ".js",
        ".jsx",
        ".mjs",
        ".cjs",
        ".json",
        ".toml",
        ".yaml",
        ".yml",
        ".md",
        ".rs",
        ".go",
        ".java",
        ".kt",
        ".cs",
        ".cpp",
        ".c",
        ".h",
        ".hpp",
        ".css",
        ".scss",
        ".html",
        ".vue",
        ".svelte",
        ".sh",
        ".bat",
        ".ps1",
        ".sql",
    }
)

_STOPWORDS = frozenset(
    {
        "the",
        "and",
        "for",
        "with",
        "from",
        "that",
        "this",
        "into",
        "your",
        "please",
        "fix",
        "repair",
        "debug",
        "implement",
        "add",
        "update",
        "make",
        "sure",
        "need",
        "needs",
        "using",
        "use",
        "file",
        "files",
        "code",
        "project",
        "workspace",
        "function",
        "class",
        "method",
        "error",
        "bug",
        "issue",
        "task",
        "agent",
        "true",
        "false",
        "null",
        "none",
        "修复",
        "修改",
        "实现",
        "增加",
        "添加",
        "更新",
        "调试",
        "问题",
        "文件",
        "代码",
        "项目",
        "请",
        "把",
        "将",
        "一个",
        "这个",
        "那个",
    }
)

_TOKEN_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_\-]{1,48}|[\u4e00-\u9fff]{2,12}")
_PATHISH_RE = re.compile(
    r"(?:[\w.\-]+/)+[\w.\-]+\.[A-Za-z0-9]{1,8}|[\w.\-]+\.(?:py|ts|tsx|js|jsx|json|md|toml|yml|yaml)\b"
)


def extract_goal_tokens(goal: str) -> list[str]:
    """Extract lightweight search tokens from a user goal."""
    text = str(goal or "").strip()
    if not text:
        return []
    tokens: list[str] = []
    seen: set[str] = set()

    def add(raw: str) -> None:
        tok = raw.strip().strip("`'\".,;:()[]{}")
        if len(tok) < 2:
            return
        key = tok.lower()
        if key in _STOPWORDS or key in seen:
            return
        if tok.isdigit():
            return
        seen.add(key)
        tokens.append(tok)

    for match in _PATHISH_RE.findall(text):
        add(match)
        for part in match.replace("\\", "/").split("/"):
            add(part)
            stem = Path(part).stem
            if stem != part:
                add(stem)
    for match in _TOKEN_RE.findall(text):
        add(match)
        if "_" in match or "-" in match:
            for part in re.split(r"[_\-]+", match):
                add(part)
    return tokens[:40]


def build_workspace_inventory(
    project_path: str | Path | None,
    goal: str,
    *,
    task_scope: dict[str, Any] | None = None,
    max_depth: int = _MAX_DEPTH,
    max_tree_entries: int = _MAX_TREE_ENTRIES,
    max_matched_files: int = _MAX_MATCHED_FILES,
) -> dict[str, Any]:
    """Build a bounded inventory for kickoff injection.

    Returns a dict with ``status`` in {ok, empty, skipped, error}, markdown text,
    recommended read paths, and structured tree/matches for metadata.
    """
    if not project_path:
        return _empty_result("skipped", reason="no_project_path")
    root = Path(project_path)
    try:
        root = root.resolve()
    except OSError as exc:
        return _empty_result("error", reason=f"resolve_failed:{exc}")
    if not root.is_dir():
        return _empty_result("error", reason="not_a_directory")

    tokens = extract_goal_tokens(goal)
    token_keys = [t.lower() for t in tokens]
    scope_active = bool(task_scope and (task_scope.get("paths") or []))

    tree_entries: list[str] = []
    candidates: list[tuple[int, str, str]] = []  # score, rel, reason
    scanned_files = 0

    try:
        for dirpath, dirnames, filenames in _walk(root, max_depth=max_depth):
            dirnames[:] = sorted(
                name
                for name in dirnames
                if name not in _SKIP_DIR_NAMES and not name.startswith(".")
            )
            rel_dir = _rel_posix(root, Path(dirpath))
            if rel_dir and not path_in_scope(rel_dir, task_scope):
                # Still allow walking into unscoped parents of scoped children? B0 paths are
                # usually prefixes; if current dir out of scope, prune children.
                dirnames[:] = []
                continue
            if rel_dir:
                if len(tree_entries) < max_tree_entries:
                    tree_entries.append(f"{rel_dir}/")
            for name in sorted(filenames):
                if name.startswith(".") and name not in {".env.example"}:
                    continue
                path = Path(dirpath) / name
                if not path.is_file():
                    continue
                rel = _rel_posix(root, path)
                if not rel or not path_in_scope(rel, task_scope):
                    continue
                if len(tree_entries) < max_tree_entries:
                    tree_entries.append(rel)
                scanned_files += 1
                if scanned_files > _MAX_SCANNED_FILES:
                    break
                suffix = path.suffix.lower()
                if suffix and suffix not in _CODE_SUFFIXES and name not in {
                    "Makefile",
                    "Dockerfile",
                    "README",
                    "LICENSE",
                }:
                    continue
                score, reason = _score_file(rel, name, token_keys)
                if score > 0:
                    candidates.append((score, rel, reason))
            if scanned_files > _MAX_SCANNED_FILES:
                break
    except OSError as exc:
        return _empty_result("error", reason=f"walk_failed:{exc}")

    candidates.sort(key=lambda item: (-item[0], item[1]))
    matched: list[dict[str, Any]] = []
    for score, rel, reason in candidates[:max_matched_files]:
        preview = _file_preview(root / Path(*rel.split("/")))
        matched.append(
            {
                "path": rel,
                "score": score,
                "reason": reason,
                "preview": preview,
            }
        )

    # Prefer matched files; fall back to shallow code files from tree.
    recommended = [item["path"] for item in matched]
    if not recommended:
        for entry in tree_entries:
            if entry.endswith("/"):
                continue
            suffix = Path(entry).suffix.lower()
            if suffix in _CODE_SUFFIXES:
                recommended.append(entry)
            if len(recommended) >= min(5, max_matched_files):
                break

    if not tree_entries and not recommended:
        return {
            "schema_version": 1,
            "status": "empty",
            "reason": "no_files",
            "scoped": scope_active,
            "tokens": tokens,
            "tree": [],
            "matched_files": [],
            "recommended_reads": [],
            "markdown": "# Workspace Inventory\n\n(no files found under project root)\n",
            "scanned_files": scanned_files,
        }

    markdown = _render_markdown(
        tree_entries=tree_entries,
        matched=matched,
        recommended=recommended,
        tokens=tokens,
        scoped=scope_active,
        scanned_files=scanned_files,
    )
    return {
        "schema_version": 1,
        "status": "ok",
        "reason": None,
        "scoped": scope_active,
        "tokens": tokens,
        "tree": tree_entries,
        "matched_files": [
            {"path": m["path"], "score": m["score"], "reason": m["reason"]} for m in matched
        ],
        "recommended_reads": recommended,
        "markdown": markdown,
        "scanned_files": scanned_files,
    }


def _walk(root: Path, *, max_depth: int):
    """os.walk-like generator limited by depth from root."""
    import os

    root_depth = len(root.parts)
    for dirpath, dirnames, filenames in os.walk(root):
        depth = len(Path(dirpath).parts) - root_depth
        if depth >= max_depth:
            dirnames[:] = []
        yield dirpath, dirnames, filenames


def _rel_posix(root: Path, path: Path) -> str:
    try:
        rel = path.resolve().relative_to(root)
    except (ValueError, OSError):
        return ""
    text = rel.as_posix()
    if text == ".":
        return ""
    try:
        return normalize_rel_path(text)
    except ValueError:
        return ""


def _score_file(rel: str, name: str, token_keys: list[str]) -> tuple[int, str]:
    if not token_keys:
        # Without tokens, lightly prefer common entrypoints.
        lowered = name.lower()
        if lowered in {"main.py", "app.py", "cli.py", "index.ts", "index.tsx", "index.js"}:
            return 3, "entrypoint"
        if lowered in {"readme.md", "package.json", "pyproject.toml"}:
            return 2, "manifest"
        return 0, ""

    rel_l = rel.lower()
    name_l = name.lower()
    stem = Path(name).stem.lower()
    score = 0
    reasons: list[str] = []
    for tok in token_keys:
        if tok in rel_l:
            score += 8 if "/" in tok or "." in tok else 5
            reasons.append(f"path:{tok}")
        elif tok == stem or tok in stem:
            score += 6
            reasons.append(f"name:{tok}")
        elif tok in name_l:
            score += 4
            reasons.append(f"file:{tok}")
    if score <= 0:
        return 0, ""
    # Prefer source over docs slightly when scores tie later.
    if Path(name).suffix.lower() in {".py", ".ts", ".tsx", ".js", ".jsx"}:
        score += 1
    return score, ",".join(reasons[:4])


def _file_preview(path: Path) -> str:
    try:
        if path.stat().st_size > 120_000:
            return ""
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    lines = [line.rstrip() for line in text.splitlines() if line.strip()][:12]
    preview = "\n".join(lines)
    if len(preview) > _MAX_PREVIEW_CHARS:
        preview = preview[:_MAX_PREVIEW_CHARS].rstrip() + "\n..."
    return preview


def _render_markdown(
    *,
    tree_entries: list[str],
    matched: list[dict[str, Any]],
    recommended: list[str],
    tokens: list[str],
    scoped: bool,
    scanned_files: int,
) -> str:
    lines = [
        "# Workspace Inventory (B1)",
        "",
        "Platform-generated kickoff map (no embedding index required).",
        "Prefer reading recommended real files under `/workspace/...` before broad ls/glob.",
        f"- scanned_files: {scanned_files}",
        f"- scope_filtered: {'yes' if scoped else 'no'}",
    ]
    if tokens:
        lines.append("- goal_tokens: " + ", ".join(f"`{t}`" for t in tokens[:16]))
    lines.extend(["", "## Recommended reads"])
    if recommended:
        for path in recommended:
            lines.append(f"- `/workspace/{path}`")
    else:
        lines.append("- (none ranked; inspect tree below)")

    if matched:
        lines.extend(["", "## Keyword matches"])
        for item in matched:
            lines.append(
                f"- `{item['path']}` (score={item['score']}; {item.get('reason') or 'match'})"
            )
            preview = str(item.get("preview") or "").strip()
            if preview:
                lines.extend(["", "```text", preview, "```", ""])

    lines.extend(["", "## Shallow tree"])
    if tree_entries:
        for entry in tree_entries:
            lines.append(f"- `{entry}`")
    else:
        lines.append("- (empty)")
    text = "\n".join(lines).strip() + "\n"
    if len(text) > _MAX_MARKDOWN_CHARS:
        text = text[:_MAX_MARKDOWN_CHARS].rstrip() + "\n\n[truncated]\n"
    return text


def _empty_result(status: str, *, reason: str) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "status": status,
        "reason": reason,
        "scoped": False,
        "tokens": [],
        "tree": [],
        "matched_files": [],
        "recommended_reads": [],
        "markdown": f"# Workspace Inventory\n\nstatus: {status}\nreason: {reason}\n",
        "scanned_files": 0,
    }


__all__ = [
    "build_workspace_inventory",
    "extract_goal_tokens",
]
