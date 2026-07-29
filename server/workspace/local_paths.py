from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Iterable

WORKSPACE_METADATA_FILE = Path("data/workspaces/metadata.json")
WORKSPACE_ROOT_ENV_KEYS = ("WORKSPACE_ROOT", "PROJECT_ROOT")


def workspace_metadata_candidates() -> list[Path]:
    """Return candidate metadata paths (cwd-relative + server base_dir layouts)."""
    candidates: list[Path] = []
    seen: set[Path] = set()

    def _add(path: Path) -> None:
        try:
            resolved = path.resolve()
        except Exception:
            resolved = path
        if resolved not in seen:
            seen.add(resolved)
            candidates.append(resolved)

    _add(WORKSPACE_METADATA_FILE)
    try:
        from core.config import settings

        base = Path(settings.base_dir).resolve()
        _add(base / "data" / "workspaces" / "metadata.json")
        if base.name == "server":
            _add(base.parent / "data" / "workspaces" / "metadata.json")
    except Exception:
        pass
    return candidates


def load_workspace_metadata() -> dict[str, dict]:
    """Load and merge workspace metadata from known layout locations."""
    merged: dict[str, dict] = {}
    for path in workspace_metadata_candidates():
        if not path.exists():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(data, dict):
            continue
        for key, value in data.items():
            if isinstance(value, dict):
                merged[str(key)] = value
    return merged


def iter_registered_workspace_roots() -> list[Path]:
    roots: list[Path] = []
    for payload in load_workspace_metadata().values():
        raw = str(payload.get("local_path") or "").strip()
        if not raw:
            continue
        try:
            resolved = Path(raw).expanduser().resolve()
        except Exception:
            continue
        if resolved.exists() and resolved.is_dir() and resolved not in roots:
            roots.append(resolved)
    return roots


def get_allowed_workspace_roots(
    default_roots: Iterable[Path] | None = None,
    *,
    include_registered: bool = True,
) -> set[Path]:
    roots = {path.resolve() for path in (default_roots or [])}
    for env_key in WORKSPACE_ROOT_ENV_KEYS:
        raw = os.getenv(env_key)
        if not raw:
            continue
        try:
            resolved = Path(raw).expanduser().resolve()
        except Exception:
            continue
        if resolved.exists() and resolved.is_dir():
            roots.add(resolved)
    if include_registered:
        roots.update(iter_registered_workspace_roots())
    return roots


def normalize_local_workspace_path(raw_path: str | None) -> str | None:
    if not raw_path or not raw_path.strip():
        return None
    resolved = Path(raw_path).expanduser().resolve()
    if not resolved.exists():
        raise ValueError("local_path does not exist")
    if not resolved.is_dir():
        raise ValueError("local_path must be a directory")
    return str(resolved)
