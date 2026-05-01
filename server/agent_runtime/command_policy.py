"""Command allowlist and project verification command discovery."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from fastapi import HTTPException


COMMAND_ALLOWLIST = (
    ("npm", "run", "typecheck"),
    ("npm", "test"),
    ("python", "-m", "pytest"),
    ("python", "-m", "py_compile"),
)

FORBIDDEN_TOKENS = {"|", "&&", "||", ";", ">", ">>", "<", "`"}
DESTRUCTIVE = {"rm", "del", "erase", "rmdir", "move", "mv", "git"}


def normalize_executable(value: str) -> str:
    name = Path(value).name.lower()
    for suffix in (".cmd", ".exe", ".bat"):
        if name.endswith(suffix):
            return name[: -len(suffix)]
    return name


def normalize_command(command: Any) -> list[str]:
    if isinstance(command, list):
        args = [str(item) for item in command]
    elif isinstance(command, str):
        if any(token in command for token in FORBIDDEN_TOKENS):
            raise HTTPException(status_code=400, detail="Command must be an argv list without shell operators")
        args = command.split()
    else:
        args = []
    if not args:
        raise HTTPException(status_code=400, detail="Command action requires command")
    if normalize_executable(args[0]) in DESTRUCTIVE:
        raise HTTPException(status_code=400, detail="Destructive commands are not allowed")
    if any(str(item) in FORBIDDEN_TOKENS for item in args):
        raise HTTPException(status_code=400, detail="Shell operators are not allowed in commands")
    return args


def command_allowed(args: list[str]) -> bool:
    lowered = tuple(normalize_executable(item) if index == 0 else item.lower() for index, item in enumerate(args))
    return any(lowered[: len(prefix)] == prefix for prefix in COMMAND_ALLOWLIST)


def summarize_failure(stdout: str = "", stderr: str = "", error: str | None = None, limit: int = 1600) -> str:
    text = "\n".join(part for part in [error or "", stderr or "", stdout or ""] if part).strip()
    if not text:
        return ""
    lines = [line.rstrip() for line in text.splitlines() if line.strip()]
    selected = lines[-20:]
    summary = "\n".join(selected)
    return summary[:limit]


def detect_project_commands(root: Path) -> list[dict[str, Any]]:
    commands: list[dict[str, Any]] = []
    package_candidates = [root / "package.json", root / "client" / "package.json"]
    seen: set[tuple[str, ...]] = set()
    for package_json in package_candidates:
        if not package_json.exists():
            continue
        try:
            data = json.loads(package_json.read_text(encoding="utf-8"))
        except Exception:
            continue
        scripts = data.get("scripts") or {}
        for name in ("typecheck", "test"):
            if name in scripts:
                command = ["npm", "run", name] if name != "test" else ["npm", "test"]
                key = tuple(command + [str(package_json.parent)])
                if key not in seen:
                    seen.add(key)
                    commands.append(
                        {
                            "command": command,
                            "cwd": str(package_json.parent),
                            "source": package_json.relative_to(root).as_posix() if package_json.is_relative_to(root) else str(package_json),
                            "description": f"package script: {name}",
                            "allowed": command_allowed(command),
                        }
                    )
    if (root / "pytest.ini").exists() or (root / "pyproject.toml").exists() or (root / "server" / "tests").exists():
        command = ["python", "-m", "pytest"]
        commands.append({"command": command, "cwd": str(root), "source": "python", "description": "Python tests", "allowed": True})
    return commands


def run_git(args: list[str], root: Path, timeout: int = 10) -> dict[str, Any]:
    command = ["git", *args]
    completed = subprocess.run(command, cwd=str(root), text=True, capture_output=True, timeout=timeout, shell=False)
    return {
        "status": "completed" if completed.returncode == 0 else "failed",
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "exit_code": completed.returncode,
    }
