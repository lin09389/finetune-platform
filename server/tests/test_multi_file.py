"""Phase B4: multi-file completion semantics (lean)."""
from __future__ import annotations

from pathlib import Path

from agent_session.multi_file import (
    apply_multi_file_completion_rules,
    build_multi_file_state,
    companion_candidates_for_path,
    find_existing_companions,
    format_multi_file_card_lines,
    multi_file_correction_blurb,
)
from agent_session.session_progress import (
    build_completion_gate,
    build_working_state_card,
    empty_tool_metrics,
)


def test_companion_candidates_for_python_and_ts():
    py = companion_candidates_for_path("src/cli.py")
    assert "test_cli.py" in py or any("test_cli" in p for p in py)
    ts = companion_candidates_for_path("src/Counter.tsx")
    assert any("Counter.test" in p or "Counter.spec" in p for p in ts)


def test_find_existing_companions(tmp_path: Path):
    (tmp_path / "cli.py").write_text("def main():\n    pass\n", encoding="utf-8")
    (tmp_path / "test_cli.py").write_text("def test_main():\n    assert True\n", encoding="utf-8")
    found = find_existing_companions(tmp_path, ["cli.py"])
    assert "test_cli.py" in found


def test_build_multi_file_state_flags_unverified_paths():
    metadata = {
        "trajectory_guard": {
            "writes": {"/workspace/a.py": 1, "/workspace/b.py": 2},
            "verified_paths": ["a.py"],
            "reads": {"a.py": 1, "b.py": 1},
        }
    }
    multi = build_multi_file_state(metadata)
    assert multi["is_multi_file"] is True
    assert multi["source_write_count"] == 2
    assert multi["path_verify_ok"] is False
    assert "b.py" in multi["unverified_paths"]


def test_completion_gate_multi_file_requires_path_level_verify():
    metadata = {
        "trajectory_guard": {
            "writes": {"app.py": 1, "util.py": 2},
            "verified_paths": [],
            "successful_write_sequences": [1, 2],
            "diff_write_sequences": [1, 2],
            # Sequence-only verify would look "ok" without path coverage:
            "last_write_sequence": 2,
            "last_verification_sequence": 3,
        },
        "tool_metrics": {**empty_tool_metrics(), "verify_attempted": 1, "verify_ok": 1},
    }
    gate = build_completion_gate(metadata, status="completed")
    assert gate["multi_file"]["is_multi_file"] is True
    assert "multi_file_path_verify_required" in gate["gaps"]
    assert gate["completed_ok"] is False
    assert gate["verify_ok"] in (0, False)


def test_completion_gate_multi_file_passes_when_all_paths_verified():
    metadata = {
        "trajectory_guard": {
            "writes": {"app.py": 1, "util.py": 2},
            "verified_paths": ["app.py", "util.py"],
            "successful_write_sequences": [1, 2],
            "diff_write_sequences": [1, 2],
            "last_write_sequence": 2,
            "last_verification_sequence": 3,
        },
        "tool_metrics": {**empty_tool_metrics(), "verify_attempted": 1, "verify_ok": 1},
    }
    gate = build_completion_gate(metadata, status="completed")
    assert gate["multi_file"]["is_multi_file"] is True
    assert "multi_file_path_verify_required" not in gate["gaps"]
    assert gate["completed_ok"] is True


def test_single_file_unchanged_by_multi_file_rules():
    metadata = {
        "trajectory_guard": {
            "writes": {"app.py": 1},
            "verified_paths": [],
            "successful_write_sequences": [1],
            "diff_write_sequences": [1],
            "last_write_sequence": 1,
            "last_verification_sequence": 2,
        },
        "tool_metrics": {**empty_tool_metrics(), "verify_attempted": 1, "verify_ok": 1},
    }
    gate = build_completion_gate(metadata, status="completed")
    assert gate.get("multi_file", {}).get("is_multi_file") is False
    # Sequence-based verify still allowed for single-file.
    assert gate["completed_ok"] is True


def test_working_state_card_multi_file_section(tmp_path: Path):
    (tmp_path / "a.py").write_text("a=1\n", encoding="utf-8")
    (tmp_path / "b.py").write_text("b=1\n", encoding="utf-8")
    (tmp_path / "test_a.py").write_text("def test_a():\n    assert True\n", encoding="utf-8")
    metadata = {
        "project_path": str(tmp_path),
        "trajectory_guard": {
            "writes": {"a.py": 1, "b.py": 2},
            "reads": {"a.py": 1, "b.py": 1},
            "verified_paths": [],
        },
        "tool_metrics": {**empty_tool_metrics(), "tools_total": 4},
    }
    card = build_working_state_card(metadata)
    assert "多文件编辑（B4）" in card
    blurb = multi_file_correction_blurb(build_multi_file_state(metadata, project_path=tmp_path))
    assert "多文件编辑" in blurb
    lines = format_multi_file_card_lines(build_multi_file_state(metadata, project_path=tmp_path))
    assert any("B4" in line for line in lines)


def test_apply_multi_file_rules_pure():
    gate = {
        "status": "completed",
        "completed_ok": True,
        "verify_ok": 1,
        "gaps": [],
        "summary": "已写 2 个路径；验证通过",
    }
    multi = {
        "is_multi_file": True,
        "source_write_count": 2,
        "unverified_paths": ["b.py"],
        "path_verify_ok": False,
        "companions_unread": ["test_a.py"],
        "companion_paths": ["test_a.py"],
    }
    out = apply_multi_file_completion_rules(gate, multi)
    assert out["completed_ok"] is False
    assert "multi_file_path_verify_required" in out["gaps"]
    assert "multi_file_companions_unread" in out["gaps"]
