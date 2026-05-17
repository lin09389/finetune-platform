"""
Guard test: no production module may import from deleted legacy packages.

Deleted packages:
  - agent_runtime_legacy
  - workflow_templates
  - digital_team
  - agent_kernel
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SERVER_ROOT = REPO_ROOT / "server"

BANNED_PREFIXES = (
    "agent_runtime_legacy",
    "workflow_templates",
    "digital_team",
    "agent_kernel",
)

EXCLUDED_DIRS = {
    "tests",
    "__pycache__",
    "backup_old_modules",
    "scratch",
}


def _collect_py_files() -> list[Path]:
    files: list[Path] = []
    for path in SERVER_ROOT.rglob("*.py"):
        parts = set(path.relative_to(SERVER_ROOT).parts)
        if parts & EXCLUDED_DIRS:
            continue
        files.append(path)
    return files


def _extract_imports(source: str) -> list[str]:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                modules.append(node.module)
    return modules


def test_no_production_imports_from_deleted_packages() -> None:
    violations: list[str] = []
    for path in _collect_py_files():
        try:
            source = path.read_text(encoding="utf-8")
        except Exception:
            continue
        for module in _extract_imports(source):
            if any(module == prefix or module.startswith(prefix + ".") for prefix in BANNED_PREFIXES):
                rel = path.relative_to(SERVER_ROOT)
                violations.append(f"{rel}: imports '{module}'")

    assert not violations, (
        f"Found {len(violations)} import(s) from deleted legacy packages:\n"
        + "\n".join(f"  {v}" for v in violations)
    )
