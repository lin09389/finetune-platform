"""A bounded, non-extracting codec for `.ftworkspace` archives."""

from __future__ import annotations

import hashlib
import hmac
import io
import json
import os
import stat
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from .schemas import ChecksumsDocument, TaskContextsDocument, WorkspaceManifestV1


MANIFEST_ENTRY = "manifest.json"
TASK_CONTEXTS_ENTRY = "contexts/tasks.json"
CHECKSUMS_ENTRY = "checksums.json"
ALLOWED_ENTRIES = (MANIFEST_ENTRY, TASK_CONTEXTS_ENTRY, CHECKSUMS_ENTRY)

MAX_ENTRY_COUNT = 32
MAX_ENTRY_BYTES = 2 * 1024 * 1024
MAX_TOTAL_UNCOMPRESSED_BYTES = 10 * 1024 * 1024
MAX_ARCHIVE_BYTES = 12 * 1024 * 1024
MAX_COMPRESSION_RATIO = 100


class WorkspaceArchiveError(ValueError):
    """Base error for untrusted .ftworkspace package failures."""


class UnsafeWorkspaceArchiveError(WorkspaceArchiveError):
    """The package violates container, JSON, or contract safety rules."""


class ArchiveTamperedError(UnsafeWorkspaceArchiveError):
    """A package member did not match its declared checksum."""


class UnsupportedWorkspaceManifestVersion(UnsafeWorkspaceArchiveError):
    """The otherwise well-formed package uses an unsupported schema version."""


@dataclass(frozen=True)
class ArchiveInspection:
    manifest: WorkspaceManifestV1
    package_digest: str
    entry_checksums: dict[str, str]


def _canonical_json(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _load_json(raw: bytes, entry_name: str) -> Any:
    def reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, item in pairs:
            if key in value:
                raise ValueError(f"duplicate JSON key in {entry_name}")
            value[key] = item
        return value

    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=reject_duplicate_keys)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise UnsafeWorkspaceArchiveError(f"{entry_name} is not valid UTF-8 JSON") from exc


class SafeWorkspaceArchiveCodec:
    """Encode and inspect exactly three checksum-protected JSON ZIP entries."""

    def encode(self, manifest: WorkspaceManifestV1) -> bytes:
        contexts = TaskContextsDocument(task_contexts=manifest.task_contexts)
        payloads = {
            MANIFEST_ENTRY: _canonical_json(manifest.model_dump(mode="json")),
            TASK_CONTEXTS_ENTRY: _canonical_json(contexts.model_dump(mode="json")),
        }
        checksums = ChecksumsDocument(
            algorithm="sha256",
            entries={name: hashlib.sha256(payload).hexdigest() for name, payload in payloads.items()},
        )
        payloads[CHECKSUMS_ENTRY] = _canonical_json(checksums.model_dump(mode="json"))

        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
            for entry_name in ALLOWED_ENTRIES:
                info = zipfile.ZipInfo(entry_name, date_time=(1980, 1, 1, 0, 0, 0))
                info.create_system = 3
                info.external_attr = (stat.S_IFREG | 0o644) << 16
                info.compress_type = zipfile.ZIP_DEFLATED
                archive.writestr(info, payloads[entry_name], compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
        package = buffer.getvalue()
        if len(package) > MAX_ARCHIVE_BYTES:  # Defensive assertion for future schema changes.
            raise UnsafeWorkspaceArchiveError("encoded package exceeds archive size limit")
        return package

    def inspect(self, package: bytes) -> ArchiveInspection:
        if not isinstance(package, bytes) or not package:
            raise UnsafeWorkspaceArchiveError("package must be non-empty bytes")
        if len(package) > MAX_ARCHIVE_BYTES:
            raise UnsafeWorkspaceArchiveError("archive exceeds compressed size limit")
        try:
            archive = zipfile.ZipFile(io.BytesIO(package), mode="r")
        except (OSError, zipfile.BadZipFile) as exc:
            raise UnsafeWorkspaceArchiveError("package is not a valid ZIP archive") from exc

        with archive:
            infos = archive.infolist()
            self._validate_infos(infos)
            payloads = {info.filename: self._read_entry(archive, info) for info in infos}

        checksums_raw = _load_json(payloads[CHECKSUMS_ENTRY], CHECKSUMS_ENTRY)
        try:
            checksums = ChecksumsDocument.model_validate(checksums_raw)
        except ValidationError as exc:
            raise UnsafeWorkspaceArchiveError("checksums.json violates the v1 contract") from exc
        for entry_name, expected in checksums.entries.items():
            actual = hashlib.sha256(payloads[entry_name]).hexdigest()
            if not hmac.compare_digest(expected, actual):
                raise ArchiveTamperedError(f"checksum mismatch for {entry_name}")

        manifest_raw = _load_json(payloads[MANIFEST_ENTRY], MANIFEST_ENTRY)
        if not isinstance(manifest_raw, dict):
            raise UnsafeWorkspaceArchiveError("manifest.json must be a JSON object")
        if manifest_raw.get("schema") == "finetune.workspace-manifest" and manifest_raw.get("schema_version") != 1:
            raise UnsupportedWorkspaceManifestVersion("unsupported workspace manifest version")
        try:
            manifest = WorkspaceManifestV1.model_validate(manifest_raw)
        except ValidationError as exc:
            raise UnsafeWorkspaceArchiveError("manifest.json violates the v1 contract") from exc

        contexts_raw = _load_json(payloads[TASK_CONTEXTS_ENTRY], TASK_CONTEXTS_ENTRY)
        try:
            contexts = TaskContextsDocument.model_validate(contexts_raw)
        except ValidationError as exc:
            raise UnsafeWorkspaceArchiveError("contexts/tasks.json violates the v1 contract") from exc
        if contexts.task_contexts != manifest.task_contexts:
            raise UnsafeWorkspaceArchiveError("task context document does not match manifest")

        return ArchiveInspection(
            manifest=manifest,
            package_digest=hashlib.sha256(package).hexdigest(),
            entry_checksums=dict(checksums.entries),
        )

    def write_export(self, destination: Path, manifest: WorkspaceManifestV1) -> Path:
        """Write an export atomically; untrusted imports are never extracted here."""
        package = self.encode(manifest)
        destination = Path(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary_name = tempfile.mkstemp(prefix=f".{destination.name}.", dir=destination.parent)
        try:
            with os.fdopen(fd, "wb") as temporary:
                temporary.write(package)
                temporary.flush()
                os.fsync(temporary.fileno())
            os.replace(temporary_name, destination)
        except BaseException:
            try:
                os.unlink(temporary_name)
            except FileNotFoundError:
                pass
            raise
        return destination

    @staticmethod
    def _validate_infos(infos: list[zipfile.ZipInfo]) -> None:
        if not infos or len(infos) > MAX_ENTRY_COUNT:
            raise UnsafeWorkspaceArchiveError("archive has an invalid entry count")
        names = [info.filename for info in infos]
        if len(set(names)) != len(names):
            raise UnsafeWorkspaceArchiveError("archive contains duplicate entries")
        if set(names) != set(ALLOWED_ENTRIES):
            raise UnsafeWorkspaceArchiveError("archive contains entries outside the v1 allowlist")

        total_size = 0
        for info in infos:
            mode = info.external_attr >> 16
            if info.is_dir() or stat.S_ISLNK(mode):
                raise UnsafeWorkspaceArchiveError("archive contains a directory or symbolic link")
            if info.flag_bits & 0x1:
                raise UnsafeWorkspaceArchiveError("encrypted archive entries are not supported")
            if info.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
                raise UnsafeWorkspaceArchiveError("archive uses an unsupported compression method")
            if info.file_size < 0 or info.file_size > MAX_ENTRY_BYTES:
                raise UnsafeWorkspaceArchiveError("archive entry exceeds uncompressed size limit")
            if info.file_size and not info.compress_size:
                raise UnsafeWorkspaceArchiveError("archive entry has an invalid compressed size")
            if info.file_size / max(info.compress_size, 1) > MAX_COMPRESSION_RATIO:
                raise UnsafeWorkspaceArchiveError("archive entry exceeds compression ratio limit")
            total_size += info.file_size
            if total_size > MAX_TOTAL_UNCOMPRESSED_BYTES:
                raise UnsafeWorkspaceArchiveError("archive exceeds total uncompressed size limit")

    @staticmethod
    def _read_entry(archive: zipfile.ZipFile, info: zipfile.ZipInfo) -> bytes:
        try:
            value = archive.read(info)
        except (OSError, RuntimeError, zipfile.BadZipFile) as exc:
            raise UnsafeWorkspaceArchiveError(f"unable to read {info.filename}") from exc
        if len(value) != info.file_size:
            raise UnsafeWorkspaceArchiveError(f"entry size changed while reading {info.filename}")
        return value


__all__ = [
    "ALLOWED_ENTRIES",
    "ArchiveInspection",
    "ArchiveTamperedError",
    "SafeWorkspaceArchiveCodec",
    "UnsafeWorkspaceArchiveError",
    "UnsupportedWorkspaceManifestVersion",
    "WorkspaceArchiveError",
]
