from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent_session.file_tools import FileToolsMixin
from agent_session.tool_types import ToolResult


class _Host(FileToolsMixin):
    """Minimal concrete host — stubs cross-mixin calls to SymbolIndexToolsMixin."""

    repository = None

    def _root(self, context: dict) -> Path:
        return Path(context["project_path"])

    def _safe_path(self, root: Path, raw_path: str) -> Path:
        target = Path(raw_path)
        if not target.is_absolute():
            target = root / target
        target = target.resolve()
        if not target.is_relative_to(root):
            raise ValueError("path must stay inside project path")
        return target

    def _normalize_tool_payload(self, payload: dict) -> dict:
        return payload

    def _find_symbol(self, args: dict, context: dict) -> ToolResult:
        return ToolResult("completed", "", {"matches": [], "engine": "stub"})

    def _find_references(self, args: dict, context: dict) -> ToolResult:
        return ToolResult("completed", "", {"matches": [], "engine": "stub"})


def _ctx(path: Path) -> dict:
    return {"project_path": str(path)}


# ── _read ──────────────────────────────────────────────────────────────────

def test_read_existing_file(tmp_path):
    f = tmp_path / "hello.py"
    f.write_text("print('hello')")
    r = _Host()._read({"path": "hello.py"}, _ctx(tmp_path))
    assert r.status == "completed"
    assert "print" in r.payload["content"]
    assert r.payload["path"] == "hello.py"
    assert r.payload["truncated"] is False


def test_read_missing_file_returns_failed(tmp_path):
    r = _Host()._read({"path": "nope.py"}, _ctx(tmp_path))
    assert r.status == "failed"
    assert r.error == "file not found"


def test_read_empty_path_returns_failed(tmp_path):
    r = _Host()._read({}, _ctx(tmp_path))
    assert r.status == "failed"
    assert r.error == "path is required"


def test_read_path_escape_raises(tmp_path):
    with pytest.raises(ValueError, match="inside project path"):
        _Host()._read({"path": "../../etc/passwd"}, _ctx(tmp_path))


def test_read_batch_multiple_paths(tmp_path):
    (tmp_path / "a.py").write_text("a = 1")
    (tmp_path / "b.py").write_text("b = 2")
    r = _Host()._read({"paths": ["a.py", "b.py"]}, _ctx(tmp_path))
    assert r.status == "completed"
    assert len(r.payload["files"]) == 2
    assert r.payload["touched_paths"] == ["a.py", "b.py"]


def test_read_batch_partial_failure(tmp_path):
    (tmp_path / "good.py").write_text("x = 1")
    r = _Host()._read({"paths": ["good.py", "missing.py"]}, _ctx(tmp_path))
    assert r.status == "completed"
    assert len(r.payload["files"]) == 1
    assert len(r.payload["failures"]) == 1


def test_read_truncates_large_file(tmp_path):
    f = tmp_path / "big.py"
    f.write_text("x" * 25_000)
    r = _Host()._read({"path": "big.py"}, _ctx(tmp_path))
    assert r.status == "completed"
    assert r.payload["truncated"] is True
    assert len(r.payload["content"]) == 20_000


# ── _search ────────────────────────────────────────────────────────────────

def test_search_finds_match(tmp_path):
    (tmp_path / "code.py").write_text("def authenticate(user):\n    pass\n")
    r = _Host()._search({"query": "authenticate"}, _ctx(tmp_path))
    assert r.status == "completed"
    assert len(r.payload["matches"]) >= 1
    assert r.payload["matches"][0]["preview"] == "def authenticate(user):"


def test_search_no_results(tmp_path):
    (tmp_path / "code.py").write_text("x = 1\n")
    r = _Host()._search({"query": "nonexistent_keyword_xyz"}, _ctx(tmp_path))
    assert r.status == "completed"
    assert r.payload["matches"] == []


def test_search_empty_query_returns_failed(tmp_path):
    r = _Host()._search({}, _ctx(tmp_path))
    assert r.status == "failed"
    assert r.error == "query is required"


def test_search_case_insensitive(tmp_path):
    (tmp_path / "code.ts").write_text("const MyComponent = () => {}\n")
    r = _Host()._search({"query": "mycomponent"}, _ctx(tmp_path))
    assert r.status == "completed"
    assert len(r.payload["matches"]) >= 1


# ── _glob ──────────────────────────────────────────────────────────────────

def test_glob_lists_py_files(tmp_path):
    (tmp_path / "a.py").write_text("")
    (tmp_path / "b.py").write_text("")
    (tmp_path / "c.txt").write_text("")
    r = _Host()._glob({"path_glob": "**/*.py"}, _ctx(tmp_path))
    assert r.status == "completed"
    assert set(r.payload["files"]) == {"a.py", "b.py"}


def test_glob_default_pattern(tmp_path):
    (tmp_path / "x.ts").write_text("")
    r = _Host()._glob({}, _ctx(tmp_path))
    assert "x.ts" in r.payload["files"]


# ── _is_searchable_code_file ───────────────────────────────────────────────

@pytest.mark.parametrize("name", ["main.py", "app.ts", "comp.tsx", "style.css", "doc.md"])
def test_is_searchable_accepts_code_extensions(name):
    assert _Host()._is_searchable_code_file(Path(name)) is True


@pytest.mark.parametrize("name", ["image.png", "binary.exe", "archive.zip"])
def test_is_searchable_rejects_binary_extensions(name):
    assert _Host()._is_searchable_code_file(Path(name)) is False


# ── _detect_project_commands ───────────────────────────────────────────────

def test_detect_commands_empty_root_has_python_compile(tmp_path):
    r = _Host()._detect_project_commands({}, _ctx(tmp_path))
    assert r.status == "completed"
    kinds = {c["kind"] for c in r.payload["commands"]}
    assert "python_compile" in kinds


def test_detect_commands_reads_npm_scripts(tmp_path):
    pkg = {"scripts": {"typecheck": "tsc --noEmit", "test": "vitest", "build": "vite build", "lint": "eslint ."}}
    (tmp_path / "package.json").write_text(json.dumps(pkg))
    r = _Host()._detect_project_commands({}, _ctx(tmp_path))
    kinds = {c["kind"] for c in r.payload["commands"]}
    assert "typecheck" in kinds
    assert "test" in kinds
    assert "build" in kinds
    assert "lint" in kinds


def test_detect_commands_no_duplicate_commands(tmp_path):
    pkg = {"scripts": {"typecheck": "tsc --noEmit"}}
    (tmp_path / "package.json").write_text(json.dumps(pkg))
    r = _Host()._detect_project_commands({}, _ctx(tmp_path))
    commands = [tuple(c["command"]) for c in r.payload["commands"]]
    assert len(commands) == len(set(commands))


# ── _candidate_files ───────────────────────────────────────────────────────

def test_candidate_files_ignores_node_modules(tmp_path):
    nm = tmp_path / "node_modules"
    nm.mkdir()
    (nm / "pkg.js").write_text("")
    (tmp_path / "real.py").write_text("")
    files = list(_Host()._candidate_files(tmp_path))
    paths = [f.name for f in files]
    assert "real.py" in paths
    assert "pkg.js" not in paths


def test_candidate_files_ignores_git(tmp_path):
    git = tmp_path / ".git"
    git.mkdir()
    (git / "config").write_text("")
    (tmp_path / "src.py").write_text("")
    files = list(_Host()._candidate_files(tmp_path))
    paths = [f.name for f in files]
    assert "src.py" in paths
    assert "config" not in paths
