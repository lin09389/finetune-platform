"""Platform-owned canonical execute / run_tests tools.

These are the managed execution surface for controlled mode.  Unlike the
legacy DeepAgents ``execute`` (which runs directly in the backend), these
tools are dispatched through the Task-7 Tool Gateway, so policy / approval
gates apply before any subprocess runs.  The legacy ``execute`` entry point
is blocked at the backend layer in controlled mode
(see :class:`agent_session.platform_shell.PlatformShellBackend`).

Handlers reuse the platform's ``/workspace/`` path-rewriting and output
truncation conventions but do NOT delegate to ``PlatformShellBackend.execute``
(they are the authorized path that runs only after the Gateway approves).
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from ..definition import ToolDefinition
from ..models import CanonicalToolMeta
from ..taxonomy import ToolKind, defaults_for_kind

_EXECUTE_TIMEOUT_SECONDS = 300
_MAX_OUTPUT_BYTES = 500_000


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class ExecuteInput(_StrictModel):
    command: str
    timeout: int | None = Field(default=None, ge=1, le=3600)


class ExecuteOutput(_StrictModel):
    output: str
    exit_code: int = Field(default=0, ge=0)
    truncated: bool = False


class RunTestsInput(_StrictModel):
    command: str
    timeout: int | None = Field(default=None, ge=1, le=3600)


class RunTestsOutput(_StrictModel):
    output: str
    exit_code: int = Field(default=0, ge=0)
    truncated: bool = False
    passed: bool = False


def _mutable_meta(canonical_name: str) -> CanonicalToolMeta:
    defaults = defaults_for_kind(ToolKind.EXECUTE)
    return CanonicalToolMeta(
        canonical_name=canonical_name,
        kind=ToolKind.EXECUTE,
        side_effects=defaults.side_effects,
        risk=defaults.risk,
        execution_location=defaults.execution_location,
        display_name=canonical_name,
        description=f"Platform-enforced {canonical_name} tool (managed execution).",
        idempotent=False,
        cacheable=False,
    )


def _definition(canonical_name: str, alias: str, input_model, output_model) -> ToolDefinition:
    return ToolDefinition(
        meta=_mutable_meta(canonical_name),
        input_model=input_model,
        output_model=output_model,
        handler=None,
        aliases=(alias,),
        runtime_kinds=frozenset({"agent_session"}),
        required_capabilities=frozenset({"deepagents"}),
    )


EXECUTE_DEFINITIONS: tuple[ToolDefinition, ...] = (
    _definition("workspace.execute", "execute", ExecuteInput, ExecuteOutput),
    _definition("workspace.run_tests", "run_tests", RunTestsInput, RunTestsOutput),
)


def _truncate(text: str) -> tuple[str, bool]:
    encoded = text.encode("utf-8", errors="replace")
    if len(encoded) > _MAX_OUTPUT_BYTES:
        text = encoded[:_MAX_OUTPUT_BYTES].decode("utf-8", errors="ignore")
        text += f"\n\n... Output truncated at {_MAX_OUTPUT_BYTES} bytes."
        return text, True
    return text, False


async def _run_command(command: str, root: Path, timeout: int | None) -> ExecuteOutput:
    # Lazy import to keep tool_platform free of agent_session at module load.
    from agent_session.platform_shell import rewrite_workspace_paths

    path_separator = "/" if sys.platform == "win32" else None
    rewritten, _ = rewrite_workspace_paths(command, str(root), path_separator=path_separator)
    effective_timeout = timeout if timeout is not None else _EXECUTE_TIMEOUT_SECONDS
    try:
        proc = await asyncio.create_subprocess_shell(
            rewritten,
            cwd=str(root),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        try:
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=effective_timeout)
        except TimeoutError:
            proc.kill()
            await proc.wait()
            return ExecuteOutput(
                output=f"Error: command timed out after {effective_timeout}s",
                exit_code=124,
                truncated=False,
            )
    except FileNotFoundError as exc:
        return ExecuteOutput(output=f"Error: {exc}", exit_code=127, truncated=False)

    text = stdout.decode("utf-8", errors="replace") if stdout else ""
    text, truncated = _truncate(text)
    exit_code = proc.returncode if proc.returncode is not None else 1
    if exit_code != 0:
        text = f"{text.rstrip()}\n\nExit code: {exit_code}"
    return ExecuteOutput(output=text or "<no output>", exit_code=exit_code, truncated=truncated)


def make_execute_handlers(project_root: str | Path, *, shell_env: dict[str, str] | None = None) -> dict[str, Any]:
    """Return ``{canonical_name: async handler}`` for managed execution tools.

    Handlers run only after the Task-7 Gateway has authorized the invocation.
    ``shell_env`` is accepted for future per-session environment scoping but is
    not applied here (the managed path inherits the worker environment).
    """
    _ = shell_env  # reserved for per-session env scoping
    root = Path(project_root).resolve()

    async def execute(request: ExecuteInput) -> ExecuteOutput:
        return await _run_command(request.command, root, request.timeout)

    async def run_tests(request: RunTestsInput) -> RunTestsOutput:
        result = await _run_command(request.command, root, request.timeout)
        return RunTestsOutput(
            output=result.output,
            exit_code=result.exit_code,
            truncated=result.truncated,
            passed=result.exit_code == 0,
        )

    return {
        "workspace.execute": execute,
        "workspace.run_tests": run_tests,
    }


__all__ = [
    "EXECUTE_DEFINITIONS",
    "ExecuteInput",
    "ExecuteOutput",
    "RunTestsInput",
    "RunTestsOutput",
    "make_execute_handlers",
]
