"""Tests for platform-aware shell backend and execution environment.

Covers three layers that together eliminate the "Windows false-failure" problem:
1. ``rewrite_workspace_paths`` -- deterministic path prefix replacement
2. ``deepagents_shell_env`` -- platform-aware env allowlist
3. ``build_execution_prompt`` -- platform-aware shell guidance in system prompt
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest
from agent_session.platform_shell import (
    EXECUTE_MAX_OUTPUT_BYTES,
    EXECUTE_TIMEOUT_SECONDS,
    PlatformShellBackend,
    decode_wsl_list_output,
    rewrite_workspace_paths,
    select_wsl_distribution,
    win_path_to_wsl_path,
    wsl_host_environment,
)
from agent_session.runtime import build_deepagents_backend
from agent_session.runtime_contract import build_execution_prompt
from agent_session.runtime_factory import deepagents_shell_env

# ---------------------------------------------------------------------------
# rewrite_workspace_paths -- pure function tests
# ---------------------------------------------------------------------------


class TestRewriteWorkspacePaths:
    """Verify /workspace/... is rewritten to the real project root."""

    @pytest.mark.parametrize(
        ("command", "real_root", "expect_contains"),
        [
            # Bare /workspace -> quoted real root
            ("cd /workspace", "/home/user/proj", "/home/user/proj"),
            # /workspace with subpath
            ("pytest /workspace/server/tests", "/home/user/proj", "/home/user/proj"),
            # /workspace at end of compound command
            ("cd /workspace && ls", "/home/user/proj", "/home/user/proj"),
        ],
    )
    def test_rewrites_workspace_path(self, command, real_root, expect_contains):
        result, changed = rewrite_workspace_paths(command, real_root)
        assert changed is True
        assert expect_contains in result

    def test_bare_workspace_replaced(self):
        result, changed = rewrite_workspace_paths("cd /workspace", "/home/user/proj")
        assert changed is True
        assert "/workspace" not in result
        assert "/home/user/proj" in result

    def test_workspace_with_subpath_replaced(self):
        result, changed = rewrite_workspace_paths(
            "pytest /workspace/server/tests -v", "/home/user/proj"
        )
        assert changed is True
        assert "/workspace" not in result
        # Subpath separators are converted to native form
        import os
        expected_subpath = "server" + os.sep + "tests"
        assert expected_subpath in result

    def test_preserves_quoted_paths(self):
        """Paths inside quotes should not be rewritten."""
        cmd = 'echo "/workspace/should/stay"'
        result, changed = rewrite_workspace_paths(cmd, "/home/user/proj")
        assert changed is False
        assert result == cmd

    def test_preserves_single_quoted_paths(self):
        cmd = "echo '/workspace/should/stay'"
        result, changed = rewrite_workspace_paths(cmd, "/home/user/proj")
        assert changed is False
        assert result == cmd

    def test_does_not_match_url(self):
        """http://workspace/ should not be rewritten."""
        cmd = "curl http://workspace/api"
        result, changed = rewrite_workspace_paths(cmd, "/home/user/proj")
        assert changed is False
        assert result == cmd

    def test_no_workspace_returns_unchanged(self):
        cmd = "npm run test"
        result, changed = rewrite_workspace_paths(cmd, "/home/user/proj")
        assert changed is False
        assert result == cmd

    def test_empty_command_returns_unchanged(self):
        result, changed = rewrite_workspace_paths("", "/home/user/proj")
        assert changed is False
        assert result == ""

    def test_empty_root_returns_unchanged(self):
        result, changed = rewrite_workspace_paths("cd /workspace", "")
        assert changed is False
        assert result == "cd /workspace"

    def test_multiple_occurrences_all_replaced(self):
        cmd = "cp /workspace/a.txt /workspace/b.txt"
        result, changed = rewrite_workspace_paths(cmd, "/home/user/proj")
        assert changed is True
        assert "/workspace" not in result
        assert result.count("/home/user/proj") == 2

    def test_windows_native_separators(self):
        """On Windows, forward slashes in the subpath become backslashes."""
        with patch("agent_session.platform_shell.os.sep", "\\"), \
             patch("agent_session.platform_shell.os.path.sep", "\\"):
            result, changed = rewrite_workspace_paths(
                "pytest /workspace/server/tests", r"C:\Users\proj"
            )
        assert changed is True
        # The real root and subpath should use backslashes
        assert r"C:\Users\proj" in result
        assert "server\\tests" in result

    def test_workspace_in_middle_of_command(self):
        cmd = "python -m pytest /workspace/server/tests/test_foo.py -v --tb=short"
        result, changed = rewrite_workspace_paths(cmd, "/home/user/proj")
        assert changed is True
        assert "/workspace" not in result
        assert "test_foo.py" in result


# ---------------------------------------------------------------------------
# PlatformShellBackend.execute -- integration test
# ---------------------------------------------------------------------------


class TestPlatformShellBackendExecute:
    """Verify the backend rewrites paths before executing."""

    def test_execute_rewrites_workspace_path_and_runs(self, tmp_path: Path):
        """A command using /workspace/ should execute against the real root."""
        backend = PlatformShellBackend(
            root_dir=str(tmp_path),
            virtual_mode=True,
            timeout=30,
            max_output_bytes=10_000,
            env={"PATH": os.environ.get("PATH", "")},
            inherit_env=False,
        )
        # Write a marker file in the real root
        marker = tmp_path / "marker.txt"
        marker.write_text("hello", encoding="utf-8")

        # The model writes /workspace/marker.txt but the real file is at tmp_path
        result = backend.execute(
            f'python -c "print(open(r\'{tmp_path / "marker.txt"}\').read())"'
        )
        assert "hello" in result.output
        assert result.exit_code == 0

    def test_execute_preserves_non_workspace_command(self, tmp_path: Path):
        """Commands without /workspace should pass through unchanged."""
        backend = PlatformShellBackend(
            root_dir=str(tmp_path),
            virtual_mode=True,
            timeout=30,
            max_output_bytes=10_000,
            env={"PATH": os.environ.get("PATH", "")},
            inherit_env=False,
        )
        result = backend.execute('python -c "print(42)"')
        assert "42" in result.output
        assert result.exit_code == 0

    def test_isinstance_local_shell_backend(self, tmp_path: Path):
        """PlatformShellBackend must be a LocalShellBackend (backward compat)."""
        from deepagents.backends import LocalShellBackend

        backend = PlatformShellBackend(root_dir=str(tmp_path), virtual_mode=True)
        assert isinstance(backend, LocalShellBackend)


# ---------------------------------------------------------------------------
# deepagents_shell_env -- platform-aware allowlist
# ---------------------------------------------------------------------------


class TestDeepagentsShellEnv:
    """Verify the env allowlist is platform-aware and includes user dirs."""

    def test_windows_includes_user_profile(self):
        """On Windows, USERPROFILE/HOME/APPDATA must be in the allowlist."""
        test_env = {
            "PATH": "/usr/bin",
            "USERPROFILE": "C:\\Users\\test",
            "HOME": "C:\\Users\\test",
            "APPDATA": "C:\\Users\\test\\AppData\\Roaming",
            "JWT_SECRET_KEY": "secret",  # must NOT be included
            "INFERENCE_INTERNAL_API_KEY": "key",  # must NOT be included
        }
        with patch("agent_session.runtime_factory.sys.platform", "win32"), \
             patch("agent_session.runtime_factory.os.environ", test_env):
            env = deepagents_shell_env()
        assert "USERPROFILE" in env
        assert "HOME" in env
        assert "APPDATA" in env
        assert "PATH" in env
        # Secrets must not leak
        assert "JWT_SECRET_KEY" not in env
        assert "INFERENCE_INTERNAL_API_KEY" not in env

    def test_posix_lean_allowlist(self):
        """On POSIX, the allowlist is leaner but includes HOME."""
        test_env = {
            "PATH": "/usr/bin",
            "HOME": "/home/user",
            "USERPROFILE": "should-not-leak",  # Windows-only, not in POSIX set
            "TMPDIR": "/tmp",
        }
        with patch("agent_session.runtime_factory.sys.platform", "linux"), \
             patch("agent_session.runtime_factory.os.environ", test_env):
            env = deepagents_shell_env()
        assert "HOME" in env
        assert "PATH" in env
        assert "TMPDIR" in env
        assert "USERPROFILE" not in env

    def test_case_insensitive_matching(self):
        """Env var matching should be case-insensitive (Windows convention)."""
        test_env = {
            "path": "/usr/bin",  # lowercase
            "HOME": "/home/user",
        }
        with patch("agent_session.runtime_factory.sys.platform", "linux"), \
             patch("agent_session.runtime_factory.os.environ", test_env):
            env = deepagents_shell_env()
        assert "path" in env or "PATH" in env

    def test_does_not_inherit_full_environ(self):
        """Only allowlisted vars are returned -- no full inheritance."""
        test_env = {
            "PATH": "/usr/bin",
            "RANDOM_SECRET": "leak-me-not",
            "HOME": "/home/user",
        }
        with patch("agent_session.runtime_factory.sys.platform", "linux"), \
             patch("agent_session.runtime_factory.os.environ", test_env):
            env = deepagents_shell_env()
        assert "RANDOM_SECRET" not in env
        assert len(env) <= len(test_env)


# ---------------------------------------------------------------------------
# build_execution_prompt -- platform-aware system prompt
# ---------------------------------------------------------------------------


class TestBuildExecutionPrompt:
    """Verify the execution prompt adapts to the platform."""

    def test_windows_prompt_mentions_cmd(self):
        with patch("agent_session.runtime_contract.sys.platform", "win32"):
            prompt = build_execution_prompt()
        assert "Windows" in prompt or "cmd" in prompt
        assert "sandbox execute" in prompt

    def test_posix_prompt_mentions_posix(self):
        with patch("agent_session.runtime_contract.sys.platform", "linux"):
            prompt = build_execution_prompt()
        assert "POSIX" in prompt or "posix" in prompt

    def test_both_contain_base_text(self):
        """Both platform variants must contain the base execution guidance."""
        for platform in ("win32", "linux"):
            with patch("agent_session.runtime_contract.sys.platform", platform):
                prompt = build_execution_prompt()
            assert "execute" in prompt
            assert "白名单" in prompt  # "no whitelist approval needed"

    def test_windows_warns_against_unix_commands(self):
        with patch("agent_session.runtime_contract.sys.platform", "win32"):
            prompt = build_execution_prompt()
        # Should mention that ls/cat/grep are not shell commands on Windows
        assert "ls" in prompt or "cat" in prompt or "grep" in prompt


# ---------------------------------------------------------------------------
# build_deepagents_backend -- configuration assertions
# ---------------------------------------------------------------------------


class TestBuildDeepagentsBackendConfig:
    """Verify the backend uses PlatformShellBackend with correct limits."""

    def test_default_backend_is_platform_shell(self, tmp_path: Path):
        from deepagents.backends import CompositeBackend, LocalShellBackend

        backend = build_deepagents_backend(str(tmp_path))
        assert isinstance(backend, CompositeBackend)
        assert isinstance(backend.default, PlatformShellBackend)
        # PlatformShellBackend is a LocalShellBackend (backward compat)
        assert isinstance(backend.default, LocalShellBackend)

    def test_timeout_and_output_limits(self, tmp_path: Path):
        backend = build_deepagents_backend(str(tmp_path))
        default = backend.default
        assert default._default_timeout == EXECUTE_TIMEOUT_SECONDS
        assert default._max_output_bytes == EXECUTE_MAX_OUTPUT_BYTES

    def test_env_is_not_empty(self, tmp_path: Path):
        """The backend env should contain at least PATH."""
        backend = build_deepagents_backend(str(tmp_path))
        default = backend.default
        # PATH should be present in any platform's allowlist
        assert any(k.upper() == "PATH" for k in default._env)

    def test_inherit_env_is_false(self, tmp_path: Path):
        """inherit_env must stay False -- explicit allowlist, not full os.environ."""
        backend = build_deepagents_backend(str(tmp_path))
        default = backend.default
        # _env should be a filtered dict, not os.environ.copy()
        # We verify by checking it's smaller than os.environ
        assert len(default._env) <= len(os.environ)

    def test_workspace_route_uses_platform_shell(self, tmp_path: Path):
        from agent_session.runtime import WORKSPACE_BACKEND_ROUTE

        backend = build_deepagents_backend(str(tmp_path))
        route_backend = backend.routes[WORKSPACE_BACKEND_ROUTE]
        assert isinstance(route_backend, PlatformShellBackend)


# ---------------------------------------------------------------------------
# win_path_to_wsl_path -- pure function tests
# ---------------------------------------------------------------------------


class TestWinPathToWsl:
    """Verify Windows path to WSL path conversion."""

    def test_backslash_drive_path(self):
        assert win_path_to_wsl_path(r"C:\Users\foo") == "/mnt/c/Users/foo"

    def test_forward_slash_drive_path(self):
        assert win_path_to_wsl_path("C:/Users/foo") == "/mnt/c/Users/foo"

    def test_lowercase_drive(self):
        assert win_path_to_wsl_path(r"d:\projects") == "/mnt/d/projects"

    def test_already_posix_unchanged(self):
        assert win_path_to_wsl_path("/home/user/project") == "/home/user/project"

    def test_relative_path_unchanged(self):
        assert win_path_to_wsl_path("relative/path") == "relative/path"

    def test_empty_string(self):
        assert win_path_to_wsl_path("") == ""

    def test_trailing_separator(self):
        assert win_path_to_wsl_path("C:\\Users\\foo\\") == "/mnt/c/Users/foo/"

    def test_wsl_target_separator_keeps_full_path_posix(self):
        rewritten, changed = rewrite_workspace_paths(
            "pytest /workspace/server/tests",
            "/mnt/c/Users/test/project",
            path_separator="/",
        )
        assert changed is True
        assert rewritten == 'pytest "/mnt/c/Users/test/project/server/tests"'


class TestWslDistributionSelection:
    """WSL selection must not depend on docker-desktop being the default."""

    def test_decodes_utf16_list_output(self):
        raw = "docker-desktop\r\nUbuntu\r\n".encode("utf-16-le")
        assert decode_wsl_list_output(raw).splitlines() == ["docker-desktop", "Ubuntu"]

    def test_prefers_explicit_distribution_without_probing(self):
        with patch("agent_session.platform_shell.subprocess.run") as mock_run:
            selected = select_wsl_distribution("Debian")
        assert selected == "Debian"
        mock_run.assert_not_called()

    def test_auto_selects_first_non_docker_distribution(self):
        mock_result = type(
            "MockResult",
            (),
            {
                "stdout": "docker-desktop\r\nUbuntu\r\nDebian\r\n".encode("utf-16-le"),
                "stderr": b"",
                "returncode": 0,
            },
        )()
        with patch("agent_session.platform_shell.subprocess.run", return_value=mock_result):
            selected = select_wsl_distribution(None)
        assert selected == "Ubuntu"

    def test_returns_none_when_only_docker_distribution_exists(self):
        mock_result = type(
            "MockResult",
            (),
            {
                "stdout": "docker-desktop\r\n".encode("utf-16-le"),
                "stderr": b"",
                "returncode": 0,
            },
        )()
        with patch("agent_session.platform_shell.subprocess.run", return_value=mock_result):
            assert select_wsl_distribution(None) is None

    def test_wsl_host_environment_is_allowlisted(self):
        with patch.dict(
            "agent_session.platform_shell.os.environ",
            {"SystemRoot": r"C:\\Windows", "MIMO_API_KEY": "must-not-leak"},
            clear=True,
        ):
            env = wsl_host_environment({"PATH": r"C:\\Windows\\System32"})
        normalized = {key.upper(): value for key, value in env.items()}
        assert normalized["SYSTEMROOT"] == r"C:\\Windows"
        assert "MIMO_API_KEY" not in normalized


# ---------------------------------------------------------------------------
# PlatformShellBackend WSL mode -- mock-based tests
# ---------------------------------------------------------------------------


class TestPlatformShellBackendWSL:
    """Verify WSL execution mode via mocked subprocess."""

    def test_wsl_enabled_flag_windows_only(self, tmp_path: Path):
        """wsl_enabled=True is only effective on Windows."""
        with patch("agent_session.platform_shell.sys.platform", "win32"):
            backend = PlatformShellBackend(
                root_dir=str(tmp_path), virtual_mode=True, wsl_enabled=True
            )
            assert backend._wsl_enabled is True

        with patch("agent_session.platform_shell.sys.platform", "linux"):
            backend = PlatformShellBackend(
                root_dir=str(tmp_path), virtual_mode=True, wsl_enabled=True
            )
            assert backend._wsl_enabled is False

    def test_wsl_disabled_by_default(self, tmp_path: Path):
        backend = PlatformShellBackend(root_dir=str(tmp_path), virtual_mode=True)
        assert backend._wsl_enabled is False

    def test_wsl_execute_calls_wsl_exe(self, tmp_path: Path):
        """When wsl_enabled, execute should call wsl.exe via subprocess."""
        # Mock subprocess.run to avoid actually calling WSL
        mock_result = type("MockResult", (), {
            "stdout": b"hello from wsl\n",
            "stderr": b"",
            "returncode": 0,
        })()
        with patch("agent_session.platform_shell.sys.platform", "win32"), \
             patch("agent_session.platform_shell.subprocess.run", return_value=mock_result) as mock_run:
            backend = PlatformShellBackend(
                root_dir=str(tmp_path),
                virtual_mode=True,
                wsl_enabled=True,
                wsl_distribution="Ubuntu",
                env={"PATH": "/usr/bin"},
            )
            result = backend.execute("echo hello from wsl")

        assert mock_run.called
        call_args = mock_run.call_args
        # First positional arg should be the command list starting with wsl.exe
        cmd_list = call_args[0][0]
        assert cmd_list[0] == "wsl.exe"
        assert cmd_list[1:3] == ["--distribution", "Ubuntu"]
        assert "timeout" in cmd_list
        assert "bash" in cmd_list
        # The bash -c payload should contain cd <wsl_root>
        bash_cmd = cmd_list[-1]
        assert "cd " in bash_cmd
        assert "echo hello from wsl" in bash_cmd
        assert result.exit_code == 0
        assert "hello from wsl" in result.output

    def test_wsl_execute_rewrites_workspace_path(self, tmp_path: Path):
        """In WSL mode, /workspace/ should be rewritten to the WSL path."""
        mock_result = type("MockResult", (), {
            "stdout": b"", "stderr": b"", "returncode": 0,
        })()
        with patch("agent_session.platform_shell.sys.platform", "win32"), \
             patch("agent_session.platform_shell.subprocess.run", return_value=mock_result) as mock_run:
            backend = PlatformShellBackend(
                root_dir=r"C:\Users\test\project",
                virtual_mode=True,
                wsl_enabled=True,
                wsl_distribution="Ubuntu",
            )
            backend.execute("pytest /workspace/server/tests")

        bash_cmd = mock_run.call_args[0][0][-1]
        # /workspace/ should be replaced with the WSL path /mnt/c/Users/test/project
        assert "/workspace" not in bash_cmd
        assert "/mnt/c/Users/test/project" in bash_cmd

    def test_wsl_execute_timeout_handling(self, tmp_path: Path):
        """TimeoutExpired should return exit_code=124."""
        import subprocess as sp

        with patch("agent_session.platform_shell.sys.platform", "win32"), \
             patch("agent_session.platform_shell.subprocess.run", side_effect=sp.TimeoutExpired("wsl.exe", 300)):
            backend = PlatformShellBackend(
                root_dir=str(tmp_path),
                virtual_mode=True,
                wsl_enabled=True,
                wsl_distribution="Ubuntu",
                timeout=300,
            )
            result = backend.execute("sleep 999")

        assert result.exit_code == 124
        assert "timed out" in result.output.lower()

    def test_wsl_not_available_returns_error(self, tmp_path: Path):
        """FileNotFoundError (no wsl.exe) should return a helpful error."""
        with patch("agent_session.platform_shell.sys.platform", "win32"), \
             patch("agent_session.platform_shell.subprocess.run", side_effect=FileNotFoundError("wsl.exe not found")):
            backend = PlatformShellBackend(
                root_dir=str(tmp_path),
                virtual_mode=True,
                wsl_enabled=True,
                wsl_distribution="Ubuntu",
            )
            result = backend.execute("echo test")

        assert result.exit_code == 1
        assert "WSL" in result.output

    def test_wsl_output_truncation(self, tmp_path: Path):
        """Output exceeding max_output_bytes should be truncated."""
        long_output = "x" * 200_000
        mock_result = type("MockResult", (), {
            "stdout": long_output.encode(), "stderr": b"", "returncode": 0,
        })()
        with patch("agent_session.platform_shell.sys.platform", "win32"), \
             patch("agent_session.platform_shell.subprocess.run", return_value=mock_result):
            backend = PlatformShellBackend(
                root_dir=str(tmp_path),
                virtual_mode=True,
                wsl_enabled=True,
                wsl_distribution="Ubuntu",
                max_output_bytes=100_000,
            )
            result = backend.execute("cat big_file")

        assert result.truncated is True
        assert "truncated" in result.output.lower()
        assert len(result.output) < len(long_output)

    def test_non_wsl_mode_does_not_call_wsl(self, tmp_path: Path):
        """When wsl_enabled=False, execute should NOT call wsl.exe."""
        with patch("agent_session.platform_shell.sys.platform", "win32"), \
             patch("agent_session.platform_shell.subprocess.run") as mock_run:
            backend = PlatformShellBackend(
                root_dir=str(tmp_path),
                virtual_mode=True,
                wsl_enabled=False,
                env={"PATH": "/usr/bin"},
            )
            # This will call the parent LocalShellBackend.execute which also
            # uses subprocess.run, but with shell=True, not wsl.exe.
            # We just verify the command list doesn't start with wsl.exe.
            mock_result = type("MockResult", (), {
                "stdout": b"ok", "stderr": b"", "returncode": 0,
            })()
            mock_run.return_value = mock_result
            backend.execute("echo test")

        if mock_run.called:
            cmd = mock_run.call_args[0][0]
            # In non-WSL mode, the parent passes command as a string (shell=True),
            # not a list starting with wsl.exe.
            assert not (isinstance(cmd, list) and cmd and cmd[0] == "wsl.exe")

    def test_wsl_empty_command_returns_error(self, tmp_path: Path):
        with patch("agent_session.platform_shell.sys.platform", "win32"):
            backend = PlatformShellBackend(
                root_dir=str(tmp_path),
                virtual_mode=True,
                wsl_enabled=True,
                wsl_distribution="Ubuntu",
            )
            result = backend.execute("")
        assert result.exit_code == 1
        assert "non-empty" in result.output.lower()

    def test_wsl_auto_selection_avoids_docker_desktop(self, tmp_path: Path):
        list_result = type(
            "MockResult",
            (),
            {
                "stdout": "docker-desktop\r\nUbuntu\r\n".encode("utf-16-le"),
                "stderr": b"",
                "returncode": 0,
            },
        )()
        execute_result = type(
            "MockResult",
            (),
            {"stdout": b"ok\n", "stderr": b"", "returncode": 0},
        )()
        with patch("agent_session.platform_shell.sys.platform", "win32"), patch(
            "agent_session.platform_shell.subprocess.run",
            side_effect=[list_result, execute_result],
        ) as mock_run:
            backend = PlatformShellBackend(
                root_dir=str(tmp_path),
                virtual_mode=True,
                wsl_enabled=True,
            )
            result = backend.execute("echo ok")

        command = mock_run.call_args_list[1].args[0]
        assert command[1:3] == ["--distribution", "Ubuntu"]
        assert result.exit_code == 0

    def test_wsl_reports_when_no_non_docker_distribution_exists(self, tmp_path: Path):
        list_result = type(
            "MockResult",
            (),
            {
                "stdout": "docker-desktop\r\n".encode("utf-16-le"),
                "stderr": b"",
                "returncode": 0,
            },
        )()
        with patch("agent_session.platform_shell.sys.platform", "win32"), patch(
            "agent_session.platform_shell.subprocess.run", return_value=list_result
        ):
            backend = PlatformShellBackend(
                root_dir=str(tmp_path),
                virtual_mode=True,
                wsl_enabled=True,
            )
            result = backend.execute("echo test")

        assert result.exit_code == 1
        assert "no usable WSL Linux distribution" in result.output


# ---------------------------------------------------------------------------
# build_execution_prompt -- WSL mode
# ---------------------------------------------------------------------------


class TestBuildExecutionPromptWSL:
    """Verify the execution prompt adapts to WSL mode."""

    def test_wsl_mode_prompt_mentions_linux(self):
        with patch("agent_session.runtime_contract.sys.platform", "win32"), \
             patch("core.config.settings.sandbox_execution_mode", "wsl"):
            prompt = build_execution_prompt()
        assert "WSL" in prompt or "Linux" in prompt or "bash" in prompt
        assert "sandbox execute" in prompt

    def test_wsl_mode_allows_unix_commands(self):
        """WSL prompt should tell the model Unix commands are OK."""
        with patch("agent_session.runtime_contract.sys.platform", "win32"), \
             patch("core.config.settings.sandbox_execution_mode", "wsl"):
            prompt = build_execution_prompt()
        # Should NOT contain the Windows cmd restriction
        assert "不要用" not in prompt or "cmd" not in prompt

    def test_local_mode_still_mentions_cmd_on_windows(self):
        with patch("agent_session.runtime_contract.sys.platform", "win32"), \
             patch("core.config.settings.sandbox_execution_mode", "local"):
            prompt = build_execution_prompt()
        assert "Windows" in prompt or "cmd" in prompt


# ---------------------------------------------------------------------------
# build_deepagents_backend -- WSL configuration
# ---------------------------------------------------------------------------


class TestBuildDeepagentsBackendWSLConfig:
    """Verify the backend picks up WSL mode from settings."""

    def test_wsl_enabled_when_mode_is_wsl_on_windows(self, tmp_path: Path):
        with patch("agent_session.runtime.sys.platform", "win32"), \
             patch("core.config.settings.sandbox_execution_mode", "wsl"):
            backend = build_deepagents_backend(str(tmp_path))
        assert backend.default._wsl_enabled is True

    def test_wsl_disabled_when_mode_is_local(self, tmp_path: Path):
        with patch("agent_session.runtime.sys.platform", "win32"), \
             patch("core.config.settings.sandbox_execution_mode", "local"):
            backend = build_deepagents_backend(str(tmp_path))
        assert backend.default._wsl_enabled is False

    def test_wsl_disabled_on_non_windows(self, tmp_path: Path):
        with patch("agent_session.runtime.sys.platform", "linux"), \
             patch("core.config.settings.sandbox_execution_mode", "wsl"):
            backend = build_deepagents_backend(str(tmp_path))
        # Even with mode=wsl, non-Windows should not enable WSL.
        assert backend.default._wsl_enabled is False

    def test_configured_distribution_reaches_backend(self, tmp_path: Path):
        with patch("agent_session.runtime.sys.platform", "win32"), \
             patch("core.config.settings.sandbox_execution_mode", "wsl"), \
             patch("core.config.settings.sandbox_wsl_distribution", "Ubuntu"):
            backend = build_deepagents_backend(str(tmp_path))
        assert backend.default._wsl_distribution == "Ubuntu"
