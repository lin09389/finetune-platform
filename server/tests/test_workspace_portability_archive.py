"""Adversarial tests for the bounded .ftworkspace ZIP codec."""

from __future__ import annotations

import hashlib
import io
import json
import stat
import sys
import zipfile
from datetime import UTC, datetime
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from workspace.portability.archive import (  # noqa: E402
    ArchiveTamperedError,
    SafeWorkspaceArchiveCodec,
    UnsafeWorkspaceArchiveError,
)
from workspace.portability.schemas import (  # noqa: E402
    PortableProjectReference,
    ProducerInfo,
    WorkspaceIdentity,
    WorkspaceManifestV1,
)
from workspace.portability.service import (  # noqa: E402
    SecretFinding,
    WorkspaceManifestService,
    WorkspacePortabilitySecretError,
)


def _manifest() -> WorkspaceManifestV1:
    return WorkspaceManifestV1(
        portable_workspace_id="pws_0123456789abcdef",
        exported_at=datetime(2026, 7, 13, tzinfo=UTC),
        producer=ProducerInfo(name="finetune-platform", version="2.1.0"),
        workspace=WorkspaceIdentity(name="demo"),
        project=PortableProjectReference(display_name="demo", git_head="a" * 40),
    )


def _zip(entries: dict[str, bytes], *, symlink: str | None = None) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in entries.items():
            info = zipfile.ZipInfo(name)
            if name == symlink:
                info.create_system = 3
                info.external_attr = (stat.S_IFLNK | 0o777) << 16
            archive.writestr(info, content)
    return buffer.getvalue()


def test_round_trip_is_deterministic_and_has_only_allowlisted_entries() -> None:
    codec = SafeWorkspaceArchiveCodec()
    first = codec.encode(_manifest())
    second = codec.encode(_manifest())

    assert first == second
    inspected = codec.inspect(first)
    assert inspected.manifest == _manifest()
    with zipfile.ZipFile(io.BytesIO(first)) as archive:
        assert archive.namelist() == ["manifest.json", "contexts/tasks.json", "checksums.json"]


def test_rejects_checksum_tampering_before_schema_construction() -> None:
    codec = SafeWorkspaceArchiveCodec()
    package = codec.encode(_manifest())
    with zipfile.ZipFile(io.BytesIO(package)) as archive:
        entries = {name: archive.read(name) for name in archive.namelist()}
    entries["manifest.json"] = entries["manifest.json"].replace(b'"demo"', b'"evil"')

    with pytest.raises(ArchiveTamperedError):
        codec.inspect(_zip(entries))


@pytest.mark.parametrize("unsafe_name", ["../manifest.json", "nested/evil.json", "source.py"])
def test_rejects_unallowlisted_and_zip_slip_entries(unsafe_name: str) -> None:
    codec = SafeWorkspaceArchiveCodec()
    package = codec.encode(_manifest())
    with zipfile.ZipFile(io.BytesIO(package)) as archive:
        entries = {name: archive.read(name) for name in archive.namelist()}
    entries[unsafe_name] = b"{}"

    with pytest.raises(UnsafeWorkspaceArchiveError):
        codec.inspect(_zip(entries))


def test_rejects_symlink_duplicate_and_archive_bomb() -> None:
    codec = SafeWorkspaceArchiveCodec()
    package = codec.encode(_manifest())
    with zipfile.ZipFile(io.BytesIO(package)) as archive:
        entries = {name: archive.read(name) for name in archive.namelist()}

    with pytest.raises(UnsafeWorkspaceArchiveError):
        codec.inspect(_zip(entries, symlink="manifest.json"))

    duplicate = io.BytesIO()
    with zipfile.ZipFile(duplicate, "w") as archive:
        for name, content in entries.items():
            archive.writestr(name, content)
        archive.writestr("manifest.json", entries["manifest.json"])
    with pytest.raises(UnsafeWorkspaceArchiveError):
        codec.inspect(duplicate.getvalue())

    bomb_entries = dict(entries)
    bomb_entries["contexts/tasks.json"] = b"a" * (2 * 1024 * 1024 + 1)
    with pytest.raises(UnsafeWorkspaceArchiveError):
        codec.inspect(_zip(bomb_entries))


def test_rejects_checksum_manifest_mismatch_and_invalid_context_document() -> None:
    codec = SafeWorkspaceArchiveCodec()
    package = codec.encode(_manifest())
    with zipfile.ZipFile(io.BytesIO(package)) as archive:
        entries = {name: archive.read(name) for name in archive.namelist()}
    entries["contexts/tasks.json"] = b'{"task_contexts":[{"wrong":true}]}'
    checksum_payload = json.loads(entries["checksums.json"])
    checksum_payload["entries"]["contexts/tasks.json"] = hashlib.sha256(entries["contexts/tasks.json"]).hexdigest()
    entries["checksums.json"] = json.dumps(checksum_payload, separators=(",", ":")).encode()

    with pytest.raises(UnsafeWorkspaceArchiveError):
        codec.inspect(_zip(entries))


def test_export_preflight_fails_closed_on_high_confidence_secret() -> None:
    class Scanner:
        def scan(self, manifest: WorkspaceManifestV1) -> list[SecretFinding]:
            return [SecretFinding(field_path="task_contexts[0].summary", kind="api_key", confidence="high")]

    service = WorkspaceManifestService(secret_scanner=Scanner())
    with pytest.raises(WorkspacePortabilitySecretError) as exc_info:
        service.export_package(_manifest())
    assert exc_info.value.findings[0].field_path == "task_contexts[0].summary"
