"""Platform-aware shell backend for DeepAgents command execution.

The filesystem prompt teaches the model to use ``/workspace/...`` virtual paths
for file tools (``read_file``/``edit_file``/``ls``/``grep``/``glob``), and the
DeepAgents ``FilesystemBackend`` correctly maps those to the real project root.

But the ``execute`` tool bypasses virtual path resolution entirely:
``LocalShellBackend.execute`` runs ``subprocess.run(command, shell=True,
cwd=<real root>)``. On Windows ``shell=True`` means ``cmd.exe``, so a model that
writes ``cd /workspace && ls`` (a natural habit given the prompt) gets a hard
failure: ``cmd.exe`` does not understand ``/workspace`` as a path.

``PlatformShellBackend`` fixes this structurally by rewriting ``/workspace/...``
tokens in the command string to the real ``root_dir`` *before* delegating to the
parent ``execute``. This is deterministic and testable -- unlike prompt tweaks,
which are advisory.

Only path-prefix replacement is performed. We deliberately do NOT translate
commands (``ls`` -> ``dir`` etc.): translation is fragile and would mask real
issues. The model can still learn from ``execute`` output.
"""

from __future__ import annotations

import os
import re
from typing import Any

from deepagents.backends import LocalShellBackend

# ---------------------------------------------------------------------------
# Tunable execution limits
#
# These override the deepagents library defaults (120s / 100_000 bytes) which
# are too tight for real test suites: a full ``pytest -v`` or ``tsc --noEmit``
# commonly exceeds 120s, and 100KB of output hides the tail where the actual
# failure summary lives. The model then cannot tell "passed" from "failed" and
# enters a read-edit-retry loop on code that was already correct.
# ---------------------------------------------------------------------------

EXECUTE_TIMEOUT_SECONDS = 300
"""Default per-command timeout (seconds). 5 minutes covers most test suites."""

EXECUTE_MAX_OUTPUT_BYTES = 500_000
"""Max captured output per command. 500KB aligns with BaseSandbox read limits."""

WORKSPACE_VIRTUAL_PREFIX = "/workspace"
"""The virtual path prefix the filesystem prompt tells the model to use."""


def _to_native(path: str) -> str:
    """Convert ``path`` to OS-native separators.

    On POSIX this is a no-op. On Windows, forward slashes become backslashes
    so the path is unambiguous under ``cmd.exe``.
    """
    if os.sep == "\\":
        return path.replace("/", "\\")
    return path


def rewrite_workspace_paths(command: str, real_root: str) -> tuple[str, bool]:
    r"""Rewrite ``/workspace/...`` virtual paths in ``command`` to ``real_root``.

    This makes the model's Unix-style ``/workspace`` habit (taught by the
    filesystem prompt) work under ``cmd.exe`` on Windows, where ``/workspace``
    is not a valid path.

    Rules (conservative -- only token-level path prefixes are replaced):
    - ``/workspace/foo/bar``  ->  ``"<real_root>\foo\bar"`` (native separators, quoted)
    - ``/workspace`` (bare)   ->  ``"<real_root>"``
    - Paths inside single/double quotes are left untouched (the model may be
      quoting a literal for other reasons, and rewriting quoted content is
      riskier than rewriting bare tokens).
    - URLs (``http://...``) are never matched because ``/workspace`` must be
      preceded by a non-word character or start-of-string, not ``:``.

    Args:
        command: The shell command string from the model.
        real_root: The real absolute project root directory.

    Returns:
        A tuple of (rewritten_command, was_change).
    """
    if not command or not real_root:
        return command, False

    # Use the real_root as-is (it comes from Path.resolve() so it's already
    # in the platform's native form). We only convert the *subpath* that
    # follows /workspace/ to native separators.
    native_root = real_root
    changed = False

    # Order matters: wspath (/workspace/sub/...) must be tried before bare
    # (/workspace), otherwise bare's lookahead would consume the leading slash.
    # The lookbehind (?<![:/\w]) prevents matching inside URLs like
    # http://workspace/.
    token_re = re.compile(
        r"""
        (?P<quote>
            '(?:[^'\\]|\\.)*'
            |
            "(?:[^"\\]|\\.)*"
        )
        |
        (?P<wspath>
            (?<![:/\w])
            /workspace/
            [^\s"'&|;<>()\n]*
        )
        |
        (?P<bare>
            (?<![:/\w])
            /workspace
            (?=[\s"'&|;<>)\n]|$)
        )
        """,
        re.VERBOSE,
    )

    def _replace(match: re.Match[str]) -> str:
        nonlocal changed
        if match.group("quote") is not None:
            return match.group("quote")
        if match.group("wspath") is not None:
            changed = True
            full = match.group("wspath")
            subpath = full[len(WORKSPACE_VIRTUAL_PREFIX) + 1 :]  # strip "/workspace/"
            subpath_native = _to_native(subpath)
            sep = os.sep
            return f'"{native_root}{sep}{subpath_native}"' if subpath_native else f'"{native_root}"'
        if match.group("bare") is not None:
            changed = True
            return f'"{native_root}"'
        return match.group(0)

    result = token_re.sub(_replace, command)
    return result, changed


class PlatformShellBackend(LocalShellBackend):
    """``LocalShellBackend`` with Windows-aware command preprocessing.

    Rewrites ``/workspace/...`` virtual paths in shell commands to the real
    project ``root_dir`` before delegating to ``LocalShellBackend.execute()``.
    This ensures the model's filesystem-prompt-taught ``/workspace`` habit
    does not cause hard failures under ``cmd.exe`` on Windows.

    All other behavior (timeout, output truncation, env, virtual_mode for
    file operations) is inherited unchanged from ``LocalShellBackend``.
    """

    def execute(
        self,
        command: str,
        *,
        timeout: int | None = None,
    ) -> Any:
        """Execute ``command`` after rewriting ``/workspace`` paths.

        Args:
            command: Shell command string (may contain ``/workspace/...``).
            timeout: Optional per-command timeout override.

        Returns:
            ``ExecuteResponse`` from the parent ``LocalShellBackend.execute``.
        """
        rewritten, _ = rewrite_workspace_paths(command, str(self.cwd))
        return super().execute(rewritten, timeout=timeout)


__all__ = [
    "EXECUTE_MAX_OUTPUT_BYTES",
    "EXECUTE_TIMEOUT_SECONDS",
    "PlatformShellBackend",
    "WORKSPACE_VIRTUAL_PREFIX",
    "rewrite_workspace_paths",
]
