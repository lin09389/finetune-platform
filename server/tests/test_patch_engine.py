from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import HTTPException

from agent_runtime.patch_engine import SafePatchEngine


def test_unified_diff_patch_applies_text_change(tmp_path: Path):
    target = tmp_path / "hello.txt"
    target.write_text("one\ntwo\n", encoding="utf-8")
    diff = """--- a/hello.txt
+++ b/hello.txt
@@ -1,2 +1,2 @@
 one
-two
+three
"""

    result = SafePatchEngine(tmp_path).apply_payload({"format": "unified_diff", "diff": diff})

    assert result.changed_files == ["hello.txt"]
    assert target.read_text(encoding="utf-8") == "one\nthree\n"


def test_unified_diff_can_create_new_text_file(tmp_path: Path):
    diff = """--- /dev/null
+++ b/tmp/smoke.txt
@@ -0,0 +1,2 @@
+hello
+agent
"""

    result = SafePatchEngine(tmp_path).apply_payload({"format": "unified_diff", "diff": diff})

    assert result.changed_files == ["tmp/smoke.txt"]
    assert (tmp_path / "tmp" / "smoke.txt").read_text(encoding="utf-8") == "hello\nagent\n"


def test_unified_diff_rejects_workspace_escape(tmp_path: Path):
    diff = """--- /dev/null
+++ b/../outside.txt
@@ -0,0 +1 @@
+bad
"""

    with pytest.raises(HTTPException):
        SafePatchEngine(tmp_path).apply_payload({"format": "unified_diff", "diff": diff})


def test_unified_diff_rejects_delete_and_conflict(tmp_path: Path):
    target = tmp_path / "hello.txt"
    target.write_text("one\n", encoding="utf-8")
    delete_diff = """--- a/hello.txt
+++ /dev/null
@@ -1 +0,0 @@
-one
"""
    conflict_diff = """--- a/hello.txt
+++ b/hello.txt
@@ -1 +1 @@
-missing
+two
"""

    with pytest.raises(HTTPException):
        SafePatchEngine(tmp_path).apply_payload({"format": "unified_diff", "diff": delete_diff})
    with pytest.raises(HTTPException):
        SafePatchEngine(tmp_path).apply_payload({"format": "unified_diff", "diff": conflict_diff})

