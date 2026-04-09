#!/usr/bin/env python3
"""Guard critical source files against encoding regressions."""

from __future__ import annotations

import codecs
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace")


ROOT = Path(__file__).resolve().parent.parent

TARGETS = [
    ROOT / "client" / "src",
    ROOT / "server" / "api",
    ROOT / "server" / "agent",
    ROOT / "server" / "core",
    ROOT / "server" / "context",
    ROOT / "server" / "memory",
    ROOT / "server" / "security",
    ROOT / "server" / "gateway",
    ROOT / "server" / "heartbeat",
    ROOT / "server" / "workspace",
    ROOT / "server" / "cua",
    ROOT / "server" / "backends",
    ROOT / "server" / "tests",
    ROOT / "server" / "main.py",
    ROOT / "scripts",
    ROOT / "tests",
    ROOT / ".github" / "workflows",
    ROOT / "package.json",
    ROOT / "pyproject.toml",
    ROOT / "README.md",
    ROOT / "AGENTS.md",
]

TEXT_SUFFIXES = {
    ".py",
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".json",
    ".yml",
    ".yaml",
    ".md",
    ".toml",
    ".css",
    ".scss",
    ".html",
}

SKIP_DIR_NAMES = {
    ".git",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    ".trae",
    "__pycache__",
    "backup_old_modules",
    "build",
    "data",
    "dist",
    "logs",
    "models",
    "node_modules",
    "outputs",
    "venv",
}

SUSPICIOUS_TOKENS = [
    "鏀寔",
    "妫€鏌",
    "鍒濆",
    "璇锋眰",
    "鍝嶅簲",
    "閿欒",
    "鏈嶅姟",
    "缂栫爜",
    "榛戝悕",
    "闄愬埗",
    "杩囨护",
    "寮€濮",
    "鏁版嵁",
    "瀛樺偍",
    "鍒犻櫎",
    "璁板繂",
    "浼氳瘽",
    "鍔熻兘",
    "鍙傛暟",
    "杩斿洖",
    "绫诲瀷",
    "鐘舵€",
    "璺緞",
]


def iter_target_files() -> list[Path]:
    files: list[Path] = []

    for target in TARGETS:
        if not target.exists():
            continue

        if target.is_file():
            files.append(target)
            continue

        for path in sorted(target.rglob("*")):
            if not path.is_file():
                continue
            if any(part in SKIP_DIR_NAMES for part in path.parts):
                continue
            if path.suffix.lower() in TEXT_SUFFIXES:
                files.append(path)

    return files


def find_content_issue(text: str, *, check_tokens: bool = True) -> tuple[int, str] | None:
    for line_no, line in enumerate(text.splitlines(), start=1):
        if "\ufffd" in line:
            return line_no, "replacement character found"

        if any("\ue000" <= ch <= "\uf8ff" for ch in line):
            return line_no, "private-use character found"

        if check_tokens:
            for token in SUSPICIOUS_TOKENS:
                if token in line:
                    return line_no, f"suspicious mojibake token '{token}' found"

    return None


def check_file(path: Path) -> list[str]:
    issues: list[str] = []
    raw = path.read_bytes()

    if raw.startswith(codecs.BOM_UTF8):
        issues.append("UTF-8 BOM found")

    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        issues.append(f"invalid UTF-8 bytes at offset {exc.start}")
        return issues

    if path.resolve() != Path(__file__).resolve():
        content_issue = find_content_issue(text, check_tokens=True)
        if content_issue:
            line_no, detail = content_issue
            issues.append(f"line {line_no}: {detail}")

    return issues


def main() -> int:
    files = iter_target_files()
    failures: list[tuple[Path, list[str]]] = []

    for path in files:
        issues = check_file(path)
        if issues:
            failures.append((path, issues))

    if failures:
        print("Encoding check failed.")
        print()
        for path, issues in failures:
            rel = path.relative_to(ROOT)
            print(rel)
            for issue in issues:
                print(f"  - {issue}")
        print()
        print(f"Scanned {len(files)} files, found {len(failures)} problematic files.")
        return 1

    print(f"Encoding check passed for {len(files)} files.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
