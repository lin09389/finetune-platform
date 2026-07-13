from __future__ import annotations

from workspace.portability.repository import WorkspacePortabilityRepository


def test_inspection_token_is_bound_to_owner_and_expires(tmp_path):
    repository = WorkspacePortabilityRepository(str(tmp_path / "portability.db"))
    inspection = repository.create_inspection(
        owner_id="owner-a",
        package_digest="digest",
        manifest={"portable_workspace_id": "pws_test"},
        preview={},
        ttl_seconds=0,
    )

    assert repository.get_inspection(inspection["token"], "owner-b") is None
    assert repository.get_inspection(inspection["token"], "owner-a") is None
