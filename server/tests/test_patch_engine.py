"""Tests for the SafePatchEngine: file writes, unified diffs, path safety, and rollback."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import HTTPException

from agent_session.patch_engine import SafePatchEngine, MAX_PATCH_FILES, MAX_FILE_CHARS, MAX_DIFF_CHARS


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("print('hello')\n", encoding="utf-8")
    (tmp_path / "src" / "utils.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "readme.md").write_text("# Hello\n", encoding="utf-8")
    return tmp_path


class TestApplyFileWrites:
    def test_single_file_write(self, workspace: Path):
        engine = SafePatchEngine(workspace)
        result = engine.apply_payload({
            "files": [
                {"path": "src/main.py", "content": "print('updated')\n"},
            ]
        })
        assert result.changed_files == ["src/main.py"]
        assert (workspace / "src" / "main.py").read_text() == "print('updated')\n"
        assert result.summaries[0]["mode"] == "write_file"

    def test_multiple_file_writes(self, workspace: Path):
        engine = SafePatchEngine(workspace)
        result = engine.apply_payload({
            "files": [
                {"path": "src/main.py", "content": "updated1\n"},
                {"path": "docs/readme.md", "content": "# Updated\n"},
            ]
        })
        assert len(result.changed_files) == 2
        assert (workspace / "src" / "main.py").read_text() == "updated1\n"
        assert (workspace / "docs" / "readme.md").read_text() == "# Updated\n"

    def test_create_new_file(self, workspace: Path):
        engine = SafePatchEngine(workspace)
        result = engine.apply_payload({
            "files": [
                {"path": "src/new_module.py", "content": "# new file\n"},
            ]
        })
        assert "src/new_module.py" in result.changed_files
        assert (workspace / "src" / "new_module.py").read_text() == "# new file\n"

    def test_create_nested_directory(self, workspace: Path):
        engine = SafePatchEngine(workspace)
        result = engine.apply_payload({
            "files": [
                {"path": "src/deep/nested/dir.py", "content": "nested\n"},
            ]
        })
        assert (workspace / "src" / "deep" / "nested" / "dir.py").read_text() == "nested\n"

    def test_file_changes_key_alias(self, workspace: Path):
        engine = SafePatchEngine(workspace)
        result = engine.apply_payload({
            "file_changes": [
                {"path": "src/main.py", "content": "alt key\n"},
            ]
        })
        assert "src/main.py" in result.changed_files

    def test_existing_file_requires_old_string_for_safe_replacement(self, workspace: Path):
        engine = SafePatchEngine(workspace)
        with pytest.raises(HTTPException) as exc_info:
            engine.apply_payload({
                "file_path": "src/main.py",
                "new_string": "print('overwrite')\n",
            })
        assert exc_info.value.status_code == 400
        assert "require old_string" in exc_info.value.detail

    def test_file_path_shorthand_can_create_new_file(self, workspace: Path):
        engine = SafePatchEngine(workspace)
        result = engine.apply_payload({
            "file_path": "src/new_file.py",
            "new_string": "print('new')\n",
            "create": True,
        })
        assert "src/new_file.py" in result.changed_files
        assert (workspace / "src" / "new_file.py").read_text() == "print('new')\n"

    def test_file_path_shorthand_cannot_bypass_existing_file_with_create_flag(self, workspace: Path):
        engine = SafePatchEngine(workspace)
        with pytest.raises(HTTPException) as exc_info:
            engine.apply_payload({
                "file_path": "src/main.py",
                "new_string": "print('overwrite')\n",
                "create": True,
            })
        assert exc_info.value.status_code == 400
        assert "require old_string" in exc_info.value.detail

    def test_too_many_files(self, workspace: Path):
        engine = SafePatchEngine(workspace)
        with pytest.raises(HTTPException) as exc_info:
            engine.apply_payload({
                "files": [{"path": f"file{i}.py", "content": "x"} for i in range(MAX_PATCH_FILES + 1)]
            })
        assert exc_info.value.status_code == 400
        assert "too many files" in exc_info.value.detail.lower()

    def test_file_too_large(self, workspace: Path):
        engine = SafePatchEngine(workspace)
        with pytest.raises(HTTPException) as exc_info:
            engine.apply_payload({
                "files": [{"path": "src/huge.py", "content": "x" * (MAX_FILE_CHARS + 1)}]
            })
        assert exc_info.value.status_code == 400
        assert "too large" in exc_info.value.detail.lower()

    def test_empty_files_list(self, workspace: Path):
        engine = SafePatchEngine(workspace)
        with pytest.raises(HTTPException) as exc_info:
            engine.apply_payload({"files": []})
        assert exc_info.value.status_code == 400

    def test_missing_path_key(self, workspace: Path):
        engine = SafePatchEngine(workspace)
        with pytest.raises(HTTPException) as exc_info:
            engine.apply_payload({"files": [{"content": "data"}]})
        assert exc_info.value.status_code == 400


class TestApplyUnifiedDiff:
    def test_simple_hunk(self, workspace: Path):
        original = "line1\nline2\nline3\n"
        target = workspace / "src" / "main.py"
        target.write_text(original, encoding="utf-8")

        engine = SafePatchEngine(workspace)
        diff = "--- a/src/main.py\n+++ b/src/main.py\n@@ -1,3 +1,3 @@\n line1\n-line2\n+line2_modified\n line3\n"
        result = engine.apply_payload({"format": "unified_diff", "diff": diff})

        assert "src/main.py" in result.changed_files
        assert "line2_modified" in target.read_text()

    def test_add_new_lines(self, workspace: Path):
        original = "line1\nline3\n"
        target = workspace / "src" / "main.py"
        target.write_text(original, encoding="utf-8")

        engine = SafePatchEngine(workspace)
        diff = "--- a/src/main.py\n+++ b/src/main.py\n@@ -1,2 +1,3 @@\n line1\n+line2\n line3\n"
        result = engine.apply_payload({"format": "unified_diff", "diff": diff})

        content = target.read_text()
        assert "line2" in content

    def test_delete_lines(self, workspace: Path):
        original = "line1\ndelete_me\nline3\n"
        target = workspace / "src" / "main.py"
        target.write_text(original, encoding="utf-8")

        engine = SafePatchEngine(workspace)
        diff = "--- a/src/main.py\n+++ b/src/main.py\n@@ -1,3 +1,2 @@\n line1\n-delete_me\n line3\n"
        engine.apply_payload({"format": "unified_diff", "diff": diff})

        content = target.read_text()
        assert "delete_me" not in content
        assert "line1" in content
        assert "line3" in content

    def test_diff_too_large(self, workspace: Path):
        engine = SafePatchEngine(workspace)
        with pytest.raises(HTTPException) as exc_info:
            engine.apply_payload({"format": "unified_diff", "diff": "x" * (MAX_DIFF_CHARS + 1)})
        assert exc_info.value.status_code == 400

    def test_binary_diff_rejected(self, workspace: Path):
        engine = SafePatchEngine(workspace)
        diff = "--- a/src/main.py\n+++ b/src/main.py\nBinary files differ\n"
        with pytest.raises(HTTPException) as exc_info:
            engine.apply_payload({"format": "unified_diff", "diff": diff})
        assert exc_info.value.status_code == 400
        assert "Binary" in exc_info.value.detail

    def test_rename_diff_rejected(self, workspace: Path):
        engine = SafePatchEngine(workspace)
        diff = "--- a/src/main.py\n+++ b/src/main.py\nrename from src/main.py\nrename to src/renamed.py\n"
        with pytest.raises(HTTPException) as exc_info:
            engine.apply_payload({"format": "unified_diff", "diff": diff})
        assert "rename" in exc_info.value.detail.lower()

    def test_empty_diff_rejected(self, workspace: Path):
        engine = SafePatchEngine(workspace)
        with pytest.raises(HTTPException) as exc_info:
            engine.apply_payload({"format": "unified_diff", "diff": "   \n  \n"})
        assert exc_info.value.status_code == 400

    def test_new_file_creation_via_diff(self, workspace: Path):
        engine = SafePatchEngine(workspace)
        diff = "--- /dev/null\n+++ b/src/brand_new.py\n@@ -0,0 +1,3 @@\n+import os\n+\n+print(os.getcwd())\n"
        result = engine.apply_payload({"format": "unified_diff", "diff": diff})
        assert (workspace / "src" / "brand_new.py").exists()
        content = (workspace / "src" / "brand_new.py").read_text()
        assert "import os" in content


class TestPathSafety:
    def test_path_traversal_blocked(self, workspace: Path):
        engine = SafePatchEngine(workspace)
        with pytest.raises(HTTPException) as exc_info:
            engine.apply_payload({
                "files": [{"path": "../../etc/passwd", "content": "hacked"}]
            })
        assert exc_info.value.status_code == 400
        assert "inside" in exc_info.value.detail.lower() or "path" in exc_info.value.detail.lower()

    def test_absolute_path_outside_workspace(self, workspace: Path):
        engine = SafePatchEngine(workspace)
        with pytest.raises(HTTPException) as exc_info:
            engine.apply_payload({
                "files": [{"path": "C:/Windows/System32/exploit.py", "content": "bad"}]
            })
        assert exc_info.value.status_code == 400

    def test_dev_null_path_rejected(self, workspace: Path):
        engine = SafePatchEngine(workspace)
        with pytest.raises(HTTPException) as exc_info:
            engine.apply_payload({
                "files": [{"path": "/dev/null", "content": "x"}]
            })
        assert exc_info.value.status_code == 400


class TestRollback:
    def test_rollback_restores_original(self, workspace: Path):
        engine = SafePatchEngine(workspace)
        original = (workspace / "src" / "main.py").read_text()

        engine.apply_payload({
            "files": [{"path": "src/main.py", "content": "MODIFIED\n"}]
        })
        assert (workspace / "src" / "main.py").read_text() == "MODIFIED\n"

        restored = engine.rollback()
        assert len(restored) >= 1
        assert (workspace / "src" / "main.py").read_text() == original

    def test_rollback_removes_new_file(self, workspace: Path):
        engine = SafePatchEngine(workspace)
        engine.apply_payload({
            "files": [{"path": "src/brand_new.py", "content": "new file\n"}]
        })
        assert (workspace / "src" / "brand_new.py").exists()

        engine.rollback()
        assert not (workspace / "src" / "brand_new.py").exists()

    def test_has_backup_property(self, workspace: Path):
        engine = SafePatchEngine(workspace)
        assert not engine.has_backup
        engine.apply_payload({
            "files": [{"path": "src/main.py", "content": "changed\n"}]
        })
        assert engine.has_backup
        engine.clear_backup()
        assert not engine.has_backup
