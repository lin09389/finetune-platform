from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Iterable


WORKSPACE_METADATA_FILE = Path("data/workspaces/metadata.json")
WORKSPACE_ROOT_ENV_KEYS = ("WORKSPACE_ROOT", "PROJECT_ROOT")


def load_workspace_metadata() -> dict[str, dict]:
    if not WORKSPACE_METADATA_FILE.exists():
        return {}
    try:
        data = json.loads(WORKSPACE_METADATA_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(data, dict):
        return {}
    return {key: value for key, value in data.items() if isinstance(value, dict)}


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


def get_allowed_workspace_roots(default_roots: Iterable[Path] | None = None) -> set[Path]:
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
