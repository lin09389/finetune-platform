"""Fail-closed catalog and fixture loading."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path, PurePosixPath

from pydantic import ValidationError

from .models import OracleCatalog, ScenarioCatalog

MAX_CATALOG_BYTES = 2 * 1024 * 1024
ORACLE_FILENAME = "oracles.v1.json"
INTEGRITY_FILENAME = "integrity.v1.json"
REPARSE_POINT_ATTRIBUTE = 0x400
RESOURCE_ROOT = Path(__file__).resolve().parent / "resources" / "v1"


class CatalogLoadError(ValueError):
    """Raised when a catalog or one of its fixture references is unsafe."""


def default_fixture_root() -> Path:
    """Return the publishable, package-owned v1 fixture root for API wiring."""

    return RESOURCE_ROOT


def default_catalog_path() -> Path:
    """Return the versioned catalog paired with :func:`default_fixture_root`."""

    return RESOURCE_ROOT / "catalog.v1.json"


def load_default_scenario_catalog() -> ScenarioCatalog:
    """Load the production v1 baseline without ever consulting test fixtures."""

    return load_scenario_catalog(default_catalog_path(), default_fixture_root())


def resolve_fixture_directory(fixture_root: Path, fixture_id: str) -> Path:
    """Resolve a portable fixture id while rejecting traversal and escapes."""

    root = fixture_root.resolve(strict=True)
    if not root.is_dir():
        raise CatalogLoadError("fixture root must be a directory")
    pure_path = PurePosixPath(fixture_id)
    if pure_path.is_absolute() or any(part in {"", ".", ".."} for part in pure_path.parts):
        raise CatalogLoadError(f"unsafe fixture_id: {fixture_id!r}")
    candidate = root.joinpath(*pure_path.parts)
    try:
        resolved = candidate.resolve(strict=True)
    except OSError as exc:
        raise CatalogLoadError(f"fixture does not exist: {fixture_id!r}") from exc
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise CatalogLoadError(f"fixture escapes fixture root: {fixture_id!r}") from exc
    if not resolved.is_dir():
        raise CatalogLoadError(f"fixture must be a directory: {fixture_id!r}")
    _reject_links_and_reparse_points(resolved)
    return resolved


def _reject_links_and_reparse_points(root: Path) -> None:
    for current_root, directories, files in os.walk(root, followlinks=False):
        for name in (*directories, *files):
            path = Path(current_root, name)
            try:
                metadata = path.lstat()
            except OSError as exc:
                raise CatalogLoadError("fixture contains an unreadable entry") from exc
            attributes = int(getattr(metadata, "st_file_attributes", 0))
            if path.is_symlink() or attributes & REPARSE_POINT_ATTRIBUTE:
                raise CatalogLoadError("fixture cannot contain symlinks, junctions, or reparse points")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(64 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def _sha256_directory(root: Path) -> str:
    digest = hashlib.sha256()
    files = sorted((path for path in root.rglob("*") if path.is_file()), key=lambda path: path.as_posix())
    if not files:
        raise CatalogLoadError("fixture directory cannot be empty")
    for path in files:
        relative = path.relative_to(root).as_posix().encode("utf-8")
        digest.update(len(relative).to_bytes(4, "big"))
        digest.update(relative)
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(64 * 1024), b""):
                digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def _load_oracles(fixture_root: Path) -> OracleCatalog:
    path = fixture_root.resolve(strict=True) / ORACLE_FILENAME
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return OracleCatalog.model_validate(payload)
    except (OSError, UnicodeError, json.JSONDecodeError, ValidationError) as exc:
        raise CatalogLoadError("oracle catalog is missing or invalid") from exc


def _load_integrity_manifest(fixture_root: Path) -> dict[str, object]:
    path = fixture_root.resolve(strict=True) / INTEGRITY_FILENAME
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise CatalogLoadError("integrity manifest is missing or invalid") from exc
    if not isinstance(payload, dict) or set(payload) != {"catalog_checksum", "scenarios"}:
        raise CatalogLoadError("integrity manifest has an invalid shape")
    if not isinstance(payload["catalog_checksum"], str):
        raise CatalogLoadError("integrity manifest has no catalog checksum")
    if not isinstance(payload["scenarios"], dict):
        raise CatalogLoadError("integrity manifest has no scenario checksums")
    return payload


def _require_checksum(value: object, description: str) -> str:
    if not isinstance(value, str) or not value.startswith("sha256:") or len(value) != 71:
        raise CatalogLoadError(f"integrity manifest has invalid {description}")
    if any(character not in "0123456789abcdef" for character in value.removeprefix("sha256:")):
        raise CatalogLoadError(f"integrity manifest has invalid {description}")
    return value


def _validator_checksum(validators: tuple[object, ...]) -> str:
    payload = [validator.model_dump(mode="json") for validator in validators]
    serialized = json.dumps(payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True)
    return f"sha256:{hashlib.sha256(serialized.encode('utf-8')).hexdigest()}"


def load_scenario_catalog(catalog_path: Path, fixture_root: Path) -> ScenarioCatalog:
    """Load schema v1 and verify every fixture before returning any scenarios."""

    path = catalog_path.resolve(strict=True)
    if path.suffix.lower() != ".json" or not path.is_file():
        raise CatalogLoadError("catalog must be an existing JSON file")
    if path.stat().st_size > MAX_CATALOG_BYTES:
        raise CatalogLoadError("catalog exceeds the maximum supported size")
    try:
        raw_catalog = path.read_bytes()
        payload = json.loads(raw_catalog.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise CatalogLoadError("catalog is not valid UTF-8 JSON") from exc
    try:
        catalog = ScenarioCatalog.model_validate(payload)
    except ValidationError as exc:
        raise CatalogLoadError(f"catalog schema validation failed: {exc}") from exc
    integrity = _load_integrity_manifest(fixture_root)
    catalog_checksum = f"sha256:{hashlib.sha256(raw_catalog).hexdigest()}"
    if _require_checksum(integrity["catalog_checksum"], "catalog checksum") != catalog_checksum:
        raise CatalogLoadError("catalog checksum mismatch")
    oracle_catalog = _load_oracles(fixture_root)
    oracles = {oracle.scenario_id: oracle for oracle in oracle_catalog.scenarios}
    scenario_ids = {scenario.id for scenario in catalog.scenarios}
    if set(oracles) != scenario_ids:
        missing = sorted(scenario_ids - set(oracles))
        unknown = sorted(set(oracles) - scenario_ids)
        raise CatalogLoadError(f"oracle coverage mismatch; missing={missing}, unknown={unknown}")

    manifest_scenarios = integrity["scenarios"]
    if set(manifest_scenarios) != scenario_ids:
        raise CatalogLoadError("integrity scenario coverage mismatch")
    loaded_scenarios = []
    for scenario in catalog.scenarios:
        fixture = resolve_fixture_directory(fixture_root, scenario.fixture_id)
        oracle = oracles[scenario.id]
        criterion_ids = {criterion.id for criterion in scenario.criteria}
        validator_ids = {validator.criterion_id for validator in oracle.validators}
        if criterion_ids != validator_ids:
            raise CatalogLoadError(f"validator coverage mismatch for scenario {scenario.id!r}")
        for validator in oracle.validators:
            target = fixture.joinpath(*PurePosixPath(validator.path).parts)
            try:
                resolved_target = target.resolve(strict=True)
                resolved_target.relative_to(fixture)
            except (OSError, ValueError) as exc:
                raise CatalogLoadError(
                    f"validator target is missing or unsafe for scenario {scenario.id!r}"
                ) from exc
            if not resolved_target.is_file():
                raise CatalogLoadError(f"validator target must be a file for scenario {scenario.id!r}")
        actual_fixture_checksum = _sha256_directory(fixture)
        actual_validator_checksum = _validator_checksum(oracle.validators)
        manifest_entry = manifest_scenarios[scenario.id]
        if not isinstance(manifest_entry, dict) or set(manifest_entry) != {
            "fixture_checksum",
            "validator_checksum",
        }:
            raise CatalogLoadError(f"integrity manifest has invalid scenario entry for {scenario.id!r}")
        if _require_checksum(manifest_entry["fixture_checksum"], "fixture checksum") != actual_fixture_checksum:
            raise CatalogLoadError(f"fixture checksum mismatch for scenario {scenario.id!r}")
        if _require_checksum(manifest_entry["validator_checksum"], "validator checksum") != actual_validator_checksum:
            raise CatalogLoadError(f"validator checksum mismatch for scenario {scenario.id!r}")
        loaded_scenarios.append(
            scenario.model_copy(
                update={
                    "validators": oracle.validators,
                    "fixture_checksum": actual_fixture_checksum,
                    "validator_checksum": actual_validator_checksum,
                }
            )
        )
    return catalog.model_copy(
        update={
            "scenarios": tuple(loaded_scenarios),
            "catalog_checksum": catalog_checksum,
        }
    )
