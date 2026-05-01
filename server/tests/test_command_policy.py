from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import HTTPException

from agent_runtime.command_policy import command_allowed, detect_project_commands, normalize_command


def test_detect_project_commands_finds_npm_and_pytest(tmp_path: Path):
    (tmp_path / "package.json").write_text('{"scripts":{"typecheck":"tsc --noEmit","test":"vitest"}}', encoding="utf-8")
    (tmp_path / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")

    commands = detect_project_commands(tmp_path)

    command_text = {" ".join(item["command"]) for item in commands}
    assert "npm run typecheck" in command_text
    assert "npm test" in command_text
    assert "python -m pytest" in command_text


def test_command_allowlist_and_shell_rejection():
    assert command_allowed(["npm", "run", "typecheck"]) is True
    assert command_allowed(["python", "-m", "pytest", "server/tests"]) is True
    assert command_allowed(["npm", "run", "build"]) is False

    with pytest.raises(HTTPException):
        normalize_command("npm run typecheck && del important.txt")
    with pytest.raises(HTTPException):
        normalize_command(["git", "commit", "-m", "bad"])

