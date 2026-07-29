from __future__ import annotations

from types import MappingProxyType

import pytest
from agent_session.goal_plan import GOAL_PLAN_SCHEMA_VERSION
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
    WorkUnitToolProjection,
    build_parent_only_fallback,
    can_transition_work_unit_status,
    compile_work_units,
    fingerprint_goal_plan,
    normalize_work_unit_phase,
    parse_work_unit,
    parse_work_unit_result,
    serialize_work_unit,
    validate_work_unit_graph,
)
from pydantic import ValidationError
from tool_platform.models import CanonicalToolMeta
from tool_platform.taxonomy import (
    ExecutionLocation,
    SideEffect,
    ToolKind,
    ToolRisk,
)


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


def _goal_plan_payload() -> dict[str, object]:
    return {
        "schema_version": GOAL_PLAN_SCHEMA_VERSION,
        "goal": "Harden typed orchestration",
        "constraints": ["Keep child agents read-only"],
        "phases": [
            {
                "id": "inspect",
                "title": "Inspect",
                "summary": "Inspect the current boundary",
                "order": 0,
            },
            {
                "id": "plan",
                "title": "Plan",
                "summary": "Plan the bounded implementation",
                "order": 1,
            },
            {
                "id": "implement",
                "title": "Implement",
                "summary": "Implement the bounded change",
                "order": 2,
            },
            {
                "id": "verify",
                "title": "Verify",
                "summary": "Verify the bounded change",
                "order": 3,
            },
            {
                "id": "review",
                "title": "Review",
                "summary": "Review the resulting diff",
                "order": 4,
            },
            {
                "id": "deliver",
                "title": "Deliver",
                "summary": "Deliver the verified result",
                "order": 5,
            },
        ],
        "work_unit_candidates": [
            {
                "id": "inspect-runtime",
                "phase_id": "inspect",
                "title": "Inspect runtime",
                "summary": "Read the runtime contracts and cite evidence.",
            },
            {
                "id": "plan-runtime",
                "phase_id": "plan",
                "title": "Plan runtime",
                "summary": "Plan the smallest safe implementation.",
            },
            {
                "id": "implement-runtime",
                "phase_id": "implement",
                "title": "Implement runtime",
                "summary": "Implement the approved bounded change.",
            },
            {
                "id": "verify-runtime",
                "phase_id": "verify",
                "title": "Verify runtime",
                "summary": "Run the required verification.",
            },
            {
                "id": "review-runtime",
                "phase_id": "review",
                "title": "Review runtime",
                "summary": "Review the diff and verification evidence.",
            },
            {
                "id": "deliver-runtime",
                "phase_id": "deliver",
                "title": "Deliver runtime",
                "summary": "Summarize the completed result and evidence.",
            },
        ],
        "dependencies": [
            {
                "from": "inspect-runtime",
                "to": "plan-runtime",
                "kind": "depends_on",
            },
            {
                "from": "plan-runtime",
                "to": "implement-runtime",
                "kind": "depends_on",
            },
            {
                "from": "implement-runtime",
                "to": "verify-runtime",
                "kind": "depends_on",
            },
            {
                "from": "verify-runtime",
                "to": "review-runtime",
                "kind": "depends_on",
            },
            {
                "from": "review-runtime",
                "to": "deliver-runtime",
                "kind": "depends_on",
            },
        ],
        "file_scopes": [
            {"path": "server/agent_session", "mode": "read_write"},
        ],
        "verification_requirements": [
            {
                "id": "tests",
                "description": "Run the focused WorkUnit tests.",
                "command": "pytest server/tests/test_agent_work_unit.py -q",
                "required": True,
            }
        ],
        "risk_summaries": [
            {
                "id": "scope",
                "summary": "The compiler must not widen workspace authority.",
                "severity": "high",
            }
        ],
        "retry_policy": {
            "max_replan_attempts": 1,
            "max_phase_retries": 2,
        },
    }


def _phase_tool_projections() -> dict[str, WorkUnitToolProjection]:
    return {
        phase: WorkUnitToolProjection(
            catalog_fingerprint=(index + 1).to_bytes(32, "big").hex(),
            allowed_tools=(
                ("workspace.read_file", "workspace.search")
                if phase in {"inspect", "plan", "review"}
                else ("workspace.read_file", "workspace.write_file")
            ),
            facts={"phase": phase},
        )
        for index, phase in enumerate(
            ("inspect", "plan", "implement", "verify", "review", "deliver")
        )
    }


def _tool_metadata_by_name() -> dict[str, CanonicalToolMeta]:
    def meta(
        canonical_name: str,
        kind: ToolKind,
        side_effects: frozenset[SideEffect],
        risk: ToolRisk,
        execution_location: ExecutionLocation,
    ) -> CanonicalToolMeta:
        return CanonicalToolMeta(
            canonical_name=canonical_name,
            kind=kind,
            side_effects=side_effects,
            risk=risk,
            execution_location=execution_location,
            display_name=canonical_name,
            description=f"Canonical metadata for {canonical_name}",
        )

    return {
        "workspace.read_file": meta(
            "workspace.read_file",
            ToolKind.READ,
            frozenset({SideEffect.NONE}),
            ToolRisk.LOW,
            ExecutionLocation.CONTROL_PLANE,
        ),
        "workspace.search": meta(
            "workspace.search",
            ToolKind.SEARCH,
            frozenset({SideEffect.NONE}),
            ToolRisk.LOW,
            ExecutionLocation.CONTROL_PLANE,
        ),
        "workspace.write_file": meta(
            "workspace.write_file",
            ToolKind.WRITE,
            frozenset({SideEffect.WORKSPACE_WRITE}),
            ToolRisk.MEDIUM,
            ExecutionLocation.WORKER,
        ),
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


def test_tool_projection_facts_are_redacted_before_persistence() -> None:
    projection = WorkUnitToolProjection(
        catalog_fingerprint="c" * 64,
        allowed_tools=("workspace.read_file",),
        facts={
            "authorization": "Bearer secret-value",
            "url": "https://example.test/path?api_key=private",
        },
    )

    dumped = projection.model_dump(mode="json")
    assert dumped["facts"]["authorization"] == "[REDACTED]"
    assert "private" not in dumped["facts"]["url"]


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


def test_goal_plan_fingerprint_is_canonical_and_stable() -> None:
    payload = _goal_plan_payload()
    reordered = dict(reversed(list(payload.items())))
    reordered["constraints"] = list(reversed(payload["constraints"]))
    reordered["phases"] = list(reversed(payload["phases"]))
    reordered["work_unit_candidates"] = list(
        reversed(payload["work_unit_candidates"])
    )
    reordered["dependencies"] = list(reversed(payload["dependencies"]))

    first = fingerprint_goal_plan(payload)
    second = fingerprint_goal_plan(reordered)

    assert first == second
    assert len(first) == 64


@pytest.mark.parametrize(
    ("phase_id", "title", "expected"),
    [
        ("inspect", "Anything", ("inspect", "explore_child")),
        ("custom-id", " Plan ", ("plan", "explore_child")),
        ("review", "Review", ("review", "review_child")),
        ("custom", "Security audit", ("implement", "parent_build")),
    ],
)
def test_phase_normalization_uses_fixed_platform_ownership(
    phase_id: str,
    title: str,
    expected: tuple[str, str],
) -> None:
    assert normalize_work_unit_phase(phase_id, title) == expected


def test_conflicting_phase_id_and_title_are_parent_owned() -> None:
    assert normalize_work_unit_phase("inspect", "Review") == (
        "implement",
        "parent_build",
    )


def test_goal_plan_compiles_to_stable_scoped_work_units_without_model_calls() -> None:
    payload = _goal_plan_payload()
    kwargs = {
        "parent_session_id": "session-1",
        "parent_file_scopes": (
            {"path": "server", "mode": "read_write"},
        ),
        "phase_tool_projections": _phase_tool_projections(),
        "tool_metadata_by_name": _tool_metadata_by_name(),
    }

    first = compile_work_units(payload, **kwargs)
    second = compile_work_units(payload, **kwargs)

    assert first.mode == "compiled"
    assert first == second
    assert len(first.work_units) == 6
    assert [unit.owner for unit in first.work_units] == [
        "explore_child",
        "explore_child",
        "parent_build",
        "parent_build",
        "review_child",
        "parent_build",
    ]
    assert all(
        scope.mode == "read"
        for unit in first.work_units
        if unit.owner != "parent_build"
        for scope in unit.file_scopes
    )
    assert first.work_units[2].file_scopes[0].mode == "read_write"
    for predecessor, successor in zip(
        first.work_units[:-1],
        first.work_units[1:],
        strict=True,
    ):
        assert successor.dependencies[0].work_unit_id == predecessor.work_unit_id
    assert first.work_units[0].budget.max_attempts == 3
    assert first.work_units[0].retry_policy.max_retries == 2


def test_phase_level_dependencies_expand_to_candidate_dependencies() -> None:
    payload = _goal_plan_payload()
    payload["dependencies"] = [
        {"from": "inspect", "to": "implement", "kind": "depends_on"},
        {"from": "implement", "to": "review", "kind": "blocks"},
    ]

    result = compile_work_units(
        payload,
        parent_session_id="session-1",
        parent_file_scopes=({"path": "server", "mode": "read_write"},),
        phase_tool_projections=_phase_tool_projections(),
        tool_metadata_by_name=_tool_metadata_by_name(),
    )

    assert result.mode == "compiled"
    by_candidate = {unit.candidate_id: unit for unit in result.work_units}
    inspect = by_candidate["inspect-runtime"]
    plan = by_candidate["plan-runtime"]
    implement = by_candidate["implement-runtime"]
    verify = by_candidate["verify-runtime"]
    review = by_candidate["review-runtime"]
    assert set(implement.dependencies) == {
        WorkUnitDependency(
            work_unit_id=inspect.work_unit_id,
            kind="depends_on",
        ),
        WorkUnitDependency(
            work_unit_id=plan.work_unit_id,
            kind="depends_on",
        ),
    }
    assert set(review.dependencies) == {
        WorkUnitDependency(
            work_unit_id=implement.work_unit_id,
            kind="blocks",
        ),
        WorkUnitDependency(
            work_unit_id=verify.work_unit_id,
            kind="depends_on",
        ),
    }


def test_unknown_phase_stays_parent_owned() -> None:
    payload = _goal_plan_payload()
    payload["phases"] = [
        *payload["phases"],
        {
            "id": "custom",
            "title": "Security audit",
            "summary": "Run a custom audit",
            "order": 6,
        },
    ]
    payload["work_unit_candidates"] = [
        *payload["work_unit_candidates"],
        {
            "id": "custom-unit",
            "phase_id": "custom",
            "title": "Custom audit",
            "summary": "Perform the custom phase without delegation.",
        },
    ]

    result = compile_work_units(
        payload,
        parent_session_id="session-1",
        parent_file_scopes=({"path": "server", "mode": "read_write"},),
        phase_tool_projections=_phase_tool_projections(),
        tool_metadata_by_name=_tool_metadata_by_name(),
    )

    assert result.mode == "compiled"
    custom = next(
        unit for unit in result.work_units if unit.candidate_id == "custom-unit"
    )
    assert custom.phase == "implement"
    assert custom.owner == "parent_build"


def test_ambiguous_phase_is_parent_owned_and_recorded() -> None:
    payload = _goal_plan_payload()
    phases = payload["phases"]
    assert isinstance(phases, list)
    phases[0] = {
        "id": "inspect",
        "title": "Review",
        "summary": "Conflicting phase labels",
        "order": 0,
    }
    payload["dependencies"] = [
        dependency
        for dependency in payload["dependencies"]
        if dependency["from"] != "inspect-runtime"
    ]

    result = compile_work_units(
        payload,
        parent_session_id="session-1",
        parent_file_scopes=({"path": "server", "mode": "read_write"},),
        phase_tool_projections=_phase_tool_projections(),
        tool_metadata_by_name=_tool_metadata_by_name(),
    )

    assert result.mode == "compiled"
    ambiguous = next(
        unit for unit in result.work_units if unit.candidate_id == "inspect-runtime"
    )
    assert ambiguous.phase == "implement"
    assert ambiguous.owner == "parent_build"
    assert result.diagnostics["ambiguous_phase_ids"] == ("inspect",)


def test_goal_plan_scope_can_narrow_but_cannot_expand_parent_scope() -> None:
    payload = _goal_plan_payload()
    workspace_root = compile_work_units(
        payload,
        parent_session_id="session-1",
        parent_file_scopes=({"path": ".", "mode": "read_write"},),
        phase_tool_projections=_phase_tool_projections(),
        tool_metadata_by_name=_tool_metadata_by_name(),
    )
    narrowed = compile_work_units(
        payload,
        parent_session_id="session-1",
        parent_file_scopes=(
            {"path": "server/agent_session", "mode": "read_write"},
        ),
        phase_tool_projections=_phase_tool_projections(),
        tool_metadata_by_name=_tool_metadata_by_name(),
    )
    expanded = compile_work_units(
        payload,
        parent_session_id="session-1",
        parent_file_scopes=(
            {"path": "server/agent_session/services", "mode": "read_write"},
        ),
        phase_tool_projections=_phase_tool_projections(),
        tool_metadata_by_name=_tool_metadata_by_name(),
    )

    assert workspace_root.mode == narrowed.mode == "compiled"
    assert expanded.mode == "parent_only"
    assert expanded.diagnostics["reason_code"] == "file_scope_expands_parent"


def test_compiler_fails_closed_when_a_phase_projection_is_missing() -> None:
    projections = _phase_tool_projections()
    projections.pop("review")

    result = compile_work_units(
        _goal_plan_payload(),
        parent_session_id="session-1",
        parent_file_scopes=({"path": "server", "mode": "read_write"},),
        phase_tool_projections=projections,
        tool_metadata_by_name=_tool_metadata_by_name(),
    )

    assert result.mode == "parent_only"
    assert result.diagnostics["reason_code"] == "tool_projection_missing"


def test_incomplete_canonical_lifecycle_falls_back_to_parent() -> None:
    payload = _goal_plan_payload()
    payload["work_unit_candidates"] = [
        candidate
        for candidate in payload["work_unit_candidates"]
        if candidate["phase_id"] != "deliver"
    ]
    payload["dependencies"] = [
        dependency
        for dependency in payload["dependencies"]
        if dependency["to"] != "deliver-runtime"
    ]

    result = compile_work_units(
        payload,
        parent_session_id="session-1",
        parent_file_scopes=({"path": "server", "mode": "read_write"},),
        phase_tool_projections=_phase_tool_projections(),
        tool_metadata_by_name=_tool_metadata_by_name(),
    )

    assert result.mode == "parent_only"
    assert result.diagnostics["reason_code"] == "canonical_lifecycle_incomplete"


def test_child_projection_with_side_effects_fails_closed() -> None:
    projections = _phase_tool_projections()
    projections["review"] = WorkUnitToolProjection(
        catalog_fingerprint="f" * 64,
        allowed_tools=("workspace.read_file", "workspace.write_file"),
        facts={"phase": "review"},
    )

    result = compile_work_units(
        _goal_plan_payload(),
        parent_session_id="session-1",
        parent_file_scopes=({"path": "server", "mode": "read_write"},),
        phase_tool_projections=projections,
        tool_metadata_by_name=_tool_metadata_by_name(),
    )

    assert result.mode == "parent_only"
    assert result.diagnostics["reason_code"] == "child_authority_unproven"


def test_invalid_missing_and_empty_goal_plans_fall_back_to_parent() -> None:
    common = {
        "parent_session_id": "session-1",
        "parent_file_scopes": ({"path": "server", "mode": "read_write"},),
        "phase_tool_projections": _phase_tool_projections(),
        "tool_metadata_by_name": _tool_metadata_by_name(),
    }
    empty = _goal_plan_payload()
    empty["work_unit_candidates"] = []
    empty["dependencies"] = []

    missing = compile_work_units(None, **common)
    invalid = compile_work_units({"schema_version": GOAL_PLAN_SCHEMA_VERSION}, **common)
    no_units = compile_work_units(empty, **common)

    assert missing.mode == invalid.mode == no_units.mode == "parent_only"
    assert missing.diagnostics["reason_code"] == "goal_plan_missing"
    assert invalid.diagnostics["reason_code"] == "goal_plan_invalid"
    assert no_units.diagnostics["reason_code"] == "goal_plan_empty"
    assert build_parent_only_fallback(
        reason_code="test",
        summary="fallback",
    ).work_units == ()


def test_compiler_rejects_more_than_twelve_units() -> None:
    payload = _goal_plan_payload()
    payload["work_unit_candidates"] = [
        {
            "id": f"unit-{index}",
            "phase_id": "implement",
            "title": f"Unit {index}",
            "summary": "Bounded implementation",
        }
        for index in range(13)
    ]
    payload["dependencies"] = []

    result = compile_work_units(
        payload,
        parent_session_id="session-1",
        parent_file_scopes=({"path": "server", "mode": "read_write"},),
        phase_tool_projections=_phase_tool_projections(),
        tool_metadata_by_name=_tool_metadata_by_name(),
    )

    assert result.mode == "parent_only"
    assert result.diagnostics["reason_code"] == "goal_plan_invalid"


def test_work_unit_graph_rejects_cycles_and_conflicting_stable_ids() -> None:
    first = parse_work_unit(_work_unit_payload())
    second_payload = _work_unit_payload()
    second_payload["candidate_id"] = "different-candidate"
    second_payload["title"] = "Different content"
    second = parse_work_unit(second_payload)
    with pytest.raises(ValueError, match="different content"):
        validate_work_unit_graph((first, second))

    left_payload = _work_unit_payload()
    left_payload["work_unit_id"] = "wu_left0000"
    left_payload["owner"] = "parent_build"
    left_payload["phase"] = "implement"
    left_payload["budget"] = {
        "max_attempts": 3,
        "max_model_calls": 20,
        "timeout_seconds": 900,
        "concurrency_class": "parent_serial",
    }
    left_payload["dependencies"] = [
        {"work_unit_id": "wu_right000", "kind": "depends_on"}
    ]
    right_payload = {**left_payload}
    right_payload["work_unit_id"] = "wu_right000"
    right_payload["candidate_id"] = "right"
    right_payload["dependencies"] = [
        {"work_unit_id": "wu_left0000", "kind": "depends_on"}
    ]

    with pytest.raises(ValueError, match="cycle"):
        validate_work_unit_graph(
            (parse_work_unit(left_payload), parse_work_unit(right_payload))
        )
