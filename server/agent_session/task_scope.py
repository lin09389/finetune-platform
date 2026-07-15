"""Task scope + verify-recipe helpers for complex coding runs (Phase B0).

Scope constrains exploration/edits to project-relative paths.
Verify recipes surface project test/typecheck conventions into /context.
"""
from __future__ import annotations

import json
import re
from pathlib import Path, PurePosixPath
from typing import Any

TASK_SCOPE_KEY = "task_scope"
VERIFY_RECIPE_KEY = "verify_recipe"

_MAX_SCOPE_PATHS = 12
_MAX_RECIPE_CHARS = 12_000
_VERIFY_DOC_CANDIDATES = (
    "VERIFY.md",
    "verify.md",
    "docs/VERIFY.md",
    "docs/verify.md",
    ".finetune/verify.md",
    "CONTRIBUTING.md",
    "AGENTS.md",
)


def normalize_rel_path(raw: str) -> str:
    text = str(raw or "").strip().replace("\\", "/")
    if text.startswith("/workspace/"):
        text = text[len("/workspace/") :]
    elif text.startswith("workspace/"):
        text = text[len("workspace/") :]
    text = text.lstrip("/")
    while "//" in text:
        text = text.replace("//", "/")
    parts: list[str] = []
    for part in text.split("/"):
        if part in {"", "."}:
            continue
        if part == "..":
            raise ValueError("scope path must not contain '..'")
        parts.append(part)
    return "/".join(parts)


def resolve_scope_paths(
    project_path: str | Path | None,
    paths: list[str] | None,
    *,
    require_existing: bool = True,
) -> list[str]:
    """Validate and normalize scope paths under the project root."""
    if not paths:
        return []
    if not project_path:
        raise ValueError("project_path is required when setting task scope")
    root = Path(project_path).resolve()
    if not root.is_dir():
        raise ValueError(f"project_path is not a directory: {root}")

    resolved: list[str] = []
    seen: set[str] = set()
    for raw in paths[:_MAX_SCOPE_PATHS]:
        rel = normalize_rel_path(str(raw))
        if not rel or rel in seen:
            continue
        candidate = (root / Path(*rel.split("/"))).resolve()
        try:
            candidate.relative_to(root)
        except ValueError as exc:
            raise ValueError(f"scope path escapes project root: {raw}") from exc
        if require_existing and not candidate.exists():
            raise ValueError(f"scope path does not exist: {rel}")
        seen.add(rel)
        resolved.append(rel)
    return resolved


def build_task_scope(
    project_path: str | Path | None,
    *,
    paths: list[str] | None = None,
    notes: str | None = None,
    require_existing: bool = True,
) -> dict[str, Any] | None:
    normalized = resolve_scope_paths(project_path, paths, require_existing=require_existing)
    note = str(notes or "").strip()[:500]
    if not normalized and not note:
        return None
    return {
        "schema_version": 1,
        "paths": normalized,
        "notes": note or None,
    }


def apply_task_scope_to_metadata(
    metadata: dict[str, Any],
    project_path: str | Path | None,
    *,
    paths: list[str] | None = None,
    notes: str | None = None,
    clear: bool = False,
) -> dict[str, Any]:
    next_metadata = dict(metadata)
    if clear:
        next_metadata.pop(TASK_SCOPE_KEY, None)
        return next_metadata
    scope = build_task_scope(project_path, paths=paths, notes=notes)
    if scope is None:
        next_metadata.pop(TASK_SCOPE_KEY, None)
    else:
        next_metadata[TASK_SCOPE_KEY] = scope
    return next_metadata


def get_task_scope(metadata: dict[str, Any] | None) -> dict[str, Any] | None:
    raw = (metadata or {}).get(TASK_SCOPE_KEY)
    return dict(raw) if isinstance(raw, dict) else None


def path_in_scope(rel_or_workspace_path: str, scope: dict[str, Any] | None) -> bool:
    """True if path is inside scope (or scope is empty/unrestricted)."""
    if not scope:
        return True
    paths = [str(p) for p in (scope.get("paths") or []) if str(p).strip()]
    if not paths:
        return True
    try:
        rel = normalize_rel_path(rel_or_workspace_path)
    except ValueError:
        return False
    if not rel:
        # bare workspace root writes — only allowed if scope includes "."
        return "." in paths or "" in paths
    for allowed in paths:
        if allowed in {".", ""}:
            return True
        if rel == allowed or rel.startswith(allowed.rstrip("/") + "/"):
            return True
    return False


def format_scope_prompt_section(scope: dict[str, Any] | None) -> str:
    if not scope:
        return ""
    paths = [str(p) for p in (scope.get("paths") or []) if str(p).strip()]
    notes = str(scope.get("notes") or "").strip()
    if not paths and not notes:
        return ""
    lines = [
        "【任务范围 Scope（平台强制）】",
        "本会话应优先在下列路径内探索与修改；默认不要改范围外文件。",
        "读取范围外仅用于理解依赖；写入范围外会被平台拦截。",
    ]
    if paths:
        lines.append("允许路径（相对项目根 / 对应 /workspace/...）：")
        for path in paths:
            lines.append(f"- `{path}` → `/workspace/{path}`" if path not in {".", ""} else "- `.`（整个工作区）")
    if notes:
        lines.append(f"范围说明：{notes}")
    return "\n".join(lines)


def discover_verify_recipe(project_path: str | Path | None) -> dict[str, Any] | None:
    """Best-effort project verify conventions for Agent consumption."""
    if not project_path:
        return None
    root = Path(project_path)
    if not root.is_dir():
        return None

    sections: list[str] = []
    sources: list[str] = []
    commands: list[str] = []

    for rel in _VERIFY_DOC_CANDIDATES:
        path = root / rel
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        snippet = _extract_verify_relevant(text, filename=rel)
        if not snippet:
            continue
        sources.append(rel)
        sections.append(f"### 来源：`{rel}`\n\n{snippet.strip()}")
        if len("\n\n".join(sections)) >= _MAX_RECIPE_CHARS:
            break

    pkg = root / "package.json"
    if pkg.is_file():
        try:
            data = json.loads(pkg.read_text(encoding="utf-8", errors="replace"))
        except (OSError, json.JSONDecodeError):
            data = {}
        scripts = data.get("scripts") if isinstance(data, dict) else None
        if isinstance(scripts, dict):
            preferred = [
                "typecheck",
                "test",
                "test:unit",
                "lint",
                "build",
            ]
            found: list[str] = []
            for key in preferred:
                if key in scripts:
                    found.append(f"npm run {key}")
            # also catch vitest/jest direct
            for key, value in scripts.items():
                if key in preferred:
                    continue
                blob = f"{key} {value}".lower()
                if any(token in blob for token in ("vitest", "jest", "pytest", "eslint", "tsc")):
                    found.append(f"npm run {key}")
            if found:
                sources.append("package.json")
                commands.extend(found[:8])
                sections.append(
                    "### 来源：`package.json` scripts\n\n"
                    + "\n".join(f"- `{cmd}`" for cmd in found[:8])
                )

    if (root / "pyproject.toml").is_file() or (root / "pytest.ini").is_file() or (root / "setup.cfg").is_file():
        sources.append("python-test-layout")
        commands.append("python -m pytest -q")
        sections.append(
            "### Python 测试\n\n"
            "- 检测到 Python 项目布局，优先：`python -m pytest -q`（或针对改动模块缩小路径）\n"
            "- 语法快检：`python -m py_compile <file.py>`"
        )

    if (root / "server").is_dir() and (root / "client").is_dir():
        sections.append(
            "### 本仓库布局提示（finetune-platform）\n\n"
            "- 后端：`server/`，测试常在 `server/tests/`，命令示例："
            "`python -m pytest server/tests/<related>.py -q`\n"
            "- 前端：`client/`，常用：`cd client && npm run typecheck` / `npx vitest run <path>`\n"
            "- 改动后端时优先跑相关 pytest；改动前端时优先 typecheck/vitest，避免无目标全仓扫描。"
        )
        if "repo-layout" not in sources:
            sources.append("repo-layout")

    if not sections:
        return None

    body = "# 项目验证菜谱（平台发现）\n\n" + "\n\n".join(sections)
    body = body[:_MAX_RECIPE_CHARS]
    # de-dupe commands preserve order
    unique_commands: list[str] = []
    for cmd in commands:
        if cmd not in unique_commands:
            unique_commands.append(cmd)

    return {
        "schema_version": 1,
        "sources": sources,
        "commands": unique_commands[:12],
        "markdown": body,
    }


def format_verify_recipe_prompt_section(recipe: dict[str, Any] | None) -> str:
    if not recipe:
        return ""
    commands = [str(c) for c in (recipe.get("commands") or []) if str(c).strip()]
    sources = [str(s) for s in (recipe.get("sources") or []) if str(s).strip()]
    lines = [
        "【验证菜谱（平台注入）】",
        "修改代码后必须按项目约定做验证，不要编造不存在的脚本。",
        "完整菜谱见虚拟文件 `/context/verify-recipe.md`（可用 read_file 打开）。",
    ]
    if commands:
        lines.append("推荐命令（按需选相关项，优先缩小到改动路径）：")
        for cmd in commands[:8]:
            lines.append(f"- `{cmd}`")
    if sources:
        lines.append("菜谱来源：" + "、".join(f"`{s}`" for s in sources[:8]))
    return "\n".join(lines)


def _extract_verify_relevant(text: str, *, filename: str) -> str:
    """Keep docs small: prefer sections about test/verify/lint/build."""
    raw = text.strip()
    if not raw:
        return ""
    lower_name = filename.lower()
    if lower_name.endswith("verify.md") or "verify" in lower_name:
        return raw[:4000]

    # AGENTS.md / CONTRIBUTING: pull matching sections
    section_pattern = re.compile(
        r"(?ms)^(#{1,3}\s+.*(?:test|testing|verify|验证|lint|typecheck|ci|构建|测试).*)\n(.*?)(?=^#{1,3}\s|\Z)"
    )
    chunks: list[str] = []
    for match in section_pattern.finditer(raw):
        chunks.append((match.group(1) + "\n" + match.group(2)).strip())
        if sum(len(c) for c in chunks) > 3500:
            break
    if chunks:
        return "\n\n".join(chunks)[:4000]

    # fallback: first lines if file mentions test/verify
    if re.search(r"pytest|vitest|typecheck|npm test|验证|测试", raw, re.I):
        return raw[:2500]
    return ""


def workspace_path_to_rel(path: str) -> str:
    """Convert DeepAgents /workspace path or relative path to project-relative."""
    try:
        return normalize_rel_path(path)
    except ValueError:
        return str(path or "").strip().replace("\\", "/").lstrip("/")


__all__ = [
    "TASK_SCOPE_KEY",
    "VERIFY_RECIPE_KEY",
    "apply_task_scope_to_metadata",
    "build_task_scope",
    "discover_verify_recipe",
    "format_scope_prompt_section",
    "format_verify_recipe_prompt_section",
    "get_task_scope",
    "normalize_rel_path",
    "path_in_scope",
    "resolve_scope_paths",
    "workspace_path_to_rel",
]
