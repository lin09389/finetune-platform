"""Two-phase, reference-only Workspace portability endpoints."""

from __future__ import annotations

import hashlib
import logging
import os
import tempfile
import uuid
from dataclasses import asdict, is_dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field

from agent_session.repository import AgentSessionRepository
from agent_session.service import AgentSessionService
from api.agent_sessions import get_agent_session_service
from api.workspace import (
    Workspace,
    _persist_workspaces,
    _require_accessible_workspace,
    get_workspace_user,
    workspaces,
)
from core.config import settings
from core.db_manager import run_sync
from security.jwt_auth import TokenPayload
from workspace.path_policy import require_valid_project_path
from workspace.portability.archive import (
    ArchiveTamperedError,
    UnsafeWorkspaceArchiveError,
    UnsupportedWorkspaceManifestVersion,
)
from workspace.portability.providers import AgentSessionTaskContextProvider, LocalWorkspaceManifestProvider
from workspace.portability.repository import WorkspacePortabilityRepository
from workspace.portability.service import WorkspacePortabilitySecretError, WorkspacePortabilityServiceError

router = APIRouter()
logger = logging.getLogger(__name__)
_MAX_PACKAGE_BYTES = 10 * 1024 * 1024
_PORTABILITY_DATA_DIR = Path(settings.base_dir).resolve() / "data" / "workspace-portability"
_PORTABILITY_DATA_DIR.mkdir(parents=True, exist_ok=True)


class ImportResourceBinding(BaseModel):
    reference_id: str = Field(min_length=1, max_length=300)
    locator: str = Field(min_length=1, max_length=4_096)


class ImportCommitRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2_000)
    project_path: str = Field(min_length=1, max_length=4_096)
    resource_bindings: list[ImportResourceBinding] = Field(default_factory=list, max_length=500)


class ContinuationSessionRequest(BaseModel):
    provider: str | None = Field(default=None, max_length=100)
    model: str | None = Field(default=None, max_length=300)


def _repository() -> WorkspacePortabilityRepository:
    from core.storage import APP_DB_PATH

    return WorkspacePortabilityRepository(APP_DB_PATH)


def _manifest_service(workspace: dict[str, Any] | None = None) -> Any:
    """Construct the contract service with an adapter only when exporting."""
    from workspace.portability.service import WorkspaceManifestService

    provider = LocalWorkspaceManifestProvider(workspace, AgentSessionRepository()) if workspace is not None else None
    return WorkspaceManifestService(manifest_provider=provider)


def _as_dict(value: Any) -> dict[str, Any]:
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    elif is_dataclass(value):
        value = asdict(value)
    return dict(value) if isinstance(value, dict) else {}


def _error(status_code: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": code, "message": message})


def _discard_temp_package(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError as exc:
        logger.warning("Could not remove rejected Workspace package: %s", exc)


def _build_preview(workspace: dict[str, Any], user_id: str) -> dict[str, Any]:
    tasks = AgentSessionTaskContextProvider(AgentSessionRepository()).list_task_contexts(workspace["id"], user_id)
    return {
        "workspace_id": workspace["id"],
        "schema_version": 1,
        "integrity": {"algorithm": "sha256", "status": "valid", "checksums_entry": "checksums.json"},
        "task_count": len(tasks),
        "resources": [],
        "included": ["workspace_manifest", "task_summaries", "execution_plan", "resource_references", "checksums"],
        "exclusions": ["源码", "模型与 checkpoint", "数据集大文件", "密钥", "终端全文", "完整 Diff", "旧审批与工具信任"],
    }


def _write_temp_package(upload: UploadFile) -> tuple[Path, str]:
    digest = hashlib.sha256()
    fd, name = tempfile.mkstemp(prefix="inspect-", suffix=".ftworkspace", dir=_PORTABILITY_DATA_DIR)
    total = 0
    try:
        with os.fdopen(fd, "wb") as handle:
            while chunk := upload.file.read(64 * 1024):
                total += len(chunk)
                if total > _MAX_PACKAGE_BYTES:
                    raise _error(413, "package_too_large", "Workspace package exceeds the 10 MiB limit")
                digest.update(chunk)
                handle.write(chunk)
            handle.flush()
            os.fsync(handle.fileno())
        return Path(name), digest.hexdigest()
    except Exception:
        try:
            os.unlink(name)
        except FileNotFoundError:
            pass
        raise


def _inspect_package(path: Path) -> dict[str, Any]:
    service = _manifest_service()
    package = path.read_bytes()
    result = service.inspect_package(package)
    manifest = result.manifest.model_dump(mode="json")
    resources = [
        {
            **resource,
            "reference_id": resource.get("resource_id")
            or resource.get("model_id")
            or resource.get("collection_id")
            or resource.get("source_run_id")
            or resource.get("task_fingerprint")
            or f"resource-{index}",
            "display_name": resource.get("display_name") or resource.get("model_id") or resource.get("collection_id") or resource.get("artifact_type") or f"Resource {index + 1}",
            "status": "missing",
        }
        for index, resource in enumerate(manifest.get("resources") or [])
    ]
    return {
        "manifest": manifest,
        "preview": {
            "schema_version": manifest["schema_version"],
            "workspace": manifest["workspace"],
            "project": manifest["project"],
            "task_count": len(manifest.get("task_contexts") or []),
            "resource_count": len(resources),
            "resources": resources,
            "exclusions": ["源码", "模型与 checkpoint", "数据集大文件", "密钥", "终端全文", "完整 Diff", "旧审批与工具信任"],
            "integrity": {"algorithm": "sha256", "status": "valid", "checksums_entry": "checksums.json"},
        },
    }


def _create_workspace_from_import(request: ImportCommitRequest, owner_id: str) -> dict[str, Any]:
    # Resolve under the current machine's allow-list.  The archive's old path is
    # never consulted and therefore cannot authorize a new local path.
    project_path = require_valid_project_path(request.project_path, settings)
    workspace_id = f"ws_{uuid.uuid4().hex[:8]}"
    now = datetime.now().isoformat()
    workspace = {
        "id": workspace_id,
        "name": request.name.strip(),
        "description": request.description,
        "created_at": now,
        "updated_at": now,
        "document_count": 0,
        "vector_count": 0,
        "vector_collection_name": workspace_id,
        "local_path": project_path,
        "status": "active",
        "owner_id": owner_id,
    }
    workspaces[workspace_id] = workspace
    try:
        _persist_workspaces()
    except Exception:
        workspaces.pop(workspace_id, None)
        raise
    return workspace


@router.get("/workspaces/{workspace_id}/portability/preview")
async def preview_workspace_export(
    workspace_id: str,
    current_user: TokenPayload = Depends(get_workspace_user),
):
    workspace = _require_accessible_workspace(workspace_id, current_user)
    return await run_sync(_build_preview, workspace, current_user.user_id)


@router.post("/workspaces/{workspace_id}/exports")
async def export_workspace(
    workspace_id: str,
    current_user: TokenPayload = Depends(get_workspace_user),
):
    workspace = _require_accessible_workspace(workspace_id, current_user)
    try:
        service = _manifest_service(workspace)
        package = await run_sync(
            service.export_package,
            workspace_id=workspace_id,
            owner_id=current_user.user_id,
        )
        if not isinstance(package, bytes):
            package = bytes(package)
    except WorkspacePortabilitySecretError as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "export_contains_secret",
                "message": "Workspace export was blocked by secret preflight",
                "findings": [asdict(finding) for finding in exc.findings],
            },
        ) from exc
    except (WorkspacePortabilityServiceError, ValueError) as exc:
        raise _error(422, "export_rejected", str(exc)) from exc
    return Response(
        content=package,
        media_type="application/vnd.finetune.workspace+zip",
        headers={"Content-Disposition": f'attachment; filename="{workspace_id}.ftworkspace"'},
    )


@router.post("/imports/inspect")
async def inspect_workspace_import(
    file: UploadFile = File(...),
    current_user: TokenPayload = Depends(get_workspace_user),
):
    if not str(file.filename or "").lower().endswith(".ftworkspace"):
        raise _error(422, "invalid_package_name", "Expected a .ftworkspace package")
    archive_path, digest = await run_sync(_write_temp_package, file)
    try:
        result = await run_sync(_inspect_package, archive_path)
        manifest = _as_dict(result.get("manifest"))
        if not manifest:
            raise _error(422, "invalid_manifest", "Package inspection did not return a manifest")
        record = await run_sync(
            _repository().create_inspection,
            owner_id=current_user.user_id,
            package_digest=digest,
            manifest=manifest,
            preview=_as_dict(result.get("preview")) or result,
            archive_path=str(archive_path),
        )
    except HTTPException:
        _discard_temp_package(archive_path)
        raise
    except UnsupportedWorkspaceManifestVersion as exc:
        _discard_temp_package(archive_path)
        raise _error(422, "unsupported_version", str(exc)) from exc
    except ArchiveTamperedError as exc:
        _discard_temp_package(archive_path)
        raise _error(422, "archive_tampered", str(exc)) from exc
    except UnsafeWorkspaceArchiveError as exc:
        _discard_temp_package(archive_path)
        raise _error(422, "unsafe_archive", str(exc)) from exc
    except Exception:
        _discard_temp_package(archive_path)
        raise
    return {"import_token": record["token"], "expires_at": record["expires_at"], "preview": record["preview"]}


@router.post("/imports/{token}/commit")
async def commit_workspace_import(
    token: str,
    request: ImportCommitRequest,
    current_user: TokenPayload = Depends(get_workspace_user),
):
    repository = _repository()
    inspection = await run_sync(repository.get_inspection, token, current_user.user_id)
    if inspection is None:
        raise _error(404, "import_token_not_found", "Import token is missing, expired, or belongs to another user")
    if inspection.get("committed_import_id"):
        result = await run_sync(
            repository.commit_import,
            token=token,
            owner_id=current_user.user_id,
            workspace_id="",
            source_portable_id="",
            package_digest=inspection["package_digest"],
            resource_bindings={},
            contexts=[],
        )
        existing_workspace = _require_accessible_workspace(result["workspace_id"], current_user)
        continuations = await run_sync(repository.list_continuations, result["workspace_id"], current_user.user_id)
        return {
            **result,
            "workspace": Workspace(**existing_workspace).model_dump(),
            "continuations": [{**context, "blocked": False, "blocked_reason": None} for context in continuations],
        }
    try:
        workspace = await run_sync(_create_workspace_from_import, request, current_user.user_id)
        manifest = inspection["manifest"]
        contexts = manifest.get("task_contexts") if isinstance(manifest.get("task_contexts"), list) else []
        result = await run_sync(
            repository.commit_import,
            token=token,
            owner_id=current_user.user_id,
            workspace_id=workspace["id"],
            source_portable_id=str(manifest.get("portable_workspace_id") or ""),
            package_digest=inspection["package_digest"],
            resource_bindings={binding.reference_id: binding.locator for binding in request.resource_bindings},
            contexts=[_as_dict(context) for context in contexts],
        )
        archive_path = inspection.get("archive_path")
        if archive_path:
            try:
                Path(str(archive_path)).unlink(missing_ok=True)
            except OSError as exc:
                logger.warning("Committed Workspace import but could not remove inspected package: %s", exc)
    except LookupError as exc:
        raise _error(409, "import_token_expired", str(exc)) from exc
    except ValueError as exc:
        if "workspace" in locals():
            workspaces.pop(workspace["id"], None)
            await run_sync(_persist_workspaces)
        raise _error(422, "invalid_project_binding", str(exc)) from exc
    except Exception:
        if "workspace" in locals():
            workspaces.pop(workspace["id"], None)
            await run_sync(_persist_workspaces)
        raise
    continuations = await run_sync(repository.list_continuations, workspace["id"], current_user.user_id)
    return {
        **result,
        "workspace": Workspace(**workspace).model_dump(),
        "continuations": [{**context, "blocked": False, "blocked_reason": None} for context in continuations],
    }


@router.get("/workspaces/{workspace_id}/continuations")
async def list_workspace_continuations(
    workspace_id: str,
    current_user: TokenPayload = Depends(get_workspace_user),
):
    _require_accessible_workspace(workspace_id, current_user)
    contexts = await run_sync(_repository().list_continuations, workspace_id, current_user.user_id)
    return [{**context, "blocked": False, "blocked_reason": None} for context in contexts]


@router.post("/workspaces/{workspace_id}/continuations/{context_id}/sessions")
async def create_continuation_session(
    workspace_id: str,
    context_id: str,
    request: ContinuationSessionRequest,
    service: AgentSessionService = Depends(get_agent_session_service),
    current_user: TokenPayload = Depends(get_workspace_user),
):
    _require_accessible_workspace(workspace_id, current_user)
    context = await run_sync(_repository().get_continuation, workspace_id, context_id, current_user.user_id)
    if context is None:
        raise _error(404, "continuation_not_found", "Continuation context was not found")
    try:
        session = await run_sync(
            service.lifecycle.create_continuation_session,
            workspace_id=workspace_id,
            continuation_context=context,
            user_id=current_user.user_id,
            provider=request.provider,
            model=request.model,
        )
    except ValueError as exc:
        raise _error(422, "continuation_session_rejected", str(exc)) from exc
    return session


__all__ = ["router"]
