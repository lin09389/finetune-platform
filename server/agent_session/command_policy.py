"""Command allowlist and project verification command discovery."""

from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path
from typing import Any

from fastapi import HTTPException

logger = logging.getLogger(__name__)


COMMAND_ALLOWLIST = (
    ("npm", "run", "typecheck"),
    ("npm", "run", "build"),
    ("npm", "run", "lint"),
    ("npm", "run", "test"),
    ("npm", "run", "dev"),
    ("npm", "test"),
    ("npx", "vitest", "run"),
    ("vitest", "run"),
    ("tsc", "--noemit"),
    ("python", "-m", "pytest"),
    ("python", "-m", "py_compile"),
)

FORBIDDEN_TOKENS = {"|", "&&", "||", ";", ">", ">>", "<", "`", "$", "(", ")", "{", "}", "\n", "\r"}
DESTRUCTIVE = {"rm", "del", "erase", "rmdir", "move", "mv", "git", "curl", "wget", "bash", "sh", "powershell", "cmd", "python3", "python2"}
MAX_ARG_LENGTH = 256
MAX_ARGS_COUNT = 20


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
    if len(args) > MAX_ARGS_COUNT:
        raise HTTPException(status_code=400, detail=f"Command has too many arguments (max {MAX_ARGS_COUNT})")
    if normalize_executable(args[0]) in DESTRUCTIVE:
        raise HTTPException(status_code=400, detail="Destructive commands are not allowed")
    if any(str(item) in FORBIDDEN_TOKENS for item in args):
        raise HTTPException(status_code=400, detail="Shell operators are not allowed in commands")
    for arg in args:
        if len(arg) > MAX_ARG_LENGTH:
            raise HTTPException(status_code=400, detail=f"Command argument too long (max {MAX_ARG_LENGTH} chars)")
        if any(ch in arg for ch in ("$", "\n", "\r")):
            raise HTTPException(status_code=400, detail="Command argument contains forbidden characters")
    args = normalize_npm_prefix_command(args)
    return args


def normalize_npm_prefix_command(args: list[str]) -> list[str]:
    if len(args) >= 5 and normalize_executable(args[0]) == "npm" and args[1].lower() == "--prefix":
        prefix = args[2].replace("\\", "/").strip("/")
        if prefix not in {"client", "."}:
            raise HTTPException(status_code=400, detail="npm --prefix is only allowed for the client workspace")
        if args[3].lower() == "run":
            return ["npm", "run", args[4], *args[5:]]
        if args[3].lower() == "test":
            return ["npm", "test", *args[4:]]
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
        except Exception as e:
            logger.debug(f"Failed to parse {package_json}: {e}")
            continue
        scripts = data.get("scripts") or {}
        for name in ("typecheck", "test", "build", "lint"):
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
        if _has_vitest_support(package_json.parent):
            command = ["npx", "vitest", "run"]
            key = tuple(command + [str(package_json.parent)])
            if key not in seen:
                seen.add(key)
                commands.append(
                    {
                        "command": command,
                        "cwd": str(package_json.parent),
                        "source": package_json.relative_to(root).as_posix() if package_json.is_relative_to(root) else str(package_json),
                        "description": "vitest run",
                        "allowed": command_allowed(command),
                    }
                )
        if (package_json.parent / "tsconfig.json").exists():
            command = ["tsc", "--noEmit"]
            key = tuple(command + [str(package_json.parent)])
            if key not in seen:
                seen.add(key)
                commands.append(
                    {
                        "command": command,
                        "cwd": str(package_json.parent),
                        "source": package_json.relative_to(root).as_posix() if package_json.is_relative_to(root) else str(package_json),
                        "description": "TypeScript compiler check",
                        "allowed": command_allowed(command),
                    }
                )
    if (root / "pytest.ini").exists() or (root / "pyproject.toml").exists() or (root / "server" / "tests").exists():
        command = ["python", "-m", "pytest"]
        commands.append({"command": command, "cwd": str(root), "source": "python", "description": "Python tests", "allowed": True})
    return commands


def resolve_command_cwd(root: Path, args: list[str]) -> Path:
    command = normalize_executable(args[0]) if args else ""
    if command == "npm" and len(args) >= 3 and args[1].lower() == "run":
        script = args[2]
        if package_has_script(root, script):
            return root
        for candidate in _javascript_roots(root):
            if candidate != root and package_has_script(candidate, script):
                return candidate
        return root
    if command == "npm" and len(args) >= 2 and args[1].lower() == "test":
        if package_has_script(root, "test"):
            return root
        for candidate in _javascript_roots(root):
            if candidate != root and package_has_script(candidate, "test"):
                return candidate
        return root
    if command in {"npx", "vitest"}:
        for candidate in _javascript_roots(root):
            if _has_vitest_support(candidate):
                return candidate
        return root
    if command == "tsc":
        for candidate in _javascript_roots(root):
            if (candidate / "tsconfig.json").exists():
                return candidate
        return root
    return root


def package_has_script(root: Path, script: str) -> bool:
    package_json = root / "package.json"
    if not package_json.exists():
        return False
    try:
        data = json.loads(package_json.read_text(encoding="utf-8"))
    except Exception as e:
        logger.debug(f"Failed to parse package.json at {root}: {e}")
        return False
    return script in (data.get("scripts") or {})


def _javascript_roots(root: Path) -> list[Path]:
    candidates: list[Path] = []
    for candidate in (root, root / "client"):
        resolved = candidate.resolve()
        if resolved not in candidates and (candidate / "package.json").exists():
            candidates.append(resolved)
    for candidate in (root / "client", root):
        resolved = candidate.resolve()
        if resolved not in candidates and candidate.exists():
            candidates.append(resolved)
    return candidates or [root.resolve()]


def _has_vitest_support(root: Path) -> bool:
    if not root.exists():
        return False
    if any((root / name).exists() for name in ("vitest.config.ts", "vitest.config.js", "vite.config.ts", "vite.config.js")):
        return True
    package_json = root / "package.json"
    if not package_json.exists():
        return False
    try:
        data = json.loads(package_json.read_text(encoding="utf-8"))
    except Exception as e:
        logger.debug(f"Failed to parse package.json at {root} for vitest check: {e}")
        return False
    scripts = data.get("scripts") or {}
    return any("vitest" in str(value).lower() for value in scripts.values())


def run_git(args: list[str], root: Path, timeout: int = 10) -> dict[str, Any]:
    command = ["git", *args]
    completed = subprocess.run(command, cwd=str(root), text=True, capture_output=True, timeout=timeout, shell=False)
    return {
        "status": "completed" if completed.returncode == 0 else "failed",
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "exit_code": completed.returncode,
    }


__all__ = [
    "COMMAND_ALLOWLIST",
    "FORBIDDEN_TOKENS",
    "DESTRUCTIVE",
    "MAX_ARG_LENGTH",
    "MAX_ARGS_COUNT",
    "normalize_executable",
    "normalize_command",
    "command_allowed",
    "summarize_failure",
    "detect_project_commands",
    "resolve_command_cwd",
    "package_has_script",
    "run_git",
]
