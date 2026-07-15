"""Multi-file edit completion helpers (Phase B4, lean).

Tracks coordinated multi-file writes and companion test/type hints without
rebuilding the Agent loop. Pure functions over session metadata + filesystem.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

DOCUMENT_EXTENSIONS = {".md", ".mdx", ".rst", ".txt", ".adoc"}
_MULTI_FILE_THRESHOLD = 2
_MAX_COMPANIONS = 8
_MAX_PATHS = 12


def is_document_path(path: str | None) -> bool:
    text = str(path or "").replace("\\", "/").rstrip("/")
    if not text:
        return False
    name = text.rsplit("/", 1)[-1]
    # extension-less docs
    if name.lower() in {"readme", "license", "changelog", "authors"}:
        return True
    suffix = Path(name).suffix.lower()
    return suffix in DOCUMENT_EXTENSIONS


def normalize_workspace_path(path: str | None) -> str:
    text = str(path or "").replace("\\", "/").strip()
    if text.startswith("/workspace/"):
        text = text[len("/workspace/") :]
    return text.lstrip("/")


def source_written_paths(metadata: dict[str, Any] | None) -> list[str]:
    """Non-document written paths from trajectory_guard (order preserved)."""
    meta = dict(metadata or {})
    guard = meta.get("trajectory_guard") if isinstance(meta.get("trajectory_guard"), dict) else {}
    raw: list[str] = []
    writes = guard.get("writes")
    if isinstance(writes, dict):
        raw = [str(k) for k in writes.keys() if str(k).strip()]
    elif isinstance(guard.get("written_paths"), list):
        raw = [str(p) for p in guard.get("written_paths") or [] if str(p).strip()]
    ordered: list[str] = []
    seen: set[str] = set()
    for item in raw:
        key = normalize_workspace_path(item) or item
        if not key or key in seen or is_document_path(key):
            continue
        seen.add(key)
        ordered.append(key)
    return ordered


def verified_path_set(metadata: dict[str, Any] | None) -> set[str]:
    meta = dict(metadata or {})
    guard = meta.get("trajectory_guard") if isinstance(meta.get("trajectory_guard"), dict) else {}
    values = guard.get("verified_paths") or []
    out: set[str] = set()
    if isinstance(values, dict):
        values = list(values.keys())
    for item in values:
        key = normalize_workspace_path(str(item))
        if key:
            out.add(key)
    return out


def read_path_set(metadata: dict[str, Any] | None) -> set[str]:
    meta = dict(metadata or {})
    guard = meta.get("trajectory_guard") if isinstance(meta.get("trajectory_guard"), dict) else {}
    values = guard.get("reads") or guard.get("read_paths") or []
    out: set[str] = set()
    if isinstance(values, dict):
        values = list(values.keys())
    for item in values:
        key = normalize_workspace_path(str(item))
        if key:
            out.add(key)
    return out


def companion_candidates_for_path(rel_path: str) -> list[str]:
    """Heuristic companion test/type paths for a written source file."""
    rel = normalize_workspace_path(rel_path)
    if not rel or is_document_path(rel):
        return []
    path = Path(rel)
    stem = path.stem
    parent = path.parent.as_posix() if str(path.parent) not in {".", ""} else ""
    suffix = path.suffix.lower()
    names: list[str] = []
    if suffix == ".py":
        names.extend(
            [
                f"test_{stem}.py",
                f"{stem}_test.py",
                f"tests/test_{stem}.py",
                f"test/test_{stem}.py",
            ]
        )
        if parent and parent != ".":
            names.extend(
                [
                    f"{parent}/test_{stem}.py",
                    f"{parent}/tests/test_{stem}.py",
                    f"tests/{parent}/test_{stem}.py",
                ]
            )
    elif suffix in {".ts", ".tsx", ".js", ".jsx"}:
        names.extend(
            [
                f"{stem}.test{suffix}",
                f"{stem}.spec{suffix}",
                f"{stem}.test.ts",
                f"{stem}.test.tsx",
                f"{stem}.spec.ts",
                f"__tests__/{stem}.test{suffix}",
            ]
        )
        if parent and parent != ".":
            names.extend(
                [
                    f"{parent}/{stem}.test{suffix}",
                    f"{parent}/{stem}.spec{suffix}",
                    f"{parent}/__tests__/{stem}.test{suffix}",
                ]
            )
    # de-dupe
    ordered: list[str] = []
    seen: set[str] = set()
    for name in names:
        key = normalize_workspace_path(name)
        if not key or key == rel or key in seen:
            continue
        seen.add(key)
        ordered.append(key)
    return ordered


def find_existing_companions(
    project_path: str | Path | None,
    written_paths: list[str],
    *,
    max_items: int = _MAX_COMPANIONS,
) -> list[str]:
    if not project_path:
        return []
    root = Path(project_path)
    if not root.is_dir():
        return []
    found: list[str] = []
    seen: set[str] = set()
    written_set = {normalize_workspace_path(p) for p in written_paths}
    for written in written_paths:
        for candidate in companion_candidates_for_path(written):
            if candidate in written_set or candidate in seen:
                continue
            if (root / Path(*candidate.split("/"))).is_file():
                seen.add(candidate)
                found.append(candidate)
                if len(found) >= max_items:
                    return found
    return found


def build_multi_file_state(
    metadata: dict[str, Any] | None,
    *,
    project_path: str | Path | None = None,
) -> dict[str, Any]:
    """Snapshot multi-file coordination facts for gate / card / correction prompts."""
    meta = dict(metadata or {})
    if project_path is None:
        workspace = meta.get("workspace") if isinstance(meta.get("workspace"), dict) else {}
        project_path = workspace.get("path") or meta.get("project_path")

    written = source_written_paths(meta)
    verified = verified_path_set(meta)
    reads = read_path_set(meta)
    is_multi = len(written) >= _MULTI_FILE_THRESHOLD
    unverified = [p for p in written if p not in verified]
    path_verify_ok = (not written) or (set(written).issubset(verified))
    companions = find_existing_companions(project_path, written)
    companions_unread = [p for p in companions if p not in reads]

    return {
        "schema_version": 1,
        "is_multi_file": is_multi,
        "source_write_count": len(written),
        "written_paths": written[:_MAX_PATHS],
        "verified_paths": sorted(verified)[:_MAX_PATHS],
        "unverified_paths": unverified[:_MAX_PATHS],
        "path_verify_ok": path_verify_ok,
        "companion_paths": companions[:_MAX_COMPANIONS],
        "companions_unread": companions_unread[:_MAX_COMPANIONS],
    }


def apply_multi_file_completion_rules(
    gate: dict[str, Any],
    multi: dict[str, Any],
) -> dict[str, Any]:
    """Tighten completion gate for multi-file edits (path-level verify).

    Single-file behavior is unchanged. Multi-file requires every non-doc
    written path to appear in trajectory verified_paths (not only a later
    verification sequence flag).
    """
    next_gate = dict(gate)
    next_gate["multi_file"] = {
        "is_multi_file": bool(multi.get("is_multi_file")),
        "source_write_count": int(multi.get("source_write_count") or 0),
        "unverified_paths": list(multi.get("unverified_paths") or []),
        "path_verify_ok": bool(multi.get("path_verify_ok")),
        "companions_unread": list(multi.get("companions_unread") or []),
        "companion_paths": list(multi.get("companion_paths") or []),
    }

    if not multi.get("is_multi_file"):
        # Soft companion hint only for multi-file; single-file keeps existing gate.
        return next_gate

    gaps = list(next_gate.get("gaps") or [])
    summary = str(next_gate.get("summary") or "")

    if multi.get("unverified_paths") or not multi.get("path_verify_ok"):
        if "multi_file_path_verify_required" not in gaps:
            gaps.append("multi_file_path_verify_required")
        # Force verify_ok false for multi-file incomplete path coverage.
        next_gate["verify_ok"] = 0
        if next_gate.get("status") == "completed":
            next_gate["completed_ok"] = False
        if "验证通过" in summary:
            summary = summary.replace("验证通过", "多文件路径级验证未齐")
        elif "验证未通过" not in summary and "未验证" not in summary:
            summary = (summary + "；多文件路径级验证未齐") if summary else "多文件路径级验证未齐"

    # Companion reads are advisory gaps (do not flip completed_ok alone).
    if multi.get("companions_unread"):
        if "multi_file_companions_unread" not in gaps:
            gaps.append("multi_file_companions_unread")
        unread = "、".join(f"`{p}`" for p in (multi.get("companions_unread") or [])[:4])
        summary = (summary + f"；建议阅读关联文件 {unread}") if summary else f"建议阅读关联文件 {unread}"

    next_gate["gaps"] = gaps
    next_gate["summary"] = summary
    return next_gate


def format_multi_file_card_lines(multi: dict[str, Any] | None) -> list[str]:
    if not multi or not multi.get("is_multi_file"):
        return []
    n = int(multi.get("source_write_count") or 0)
    lines = [f"- **多文件编辑（B4）**：已写源码 {n} 个路径"]
    unverified = list(multi.get("unverified_paths") or [])
    if unverified:
        shown = "、".join(f"`{p}`" for p in unverified[:6])
        lines.append(f"- 多文件未路径级验证：{shown}（收尾前须一次覆盖全部改动的验证）")
    else:
        lines.append("- 多文件路径级验证：已覆盖全部已写源码路径")
    companions = list(multi.get("companions_unread") or [])
    if companions:
        shown = "、".join(f"`{p}`" for p in companions[:4])
        lines.append(f"- 建议阅读关联测试/规格（尚未读）：{shown}")
    return lines


def multi_file_correction_blurb(multi: dict[str, Any] | None) -> str:
    if not multi or not multi.get("is_multi_file"):
        return ""
    parts = [
        f"多文件编辑：已写 {int(multi.get('source_write_count') or 0)} 个源码路径。",
        "验证必须覆盖全部改动路径（路径级），不能只检查其中一个文件。",
    ]
    unverified = list(multi.get("unverified_paths") or [])
    if unverified:
        parts.append("未覆盖路径：" + ", ".join(f"`{p}`" for p in unverified[:8]))
    companions = list(multi.get("companions_unread") or [])
    if companions:
        parts.append("建议先读关联文件：" + ", ".join(f"`{p}`" for p in companions[:6]))
    return " ".join(parts)


__all__ = [
    "apply_multi_file_completion_rules",
    "build_multi_file_state",
    "companion_candidates_for_path",
    "find_existing_companions",
    "format_multi_file_card_lines",
    "is_document_path",
    "multi_file_correction_blurb",
    "normalize_workspace_path",
    "source_written_paths",
]
