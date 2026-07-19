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

When ``wsl_enabled=True`` (Windows only), ``execute`` delegates to WSL2's
``bash`` instead of ``cmd.exe``. This gives the model a real Linux environment
where ``ls``/``cat``/``grep``/pipes/heredocs all work natively. WSL is a
compatibility environment, not a security boundary: it can still access mounted
Windows files and may support Windows process interop. File tools
(``read_file``/``edit_file`` etc.) are unaffected -- they still use the local
Python filesystem API.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from typing import Any

from deepagents.backends import LocalShellBackend
from deepagents.backends.protocol import ExecuteResponse

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

_WSL_HOST_ENV_KEYS = frozenset(
    {
        "PATH",
        "PATHEXT",
        "SYSTEMROOT",
        "WINDIR",
        "SYSTEMDRIVE",
        "COMSPEC",
        "TEMP",
        "TMP",
        "USERPROFILE",
        "USERNAME",
        "LOCALAPPDATA",
        "APPDATA",
    }
)


def _to_native(path: str) -> str:
    """Convert ``path`` to OS-native separators.

    On POSIX this is a no-op. On Windows, forward slashes become backslashes
    so the path is unambiguous under ``cmd.exe``.
    """
    if os.sep == "\\":
        return path.replace("/", "\\")
    return path


def win_path_to_wsl_path(win_path: str) -> str:
    r"""Convert a Windows path to its WSL2 equivalent.

    ``C:\Users\foo`` -> ``/mnt/c/Users/foo``
    ``D:/projects``  -> ``/mnt/d/projects``

    Paths that don't match a Windows drive-letter pattern (already-POSIX paths,
    relative paths) are returned unchanged.
    """
    m = re.match(r"^([A-Za-z]):[\\/](.*)", win_path)
    if m:
        drive = m.group(1).lower()
        rest = m.group(2).replace("\\", "/")
        return f"/mnt/{drive}/{rest}"
    return win_path


def decode_wsl_list_output(raw: bytes | str) -> str:
    """Decode ``wsl.exe --list --quiet`` output across Windows versions.

    The list command commonly emits UTF-16LE even when ordinary distro command
    output is UTF-8.  Treat embedded NULs as the reliable UTF-16 signal so the
    auto-selector does not mistake ``U\x00b\x00u\x00n\x00t\x00u`` for a name.
    """
    if isinstance(raw, str):
        return raw.replace("\x00", "").lstrip("\ufeff")
    if b"\x00" in raw:
        return raw.decode("utf-16-le", errors="replace").lstrip("\ufeff")
    return raw.decode("utf-8", errors="replace").lstrip("\ufeff")


def list_wsl_distributions(*, env: dict[str, str] | None = None) -> list[str]:
    """Return installed WSL distribution names without trusting the default."""
    try:
        result = subprocess.run(  # noqa: S603
            ["wsl.exe", "--list", "--quiet"],
            check=False,
            capture_output=True,
            stdin=subprocess.DEVNULL,
            timeout=10,
            env=env,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return []
    if result.returncode != 0:
        return []
    decoded = decode_wsl_list_output(result.stdout)
    return [line.strip() for line in decoded.splitlines() if line.strip()]


def select_wsl_distribution(
    configured: str | None,
    *,
    env: dict[str, str] | None = None,
) -> str | None:
    """Resolve an explicit distro or choose the first non-Docker distro."""
    explicit = str(configured or "").strip()
    if explicit:
        return explicit
    distributions = list_wsl_distributions(env=env)
    for name in distributions:
        if name.casefold() not in {"docker-desktop", "docker-desktop-data"}:
            return name
    return None


def wsl_host_environment(configured: dict[str, str] | None) -> dict[str, str]:
    """Supply only the Windows host variables required to launch ``wsl.exe``.

    ``LocalShellBackend`` legitimately permits an empty environment, but the
    WSL service needs a small Windows identity/system environment before it can
    create the Linux process. This merge remains allowlisted and does not pass
    arbitrary host secrets into the launcher.
    """
    merged = dict(configured or {})
    present = {key.upper() for key in merged}
    for key, value in os.environ.items():
        if key.upper() in _WSL_HOST_ENV_KEYS and key.upper() not in present:
            merged[key] = value
    return merged


def rewrite_workspace_paths(
    command: str,
    real_root: str,
    *,
    path_separator: str | None = None,
) -> tuple[str, bool]:
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
        path_separator: Separator expected by the target shell. Defaults to the
            host separator; WSL callers pass ``/`` explicitly.

    Returns:
        A tuple of (rewritten_command, was_change).
    """
    if not command or not real_root:
        return command, False

    # Use the real_root as-is (it comes from Path.resolve() so it's already
    # in the platform's native form). We only convert the *subpath* that
    # follows /workspace/ to native separators.
    native_root = real_root
    target_separator = path_separator or os.sep
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
            subpath_native = subpath.replace("\\", target_separator).replace("/", target_separator)
            sep = target_separator
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

    When ``wsl_enabled=True`` (Windows only), ``execute`` runs commands inside
    WSL2's ``bash`` instead of ``cmd.exe``. This provides a real Linux
    environment where Unix commands (``ls``/``cat``/``grep``/pipes/heredocs)
    work natively. It does not turn WSL into a security sandbox.

    All other behavior (timeout, output truncation, env, virtual_mode for
    file operations) is inherited unchanged from ``LocalShellBackend``.
    File tools (``read_file``/``edit_file``/``ls``/``grep``/``glob``) are
    never affected by ``wsl_enabled`` -- they always use the local Python
    filesystem API via ``FilesystemBackend``.
    """

    def __init__(
        self,
        root_dir: str | Any | None = None,
        *,
        virtual_mode: bool | None = None,
        timeout: int = EXECUTE_TIMEOUT_SECONDS,
        max_output_bytes: int = EXECUTE_MAX_OUTPUT_BYTES,
        env: dict[str, str] | None = None,
        inherit_env: bool = False,
        wsl_enabled: bool = False,
        wsl_distribution: str | None = None,
        controlled_execute: bool = False,
    ) -> None:
        """Initialize the platform shell backend.

        Args:
            root_dir: Working directory for filesystem operations and shell
                commands. Passed to ``LocalShellBackend.__init__``.
            virtual_mode: Virtual path mode for filesystem operations.
            timeout: Default per-command timeout in seconds.
            max_output_bytes: Max captured output bytes per command.
            env: Environment variables for shell commands.
            inherit_env: Whether to inherit the parent process environment.
            wsl_enabled: If True (and on Windows), ``execute`` runs commands
                inside WSL2 ``bash`` instead of ``cmd.exe``. On non-Windows
                platforms this is silently ignored.
            wsl_distribution: Optional WSL distro name. If omitted, the first
                installed non-Docker distro is selected lazily.
            controlled_execute: If True, ``execute`` short-circuits with a
                gating error and never runs a subprocess. This is the
                execution-layer deny that blocks the legacy ``execute`` entry
                point in controlled mode, forcing all execution through the
                Tool Gateway. Legacy/shadow modes pass False (unchanged).
        """
        super().__init__(
            root_dir=root_dir,
            virtual_mode=virtual_mode,
            timeout=timeout,
            max_output_bytes=max_output_bytes,
            env=env,
            inherit_env=inherit_env,
        )
        self._wsl_enabled = bool(wsl_enabled) and sys.platform == "win32"
        self._wsl_distribution = str(wsl_distribution or "").strip() or None
        self._resolved_wsl_distribution: str | None = None
        self._controlled_execute = bool(controlled_execute)

    def execute(
        self,
        command: str,
        *,
        timeout: int | None = None,
    ) -> ExecuteResponse:
        """Execute ``command`` after rewriting ``/workspace`` paths.

        In controlled mode (``controlled_execute=True``) this short-circuits
        with a gating error and never delegates to the parent ``execute`` or
        WSL, so the legacy ``execute`` entry point cannot run a subprocess
        outside the Tool Gateway.

        When WSL is enabled (and not controlled), the command runs inside the
        selected distro's bash with the working directory set to the WSL path
        of ``root_dir``. Otherwise, it delegates to the parent
        ``LocalShellBackend.execute`` (which uses ``cmd.exe`` on Windows).

        Args:
            command: Shell command string (may contain ``/workspace/...``).
            timeout: Optional per-command timeout override.

        Returns:
            ``ExecuteResponse`` with combined output, exit code, and
            truncation flag.
        """
        if self._controlled_execute:
            return ExecuteResponse(
                output=(
                    "execute is gated by the Tool Gateway in controlled mode; "
                    "use the managed execute / run_tests tool instead."
                ),
                exit_code=1,
                truncated=False,
            )
        if self._wsl_enabled:
            return self._execute_via_wsl(command, timeout)
        rewritten, _ = rewrite_workspace_paths(command, str(self.cwd))
        return super().execute(rewritten, timeout=timeout)

    def _execute_via_wsl(
        self,
        command: str,
        timeout: int | None,
    ) -> ExecuteResponse:
        """Execute ``command`` inside WSL2's ``bash``.

        The Windows ``root_dir`` is converted to a WSL path (``/mnt/c/...``),
        and the command is wrapped in ``cd "<wsl_root>" && <command>`` so the
        working directory is correct inside WSL.

        Output handling (stderr prefixing, truncation, exit code) mirrors
        ``LocalShellBackend.execute`` for consistency.
        """
        if not command or not isinstance(command, str):
            return ExecuteResponse(
                output="Error: Command must be a non-empty string.",
                exit_code=1,
                truncated=False,
            )

        wsl_root = win_path_to_wsl_path(str(self.cwd))
        # Rewrite /workspace/... to the WSL path of the real root.
        rewritten, _ = rewrite_workspace_paths(command, wsl_root, path_separator="/")
        # Wrap in cd so the working directory is the project root inside WSL.
        full_cmd = f'cd "{wsl_root}" && {rewritten}'

        effective_timeout = timeout if timeout is not None else self._default_timeout
        if effective_timeout <= 0:
            return ExecuteResponse(
                output=f"Error: timeout must be positive, got {effective_timeout}",
                exit_code=1,
                truncated=False,
            )

        host_env = wsl_host_environment(self._env)
        distribution = self._resolved_wsl_distribution or select_wsl_distribution(
            self._wsl_distribution,
            env=host_env,
        )
        if not distribution:
            return ExecuteResponse(
                output=(
                    "Error: no usable WSL Linux distribution was found. Install Ubuntu "
                    "or set SANDBOX_WSL_DISTRIBUTION to a distro with bash/coreutils."
                ),
                exit_code=1,
                truncated=False,
            )
        self._resolved_wsl_distribution = distribution

        try:
            result = subprocess.run(  # noqa: S603
                [
                    "wsl.exe",
                    "--distribution",
                    distribution,
                    "--exec",
                    "timeout",
                    "--foreground",
                    "--signal=TERM",
                    "--kill-after=2s",
                    f"{effective_timeout}s",
                    "bash",
                    "-lc",
                    full_cmd,
                ],
                check=False,
                capture_output=True,
                stdin=subprocess.DEVNULL,
                timeout=effective_timeout + 5,
                env=host_env,
            )
        except subprocess.TimeoutExpired:
            if timeout is not None:
                msg = f"Error: Command timed out after {effective_timeout} seconds (custom timeout). The command may be stuck or require more time."
            else:
                msg = f"Error: Command timed out after {effective_timeout} seconds. For long-running commands, re-run using the timeout parameter."
            return ExecuteResponse(
                output=msg,
                exit_code=124,
                truncated=False,
            )
        except FileNotFoundError:
            return ExecuteResponse(
                output="Error: WSL is not available (wsl.exe not found). "
                "Set SANDBOX_EXECUTION_MODE=local or install WSL2.",
                exit_code=1,
                truncated=False,
            )
        except Exception as e:  # noqa: BLE001
            return ExecuteResponse(
                output=f"Error executing command via WSL ({type(e).__name__}): {e}",
                exit_code=1,
                truncated=False,
            )

        # Combine stdout and stderr (same logic as LocalShellBackend.execute).
        output_parts: list[str] = []
        if result.stdout:
            output_parts.append(decode_wsl_list_output(result.stdout))
        if result.stderr:
            stderr_text = decode_wsl_list_output(result.stderr)
            stderr_lines = stderr_text.strip().split("\n")
            output_parts.extend(f"[stderr] {line}" for line in stderr_lines)

        output = "\n".join(output_parts) if output_parts else "<no output>"

        # WSL infrastructure errors produce exit code 4294967295 (0xFFFFFFFF),
        # which means WSL itself failed -- not the command. Surface a helpful
        # message so the user knows to check their WSL installation.
        if result.returncode == 4294967295 or result.returncode == -1:
            output = (
                output.rstrip()
                + "\n\n[WSL infrastructure error: WSL failed to execute the command. "
                "Ensure a Linux distro (e.g. Ubuntu) is installed: "
                "wsl --install -d Ubuntu. Then: wsl --set-default Ubuntu]"
            )
        elif result.returncode != 0 and (
            "execvpe(bash) failed" in output
            or "execvpe(timeout) failed" in output
            or "WSL_E_DISTRO_NOT_FOUND" in output
        ):
            output = (
                output.rstrip()
                + f"\n\n[WSL distribution '{distribution}' is not usable for Agent commands. "
                "Choose a distro with bash/coreutils via SANDBOX_WSL_DISTRIBUTION.]"
            )

        # Truncation check.
        truncated = False
        encoded_output = output.encode("utf-8", errors="replace")
        if len(encoded_output) > self._max_output_bytes:
            output = encoded_output[: self._max_output_bytes].decode("utf-8", errors="ignore")
            output += f"\n\n... Output truncated at {self._max_output_bytes} bytes."
            truncated = True

        # Append exit code for non-zero returns.
        if result.returncode != 0:
            output = f"{output.rstrip()}\n\nExit code: {result.returncode}"

        return ExecuteResponse(
            output=output,
            exit_code=result.returncode,
            truncated=truncated,
        )


__all__ = [
    "EXECUTE_MAX_OUTPUT_BYTES",
    "EXECUTE_TIMEOUT_SECONDS",
    "PlatformShellBackend",
    "WORKSPACE_VIRTUAL_PREFIX",
    "decode_wsl_list_output",
    "list_wsl_distributions",
    "rewrite_workspace_paths",
    "select_wsl_distribution",
    "win_path_to_wsl_path",
    "wsl_host_environment",
]
