from __future__ import annotations

import json
import hashlib
import shutil
from pathlib import Path

import pytest

from agent_eval import (
    CatalogLoadError,
    default_catalog_path,
    default_fixture_root,
    load_scenario_catalog,
)

FIXTURES = default_fixture_root()
CATALOG = default_catalog_path()


def test_loads_versioned_catalog_with_required_coverage() -> None:
    catalog = load_scenario_catalog(CATALOG, FIXTURES)

    assert catalog.schema_version == 1
    assert len(catalog.scenarios) >= 30
    assert len({scenario.id for scenario in catalog.scenarios}) == len(catalog.scenarios)
    assert {scenario.mode.value for scenario in catalog.scenarios} == {
        "coding",
        "training",
        "hybrid",
    }
    assert {scenario.category.value for scenario in catalog.scenarios} >= {
        "feature",
        "debug",
        "refactor",
        "training",
        "hybrid",
    }
    stacks = {stack for scenario in catalog.scenarios for stack in scenario.stacks}
    assert {"python", "react", "typescript", "training"} <= stacks


def _write_catalog(tmp_path: Path, mutate) -> tuple[Path, Path]:
    fixture_root = tmp_path / "baseline"
    shutil.copytree(FIXTURES, fixture_root)
    path = fixture_root / "catalog.v1.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    mutate(payload)
    path.write_text(json.dumps(payload), encoding="utf-8")
    integrity_path = fixture_root / "integrity.v1.json"
    integrity = json.loads(integrity_path.read_text(encoding="utf-8"))
    integrity["catalog_checksum"] = f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"
    integrity_path.write_text(json.dumps(integrity), encoding="utf-8")
    return path, fixture_root


@pytest.mark.parametrize("version", [0, 2, True, "1"])
def test_loader_rejects_unsupported_or_coerced_version(tmp_path: Path, version: object) -> None:
    path, fixture_root = _write_catalog(tmp_path, lambda payload: payload.update(schema_version=version))

    with pytest.raises(CatalogLoadError, match="schema validation failed"):
        load_scenario_catalog(path, fixture_root)


def test_loader_rejects_duplicate_ids(tmp_path: Path) -> None:
    def duplicate(payload: dict[str, object]) -> None:
        scenarios = payload["scenarios"]
        scenarios[1]["id"] = scenarios[0]["id"]

    path, fixture_root = _write_catalog(tmp_path, duplicate)

    with pytest.raises(CatalogLoadError, match="duplicate scenario ids"):
        load_scenario_catalog(path, fixture_root)


@pytest.mark.parametrize("fixture_id", ["../outside", "/absolute/path", "C:/outside", "missing"])
def test_loader_rejects_unsafe_or_missing_fixture(tmp_path: Path, fixture_id: str) -> None:
    def replace_fixture(payload: dict[str, object]) -> None:
        payload["scenarios"][0]["fixture_id"] = fixture_id

    path, fixture_root = _write_catalog(tmp_path, replace_fixture)

    with pytest.raises(CatalogLoadError):
        load_scenario_catalog(path, fixture_root)


def test_loader_rejects_unknown_schema_fields(tmp_path: Path) -> None:
    def add_unknown(payload: dict[str, object]) -> None:
        payload["scenarios"][0]["future_field"] = "silently unsafe"

    path, fixture_root = _write_catalog(tmp_path, add_unknown)

    with pytest.raises(CatalogLoadError, match="schema validation failed"):
        load_scenario_catalog(path, fixture_root)


def test_loader_rejects_integrity_mismatches(tmp_path: Path) -> None:
    fixture_root = tmp_path / "baseline"
    shutil.copytree(FIXTURES, fixture_root)
    target = fixture_root / "cases" / "python-debug-null-config" / "app.py"
    target.write_text("tampered", encoding="utf-8")

    with pytest.raises(CatalogLoadError, match="fixture checksum mismatch"):
        load_scenario_catalog(fixture_root / "catalog.v1.json", fixture_root)


def test_production_baseline_uses_real_stack_specific_fixture_layout() -> None:
    catalog = load_scenario_catalog(CATALOG, FIXTURES)
    for scenario in catalog.scenarios:
        fixture = FIXTURES / scenario.fixture_id
        files = tuple(path for path in fixture.rglob("*") if path.is_file())
        assert files
        assert all(path.name != "target.txt" for path in files)
        assert any(path.suffix in {".py", ".ts", ".tsx", ".json", ".yaml", ".yml"} for path in files)
        if scenario.mode.value == "hybrid" or "crossstack" in scenario.id or scenario.category.value == "refactor":
            assert len(files) >= 2
    assert any(validator.kind.value == "python_syntax" for scenario in catalog.scenarios for validator in scenario.validators)
    assert any(validator.kind.value == "json_equals" for scenario in catalog.scenarios for validator in scenario.validators)
