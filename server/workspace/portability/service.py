"""Storage- and transport-independent portability service façade."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, Protocol, Sequence

from .archive import ArchiveInspection, SafeWorkspaceArchiveCodec
from .schemas import WorkspaceManifestV1


@dataclass(frozen=True)
class SecretFinding:
    field_path: str
    kind: str
    confidence: str = "high"


class WorkspaceManifestProvider(Protocol):
    """Caller-owned adapter; it may query SQLite but this domain never does."""

    def build_manifest(self, *, workspace_id: str, owner_id: str) -> WorkspaceManifestV1:
        """Return a fully projected, reference-only manifest for one Workspace."""


class SecretScanner(Protocol):
    def scan(self, manifest: WorkspaceManifestV1) -> Sequence[SecretFinding]:
        """Return field-level high-confidence credential findings."""


class WorkspacePortabilityServiceError(RuntimeError):
    """Base error for a provider or policy preflight failure."""


class WorkspacePortabilitySecretError(WorkspacePortabilityServiceError):
    def __init__(self, findings: Iterable[SecretFinding]):
        self.findings = tuple(findings)
        super().__init__("workspace export blocked by secret preflight")


class DefaultSecretScanner:
    """Conservative local scanner for credentials accidentally present in summaries."""

    _PATTERNS = (
        ("aws_access_key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
        ("openai_api_key", re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b")),
        ("github_token", re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{20,}\b")),
        ("private_key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
        ("credential_assignment", re.compile(r"\b(?:api[_-]?key|token|secret|password)\s*[:=]\s*\S+", re.I)),
    )

    def scan(self, manifest: WorkspaceManifestV1) -> Sequence[SecretFinding]:
        findings: list[SecretFinding] = []
        for field_path, text in self._strings(manifest.model_dump(mode="json")):
            for kind, pattern in self._PATTERNS:
                if pattern.search(text):
                    findings.append(SecretFinding(field_path=field_path, kind=kind))
                    break
        return findings

    @classmethod
    def _strings(cls, value: object, path: str = "") -> Iterable[tuple[str, str]]:
        if isinstance(value, str):
            yield path, value
        elif isinstance(value, list):
            for index, item in enumerate(value):
                yield from cls._strings(item, f"{path}[{index}]")
        elif isinstance(value, dict):
            for key, item in value.items():
                nested_path = f"{path}.{key}" if path else str(key)
                yield from cls._strings(item, nested_path)


class WorkspaceManifestService:
    """Build, preflight, encode, and inspect manifests through small protocols."""

    def __init__(
        self,
        *,
        archive_codec: SafeWorkspaceArchiveCodec | None = None,
        manifest_provider: WorkspaceManifestProvider | None = None,
        secret_scanner: SecretScanner | None = None,
    ) -> None:
        self._archive_codec = archive_codec or SafeWorkspaceArchiveCodec()
        self._manifest_provider = manifest_provider
        self._secret_scanner = secret_scanner or DefaultSecretScanner()

    def export_package(
        self,
        manifest: WorkspaceManifestV1 | None = None,
        *,
        workspace_id: str | None = None,
        owner_id: str | None = None,
    ) -> bytes:
        if manifest is None:
            if self._manifest_provider is None or not workspace_id or not owner_id:
                raise WorkspacePortabilityServiceError("manifest or provider workspace identity is required")
            manifest = self._manifest_provider.build_manifest(workspace_id=workspace_id, owner_id=owner_id)
        elif workspace_id is not None or owner_id is not None:
            raise WorkspacePortabilityServiceError("pass either a manifest or provider identity, not both")

        findings = tuple(self._secret_scanner.scan(manifest))
        if findings:
            raise WorkspacePortabilitySecretError(findings)
        return self._archive_codec.encode(manifest)

    def inspect_package(self, package: bytes) -> ArchiveInspection:
        return self._archive_codec.inspect(package)


__all__ = [
    "DefaultSecretScanner",
    "SecretFinding",
    "SecretScanner",
    "WorkspaceManifestProvider",
    "WorkspaceManifestService",
    "WorkspacePortabilitySecretError",
    "WorkspacePortabilityServiceError",
]
