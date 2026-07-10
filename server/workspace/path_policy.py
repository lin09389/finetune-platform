"""Shared Agent / Workspace project path allowlist and validation.

Single source of truth for:
- default project path
- allowed workspace roots (defaults + env + registered workspaces)
- structured validation outcomes used by HTTP and Agent session create
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Literal

from workspace.local_paths import get_allowed_workspace_roots, load_workspace_metadata

ErrorCode = Literal["path_missing", "path_not_dir", "path_not_allowed"]


@dataclass(frozen=True)
class AllowedRoot:
    path: str
    source: str
    label: str | None = None

    def as_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"path": self.path, "source": self.source}
        if self.label:
            payload["label"] = self.label
        return payload


@dataclass(frozen=True)
class PathValidationResult:
    ok: bool
    resolved_path: str | None
    allowed: bool
    exists: bool
    is_dir: bool
    needs_register: bool
    message: str | None
    error_code: ErrorCode | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "resolved_path": self.resolved_path,
            "allowed": self.allowed,
            "exists": self.exists,
            "is_dir": self.is_dir,
            "needs_register": self.needs_register,
            "message": self.message,
            "error_code": self.error_code,
        }


def resolve_default_project_path(settings: Any | None = None) -> str:
    """Return the platform default Agent project root as an absolute path string."""
    if settings is None:
        from core.config import settings as app_settings

        settings = app_settings

    env_path = getattr(settings, "agent_default_project_path", None)
    if env_path:
        candidate = Path(str(env_path)).expanduser()
        if candidate.exists() and candidate.is_dir():
            return str(candidate.resolve())

    base_dir = Path(getattr(settings, "base_dir", Path.cwd())).resolve()
    workspace = base_dir.parent if base_dir.name == "server" else base_dir
    return str(workspace)


def _base_context_roots(settings: Any) -> set[Path]:
    default_root = Path(resolve_default_project_path(settings)).resolve()
    base_dir = Path(getattr(settings, "base_dir", Path.cwd())).resolve()
    roots = {default_root, base_dir}
    try:
        roots.add(Path.cwd().resolve())
    except Exception:
        pass
    return roots


def _source_for_root(path: Path, settings: Any, context_roots: set[Path]) -> str:
    default_root = Path(resolve_default_project_path(settings)).resolve()
    base_dir = Path(getattr(settings, "base_dir", Path.cwd())).resolve()
    if path == default_root:
        return "default"
    if path == base_dir:
        return "base_dir"
    try:
        if path == Path.cwd().resolve():
            return "cwd"
    except Exception:
        pass
    import os

    for env_key in ("WORKSPACE_ROOT", "PROJECT_ROOT"):
        raw = os.getenv(env_key)
        if not raw:
            continue
        try:
            if Path(raw).expanduser().resolve() == path:
                return "env"
        except Exception:
            continue
    # Registered workspace metadata
    for payload in load_workspace_metadata().values():
        raw = str(payload.get("local_path") or "").strip()
        if not raw:
            continue
        try:
            if Path(raw).expanduser().resolve() == path:
                return "registered"
        except Exception:
            continue
    if path in context_roots:
        return "default"
    return "other"


def list_allowed_roots(
    settings: Any | None = None,
    *,
    extra_roots: Iterable[Path] | None = None,
) -> list[AllowedRoot]:
    """Return allowed roots with source labels for API/UI display."""
    if settings is None:
        from core.config import settings as app_settings

        settings = app_settings

    context = _base_context_roots(settings)
    if extra_roots:
        context.update(Path(p).resolve() for p in extra_roots)
    roots = sorted(get_allowed_workspace_roots(context), key=lambda p: str(p).lower())
    items: list[AllowedRoot] = []
    for root in roots:
        source = _source_for_root(root, settings, context)
        label = root.name or str(root)
        items.append(AllowedRoot(path=str(root), source=source, label=label))
    return items


def _is_under_allowed(resolved: Path, allowed_roots: set[Path]) -> bool:
    for allowed in allowed_roots:
        try:
            if resolved == allowed or resolved.is_relative_to(allowed):
                return True
        except (OSError, ValueError):
            continue
    return False


def validate_agent_project_path(
    path: str | None,
    settings: Any | None = None,
    *,
    extra_roots: Iterable[Path] | None = None,
) -> PathValidationResult:
    """Validate a candidate project path without raising.

    Empty/None path resolves to the default project path (always ok when default exists).
    """
    if settings is None:
        from core.config import settings as app_settings

        settings = app_settings

    if not path or not str(path).strip():
        default_path = resolve_default_project_path(settings)
        default = Path(default_path)
        return PathValidationResult(
            ok=True,
            resolved_path=default_path,
            allowed=True,
            exists=default.exists(),
            is_dir=default.is_dir() if default.exists() else False,
            needs_register=False,
            message=None,
            error_code=None,
        )

    try:
        resolved = Path(str(path).strip()).expanduser().resolve()
    except Exception:
        return PathValidationResult(
            ok=False,
            resolved_path=None,
            allowed=False,
            exists=False,
            is_dir=False,
            needs_register=False,
            message="路径无效，无法解析。",
            error_code="path_missing",
        )

    if not resolved.exists():
        return PathValidationResult(
            ok=False,
            resolved_path=str(resolved),
            allowed=False,
            exists=False,
            is_dir=False,
            needs_register=False,
            message="路径不存在。",
            error_code="path_missing",
        )
    if not resolved.is_dir():
        return PathValidationResult(
            ok=False,
            resolved_path=str(resolved),
            allowed=False,
            exists=True,
            is_dir=False,
            needs_register=False,
            message="路径必须是目录。",
            error_code="path_not_dir",
        )

    context = _base_context_roots(settings)
    if extra_roots:
        context.update(Path(p).resolve() for p in extra_roots)
    allowed_roots = get_allowed_workspace_roots(context)
    if _is_under_allowed(resolved, allowed_roots):
        return PathValidationResult(
            ok=True,
            resolved_path=str(resolved),
            allowed=True,
            exists=True,
            is_dir=True,
            needs_register=False,
            message=None,
            error_code=None,
        )

    root_list = ", ".join(sorted(str(p) for p in allowed_roots)) or "(无)"
    return PathValidationResult(
        ok=False,
        resolved_path=str(resolved),
        allowed=False,
        exists=True,
        is_dir=True,
        needs_register=True,
        message=(
            "路径不在允许的工作区根内。可先将该目录登记为工作区，或选择以下根下的子目录："
            f"{root_list}"
        ),
        error_code="path_not_allowed",
    )


def require_valid_project_path(
    path: str | None,
    settings: Any | None = None,
    *,
    extra_roots: Iterable[Path] | None = None,
) -> str:
    """Validate and return resolved path, or raise ValueError (Agent session create)."""
    result = validate_agent_project_path(path, settings, extra_roots=extra_roots)
    if result.ok and result.resolved_path:
        return result.resolved_path
    raise ValueError(result.message or "project_path is invalid")
