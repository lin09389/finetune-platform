"""Reference-only Workspace portability contracts and safe archive codec."""

from .archive import (
    ArchiveTamperedError,
    SafeWorkspaceArchiveCodec,
    UnsafeWorkspaceArchiveError,
    UnsupportedWorkspaceManifestVersion,
)
from .schemas import WorkspaceManifestV1
from .service import WorkspaceManifestService

__all__ = [
    "ArchiveTamperedError",
    "SafeWorkspaceArchiveCodec",
    "UnsafeWorkspaceArchiveError",
    "UnsupportedWorkspaceManifestVersion",
    "WorkspaceManifestService",
    "WorkspaceManifestV1",
]
