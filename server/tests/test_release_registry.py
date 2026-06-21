from __future__ import annotations

from datetime import datetime, timedelta

from core.db_manager import close_all_pools
from core.release_registry import (
    ConcurrentReleaseUpdate,
    ReleaseRegistry,
    get_release_registry,
    reset_release_registry_for_tests,
)


def test_registry_enforces_versions_and_lease_ownership(tmp_path):
    db_path = tmp_path / "registry.db"
    registry = ReleaseRegistry(str(db_path))
    registry.ensure_schema()

    payload = {
        "run_id": "eval_1",
        "status": "pending",
        "created_at": datetime.now().isoformat(),
    }
    assert registry.upsert("evaluation", "eval_1", payload, expected_version=0) == 1
    stored, version = registry.get("evaluation", "eval_1")
    assert stored["status"] == "pending"
    assert version == 1

    payload["status"] = "running"
    assert registry.upsert("evaluation", "eval_1", payload, expected_version=1) == 2
    try:
        registry.upsert("evaluation", "eval_1", payload, expected_version=1)
    except ConcurrentReleaseUpdate:
        pass
    else:
        raise AssertionError("stale update must be rejected")

    assert registry.claim("eval_1:run", "evaluation", "worker-a", ttl_seconds=60)
    assert not registry.claim("eval_1:run", "evaluation", "worker-b", ttl_seconds=60)
    assert registry.heartbeat("eval_1:run", "worker-a", ttl_seconds=60)
    assert not registry.release("eval_1:run", "worker-b")
    assert registry.release("eval_1:run", "worker-a")
    assert registry.claim("eval_1:run", "evaluation", "worker-b", ttl_seconds=60)

    close_all_pools()


def test_registry_recovers_expired_lease_and_migrates_json(tmp_path):
    db_path = tmp_path / "registry.db"
    registry = ReleaseRegistry(str(db_path))
    registry.ensure_schema()
    assert registry.claim("eval_2:run", "evaluation", "dead-worker", ttl_seconds=5)

    with registry.pool.get_connection() as conn:
        conn.execute(
            "UPDATE release_leases SET expires_at = ? WHERE resource_id = ?",
            ((datetime.now() - timedelta(seconds=1)).isoformat(), "eval_2:run"),
        )
    assert registry.claim("eval_2:run", "evaluation", "new-worker", ttl_seconds=60)

    legacy_dir = tmp_path / "evaluations"
    legacy_dir.mkdir()
    (legacy_dir / "eval_legacy.json").write_text(
        '{"run_id":"eval_legacy","status":"completed","created_at":"2026-01-01T00:00:00"}',
        encoding="utf-8",
    )
    assert registry.migrate_json_directory("evaluation", legacy_dir, "eval_*.json") == 1
    assert registry.get("evaluation", "eval_legacy")[0]["status"] == "completed"
    assert registry.migrate_json_directory("evaluation", legacy_dir, "eval_*.json") == 0

    close_all_pools()


def test_deployment_activation_is_exclusive_per_alias(tmp_path):
    registry = ReleaseRegistry(str(tmp_path / "registry.db"))
    registry.ensure_schema()
    first = {
        "package_id": "deploy_first",
        "status": "active",
        "created_at": "2026-01-01T00:00:00",
        "inference_target": {"model_alias": "support-bot"},
        "audit": [],
    }
    second = {
        "package_id": "deploy_second",
        "status": "draft",
        "created_at": "2026-01-02T00:00:00",
        "inference_target": {"model_alias": "support-bot"},
        "audit": [],
    }
    registry.upsert("deployment", "deploy_first", first)
    registry.upsert("deployment", "deploy_second", second)

    second["status"] = "active"
    registry.activate_deployment_exclusively(second, "support-bot")

    assert registry.get("deployment", "deploy_first")[0]["status"] == "inactive"
    assert registry.get("deployment", "deploy_second")[0]["status"] == "active"
    active = [
        item
        for item in registry.list("deployment")
        if item["status"] == "active"
        and item["inference_target"]["model_alias"] == "support-bot"
    ]
    assert [item["package_id"] for item in active] == ["deploy_second"]

    close_all_pools()


def test_many_workspace_databases_evict_idle_pools_safely(tmp_path):
    reset_release_registry_for_tests()
    for index in range(40):
        registry = get_release_registry(str(tmp_path / f"workspace-{index}.db"))
        registry.upsert(
            "evaluation",
            f"eval_{index}",
            {
                "run_id": f"eval_{index}",
                "status": "completed",
                "created_at": datetime.now().isoformat(),
            },
        )

    # The first pool may have been evicted, but its registry transparently
    # reconnects and durable state remains readable.
    first = get_release_registry(str(tmp_path / "workspace-0.db"))
    assert first.get("evaluation", "eval_0")[0]["status"] == "completed"

    close_all_pools()
    reset_release_registry_for_tests()
