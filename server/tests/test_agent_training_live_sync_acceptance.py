"""CPU-only acceptance contract for Phase 6 live training reconciliation.

This is deliberately a fixture/fake harness owned by Track C.  Track A owns
the production SQLite repository and reconciler; its integration tests should
use these scenarios unchanged after the tracks are combined.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "agent_training_live_sync.json"
TERMINAL_STATUSES = {"completed", "failed", "missing"}
UNSAFE_KEYWORDS = ("path", "worker", "raw_event", "token", "secret", "prompt")


def _fixture() -> dict[str, Any]:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


@dataclass
class _Link:
    task_id: str
    owner_id: str
    session_id: str
    part_id: str
    cursor: int = 0
    status: str = "queued"
    sync_status: str = "healthy"


class _SqliteFakeReconciler:
    """A small deterministic fake for freezing Track A's external contract."""

    def __init__(self, db_path: Path):
        self.conn = sqlite3.connect(db_path)
        self.conn.execute(
            "CREATE TABLE links (task_id TEXT PRIMARY KEY, owner_id TEXT NOT NULL, session_id TEXT NOT NULL, part_id TEXT NOT NULL, cursor INTEGER NOT NULL, status TEXT NOT NULL, sync_status TEXT NOT NULL)"
        )
        self.conn.execute("CREATE TABLE parts (part_id TEXT PRIMARY KEY, task_id TEXT UNIQUE NOT NULL, status TEXT NOT NULL)")

    def close(self) -> None:
        self.conn.close()

    def create_link(self, scenario: dict[str, Any]) -> _Link:
        link = _Link(
            task_id=scenario["task_id"],
            owner_id=scenario["owner_id"],
            session_id=scenario["session_id"],
            part_id=scenario["part_id"],
            cursor=scenario.get("initial_cursor", 0),
        )
        self.conn.execute(
            "INSERT INTO links VALUES (?, ?, ?, ?, ?, ?, ?)",
            (link.task_id, link.owner_id, link.session_id, link.part_id, link.cursor, link.status, link.sync_status),
        )
        self.conn.execute("INSERT INTO parts VALUES (?, ?, ?)", (link.part_id, link.task_id, link.status))
        self.conn.commit()
        return link

    def replay(
        self, task_id: str, owner_id: str, events: list[dict[str, Any]], *, crash_after_part_sequence: int | None = None
    ) -> list[int]:
        row = self.conn.execute("SELECT owner_id, cursor, status FROM links WHERE task_id = ?", (task_id,)).fetchone()
        if row is None or row[0] != owner_id:
            raise PermissionError("Training task is not owned by this Agent session.")
        cursor = int(row[1])
        terminal = row[2] in TERMINAL_STATUSES
        applied: list[int] = []
        for event in sorted(events, key=lambda item: item["sequence"]):
            sequence = int(event["sequence"])
            if sequence <= cursor:
                continue
            cursor = sequence
            applied.append(sequence)
            if event.get("kind") == "unknown" or terminal:
                self.conn.execute("UPDATE links SET cursor = ? WHERE task_id = ?", (cursor, task_id))
                continue
            self.conn.execute("UPDATE parts SET status = ? WHERE task_id = ?", (event["status"], task_id))
            if crash_after_part_sequence == sequence:
                self.conn.commit()
                return applied
            self.conn.execute(
                "UPDATE links SET cursor = ?, status = ?, sync_status = 'healthy' WHERE task_id = ?",
                (cursor, event["status"], task_id),
            )
            terminal = event["status"] in TERMINAL_STATUSES
        self.conn.commit()
        return applied

    def link(self, task_id: str) -> _Link:
        row = self.conn.execute("SELECT task_id, owner_id, session_id, part_id, cursor, status, sync_status FROM links WHERE task_id = ?", (task_id,)).fetchone()
        assert row is not None
        return _Link(*row)

    def part_count(self, task_id: str) -> int:
        return int(self.conn.execute("SELECT COUNT(*) FROM parts WHERE task_id = ?", (task_id,)).fetchone()[0])

    def part_status(self, task_id: str) -> str:
        row = self.conn.execute("SELECT status FROM parts WHERE task_id = ?", (task_id,)).fetchone()
        assert row is not None
        return str(row[0])

    def rewrite_binding(self, task_id: str, *, owner_id: str, session_id: str, replacement_task_id: str) -> None:
        current = self.link(task_id)
        if (owner_id, session_id, replacement_task_id) != (current.owner_id, current.session_id, current.task_id):
            raise PermissionError("Agent training link bindings are immutable.")


class _ReconcilerServiceFake:
    """Models singleton, bounded work, and agent-only startup behavior."""

    def __init__(self, *, event_source_available: bool, batch_size: int = 2):
        self.event_source_available = event_source_available
        self.batch_size = batch_size
        self.started = False

    def start(self) -> bool:
        if not self.event_source_available or self.started:
            return False
        self.started = True
        return True

    def bounded_batch(self, links: list[str]) -> list[str]:
        return links[:self.batch_size]


def _scenario(fixture: dict[str, Any], scenario_id: str) -> dict[str, Any]:
    return next(item for item in fixture["scenarios"] if item["id"] == scenario_id)


def test_live_sync_fixture_freezes_all_required_recovery_scenarios():
    fixture = _fixture()
    assert fixture["contract_version"] == 1
    assert {item["id"] for item in fixture["scenarios"]} == {
        "ordered-progress", "duplicate-replay", "api-restart-cursor-recovery", "refresh-recovery",
        "worker-outage-recovery", "missing-job-grace", "cross-user-rejection", "terminal-completion",
        "safe-artifact-handoff", "unknown-event-cursor-advance", "terminal-old-event-cannot-regress",
        "crash-after-part-before-cursor", "agent-only-event-source-unavailable", "reconciler-singleton-bounded-batch",
        "build-session-exclusion", "hybrid-coding-coexistence", "terminal-isolation-and-refresh",
    }


def test_ordered_replay_is_monotonic_and_keeps_one_stable_card(tmp_path: Path):
    scenario = _scenario(_fixture(), "ordered-progress")
    reconciler = _SqliteFakeReconciler(tmp_path / "acceptance.db")
    try:
        link = reconciler.create_link(scenario)
        assert reconciler.replay(link.task_id, link.owner_id, scenario["events"]) == [10, 20, 25, 30]
        recovered = reconciler.link(link.task_id)
        assert recovered.part_id == scenario["part_id"]
        assert recovered.cursor == scenario["expected"]["cursor"]
        assert reconciler.part_count(link.task_id) == 1
        assert reconciler.part_status(link.task_id) == "running"
    finally:
        reconciler.close()


def test_duplicate_replay_and_restart_resume_the_existing_cursor_and_card(tmp_path: Path):
    fixture = _fixture()
    duplicate = _scenario(fixture, "duplicate-replay")
    restart = _scenario(fixture, "api-restart-cursor-recovery")
    reconciler = _SqliteFakeReconciler(tmp_path / "acceptance.db")
    try:
        duplicate_link = reconciler.create_link(duplicate)
        assert reconciler.replay(duplicate_link.task_id, duplicate_link.owner_id, duplicate["events"]) == [30]
        assert reconciler.link(duplicate_link.task_id).cursor == 30
        assert reconciler.part_count(duplicate_link.task_id) == 1

        restart_link = reconciler.create_link(restart)
        assert reconciler.replay(restart_link.task_id, restart_link.owner_id, restart["events"]) == [20, 30]
        assert reconciler.link(restart_link.task_id).part_id == restart["part_id"]
        assert reconciler.part_count(restart_link.task_id) == 1
    finally:
        reconciler.close()


def test_cross_user_rejection_never_creates_or_updates_a_card(tmp_path: Path):
    scenario = _scenario(_fixture(), "cross-user-rejection")
    reconciler = _SqliteFakeReconciler(tmp_path / "acceptance.db")
    try:
        link = reconciler.create_link(scenario)
        try:
            reconciler.replay(link.task_id, scenario["attempted_owner_id"], [{"sequence": 10, "status": "running"}])
        except PermissionError:
            pass
        else:  # pragma: no cover - assertion guard
            raise AssertionError("cross-user replay must be rejected")
        assert reconciler.link(link.task_id).cursor == 0
        assert reconciler.part_count(link.task_id) == 1
    finally:
        reconciler.close()


def test_owner_session_and_task_bindings_cannot_be_rewritten(tmp_path: Path):
    scenario = _scenario(_fixture(), "cross-user-rejection")
    reconciler = _SqliteFakeReconciler(tmp_path / "acceptance.db")
    try:
        link = reconciler.create_link(scenario)
        try:
            reconciler.rewrite_binding(
                link.task_id,
                owner_id=scenario["attempted_owner_id"],
                session_id=scenario["attempted_session_id"],
                replacement_task_id=scenario["attempted_task_id"],
            )
        except PermissionError:
            pass
        else:  # pragma: no cover - assertion guard
            raise AssertionError("owner/session/task binding rewrite must be rejected")
        assert reconciler.link(link.task_id) == link
    finally:
        reconciler.close()


def test_unknown_events_advance_the_cursor_without_changing_the_card(tmp_path: Path):
    scenario = _scenario(_fixture(), "unknown-event-cursor-advance")
    reconciler = _SqliteFakeReconciler(tmp_path / "acceptance.db")
    try:
        link = reconciler.create_link(scenario)
        assert reconciler.replay(link.task_id, link.owner_id, scenario["events"][:1]) == [10]
        assert reconciler.part_status(link.task_id) == "running"
        assert reconciler.replay(link.task_id, link.owner_id, scenario["events"][1:]) == [20]
        assert reconciler.link(link.task_id).cursor == 20
        assert reconciler.part_status(link.task_id) == "running"
    finally:
        reconciler.close()


def test_terminal_card_cannot_be_regressed_and_crash_replay_keeps_one_card(tmp_path: Path):
    fixture = _fixture()
    terminal = _scenario(fixture, "terminal-old-event-cannot-regress")
    crash = _scenario(fixture, "crash-after-part-before-cursor")
    reconciler = _SqliteFakeReconciler(tmp_path / "acceptance.db")
    try:
        terminal_link = reconciler.create_link(terminal)
        assert reconciler.replay(terminal_link.task_id, terminal_link.owner_id, terminal["events"]) == [5, 10]
        assert reconciler.link(terminal_link.task_id).status == "completed"
        assert reconciler.replay(terminal_link.task_id, terminal_link.owner_id, [{"sequence": 11, "status": "running"}]) == [11]
        assert reconciler.part_status(terminal_link.task_id) == "completed"

        crash_link = reconciler.create_link(crash)
        assert reconciler.replay(crash_link.task_id, crash_link.owner_id, crash["events"], crash_after_part_sequence=10) == [10]
        assert reconciler.link(crash_link.task_id).cursor == 0
        assert reconciler.replay(crash_link.task_id, crash_link.owner_id, crash["events"]) == [10]
        assert reconciler.link(crash_link.task_id).cursor == 10
        assert reconciler.part_count(crash_link.task_id) == 1
    finally:
        reconciler.close()


def test_service_is_singleton_bounded_and_agent_only_when_event_source_is_unavailable():
    unavailable = _ReconcilerServiceFake(event_source_available=False)
    assert unavailable.start() is False
    available = _ReconcilerServiceFake(event_source_available=True)
    assert available.start() is True
    assert available.start() is False
    assert available.bounded_batch(["one", "two", "three"]) == ["one", "two"]


def test_build_exclusion_and_hybrid_terminal_isolation_preserve_coding_timeline(tmp_path: Path):
    fixture = _fixture()
    build = _scenario(fixture, "build-session-exclusion")
    hybrid = _scenario(fixture, "hybrid-coding-coexistence")
    isolated = _scenario(fixture, "terminal-isolation-and-refresh")
    assert build["expected"] == {"training_link_count": 0, "training_card_count": 0}
    assert len(hybrid["session"]["coding_parts"]) == hybrid["expected"]["coding_part_count"]
    assert len(isolated["session"]["coding_parts"]) == isolated["expected"]["coding_part_count_after_refresh"]
    assert isolated["session"]["agent_status"] == isolated["expected"]["agent_status"]
    assert isolated["session"]["execution_plan_status"] == isolated["expected"]["execution_plan_status"]
    reconciler = _SqliteFakeReconciler(tmp_path / "acceptance.db")
    try:
        hybrid_link = reconciler.create_link(hybrid)
        assert reconciler.replay(hybrid_link.task_id, hybrid_link.owner_id, hybrid["events"]) == [10]
        isolated_link = reconciler.create_link(isolated)
        assert reconciler.replay(isolated_link.task_id, isolated_link.owner_id, isolated["events"]) == [10]
        assert reconciler.part_status(isolated_link.task_id) == "completed"
        assert reconciler.part_count(isolated_link.task_id) == 1
    finally:
        reconciler.close()


def test_terminal_missing_and_handoff_contracts_never_include_unsafe_values():
    fixture = _fixture()
    for scenario in fixture["scenarios"]:
        expected = scenario["expected"]
        projected = json.dumps({"events": scenario.get("events", []), "expected": expected}, ensure_ascii=False).lower()
        for forbidden in fixture["safe_handoff"]["forbidden_values"]:
            assert forbidden not in projected
        if expected.get("status") in TERMINAL_STATUSES and scenario["id"] != "safe-artifact-handoff":
            assert expected["part_count"] == 1
        for key in expected:
            assert not any(keyword in key.lower() for keyword in UNSAFE_KEYWORDS)
    assert _scenario(fixture, "safe-artifact-handoff")["expected"]["artifact_handoff"] == {
        "label": fixture["safe_handoff"]["label"], "target": fixture["safe_handoff"]["target"],
    }
