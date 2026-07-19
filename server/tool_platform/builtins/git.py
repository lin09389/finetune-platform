"""Platform-owned canonical Git read-only tools (status / diff / log).

Read-only Git surface for the controlled tool platform.  Handlers run
``git`` as a subprocess with ``cwd`` pinned to a validated project root and a
bounded timeout; output is truncated to keep canonical events bounded.  No
write commands are exposed here.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from ..definition import ToolDefinition
from ..models import CanonicalToolMeta
from ..taxonomy import ToolKind, defaults_for_kind

_GIT_TIMEOUT_SECONDS = 15
_MAX_OUTPUT_CHARS = 12_000


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class GitStatusInput(_StrictModel):
    path: str = "/workspace/"


class GitStatusOutput(_StrictModel):
    porcelain: str = ""


class GitDiffInput(_StrictModel):
    path: str = "/workspace/"
    staged: bool = False


class GitDiffOutput(_StrictModel):
    diff: str = ""


class GitLogInput(_StrictModel):
    path: str = "/workspace/"
    limit: int = Field(default=20, ge=1, le=200)


class GitLogOutput(_StrictModel):
    log: str = ""


def _meta(canonical_name: str) -> CanonicalToolMeta:
    defaults = defaults_for_kind(ToolKind.SEARCH)
    return CanonicalToolMeta(
        canonical_name=canonical_name,
        kind=ToolKind.SEARCH,
        side_effects=defaults.side_effects,
        risk=defaults.risk,
        execution_location=defaults.execution_location,
        display_name=canonical_name,
        description=f"Platform-enforced {canonical_name} tool (read-only Git).",
        idempotent=True,
        cacheable=True,
    )


def _definition(canonical_name: str, alias: str, input_model, output_model) -> ToolDefinition:
    return ToolDefinition(
        meta=_meta(canonical_name),
        input_model=input_model,
        output_model=output_model,
        handler=None,
        aliases=(alias,),
        runtime_kinds=frozenset({"agent_session"}),
        required_capabilities=frozenset({"deepagents"}),
    )


GIT_DEFINITIONS: tuple[ToolDefinition, ...] = (
    _definition("git.status", "git_status", GitStatusInput, GitStatusOutput),
    _definition("git.diff", "git_diff", GitDiffInput, GitDiffOutput),
    _definition("git.log", "git_log", GitLogInput, GitLogOutput),
)


def _validate_root(project_root: str | Path, *, extra_roots=None) -> Path:
    """Fail closed unless project_root is an allowed workspace root."""
    from workspace.path_policy import require_valid_project_path

    resolved = require_valid_project_path(str(project_root), extra_roots=extra_roots)
    root = Path(resolved).resolve()
    if not root.is_dir():
        raise ValueError(f"project_root is not a directory: {root}")
    return root


async def _run_git(root: Path, args: tuple[str, ...]) -> str:
    proc = await asyncio.create_subprocess_exec(
        "git",
        *args,
        cwd=str(root),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, _stderr = await asyncio.wait_for(proc.communicate(), timeout=_GIT_TIMEOUT_SECONDS)
    except TimeoutError:
        proc.kill()
        await proc.wait()
        raise
    text = stdout.decode("utf-8", errors="replace")
    if len(text) > _MAX_OUTPUT_CHARS:
        text = text[:_MAX_OUTPUT_CHARS] + "\n...[truncated]"
    return text


def make_git_handlers(project_root: str | Path, *, extra_roots=None) -> dict[str, Any]:
    """Return ``{canonical_name: async handler}`` bound to a validated project root."""
    root = _validate_root(project_root, extra_roots=extra_roots)

    async def git_status(request: GitStatusInput) -> GitStatusOutput:
        porcelain = await _run_git(root, ("status", "--porcelain"))
        return GitStatusOutput(porcelain=porcelain)

    async def git_diff(request: GitDiffInput) -> GitDiffOutput:
        args = ("diff", "--cached") if request.staged else ("diff",)
        diff = await _run_git(root, args)
        return GitDiffOutput(diff=diff)

    async def git_log(request: GitLogInput) -> GitLogOutput:
        log = await _run_git(root, ("log", f"-{request.limit}", "--oneline"))
        return GitLogOutput(log=log)

    return {
        "git.status": git_status,
        "git.diff": git_diff,
        "git.log": git_log,
    }


__all__ = [
    "GIT_DEFINITIONS",
    "GitDiffInput",
    "GitDiffOutput",
    "GitLogInput",
    "GitLogOutput",
    "GitStatusInput",
    "GitStatusOutput",
    "make_git_handlers",
]
