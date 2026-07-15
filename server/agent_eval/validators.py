"""Objective, shell-free validators for trusted evaluation oracles."""

from __future__ import annotations

import ast
import json
from pathlib import Path, PurePosixPath
from typing import Any

from .models import (
    CriterionObservation,
    CriterionState,
    FailureAttribution,
    ScenarioDefinition,
    ScenarioObservation,
    ValidatorDefinition,
    ValidatorKind,
)

MAX_VALIDATED_FILE_BYTES = 2 * 1024 * 1024


class WorkspaceValidationError(ValueError):
    """A validation workspace is unsafe or does not match the loaded scenario."""


def _safe_target(workspace: Path, relative_path: str) -> Path:
    root = workspace.resolve(strict=True)
    if not root.is_dir():
        raise WorkspaceValidationError("workspace must be a directory")
    target = root.joinpath(*PurePosixPath(relative_path).parts)
    try:
        resolved = target.resolve(strict=True)
        resolved.relative_to(root)
    except (OSError, ValueError) as exc:
        raise WorkspaceValidationError("validator target is missing or escapes workspace") from exc
    if not resolved.is_file() or resolved.stat().st_size > MAX_VALIDATED_FILE_BYTES:
        raise WorkspaceValidationError("validator target must be a bounded regular file")
    return resolved


def _json_pointer(document: Any, pointer: str) -> Any:
    current = document
    for raw_part in pointer.removeprefix("/").split("/"):
        part = raw_part.replace("~1", "/").replace("~0", "~")
        if isinstance(current, list):
            try:
                current = current[int(part)]
            except (ValueError, IndexError) as exc:
                raise KeyError(pointer) from exc
        elif isinstance(current, dict) and part in current:
            current = current[part]
        else:
            raise KeyError(pointer)
    return current


def _evaluate_validator(workspace: Path, validator: ValidatorDefinition) -> bool:
    try:
        target = _safe_target(workspace, validator.path)
        text = target.read_text(encoding="utf-8")
        if validator.kind is ValidatorKind.FILE_CONTAINS:
            return str(validator.expected) in text
        if validator.kind is ValidatorKind.FILE_NOT_CONTAINS:
            return str(validator.expected) not in text
        if validator.kind is ValidatorKind.PYTHON_SYNTAX:
            ast.parse(text, filename=validator.path)
            return True
        if validator.kind is ValidatorKind.JSON_EQUALS:
            document = json.loads(text)
            return _json_pointer(document, str(validator.json_pointer)) == validator.expected
    except (OSError, UnicodeError, SyntaxError, json.JSONDecodeError, KeyError, WorkspaceValidationError):
        return False
    raise WorkspaceValidationError(f"unsupported validator kind: {validator.kind}")


def validate_scenario_workspace(
    scenario: ScenarioDefinition,
    workspace: Path,
) -> ScenarioObservation:
    """Produce criterion evidence exclusively from hidden machine validators."""

    if not scenario.validators or not scenario.validator_checksum or not scenario.fixture_checksum:
        raise WorkspaceValidationError("scenario was not loaded with a complete oracle")
    results = tuple(
        CriterionObservation(
            criterion_id=validator.criterion_id,
            state=(
                CriterionState.PASSED
                if _evaluate_validator(workspace, validator)
                else CriterionState.FAILED
            ),
            summary=f"validator:{validator.kind.value}",
        )
        for validator in scenario.validators
    )
    attribution = (
        None
        if all(result.state is CriterionState.PASSED for result in results)
        else FailureAttribution.MODEL
    )
    return ScenarioObservation(
        scenario_id=scenario.id,
        criteria=results,
        failure_attribution=attribution,
    )
