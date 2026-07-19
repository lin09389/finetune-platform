"""Platform-owned canonical built-in tools (read / search / git-read).

These definitions are the platform's own tool surface, distinct from the
Task-5 :mod:`tool_platform.adapters.deepagents` characterization of the
installed DeepAgents built-ins.  They carry namespaced canonical names
(``workspace.*`` / ``git.*``) and DeepAgents-compatible aliases so that the
Task-9D controlled-mode cutover can map the model-visible tool names onto
these enforced implementations.

Definitions are shared and stateless (``handler=None``): per-session
``project_root`` context is bound through the Gateway ``handlers`` injection
(see :func:`make_filesystem_handlers`), keeping the registry globally
shareable.  No availability probes run.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from ..definition import ToolDefinition
from ..models import CanonicalToolMeta
from ..taxonomy import ToolKind, defaults_for_kind

_WORKSPACE_PREFIX = "/workspace/"


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


# --- I/O models ---------------------------------------------------------------


class LsInput(_StrictModel):
    path: str = "/workspace/"


class LsOutput(_StrictModel):
    entries: tuple[str, ...] = ()


class ReadFileInput(_StrictModel):
    file_path: str
    offset: int = Field(default=0, ge=0)
    limit: int = Field(default=2000, ge=1, le=100_000)


class ReadFileOutput(_StrictModel):
    content: str
    line_count: int = Field(default=0, ge=0)


class GlobInput(_StrictModel):
    pattern: str
    path: str = "/workspace/"


class GlobOutput(_StrictModel):
    matches: tuple[str, ...] = ()


class GrepInput(_StrictModel):
    pattern: str
    path: str = "/workspace/"
    glob: str | None = None
    output_mode: Literal["files_with_matches", "content", "count"] = "files_with_matches"


class GrepOutput(_StrictModel):
    matches: tuple[str, ...] = ()
    count: int = Field(default=0, ge=0)


class WriteFileInput(_StrictModel):
    file_path: str
    content: str


class WriteFileOutput(_StrictModel):
    bytes_written: int = Field(default=0, ge=0)
    path: str


class EditFileInput(_StrictModel):
    file_path: str
    old_string: str
    new_string: str
    replace_all: bool = False


class EditFileOutput(_StrictModel):
    replacements: int = Field(default=0, ge=0)
    path: str


# --- path isolation -----------------------------------------------------------


class WorkspacePathError(ValueError):
    """Raised when a virtual path escapes the workspace root (fail-closed)."""


def resolve_workspace_path(virtual_path: str, project_root: str | Path) -> Path:
    """Map a ``/workspace/...`` virtual path to a real path under project_root.

    Fails closed for any path that is not under ``/workspace/`` or that escapes
    the project root after normalization (e.g. ``/workspace/../etc/passwd``).
    """
    if not isinstance(virtual_path, str) or not virtual_path.startswith(_WORKSPACE_PREFIX):
        raise WorkspacePathError(f"path must be under {_WORKSPACE_PREFIX!r}: {virtual_path!r}")
    relative = virtual_path[len(_WORKSPACE_PREFIX) :]
    if not relative:
        return Path(project_root).resolve()
    candidate = (Path(project_root) / relative).resolve()
    root = Path(project_root).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise WorkspacePathError(f"path escapes workspace root: {virtual_path!r}") from exc
    return candidate


# --- definitions --------------------------------------------------------------


def _meta(canonical_name: str, kind: ToolKind) -> CanonicalToolMeta:
    defaults = defaults_for_kind(kind)
    return CanonicalToolMeta(
        canonical_name=canonical_name,
        kind=kind,
        side_effects=defaults.side_effects,
        risk=defaults.risk,
        execution_location=defaults.execution_location,
        display_name=canonical_name,
        description=f"Platform-enforced {canonical_name} tool.",
        idempotent=True,
        cacheable=True,
    )


def _mutable_meta(canonical_name: str, kind: ToolKind) -> CanonicalToolMeta:
    """Meta for workspace-mutating tools (not idempotent, not cacheable)."""
    defaults = defaults_for_kind(kind)
    return CanonicalToolMeta(
        canonical_name=canonical_name,
        kind=kind,
        side_effects=defaults.side_effects,
        risk=defaults.risk,
        execution_location=defaults.execution_location,
        display_name=canonical_name,
        description=f"Platform-enforced {canonical_name} tool.",
        idempotent=False,
        cacheable=False,
    )


def _definition(canonical_name: str, kind: ToolKind, alias: str, input_model, output_model) -> ToolDefinition:
    return ToolDefinition(
        meta=_meta(canonical_name, kind),
        input_model=input_model,
        output_model=output_model,
        handler=None,
        aliases=(alias,),
        runtime_kinds=frozenset({"agent_session"}),
        required_capabilities=frozenset({"deepagents"}),
    )


def _mutable_definition(canonical_name: str, kind: ToolKind, alias: str, input_model, output_model) -> ToolDefinition:
    return ToolDefinition(
        meta=_mutable_meta(canonical_name, kind),
        input_model=input_model,
        output_model=output_model,
        handler=None,
        aliases=(alias,),
        runtime_kinds=frozenset({"agent_session"}),
        required_capabilities=frozenset({"deepagents"}),
    )


FILESYSTEM_DEFINITIONS: tuple[ToolDefinition, ...] = (
    _definition("workspace.ls", ToolKind.LIST_DIR, "ls", LsInput, LsOutput),
    _definition("workspace.read_file", ToolKind.READ, "read_file", ReadFileInput, ReadFileOutput),
    _definition("workspace.glob", ToolKind.SEARCH, "glob", GlobInput, GlobOutput),
    _definition("workspace.grep", ToolKind.SEARCH, "grep", GrepInput, GrepOutput),
)


WRITE_DEFINITIONS: tuple[ToolDefinition, ...] = (
    _mutable_definition("workspace.write_file", ToolKind.WRITE, "write_file", WriteFileInput, WriteFileOutput),
    _mutable_definition("workspace.edit_file", ToolKind.EDIT, "edit_file", EditFileInput, EditFileOutput),
)


# --- handlers (per-session project_root closure) ------------------------------


def make_filesystem_handlers(project_root: str | Path) -> dict[str, Any]:
    """Return ``{canonical_name: async handler}`` bound to ``project_root``."""
    root = Path(project_root).resolve()

    async def ls(request: LsInput) -> LsOutput:
        target = resolve_workspace_path(request.path, root)
        if not target.exists():
            raise FileNotFoundError(f"not found: {request.path}")
        entries = tuple(sorted(item.name for item in target.iterdir())) if target.is_dir() else ()
        return LsOutput(entries=entries)

    async def read_file(request: ReadFileInput) -> ReadFileOutput:
        target = resolve_workspace_path(request.file_path, root)
        if not target.is_file():
            raise FileNotFoundError(f"not a file: {request.file_path}")
        text = target.read_text(encoding="utf-8", errors="replace")
        lines = text.splitlines()
        selected = lines[request.offset : request.offset + request.limit]
        content = "\n".join(selected)
        return ReadFileOutput(content=content, line_count=len(selected))

    async def glob(request: GlobInput) -> GlobOutput:
        base = resolve_workspace_path(request.path, root)
        if not base.exists():
            return GlobOutput(matches=())
        matches = tuple(
            str(p.relative_to(root)).replace("\\", "/")
            for p in sorted(base.rglob(request.pattern))
            if p.is_file()
        )
        return GlobOutput(matches=matches)

    async def grep(request: GrepInput) -> GrepOutput:
        base = resolve_workspace_path(request.path, root)
        if not base.exists():
            return GrepOutput(matches=(), count=0)
        try:
            regex = re.compile(request.pattern)
        except re.error as exc:
            raise ValueError(f"invalid regex: {exc}") from exc
        files = [p for p in base.rglob(request.glob or "*") if p.is_file()]
        file_matches: list[str] = []
        content_lines: list[str] = []
        total = 0
        for path in sorted(files):
            rel = str(path.relative_to(root)).replace("\\", "/")
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            hit_lines = [line for line in text.splitlines() if regex.search(line)]
            if not hit_lines:
                continue
            total += len(hit_lines)
            if request.output_mode == "files_with_matches":
                file_matches.append(rel)
            elif request.output_mode == "content":
                for line in hit_lines:
                    content_lines.append(f"{rel}:{line}")
            elif request.output_mode == "count":
                file_matches.append(rel)
        if request.output_mode == "content":
            return GrepOutput(matches=tuple(content_lines), count=total)
        return GrepOutput(matches=tuple(file_matches), count=total)

    return {
        "workspace.ls": ls,
        "workspace.read_file": read_file,
        "workspace.glob": glob,
        "workspace.grep": grep,
    }


def _atomic_write(target: Path, content: str) -> int:
    """Write ``content`` to ``target`` atomically (tmp + os.replace)."""
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(target.name + ".tmp")
    encoded = content.encode("utf-8")
    tmp.write_bytes(encoded)
    os.replace(tmp, target)
    return len(encoded)


def make_write_handlers(project_root: str | Path) -> dict[str, Any]:
    """Return ``{canonical_name: async handler}`` for workspace-mutating tools."""
    root = Path(project_root).resolve()

    async def write_file(request: WriteFileInput) -> WriteFileOutput:
        target = resolve_workspace_path(request.file_path, root)
        written = _atomic_write(target, request.content)
        return WriteFileOutput(bytes_written=written, path=request.file_path)

    async def edit_file(request: EditFileInput) -> EditFileOutput:
        target = resolve_workspace_path(request.file_path, root)
        if not target.is_file():
            raise FileNotFoundError(f"not a file: {request.file_path}")
        text = target.read_text(encoding="utf-8", errors="replace")
        if request.replace_all:
            count = text.count(request.old_string)
            if count == 0:
                raise ValueError("old_string not found")
            new_text = text.replace(request.old_string, request.new_string)
        else:
            count = text.count(request.old_string)
            if count == 0:
                raise ValueError("old_string not found")
            if count > 1:
                raise ValueError("old_string is not unique; set replace_all=True")
            new_text = text.replace(request.old_string, request.new_string, 1)
        _atomic_write(target, new_text)
        return EditFileOutput(replacements=count, path=request.file_path)

    return {
        "workspace.write_file": write_file,
        "workspace.edit_file": edit_file,
    }


__all__ = [
    "FILESYSTEM_DEFINITIONS",
    "WRITE_DEFINITIONS",
    "EditFileInput",
    "EditFileOutput",
    "GlobInput",
    "GlobOutput",
    "GrepInput",
    "GrepOutput",
    "LsInput",
    "LsOutput",
    "ReadFileInput",
    "ReadFileOutput",
    "WorkspacePathError",
    "WriteFileInput",
    "WriteFileOutput",
    "make_filesystem_handlers",
    "make_write_handlers",
    "resolve_workspace_path",
]
