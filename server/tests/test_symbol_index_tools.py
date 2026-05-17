from __future__ import annotations

from pathlib import Path

import pytest

from agent_session.file_tools import FileToolsMixin
from agent_session.symbol_index_tools import AST_GREP_SYMBOL_RE, SymbolIndexToolsMixin


class _Host(SymbolIndexToolsMixin, FileToolsMixin):
    """Concrete host: FileToolsMixin supplies _candidate_files/_is_searchable_code_file."""

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


def _ctx(path: Path) -> dict:
    return {"project_path": str(path)}


# ── AST_GREP_SYMBOL_RE ─────────────────────────────────────────────────────

@pytest.mark.parametrize("name", ["myFunc", "MyClass", "_private", "$jquery", "a1b2c3"])
def test_symbol_re_accepts_valid_identifiers(name):
    assert AST_GREP_SYMBOL_RE.match(name)


@pytest.mark.parametrize("name", ["1invalid", "has-hyphen", "has space", ""])
def test_symbol_re_rejects_invalid_identifiers(name):
    assert not AST_GREP_SYMBOL_RE.match(name)


# ── _symbol_definition_patterns ───────────────────────────────────────────

def test_patterns_detect_python_def(tmp_path):
    h = _Host()
    patterns = h._symbol_definition_patterns("my_func")
    result = h._match_symbol_definition("def my_func(arg):", "my_func", patterns)
    assert result is not None
    assert result["kind"] == "function"


def test_patterns_detect_ts_class(tmp_path):
    h = _Host()
    patterns = h._symbol_definition_patterns("MyService")
    result = h._match_symbol_definition("export class MyService {", "MyService", patterns)
    assert result is not None
    assert result["kind"] == "class"


def test_patterns_detect_ts_interface(tmp_path):
    h = _Host()
    patterns = h._symbol_definition_patterns("IProps")
    result = h._match_symbol_definition("interface IProps {", "IProps", patterns)
    assert result is not None
    assert result["kind"] == "interface"


def test_patterns_no_false_positive(tmp_path):
    h = _Host()
    patterns = h._symbol_definition_patterns("foo")
    result = h._match_symbol_definition("  const x = callFoo()", "foo", patterns)
    assert result is None


# ── _path_in_scope ─────────────────────────────────────────────────────────

def test_path_in_scope_exact_match():
    h = _Host()
    assert h._path_in_scope("server/api/routes.py", ["server/api/routes.py"])


def test_path_in_scope_subdirectory():
    h = _Host()
    assert h._path_in_scope("server/api/routes.py", ["server/api"])


def test_path_in_scope_no_match():
    h = _Host()
    assert not h._path_in_scope("client/src/App.tsx", ["server/api"])


def test_path_in_scope_empty_scope_list():
    h = _Host()
    assert not h._path_in_scope("server/api/routes.py", [])


# ── _find_symbol_builtin ───────────────────────────────────────────────────

def test_find_symbol_builtin_detects_python_function(tmp_path):
    (tmp_path / "module.py").write_text("def greet(name):\n    return name\n")
    h = _Host()
    r = h._find_symbol({"symbol": "greet"}, _ctx(tmp_path))
    assert r.status == "completed"
    matches = r.payload["matches"]
    assert any(m["kind"] == "function" and "module.py" in m["path"] for m in matches)


def test_find_symbol_builtin_detects_ts_class(tmp_path):
    (tmp_path / "service.ts").write_text("export class UserService {\n  get() {}\n}\n")
    h = _Host()
    r = h._find_symbol({"symbol": "UserService"}, _ctx(tmp_path))
    assert r.status == "completed"
    matches = r.payload["matches"]
    assert any(m["kind"] == "class" for m in matches)


def test_find_symbol_missing_name_returns_failed(tmp_path):
    h = _Host()
    r = h._find_symbol({}, _ctx(tmp_path))
    assert r.status == "failed"
    assert r.error == "symbol is required"


def test_find_symbol_no_match_returns_empty(tmp_path):
    (tmp_path / "empty.py").write_text("x = 1\n")
    h = _Host()
    r = h._find_symbol({"symbol": "nonExistentSymbol"}, _ctx(tmp_path))
    assert r.status == "completed"
    assert r.payload["matches"] == []


# ── _find_references_builtin ───────────────────────────────────────────────

def test_find_references_builtin_finds_usage(tmp_path):
    (tmp_path / "lib.py").write_text("def process():\n    pass\n")
    (tmp_path / "main.py").write_text("from lib import process\nprocess()\n")
    h = _Host()
    r = h._find_references({"symbol": "process"}, _ctx(tmp_path))
    assert r.status == "completed"
    paths = [m["path"] for m in r.payload["matches"]]
    assert any("main.py" in p for p in paths)


def test_find_references_excludes_definitions_by_default(tmp_path):
    (tmp_path / "lib.py").write_text("def process():\n    pass\n")
    (tmp_path / "main.py").write_text("process()\n")
    h = _Host()
    r = h._find_references({"symbol": "process", "include_definitions": False}, _ctx(tmp_path))
    assert r.status == "completed"
    assert all(not m.get("is_definition") for m in r.payload["matches"])


def test_find_references_missing_symbol_returns_failed(tmp_path):
    h = _Host()
    r = h._find_references({}, _ctx(tmp_path))
    assert r.status == "failed"
