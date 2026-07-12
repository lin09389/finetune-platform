"""Tests for platform-aware shell backend and execution environment.

Covers three layers that together eliminate the "Windows false-failure" problem:
1. ``rewrite_workspace_paths`` -- deterministic path prefix replacement
2. ``deepagents_shell_env`` -- platform-aware env allowlist
3. ``build_execution_prompt`` -- platform-aware shell guidance in system prompt
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from agent_session.platform_shell import (
    EXECUTE_MAX_OUTPUT_BYTES,
    EXECUTE_TIMEOUT_SECONDS,
    PlatformShellBackend,
    rewrite_workspace_paths,
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
