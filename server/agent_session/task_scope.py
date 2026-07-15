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


def _rel_paths(paths: list[str] | None) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for raw in paths or []:
        try:
            rel = workspace_path_to_rel(str(raw))
        except Exception:
            rel = str(raw or "").strip().replace("\\", "/").lstrip("/")
        if not rel or rel in seen:
            continue
        seen.add(rel)
        out.append(rel)
    return out


def recommend_verify_commands(
    *,
    written_paths: list[str] | None,
    recipe: dict[str, Any] | None = None,
    project_path: str | Path | None = None,
    scope: dict[str, Any] | None = None,
    max_commands: int = 6,
) -> dict[str, Any]:
    """Phase B2: pick focused verify commands from changed paths + recipe.

    Prefer path-narrowed checks over full-repo scans. Recipe commands are used
    as stack hints when they match the changed file kinds.
    """
    paths = _rel_paths(written_paths)
    # If no writes yet, fall back to scope paths for "what we will likely touch".
    if not paths and scope:
        paths = _rel_paths([str(p) for p in (scope.get("paths") or [])])

    root = Path(project_path).resolve() if project_path else None
    recipe_commands = [str(c).strip() for c in ((recipe or {}).get("commands") or []) if str(c).strip()]

    has_py = any(p.endswith(".py") or "/tests/" in f"/{p}/" for p in paths)
    has_ts = any(p.endswith((".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs")) for p in paths)
    has_client = any(p.startswith("client/") or "/client/" in f"/{p}/" for p in paths)
    has_server = any(p.startswith("server/") or "/server/" in f"/{p}/" for p in paths)
    # pure docs
    doc_ext = {".md", ".txt", ".rst"}
    only_docs = bool(paths) and all(Path(p).suffix.lower() in doc_ext for p in paths)

    ranked: list[dict[str, str]] = []

    def add(command: str, reason: str, *, priority: int = 50) -> None:
        cmd = " ".join(command.strip().split())
        if not cmd:
            return
        if any(item["command"] == cmd for item in ranked):
            return
        ranked.append({"command": cmd, "reason": reason, "priority": str(priority)})

    if only_docs:
        for p in paths[:3]:
            add(f"# docs-only: re-read `{p}` after edit", "文档变更：最终重新读取确认即可", priority=10)
        ranked.sort(key=lambda item: int(item.get("priority") or 99))
        return {
            "schema_version": 1,
            "commands": [item["command"] for item in ranked[:max_commands] if not item["command"].startswith("#")],
            "items": ranked[:max_commands],
            "paths": paths[:20],
            "strategy": "docs_reread",
        }

    # Path-narrowed Python checks
    py_files = [p for p in paths if p.endswith(".py")]
    for p in py_files[:4]:
        add(f"python -m py_compile {p}", f"语法快检：`{p}`", priority=20)
        # Guess related test path
        if root is not None:
            candidates = _related_pytest_targets(root, p)
            for target in candidates[:2]:
                add(
                    f"python -m pytest {target} -q",
                    f"针对 `{p}` 的相关测试",
                    priority=15,
                )

    if has_py or has_server:
        # Prefer recipe pytest if present
        pytest_from_recipe = [c for c in recipe_commands if "pytest" in c.lower()]
        if pytest_from_recipe and not any("pytest" in i["command"] for i in ranked):
            add(pytest_from_recipe[0], "项目菜谱中的 pytest", priority=30)
        elif has_server and not any("pytest" in i["command"] for i in ranked):
            # narrow to server/tests if exists
            if root is not None and (root / "server" / "tests").is_dir():
                add("python -m pytest server/tests -q --tb=line -x", "服务端测试子集（失败即停）", priority=35)
            else:
                add("python -m pytest -q --tb=line -x", "Python 测试（失败即停）", priority=40)

    if has_ts or has_client:
        typecheck_cmds = [c for c in recipe_commands if "typecheck" in c.lower() or "tsc" in c.lower()]
        vitest_cmds = [c for c in recipe_commands if "vitest" in c.lower() or c.lower() in {"npm test", "npm run test"}]
        if typecheck_cmds:
            cmd = typecheck_cmds[0]
            if has_client and not cmd.strip().startswith("cd "):
                # client scripts usually need client cwd
                if (root is not None and (root / "client" / "package.json").is_file()) or has_client:
                    add(f"cd client && {cmd}" if "client" not in cmd else cmd, "前端类型检查", priority=18)
                else:
                    add(cmd, "类型检查（菜谱）", priority=18)
            else:
                add(cmd, "类型检查（菜谱）", priority=18)
        elif has_client:
            add("cd client && npm run typecheck", "前端类型检查", priority=18)

        # Path-narrowed vitest when possible
        ts_files = [p for p in paths if p.endswith((".ts", ".tsx"))]
        for p in ts_files[:3]:
            if p.startswith("client/"):
                rel = p[len("client/") :]
                # common pattern: Foo.tsx -> Foo.test.tsx nearby
                stem = Path(rel).stem
                parent = str(Path(rel).parent).replace("\\", "/")
                guess = f"{parent}/{stem}.test.tsx" if parent != "." else f"{stem}.test.tsx"
                add(
                    f"cd client && npx vitest run {guess}",
                    f"尝试相关 vitest：`{guess}`（若文件不存在可改跑邻近测试）",
                    priority=25,
                )
        if vitest_cmds and not any("vitest" in i["command"] for i in ranked):
            cmd = vitest_cmds[0]
            if has_client and not cmd.strip().startswith("cd "):
                add(f"cd client && {cmd}" if "client" not in cmd else cmd, "前端测试（菜谱）", priority=28)
            else:
                add(cmd, "前端测试（菜谱）", priority=28)

    # Generic recipe leftovers matching stacks
    for cmd in recipe_commands:
        low = cmd.lower()
        if has_py and any(t in low for t in ("pytest", "ruff", "mypy", "py_compile")):
            add(cmd, "菜谱命令（Python）", priority=45)
        if (has_ts or has_client) and any(t in low for t in ("typecheck", "vitest", "eslint", "lint", "tsc")):
            add(cmd, "菜谱命令（前端）", priority=45)

    if not ranked and recipe_commands:
        for cmd in recipe_commands[:3]:
            add(cmd, "通用菜谱命令", priority=50)

    if not ranked and paths:
        # last resort
        if has_py:
            add("python -m pytest -q --tb=line -x", "默认 Python 验证", priority=60)
        if has_ts or has_client:
            add("cd client && npm run typecheck", "默认前端 typecheck", priority=60)

    ranked.sort(key=lambda item: int(item.get("priority") or 99))
    items = ranked[:max_commands]
    return {
        "schema_version": 1,
        "commands": [item["command"] for item in items if not str(item["command"]).startswith("#")],
        "items": items,
        "paths": paths[:20],
        "strategy": "path_aware_v1",
    }


def _related_pytest_targets(root: Path, py_rel: str) -> list[str]:
    """Heuristic related test targets for a Python source file."""
    rel = py_rel.replace("\\", "/")
    stem = Path(rel).stem
    parent = str(Path(rel).parent).replace("\\", "/")
    candidates: list[str] = []

    guesses = [
        f"server/tests/test_{stem}.py",
        f"tests/test_{stem}.py",
        f"{parent}/test_{stem}.py",
        f"{parent}/tests/test_{stem}.py",
    ]
    # map server/foo/bar.py -> server/tests/test_bar.py already covered
    if rel.startswith("server/") and not rel.startswith("server/tests/"):
        guesses.append(f"server/tests/test_{stem}.py")

    for guess in guesses:
        path = root / guess
        if path.is_file() and guess not in candidates:
            candidates.append(guess)

    # If source itself is a test file, run it directly
    if stem.startswith("test_") or "/tests/" in f"/{rel}/":
        if rel not in candidates:
            candidates.insert(0, rel)

    return candidates[:4]


def format_verify_recommendations_section(rec: dict[str, Any] | None) -> str:
    if not rec:
        return ""
    items = rec.get("items") if isinstance(rec.get("items"), list) else []
    commands = rec.get("commands") if isinstance(rec.get("commands"), list) else []
    if not items and not commands:
        return ""
    lines = [
        "【相关验证推荐（平台，按改动路径）】",
        "请优先执行下列命令（可按路径再缩小）；不要无目标全仓乱扫。验证失败则先读真实错误与相关文件再改。",
    ]
    if items:
        for item in items[:6]:
            if not isinstance(item, dict):
                continue
            cmd = str(item.get("command") or "").strip()
            reason = str(item.get("reason") or "").strip()
            if not cmd or cmd.startswith("#"):
                continue
            if reason:
                lines.append(f"- `{cmd}`  — {reason}")
            else:
                lines.append(f"- `{cmd}`")
    else:
        for cmd in commands[:6]:
            lines.append(f"- `{cmd}`")
    paths = [str(p) for p in (rec.get("paths") or []) if str(p).strip()][:8]
    if paths:
        lines.append("关联改动：" + "、".join(f"`{p}`" for p in paths))
    return "\n".join(lines)


__all__ = [
    "TASK_SCOPE_KEY",
    "VERIFY_RECIPE_KEY",
    "apply_task_scope_to_metadata",
    "build_task_scope",
    "discover_verify_recipe",
    "format_scope_prompt_section",
    "format_verify_recipe_prompt_section",
    "format_verify_recommendations_section",
    "get_task_scope",
    "normalize_rel_path",
    "path_in_scope",
    "recommend_verify_commands",
    "resolve_scope_paths",
    "workspace_path_to_rel",
]
