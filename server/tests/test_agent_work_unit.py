from __future__ import annotations

from types import MappingProxyType

import pytest
from agent_session.work_unit import (
    WORK_UNIT_RESULT_SCHEMA_VERSION,
    WORK_UNIT_SCHEMA_VERSION,
    WorkUnit,
    WorkUnitArtifactRef,
    WorkUnitBudget,
    WorkUnitCancellation,
    WorkUnitDependency,
    WorkUnitEvidenceRef,
    WorkUnitFinding,
    WorkUnitResult,
    WorkUnitRetryPolicy,
    WorkUnitRunScope,
    can_transition_work_unit_status,
    parse_work_unit,
    parse_work_unit_result,
    serialize_work_unit,
)
from pydantic import ValidationError


def _work_unit_payload() -> dict[str, object]:
    return {
        "schema_version": WORK_UNIT_SCHEMA_VERSION,
        "work_unit_id": "wu_0123456789abcdef",
        "parent_session_id": "session-1",
        "plan_fingerprint": "a" * 64,
        "candidate_id": "inspect-code",
        "phase": "inspect",
        "owner": "explore_child",
        "title": "Inspect the runtime",
        "instruction": "Read the runtime boundaries and report evidence.",
        "dependencies": [],
        "file_scopes": [{"path": "server/agent_session", "mode": "read"}],
        "tool_projection": {
            "catalog_fingerprint": "b" * 64,
            "allowed_tools": ["workspace.read_file", "workspace.search"],
            "facts": {"runtime": {"kind": "agent_session"}},
        },
        "budget": {
            "max_attempts": 3,
            "max_model_calls": 12,
            "timeout_seconds": 600,
            "concurrency_class": "readonly_parallel",
        },
        "verification_requirements": [
            {
                "requirement_id": "inspect-evidence",
                "description": "Cite the inspected modules.",
                "command": None,
                "required": True,
            }
        ],
        "expected_artifacts": [
            {"kind": "analysis", "logical_ref": "work-unit/inspect-report"}
        ],
        "retry_policy": {"max_retries": 2, "retry_all_failures": True},
        "cancellation": {
            "cascade_on_parent_cancel": True,
            "cancel_on_stale_plan": True,
        },
    }


def _result_payload() -> dict[str, object]:
    return {
        "schema_version": WORK_UNIT_RESULT_SCHEMA_VERSION,
        "work_unit_id": "wu_0123456789abcdef",
        "attempt": 1,
        "verdict": "pass",
        "summary": "Inspection completed.",
        "findings": [
            {
                "finding_id": "finding-1",
                "severity": "low",
                "summary": "The runtime boundary is explicit.",
                "evidence_refs": [
                    {
                        "ref_type": "source",
                        "ref_id": "server/agent_session/runtime_contract.py:1",
                        "label": "Runtime contract",
                    }
                ],
            }
        ],
        "evidence_refs": [
            {
                "ref_type": "test",
                "ref_id": "test_agent_work_unit",
                "label": "Contract test",
            }
        ],
        "artifact_refs": [
            {"kind": "analysis", "logical_ref": "work-unit/inspect-report"}
        ],
        "recommended_next_phase": "implement",
        "diagnostic": {"provider": {"attempt": 1}},
    }


def test_work_unit_and_result_versions_are_strict() -> None:
    unit = parse_work_unit(_work_unit_payload())
    result = parse_work_unit_result(_result_payload())

    assert unit.schema_version == "agent.work_unit.v1"
    assert result.schema_version == "agent.work_unit.result.v1"
    with pytest.raises(ValidationError):
        WorkUnit.model_validate({**_work_unit_payload(), "schema_version": "v2"})
    with pytest.raises(ValidationError):
        WorkUnitResult.model_validate({**_result_payload(), "schema_version": "v2"})


def test_work_unit_rejects_unknown_and_hidden_reasoning_fields() -> None:
    with pytest.raises(ValidationError, match="extra"):
        WorkUnit.model_validate({**_work_unit_payload(), "unknown": True})

    payload = _work_unit_payload()
    payload["tool_projection"] = {
        "catalog_fingerprint": "b" * 64,
        "allowed_tools": ["workspace.read_file"],
        "facts": {"chain_of_thought": "must not persist"},
    }
    with pytest.raises(ValidationError, match="forbidden"):
        WorkUnit.model_validate(payload)

    result = _result_payload()
    result["diagnostic"] = {"scratchpad": {"reasoning": "hidden"}}
    with pytest.raises(ValidationError, match="forbidden"):
        WorkUnitResult.model_validate(result)


def test_nested_json_is_recursively_frozen_and_round_trips() -> None:
    unit = parse_work_unit(_work_unit_payload())

    assert isinstance(unit.tool_projection.facts, MappingProxyType)
    runtime = unit.tool_projection.facts["runtime"]
    assert isinstance(runtime, MappingProxyType)
    with pytest.raises(TypeError):
        unit.tool_projection.facts["extra"] = True  # type: ignore[index]
    with pytest.raises(TypeError):
        runtime["kind"] = "other"  # type: ignore[index]

    encoded = serialize_work_unit(unit)
    assert encoded["tool_projection"]["facts"] == {
        "runtime": {"kind": "agent_session"}
    }
    assert parse_work_unit(encoded) == unit


def test_result_redacts_nested_secrets_before_persistence() -> None:
    payload = _result_payload()
    payload["summary"] = "provider rejected Bearer top-secret"
    payload["diagnostic"] = {
        "api_key": "private",
        "url": "https://example.test/path?token=secret",
    }

    result = WorkUnitResult.model_validate(payload)
    dumped = result.model_dump(mode="json")

    assert "top-secret" not in dumped["summary"]
    assert dumped["diagnostic"]["api_key"] == "[REDACTED]"
    assert "secret" not in dumped["diagnostic"]["url"]


@pytest.mark.parametrize(
    "field,value",
    [
        ("file_scopes", [{"path": "C:/Users/user/project.py", "mode": "read"}]),
        ("file_scopes", [{"path": "/etc/passwd", "mode": "read"}]),
        ("file_scopes", [{"path": "../outside", "mode": "read"}]),
        (
            "expected_artifacts",
            [{"kind": "analysis", "logical_ref": "C:/temp/report.json"}],
        ),
    ],
)
def test_work_unit_rejects_host_absolute_or_escaping_references(
    field: str,
    value: object,
) -> None:
    payload = _work_unit_payload()
    payload[field] = value

    with pytest.raises(ValidationError, match="workspace-relative|logical"):
        WorkUnit.model_validate(payload)


def test_budget_and_attempts_are_bounded() -> None:
    with pytest.raises(ValidationError):
        WorkUnitBudget(
            max_attempts=7,
            max_model_calls=1,
            timeout_seconds=1,
            concurrency_class="parent_serial",
        )
    with pytest.raises(ValidationError):
        WorkUnitRetryPolicy(max_retries=6, retry_all_failures=True)
    with pytest.raises(ValidationError):
        WorkUnitRunScope(
            work_unit_id="wu_1",
            attempt=7,
            phase="implement",
            finalize_session=False,
        )


def test_parent_and_child_authority_invariants_are_enforced() -> None:
    child = _work_unit_payload()
    child["file_scopes"] = [{"path": "server", "mode": "write"}]
    with pytest.raises(ValidationError, match="read-only"):
        WorkUnit.model_validate(child)

    parent = _work_unit_payload()
    parent["phase"] = "implement"
    parent["owner"] = "parent_build"
    parent["budget"] = {
        "max_attempts": 3,
        "max_model_calls": 20,
        "timeout_seconds": 900,
        "concurrency_class": "readonly_parallel",
    }
    with pytest.raises(ValidationError, match="parent_serial"):
        WorkUnit.model_validate(parent)


def test_work_unit_run_scope_only_deliver_can_finalize_session() -> None:
    with pytest.raises(ValidationError, match="Deliver"):
        WorkUnitRunScope(
            work_unit_id="wu_1",
            attempt=1,
            phase="implement",
            finalize_session=True,
        )

    scope = WorkUnitRunScope(
        work_unit_id="wu_1",
        attempt=1,
        phase="deliver",
        finalize_session=True,
    )
    assert scope.finalize_session is True


@pytest.mark.parametrize(
    ("current", "target", "allowed"),
    [
        ("planned", "blocked", True),
        ("planned", "ready", True),
        ("blocked", "ready", True),
        ("ready", "running", True),
        ("running", "retrying", True),
        ("retrying", "running", True),
        ("running", "completed", True),
        ("running", "degraded", True),
        ("completed", "running", False),
        ("degraded", "ready", False),
        ("cancelled", "running", False),
        ("planned", "completed", False),
    ],
)
def test_work_unit_status_transitions_are_monotonic(
    current: str,
    target: str,
    allowed: bool,
) -> None:
    assert can_transition_work_unit_status(current, target) is allowed


def test_result_components_are_strict_and_safe() -> None:
    with pytest.raises(ValidationError):
        WorkUnitEvidenceRef(
            ref_type="source",
            ref_id="x",
            label="x",
            unknown=True,  # type: ignore[call-arg]
        )
    with pytest.raises(ValidationError, match="logical"):
        WorkUnitArtifactRef(kind="analysis", logical_ref="/tmp/report")
    with pytest.raises(ValidationError, match="evidence"):
        WorkUnitFinding(
            finding_id="finding",
            severity="high",
            summary="A high-severity finding must cite evidence.",
            evidence_refs=(),
        )


def test_contract_components_are_frozen() -> None:
    unit = WorkUnit.model_validate(_work_unit_payload())

    with pytest.raises(ValidationError):
        unit.title = "changed"
    with pytest.raises(ValidationError):
        unit.file_scopes[0].mode = "write"
    assert isinstance(unit.dependencies, tuple)
    assert isinstance(unit.expected_artifacts, tuple)


def test_dependency_and_cancellation_contracts_are_strict() -> None:
    dependency = WorkUnitDependency(
        work_unit_id="wu_parent",
        kind="depends_on",
    )
    cancellation = WorkUnitCancellation(
        cascade_on_parent_cancel=True,
        cancel_on_stale_plan=True,
    )

    assert dependency.kind == "depends_on"
    assert cancellation.cascade_on_parent_cancel is True
    with pytest.raises(ValidationError):
        WorkUnitDependency(work_unit_id="", kind="depends_on")
    with pytest.raises(ValidationError):
        WorkUnitCancellation(
            cascade_on_parent_cancel=False,
            cancel_on_stale_plan=True,
        )
