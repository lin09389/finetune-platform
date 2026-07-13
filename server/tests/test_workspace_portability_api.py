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


def test_expired_token_stays_invalid_when_temp_cleanup_must_retry(tmp_path, monkeypatch):
    repository = WorkspacePortabilityRepository(str(tmp_path / "portability.db"))
    archive = tmp_path / "locked.ftworkspace"
    archive.write_bytes(b"package")
    inspection = repository.create_inspection(
        owner_id="owner-a",
        package_digest="digest",
        manifest={"portable_workspace_id": "pws_test"},
        preview={},
        archive_path=str(archive),
        ttl_seconds=0,
    )
    original_unlink = type(archive).unlink

    def locked_unlink(path, *args, **kwargs):
        if path == archive:
            raise PermissionError("locked")
        return original_unlink(path, *args, **kwargs)

    monkeypatch.setattr(type(archive), "unlink", locked_unlink)
    assert repository.cleanup_expired() == []
    assert repository.get_inspection(inspection["token"], "owner-a") is None

    monkeypatch.setattr(type(archive), "unlink", original_unlink)
    assert repository.cleanup_expired() == [str(archive)]
    assert not archive.exists()
