from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import HTTPException

from agent_runtime.command_policy import command_allowed, detect_project_commands, normalize_command, resolve_command_cwd


def test_detect_project_commands_finds_npm_and_pytest(tmp_path: Path):
    (tmp_path / "package.json").write_text(
        '{"scripts":{"typecheck":"tsc --noEmit","test":"vitest","build":"vite build","lint":"eslint ."}}',
        encoding="utf-8",
    )
    (tmp_path / "tsconfig.json").write_text("{}", encoding="utf-8")
    (tmp_path / "vitest.config.ts").write_text("export default {};\n", encoding="utf-8")
    (tmp_path / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")

    commands = detect_project_commands(tmp_path)

    command_text = {" ".join(item["command"]) for item in commands}
    assert "npm run typecheck" in command_text
    assert "npm test" in command_text
    assert "npm run build" in command_text
    assert "npm run lint" in command_text
    assert "npx vitest run" in command_text
    assert "tsc --noEmit" in command_text
    assert "python -m pytest" in command_text


def test_command_allowlist_and_shell_rejection():
    assert command_allowed(["npm", "run", "typecheck"]) is True
    assert command_allowed(["npm", "run", "build"]) is True
    assert command_allowed(["npm", "run", "lint"]) is True
    assert command_allowed(["npx", "vitest", "run", "client/src/test"]) is True
    assert command_allowed(["tsc", "--noEmit"]) is True
    assert command_allowed(["python", "-m", "pytest", "server/tests"]) is True

    with pytest.raises(HTTPException):
        normalize_command("npm run typecheck && del important.txt")
    with pytest.raises(HTTPException):
        normalize_command(["git", "commit", "-m", "bad"])


def test_resolve_command_cwd_prefers_client_for_frontend_checks(tmp_path: Path):
    (tmp_path / "client").mkdir()
    (tmp_path / "client" / "package.json").write_text(
        '{"scripts":{"build":"vite build","lint":"eslint .","test":"vitest","typecheck":"tsc --noEmit"}}',
        encoding="utf-8",
    )
    (tmp_path / "client" / "tsconfig.json").write_text("{}", encoding="utf-8")
    (tmp_path / "client" / "vitest.config.ts").write_text("export default {};\n", encoding="utf-8")

    assert resolve_command_cwd(tmp_path, ["npm", "run", "build"]) == (tmp_path / "client").resolve()
    assert resolve_command_cwd(tmp_path, ["npx", "vitest", "run"]) == (tmp_path / "client").resolve()
    assert resolve_command_cwd(tmp_path, ["tsc", "--noEmit"]) == (tmp_path / "client").resolve()
