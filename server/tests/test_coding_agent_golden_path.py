"""Deterministic coding-agent golden-path contract audit."""

from __future__ import annotations

import json
from pathlib import Path


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "coding_agent_golden_path.json"
REQUIRED_SCENARIO_KINDS = {
    "python_bug_fix",
    "react_change",
    "cross_stack_feature",
    "multi_file_refactor",
    "verification_failure_repair",
    "refresh_resume",
}
REQUIRED_FIELDS = {
    "id",
    "title",
    "kind",
    "initial_files",
    "required_reads",
    "allowed_writes",
    "commands",
    "expected_verification",
    "expected_changed_files",
    "forbidden_paths",
    "invariants",
}


def test_golden_path_fixture_has_complete_engineering_contracts():
    scenarios = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))

    assert isinstance(scenarios, list)
    assert {scenario["kind"] for scenario in scenarios} == REQUIRED_SCENARIO_KINDS
    for scenario in scenarios:
        assert REQUIRED_FIELDS <= scenario.keys(), scenario.get("id", "unknown")
        assert scenario["required_reads"]
        assert scenario["allowed_writes"]
        assert scenario["commands"]
        assert scenario["expected_changed_files"]
        assert scenario["forbidden_paths"]
        assert {"build_mode_available", "hybrid_coding_training_coexists"} <= set(
            scenario["invariants"]
        )
