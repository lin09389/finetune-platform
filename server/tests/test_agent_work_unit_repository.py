from __future__ import annotations

import sqlite3
from concurrent.futures import ThreadPoolExecutor

import pytest
from agent_session.repository import (
    AgentSessionRepository,
    WorkUnitEventConflict,
    WorkUnitIdentityConflict,
    WorkUnitStateConflict,
)
from agent_session.work_unit import (
    WORK_UNIT_RESULT_SCHEMA_VERSION,
    WORK_UNIT_SCHEMA_VERSION,
    WorkUnit,
    WorkUnitResult,
)


def _repository(tmp_path) -> AgentSessionRepository:
    repository = AgentSessionRepository(str(tmp_path / "agents.db"))
    repository.create_session(
        {
            "id": "parent-1",
            "agent_id": "build",
            "status": "running",
            "title": "Parent Build",
            "project_path": str(tmp_path),
        }
    )
    return repository


def _work_unit(
    *,
    work_unit_id: str = "wu_repository0001",
    title: str = "Implement persistence",
    plan_fingerprint: str = "a" * 64,
) -> WorkUnit:
    return WorkUnit.model_validate(
        {
            "schema_version": WORK_UNIT_SCHEMA_VERSION,
            "work_unit_id": work_unit_id,
            "parent_session_id": "parent-1",
            "plan_fingerprint": plan_fingerprint,
            "candidate_id": "persist",
            "phase": "implement",
            "owner": "parent_build",
            "title": title,
            "instruction": "Persist this WorkUnit idempotently.",
            "dependencies": [],
            "file_scopes": [{"path": ".", "mode": "read_write"}],
            "tool_projection": {
                "catalog_fingerprint": "b" * 64,
                "allowed_tools": ["workspace.read_file", "workspace.write_file"],
                "facts": {"phase": "implement"},
            },
            "budget": {
                "max_attempts": 3,
                "max_model_calls": 24,
                "timeout_seconds": 900,
                "concurrency_class": "parent_serial",
            },
            "verification_requirements": [],
            "expected_artifacts": [
                {
                    "kind": "diff",
                    "logical_ref": "work-units/wu_repository0001/diff",
                }
            ],
            "retry_policy": {
                "max_retries": 2,
                "retry_all_failures": True,
            },
            "cancellation": {
                "cascade_on_parent_cancel": True,
                "cancel_on_stale_plan": True,
            },
        },
        strict=True,
    )


def _result(work_unit_id: str, attempt: int) -> WorkUnitResult:
    return WorkUnitResult.model_validate(
        {
            "schema_version": WORK_UNIT_RESULT_SCHEMA_VERSION,
            "work_unit_id": work_unit_id,
            "attempt": attempt,
            "verdict": "completed",
            "summary": "Persistence completed.",
            "findings": [],
            "evidence_refs": [],
            "artifact_refs": [
                {
                    "kind": "diff",
                    "logical_ref": f"work-units/{work_unit_id}/diff",
                }
            ],
            "recommended_next_phase": "verify",
            "diagnostic": {},
        },
        strict=True,
    )


def test_existing_legacy_subtask_table_is_migrated_compatibly(tmp_path) -> None:
    db_path = tmp_path / "legacy.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE agent_subtasks (
                id TEXT PRIMARY KEY,
                parent_session_id TEXT NOT NULL,
                child_session_id TEXT,
                agent_name TEXT NOT NULL,
                status TEXT NOT NULL,
                input_json TEXT NOT NULL DEFAULT '{}',
                result_json TEXT NOT NULL DEFAULT '{}',
                error TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                last_checked_at TEXT
            )
            """
        )
        conn.execute(
            """
            INSERT INTO agent_subtasks (
                id, parent_session_id, child_session_id, agent_name, status,
                input_json, result_json, error, created_at, updated_at,
                last_checked_at
            )
            VALUES (
                'agt_legacy', 'parent-old', NULL, 'explore', 'pending',
                '{}', '{}', NULL, '2026-01-01', '2026-01-01', NULL
            )
            """
        )

    repository = AgentSessionRepository(str(db_path))

    with sqlite3.connect(db_path) as conn:
        columns = {
            row[1] for row in conn.execute("PRAGMA table_info(agent_subtasks)")
        }
        indexes = {
            row[1] for row in conn.execute("PRAGMA index_list(agent_subtasks)")
        }
    assert {
        "record_kind",
        "plan_fingerprint",
        "work_unit_attempt",
    }.issubset(columns)
    assert "idx_agent_subtasks_work_unit_plan" in indexes
    assert repository.get_subtask("agt_legacy")["record_kind"] == (
        "legacy_async_subtask"
    )


def test_work_unit_create_is_idempotent_and_conflicts_on_changed_envelope(
    tmp_path,
) -> None:
    repository = _repository(tmp_path)
    unit = _work_unit()

    first = repository.create_work_unit_if_absent(unit)
    second = repository.create_work_unit_if_absent(unit)

    assert first == second
    assert first["record_kind"] == "typed_work_unit"
    assert first["work_unit_attempt"] == 0
    assert first["plan_fingerprint"] == unit.plan_fingerprint
    assert first["input_json"]["type"] == "typed_work_unit"
    assert first["input_json"]["work_unit"]["work_unit_id"] == unit.work_unit_id

    with pytest.raises(WorkUnitIdentityConflict):
        repository.create_work_unit_if_absent(
            _work_unit(title="Different immutable content")
        )


def test_concurrent_create_produces_one_identical_record(tmp_path) -> None:
    first_repository = _repository(tmp_path)
    second_repository = AgentSessionRepository(first_repository.db_path)
    unit = _work_unit()

    with ThreadPoolExecutor(max_workers=2) as executor:
        records = list(
            executor.map(
                lambda repository: repository.create_work_unit_if_absent(unit),
                (first_repository, second_repository),
            )
        )

    assert records[0] == records[1]
    assert len(
        first_repository.list_work_unit_records(
            "parent-1",
            plan_fingerprint=unit.plan_fingerprint,
        )
    ) == 1


def test_typed_work_units_are_isolated_from_legacy_subtask_queries(tmp_path) -> None:
    repository = _repository(tmp_path)
    legacy = repository.create_subtask(
        {
            "parent_session_id": "parent-1",
            "agent_name": "explore",
            "status": "pending",
            "input_json": {"task": "legacy"},
        }
    )
    unit = _work_unit()
    repository.create_work_unit_if_absent(unit)

    assert repository.get_subtask(unit.work_unit_id) is None
    assert [row["id"] for row in repository.list_subtasks("parent-1")] == [
        legacy["id"]
    ]
    assert [row["id"] for row in repository.list_all_subtasks()] == [legacy["id"]]
    assert repository.get_work_unit_record(unit.work_unit_id)["id"] == (
        unit.work_unit_id
    )
    with pytest.raises(WorkUnitStateConflict):
        repository.update_subtask(unit.work_unit_id, status="completed")


def test_attempt_increment_is_transactional_idempotent_and_bounded(tmp_path) -> None:
    repository = _repository(tmp_path)
    unit = _work_unit()
    repository.create_work_unit_if_absent(unit)

    first = repository.advance_work_unit_attempt(
        unit.work_unit_id,
        expected_attempt=0,
        event_id="wue_attempt_1",
    )
    repository.transition_work_unit(
        unit.work_unit_id,
        expected_attempt=1,
        target_status="ready",
        event_id="wue_ready_before_replay",
        event_type="work_unit_ready",
        payload={},
    )
    replay = repository.advance_work_unit_attempt(
        unit.work_unit_id,
        expected_attempt=0,
        event_id="wue_attempt_1",
    )
    assert first["work_unit_attempt"] == replay["work_unit_attempt"] == 1

    with pytest.raises(WorkUnitStateConflict):
        repository.advance_work_unit_attempt(
            unit.work_unit_id,
            expected_attempt=0,
            event_id="wue_wrong_expected",
        )

    repository.advance_work_unit_attempt(
        unit.work_unit_id,
        expected_attempt=1,
        event_id="wue_attempt_2",
    )
    repository.advance_work_unit_attempt(
        unit.work_unit_id,
        expected_attempt=2,
        event_id="wue_attempt_3",
    )
    with pytest.raises(WorkUnitStateConflict, match="budget"):
        repository.advance_work_unit_attempt(
            unit.work_unit_id,
            expected_attempt=3,
            event_id="wue_attempt_4",
        )


def test_concurrent_attempt_cas_allows_only_one_revision(tmp_path) -> None:
    first_repository = _repository(tmp_path)
    second_repository = AgentSessionRepository(first_repository.db_path)
    unit = _work_unit()
    first_repository.create_work_unit_if_absent(unit)

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(
                repository.advance_work_unit_attempt,
                unit.work_unit_id,
                expected_attempt=0,
                event_id=f"wue_concurrent_{index}",
            )
            for index, repository in enumerate(
                (first_repository, second_repository),
                start=1,
            )
        ]
        outcomes: list[dict[str, object]] = []
        failures: list[Exception] = []
        for future in futures:
            try:
                outcomes.append(future.result())
            except Exception as exc:
                failures.append(exc)

    assert len(outcomes) == 1
    assert outcomes[0]["work_unit_attempt"] == 1
    assert len(failures) == 1
    assert isinstance(failures[0], WorkUnitStateConflict)
    attempt_events = [
        event
        for event in first_repository.list_work_unit_events(unit.work_unit_id)
        if event["event_type"] == "work_unit_attempt_advanced"
    ]
    assert len(attempt_events) == 1


def test_only_one_child_revision_can_bind_per_attempt(tmp_path) -> None:
    repository = _repository(tmp_path)
    unit = _work_unit()
    repository.create_work_unit_if_absent(unit)
    repository.advance_work_unit_attempt(
        unit.work_unit_id,
        expected_attempt=0,
        event_id="wue_attempt_1",
    )

    bound = repository.bind_work_unit_child_once(
        unit.work_unit_id,
        attempt=1,
        child_session_id="child-1",
        event_id="wue_child_1",
    )
    replay = repository.bind_work_unit_child_once(
        unit.work_unit_id,
        attempt=1,
        child_session_id="child-1",
        event_id="wue_child_1",
    )
    assert bound["child_session_id"] == replay["child_session_id"] == "child-1"

    with pytest.raises(WorkUnitStateConflict):
        repository.bind_work_unit_child_once(
            unit.work_unit_id,
            attempt=1,
            child_session_id="child-other",
            event_id="wue_child_other",
        )

    advanced = repository.advance_work_unit_attempt(
        unit.work_unit_id,
        expected_attempt=1,
        event_id="wue_attempt_2",
    )
    assert advanced["child_session_id"] is None
    assert advanced["previous_child_session_ids"] == ["child-1"]


def test_event_ids_are_idempotent_and_conflicting_payloads_are_rejected(
    tmp_path,
) -> None:
    repository = _repository(tmp_path)
    unit = _work_unit()
    repository.create_work_unit_if_absent(unit)

    first = repository.add_work_unit_event_once(
        event_id="wue_same",
        work_unit_id=unit.work_unit_id,
        attempt=0,
        event_type="work_unit_ready",
        payload={"safe": True},
    )
    replay = repository.add_work_unit_event_once(
        event_id="wue_same",
        work_unit_id=unit.work_unit_id,
        attempt=0,
        event_type="work_unit_ready",
        payload={"safe": True},
    )
    assert first == replay

    with pytest.raises(WorkUnitEventConflict):
        repository.add_work_unit_event_once(
            event_id="wue_same",
            work_unit_id=unit.work_unit_id,
            attempt=0,
            event_type="work_unit_ready",
            payload={"safe": False},
        )


def test_transition_and_event_are_atomic_and_terminal_state_is_monotonic(
    tmp_path,
) -> None:
    repository = _repository(tmp_path)
    unit = _work_unit()
    repository.create_work_unit_if_absent(unit)
    repository.advance_work_unit_attempt(
        unit.work_unit_id,
        expected_attempt=0,
        event_id="wue_attempt_1",
    )
    repository.transition_work_unit(
        unit.work_unit_id,
        expected_attempt=1,
        target_status="ready",
        event_id="wue_ready",
        event_type="work_unit_ready",
        payload={},
    )
    repository.transition_work_unit(
        unit.work_unit_id,
        expected_attempt=1,
        target_status="running",
        event_id="wue_running",
        event_type="work_unit_started",
        payload={},
    )
    completed = repository.transition_work_unit(
        unit.work_unit_id,
        expected_attempt=1,
        target_status="completed",
        result=_result(unit.work_unit_id, 1),
        event_id="wue_completed",
        event_type="work_unit_completed",
        payload={"verdict": "completed"},
    )
    assert completed["status"] == "completed"
    assert completed["result_json"]["schema_version"] == (
        WORK_UNIT_RESULT_SCHEMA_VERSION
    )

    with pytest.raises(WorkUnitStateConflict):
        repository.transition_work_unit(
            unit.work_unit_id,
            expected_attempt=1,
            target_status="running",
            event_id="wue_late",
            event_type="work_unit_started",
            payload={},
        )
    assert repository.get_work_unit_record(unit.work_unit_id)["status"] == (
        "completed"
    )

    with pytest.raises(WorkUnitEventConflict):
        repository.transition_work_unit(
            unit.work_unit_id,
            expected_attempt=1,
            target_status="completed",
            result=_result(unit.work_unit_id, 1),
            event_id="wue_ready",
            event_type="work_unit_completed",
            payload={},
        )
    assert repository.get_work_unit_record(unit.work_unit_id)["status"] == (
        "completed"
    )


def test_stale_attempt_and_child_result_cannot_update_current_revision(
    tmp_path,
) -> None:
    repository = _repository(tmp_path)
    unit = _work_unit()
    repository.create_work_unit_if_absent(unit)
    repository.advance_work_unit_attempt(
        unit.work_unit_id,
        expected_attempt=0,
        event_id="wue_attempt_1",
    )
    repository.bind_work_unit_child_once(
        unit.work_unit_id,
        attempt=1,
        child_session_id="child-1",
        event_id="wue_child_1",
    )
    repository.advance_work_unit_attempt(
        unit.work_unit_id,
        expected_attempt=1,
        event_id="wue_attempt_2",
    )
    repository.bind_work_unit_child_once(
        unit.work_unit_id,
        attempt=2,
        child_session_id="child-2",
        event_id="wue_child_2",
    )

    with pytest.raises(WorkUnitStateConflict):
        repository.transition_work_unit(
            unit.work_unit_id,
            expected_attempt=1,
            expected_child_session_id="child-1",
            target_status="completed",
            result=_result(unit.work_unit_id, 1),
            event_id="wue_stale",
            event_type="work_unit_completed",
            payload={},
        )
    assert repository.get_work_unit_record(unit.work_unit_id)[
        "work_unit_attempt"
    ] == 2
    assert "wue_stale" not in {
        event["id"] for event in repository.list_work_unit_events(unit.work_unit_id)
    }


def test_cancelled_transition_is_terminal_without_fabricating_a_result(
    tmp_path,
) -> None:
    repository = _repository(tmp_path)
    unit = _work_unit()
    repository.create_work_unit_if_absent(unit)

    cancelled = repository.transition_work_unit(
        unit.work_unit_id,
        expected_attempt=0,
        target_status="cancelled",
        event_id="wue_cancelled",
        event_type="work_unit_cancelled",
        payload={"reason": "parent_cancelled"},
    )

    assert cancelled["status"] == "cancelled"
    assert cancelled["result_json"] == {}


def test_new_repository_instance_restores_work_unit_and_events(tmp_path) -> None:
    repository = _repository(tmp_path)
    unit = _work_unit()
    repository.create_work_unit_if_absent(unit)
    repository.advance_work_unit_attempt(
        unit.work_unit_id,
        expected_attempt=0,
        event_id="wue_attempt_1",
    )

    restored = AgentSessionRepository(repository.db_path)

    assert restored.get_work_unit_record(unit.work_unit_id)[
        "work_unit_attempt"
    ] == 1
    assert [event["id"] for event in restored.list_work_unit_events(unit.work_unit_id)] == [
        "wue_attempt_1"
    ]
