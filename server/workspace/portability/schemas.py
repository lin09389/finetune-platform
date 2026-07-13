"""Strict public DTOs for the version-one Workspace portability format.

These models deliberately contain only references and bounded summaries.  They
are independent of HTTP, SQLite, and agent-runtime implementation details.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Annotated, Literal, Union
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


MAX_TASK_CONTEXTS = 100
MAX_RESOURCE_REFERENCES = 500
MAX_TASK_PLAN_STEPS = 100
MAX_TASK_CHANGED_FILES = 500
MAX_TASK_VERIFICATIONS = 100
MAX_TASK_RESOURCE_REFERENCES = 100

_PORTABLE_ID_RE = re.compile(r"^pws_[a-zA-Z0-9][a-zA-Z0-9_-]{7,127}$")
_SHA256_RE = re.compile(r"^[a-f0-9]{64}$")
_GIT_HEAD_RE = re.compile(r"^[a-fA-F0-9]{7,64}$")


class PortableModel(BaseModel):
    """Base for external contracts: reject fields we did not explicitly export."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ProducerInfo(PortableModel):
    name: str = Field(min_length=1, max_length=100)
    version: str = Field(min_length=1, max_length=100)


class WorkspaceIdentity(PortableModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=1_000)


class PortableProjectReference(PortableModel):
    """A project identity, never a local path or a clone URL with credentials."""

    display_name: str = Field(min_length=1, max_length=200)
    git_head: str | None = Field(default=None, min_length=7, max_length=64)
    remote_hint: str | None = Field(default=None, min_length=3, max_length=300)

    @field_validator("git_head")
    @classmethod
    def validate_git_head(cls, value: str | None) -> str | None:
        if value is not None and not _GIT_HEAD_RE.fullmatch(value):
            raise ValueError("git_head must be a Git object hash")
        return value.lower() if value else value

    @field_validator("remote_hint")
    @classmethod
    def validate_remote_hint(cls, value: str | None) -> str | None:
        if value is None:
            return value
        # v1 carries only a redacted host/path, never a URL or credentials.
        if any(marker in value for marker in ("://", "@", "?", "#", "\\")):
            raise ValueError("remote_hint must be a redacted host/path")
        parsed = urlsplit("//" + value)
        if not parsed.hostname or not parsed.path or parsed.path == "/":
            raise ValueError("remote_hint must contain host/path")
        if not re.fullmatch(r"[A-Za-z0-9._/-]+", value):
            raise ValueError("remote_hint contains unsupported characters")
        return value.rstrip("/")


class PortableDatasetReference(PortableModel):
    kind: Literal["dataset"] = "dataset"
    resource_id: str = Field(min_length=1, max_length=200)
    display_name: str = Field(min_length=1, max_length=200)
    format: str = Field(min_length=1, max_length=80)
    size_bytes: int | None = Field(default=None, ge=0, le=2**63 - 1)
    checksum: str | None = Field(default=None, min_length=64, max_length=64)

    @field_validator("checksum")
    @classmethod
    def validate_checksum(cls, value: str | None) -> str | None:
        if value is not None and not _SHA256_RE.fullmatch(value):
            raise ValueError("checksum must be a lowercase SHA-256 digest")
        return value


class PortableModelReference(PortableModel):
    kind: Literal["model"] = "model"
    model_id: str = Field(min_length=1, max_length=300)
    revision: str | None = Field(default=None, min_length=1, max_length=200)
    backend_hint: str | None = Field(default=None, min_length=1, max_length=100)


class PortableCheckpointReference(PortableModel):
    kind: Literal["checkpoint"] = "checkpoint"
    task_fingerprint: str = Field(min_length=64, max_length=64)
    model_id: str = Field(min_length=1, max_length=300)
    step: int = Field(ge=0, le=2**63 - 1)
    metadata_checksum: str | None = Field(default=None, min_length=64, max_length=64)

    @field_validator("task_fingerprint", "metadata_checksum")
    @classmethod
    def validate_sha256(cls, value: str | None) -> str | None:
        if value is not None and not _SHA256_RE.fullmatch(value):
            raise ValueError("value must be a lowercase SHA-256 digest")
        return value


class PortableArtifactReference(PortableModel):
    kind: Literal["artifact"] = "artifact"
    artifact_type: str = Field(min_length=1, max_length=100)
    display_name: str = Field(min_length=1, max_length=200)
    source_task_fingerprint: str | None = Field(default=None, min_length=64, max_length=64)
    source_run_id: str | None = Field(default=None, min_length=1, max_length=200)
    checksum: str | None = Field(default=None, min_length=64, max_length=64)

    @field_validator("source_task_fingerprint", "checksum")
    @classmethod
    def validate_sha256(cls, value: str | None) -> str | None:
        if value is not None and not _SHA256_RE.fullmatch(value):
            raise ValueError("value must be a lowercase SHA-256 digest")
        return value


class PortableKnowledgeReference(PortableModel):
    kind: Literal["knowledge"] = "knowledge"
    collection_id: str = Field(min_length=1, max_length=200)
    display_name: str = Field(min_length=1, max_length=200)
    document_count: int | None = Field(default=None, ge=0, le=10_000_000)
    chunk_count: int | None = Field(default=None, ge=0, le=100_000_000)


PortableResourceReference = Annotated[
    Union[
        PortableDatasetReference,
        PortableModelReference,
        PortableCheckpointReference,
        PortableArtifactReference,
        PortableKnowledgeReference,
    ],
    Field(discriminator="kind"),
]


class PortablePlanStep(PortableModel):
    title: str = Field(min_length=1, max_length=500)
    status: Literal["pending", "in_progress", "completed", "blocked", "skipped"]
    summary: str | None = Field(default=None, max_length=2_000)


class PortableChangedFile(PortableModel):
    path: str = Field(min_length=1, max_length=1_000)
    additions: int = Field(ge=0, le=10_000_000)
    deletions: int = Field(ge=0, le=10_000_000)

    @field_validator("path")
    @classmethod
    def validate_relative_path(cls, value: str) -> str:
        if value.startswith(("/", "\\")) or re.match(r"^[A-Za-z]:", value):
            raise ValueError("changed file paths must be relative")
        parts = value.replace("\\", "/").split("/")
        if any(part in ("", ".", "..") for part in parts):
            raise ValueError("changed file path escapes its project")
        return "/".join(parts)


class PortableVerification(PortableModel):
    category: Literal["build", "test", "lint", "train", "evaluation", "manual"]
    status: Literal["passed", "failed", "skipped", "not_run"]
    summary: str | None = Field(default=None, max_length=2_000)


class PortableTaskResourceReference(PortableModel):
    kind: Literal["artifact", "training_run"]
    reference_id: str = Field(min_length=1, max_length=200)
    display_name: str = Field(min_length=1, max_length=200)


class PortableTaskContext(PortableModel):
    """A read-only, authority-free task continuation summary."""

    source_task_fingerprint: str = Field(min_length=64, max_length=64)
    title: str = Field(min_length=1, max_length=300)
    mode: Literal["build", "train", "hybrid"]
    status: Literal["completed", "failed", "cancelled", "stopped"]
    execution_plan: list[PortablePlanStep] = Field(default_factory=list, max_length=MAX_TASK_PLAN_STEPS)
    summary: str | None = Field(default=None, max_length=4_000)
    changed_files: list[PortableChangedFile] = Field(default_factory=list, max_length=MAX_TASK_CHANGED_FILES)
    verifications: list[PortableVerification] = Field(default_factory=list, max_length=MAX_TASK_VERIFICATIONS)
    resource_references: list[PortableTaskResourceReference] = Field(
        default_factory=list, max_length=MAX_TASK_RESOURCE_REFERENCES
    )
    updated_at: datetime

    @field_validator("source_task_fingerprint")
    @classmethod
    def validate_fingerprint(cls, value: str) -> str:
        if not _SHA256_RE.fullmatch(value):
            raise ValueError("source_task_fingerprint must be a SHA-256 digest")
        return value

    @field_validator("updated_at")
    @classmethod
    def validate_updated_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("updated_at must include a timezone")
        return value.astimezone(timezone.utc)


class IntegrityInfo(PortableModel):
    algorithm: Literal["sha256"] = "sha256"
    checksums_entry: Literal["checksums.json"] = "checksums.json"


class WorkspaceManifestV1(PortableModel):
    schema: Literal["finetune.workspace-manifest"] = "finetune.workspace-manifest"
    schema_version: Literal[1] = 1
    portable_workspace_id: str = Field(min_length=12, max_length=132)
    exported_at: datetime
    producer: ProducerInfo
    workspace: WorkspaceIdentity
    project: PortableProjectReference
    resources: list[PortableResourceReference] = Field(default_factory=list, max_length=MAX_RESOURCE_REFERENCES)
    task_contexts: list[PortableTaskContext] = Field(default_factory=list, max_length=MAX_TASK_CONTEXTS)
    integrity: IntegrityInfo = Field(default_factory=IntegrityInfo)

    @field_validator("portable_workspace_id")
    @classmethod
    def validate_portable_workspace_id(cls, value: str) -> str:
        if not _PORTABLE_ID_RE.fullmatch(value):
            raise ValueError("portable_workspace_id must use the pws_ stable-ID format")
        return value

    @field_validator("exported_at")
    @classmethod
    def validate_exported_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("exported_at must include a timezone")
        return value.astimezone(timezone.utc)


class TaskContextsDocument(PortableModel):
    """The dedicated archive member mirrors manifest task contexts for v1."""

    task_contexts: list[PortableTaskContext] = Field(max_length=MAX_TASK_CONTEXTS)


class ChecksumsDocument(PortableModel):
    algorithm: Literal["sha256"]
    entries: dict[str, str] = Field(min_length=2, max_length=2)

    @model_validator(mode="after")
    def validate_entries(self) -> "ChecksumsDocument":
        expected = {"manifest.json", "contexts/tasks.json"}
        if set(self.entries) != expected:
            raise ValueError("checksums must cover exactly the signed archive entries")
        if any(not _SHA256_RE.fullmatch(value) for value in self.entries.values()):
            raise ValueError("checksums must be lowercase SHA-256 digests")
        return self


__all__ = [
    "ChecksumsDocument",
    "IntegrityInfo",
    "MAX_RESOURCE_REFERENCES",
    "MAX_TASK_CONTEXTS",
    "PortableArtifactReference",
    "PortableChangedFile",
    "PortableCheckpointReference",
    "PortableDatasetReference",
    "PortableKnowledgeReference",
    "PortableModelReference",
    "PortablePlanStep",
    "PortableProjectReference",
    "PortableResourceReference",
    "PortableTaskContext",
    "PortableTaskResourceReference",
    "PortableVerification",
    "ProducerInfo",
    "TaskContextsDocument",
    "WorkspaceIdentity",
    "WorkspaceManifestV1",
]
