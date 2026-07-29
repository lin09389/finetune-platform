"""Workspace management API with persisted metadata."""

from __future__ import annotations

import json
import logging
import os
import tempfile
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from core.config import settings
from core.db_manager import run_sync
from rag.vector_store import get_vector_store
from security.auth_middleware import get_current_user_optional
from security.jwt_auth import Role, TokenPayload
from workspace.local_paths import get_allowed_workspace_roots, normalize_local_workspace_path
from workspace.path_policy import (
    list_allowed_roots,
    require_valid_project_path,
    resolve_default_project_path,
    validate_agent_project_path,
)

logger = logging.getLogger(__name__)

router = APIRouter()

WORKSPACE_DATA_DIR = Path(settings.base_dir).resolve() / "data" / "workspaces"
WORKSPACE_DATA_DIR.mkdir(parents=True, exist_ok=True)
WORKSPACE_METADATA_FILE = WORKSPACE_DATA_DIR / "metadata.json"
_workspace_store_lock = threading.RLock()


def _load_workspace_store() -> dict[str, dict[str, Any]]:
    if WORKSPACE_METADATA_FILE.exists():
        try:
            with open(WORKSPACE_METADATA_FILE, encoding="utf-8") as handle:
                data = json.load(handle)
            if isinstance(data, dict):
                return {workspace_id: payload for workspace_id, payload in data.items() if isinstance(payload, dict)}
        except Exception as exc:
            logger.warning("Failed to load workspace metadata: %s", exc)

    # One-time compatibility read for metadata written by earlier CWD-relative versions.
    from workspace.local_paths import load_workspace_metadata
    return load_workspace_metadata()


def _save_workspace_store(workspaces: dict[str, dict[str, Any]]) -> None:
    payload = json.dumps(workspaces, ensure_ascii=False, indent=2)
    with _workspace_store_lock:
        fd, temp_name = tempfile.mkstemp(prefix="metadata.", suffix=".tmp", dir=WORKSPACE_DATA_DIR)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_name, WORKSPACE_METADATA_FILE)
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)


workspaces: dict[str, dict[str, Any]] = _load_workspace_store()
DEFAULT_WORKSPACE_ID = "current_project"


class AgentWorkspaceNotFoundError(ValueError):
    """Raised when an Agent task references a Workspace that no longer exists."""


async def get_workspace_user(
    current_user: TokenPayload | None = Depends(get_current_user_optional),
) -> TokenPayload:
    """Require the same explicit local fallback used by Agent session routes."""
    if current_user:
        return current_user
    from security.runtime_policy import allow_local_agent_auth, is_production_environment

    if not settings.enable_auth:
        return TokenPayload(
            user_id="desktop-local-user",
            username="desktop",
            role=Role.USER,
            permissions=["workspace:local"],
        )
    if is_production_environment(settings) or not allow_local_agent_auth(settings):
        raise HTTPException(status_code=401, detail="Missing authorization")
    return TokenPayload(
        user_id="desktop-local-user",
        username="desktop",
        role=Role.USER,
        permissions=["workspace:local"],
    )


def _is_admin(user: TokenPayload) -> bool:
    return user.role in {Role.ADMIN, Role.SUPER_ADMIN}


def _can_access_workspace(workspace: dict[str, Any], user_id: str | None, is_admin: bool = False) -> bool:
    if user_id is None:
        return True  # Internal callers and compatibility tests must explicitly opt out of subject scoping.
    owner_id = str(workspace.get("owner_id") or "").strip()
    if not owner_id:
        # Legacy metadata written before owner scoping remains usable on
        # single-machine installs. Explicitly owned workspaces stay isolated.
        return True
    return owner_id == user_id or is_admin


def _require_accessible_workspace(workspace_id: str, user: TokenPayload) -> dict[str, Any]:
    workspace = _ensure_workspace_exists(workspace_id)
    if not _can_access_workspace(workspace, user.user_id, _is_admin(user)):
        raise HTTPException(status_code=404, detail="Workspace not found")
    return workspace


def _accessible_workspace_roots(user_id: str | None, is_admin: bool = False) -> set[Path]:
    # Only persisted metadata may expand the filesystem allowlist.  Using the
    # mutable process cache here would let an untrusted/incomplete record
    # authorize its own local_path before it has passed registration.
    from workspace.local_paths import load_workspace_metadata

    roots: set[Path] = set()
    for workspace in load_workspace_metadata().values():
        if not _can_access_workspace(workspace, user_id, is_admin):
            continue
        raw = str(workspace.get("local_path") or "").strip()
        if raw:
            roots.add(Path(raw).expanduser().resolve())
    return roots


def _default_project_path() -> str:
    return resolve_default_project_path(settings)


def _default_workspace_payload() -> dict[str, Any]:
    now = datetime.now().isoformat()
    return {
        "id": DEFAULT_WORKSPACE_ID,
        "name": "当前项目",
        "description": "当前 Finetune Platform 项目根目录",
        "created_at": now,
        "updated_at": now,
        "document_count": 0,
        "vector_count": 0,
        "vector_collection_name": DEFAULT_WORKSPACE_ID,
        "local_path": _default_project_path(),
        "status": "default",
    }


def resolve_agent_workspace(
    workspace_id: str | None,
    project_path: str | None,
    *,
    user_id: str | None = None,
    is_admin: bool = False,
) -> tuple[str, str | None]:
    """Resolve a Workspace reference into the path safe for an Agent session.

    A supplied Workspace ID is authoritative: its persisted local path is
    revalidated through the shared path policy and any concurrent client path
    is ignored.  Legacy calls without a Workspace continue to validate their
    explicit project path through that same policy.
    """
    canonical_workspace_id = str(workspace_id or "").strip() or None
    if not canonical_workspace_id:
        return require_valid_project_path(
            project_path,
            settings,
            extra_roots=_accessible_workspace_roots(user_id, is_admin),
            include_registered=False,
        ), None

    if canonical_workspace_id == DEFAULT_WORKSPACE_ID:
        workspace_path = _default_project_path()
    else:
        workspace = workspaces.get(canonical_workspace_id)
        if not workspace:
            raise AgentWorkspaceNotFoundError("Workspace not found")
        if not _can_access_workspace(workspace, user_id, is_admin):
            raise AgentWorkspaceNotFoundError("Workspace not found")
        workspace_path = str(workspace.get("local_path") or "").strip()
        if not workspace_path:
            raise ValueError("Workspace does not have a local_path")

    return require_valid_project_path(
        workspace_path,
        settings,
        extra_roots=_accessible_workspace_roots(user_id, is_admin),
        include_registered=False,
    ), canonical_workspace_id


class WorkspaceCreate(BaseModel):
    """Create workspace request."""

    name: str = Field(..., description="Workspace name")
    description: str | None = Field(default=None, description="Workspace description")
    local_path: str | None = Field(default=None, description="Optional local project path")


class Workspace(BaseModel):
    """Workspace metadata."""

    id: str
    name: str
    description: str | None
    created_at: str
    updated_at: str
    document_count: int = 0
    vector_count: int = 0
    vector_collection_name: str
    local_path: str | None = None
    status: str = "active"


class WorkspaceUpdate(BaseModel):
    """Update workspace request."""

    name: str | None = Field(default=None, description="Updated name")
    description: str | None = Field(default=None, description="Updated description")
    local_path: str | None = Field(default=None, description="Updated local project path")


class WorkspaceTreeNode(BaseModel):
    """A local workspace file tree node."""

    name: str
    path: str
    kind: str
    children: list["WorkspaceTreeNode"] | None = None


class WorkspaceTreeResponse(BaseModel):
    root: str
    nodes: list[WorkspaceTreeNode]
    truncated: bool = False


def _persist_workspaces() -> None:
    _save_workspace_store(workspaces)


def _ensure_workspace_exists(workspace_id: str) -> dict[str, Any]:
    workspace = workspaces.get(workspace_id)
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")
    return workspace


def _refresh_workspace_counts(workspace: dict[str, Any]) -> Workspace:
    collection_name = workspace.get("vector_collection_name", workspace["id"])

    try:
        vector_store = get_vector_store()
        stats = vector_store.get_collection_stats(collection_name)
        vector_count = stats.get("count", 0)
    except Exception as exc:
        vector_count = 0
        workspace["status"] = "degraded"
        workspace["vector_store_error"] = str(exc)

    workspace["vector_collection_name"] = collection_name
    workspace["vector_count"] = vector_count
    return Workspace(**workspace)


async def _refresh_workspace_counts_async(workspace: dict[str, Any]) -> Workspace:
    """Async-safe wrapper that offloads vector store I/O to a thread."""
    return await run_sync(_refresh_workspace_counts, workspace)


def _resolve_workspace_path(
    workspace_id: str | None = None,
    project_path: str | None = None,
    *,
    current_user: TokenPayload | None = None,
) -> Path:
    if project_path and project_path.strip():
        try:
            return Path(require_valid_project_path(
                project_path,
                settings,
                extra_roots=_accessible_workspace_roots(
                    current_user.user_id if current_user else None,
                    _is_admin(current_user) if current_user else False,
                ),
                include_registered=False,
            )).resolve()
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    if workspace_id:
        if workspace_id == DEFAULT_WORKSPACE_ID:
            return Path(_default_project_path()).resolve()
        workspace = (
            _require_accessible_workspace(workspace_id, current_user)
            if current_user else _ensure_workspace_exists(workspace_id)
        )
        local_path = workspace.get("local_path")
        if not local_path:
            raise HTTPException(status_code=400, detail="Workspace does not have a local_path")
        return Path(local_path).resolve()

    return Path(_default_project_path()).resolve()


def _is_ignored_tree_entry(name: str) -> bool:
    ignored_names = {
        ".git",
        ".hg",
        ".svn",
        ".vs",
        ".venv",
        "venv",
        "env",
        "node_modules",
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        "dist",
        "build",
        "coverage",
        ".idea",
        ".vscode",
        ".next",
        ".nuxt",
        "out",
    }
    return name in ignored_names


def _build_tree(
    path: Path,
    root: Path,
    *,
    depth: int,
    max_depth: int,
    budget: dict[str, int],
) -> list[WorkspaceTreeNode]:
    if depth >= max_depth or budget["remaining"] <= 0:
        return []

    try:
        # Using os.scandir is significantly faster than Path.iterdir
        # because it pre-fetches file/folder attributes in a single OS system call
        # avoiding hundreds of slow stat calls, particularly on Windows.
        with os.scandir(path) as it:
            entries = [entry for entry in it if not _is_ignored_tree_entry(entry.name)]
    except OSError:
        return []

    # Sort entries: directories first, then files, sorted alphabetically (case-insensitive)
    entries.sort(key=lambda item: (item.is_file(follow_symlinks=False), item.name.lower()))
    nodes: list[WorkspaceTreeNode] = []

    for entry in entries:
        if budget["remaining"] <= 0:
            break
        budget["remaining"] -= 1

        # Calculate a safe relative path, protecting against Windows reserved device names (e.g. NUL)
        # or cross-drive symlink ValueError.
        try:
            if entry.name.upper() in {
                "CON", "PRN", "AUX", "NUL",
                "COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7", "COM8", "COM9",
                "LPT1", "LPT2", "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9"
            }:
                continue
            rel_path = os.path.relpath(entry.path, root).replace("\\", "/")
        except ValueError as exc:
            logger.warning("Skipping entry in tree build due to mount/path error: %s (%s)", entry.path, exc)
            continue

        if entry.is_dir(follow_symlinks=False):
            nodes.append(
                WorkspaceTreeNode(
                    name=entry.name,
                    path=rel_path,
                    kind="folder",
                    children=_build_tree(Path(entry.path), root, depth=depth + 1, max_depth=max_depth, budget=budget),
                )
            )
        elif entry.is_file(follow_symlinks=False):
            nodes.append(WorkspaceTreeNode(name=entry.name, path=rel_path, kind="file"))

    return nodes


@router.post("/workspaces", response_model=Workspace)
async def create_workspace(data: WorkspaceCreate, current_user: TokenPayload = Depends(get_workspace_user)):
    """Create a workspace."""
    try:
        local_path = normalize_local_workspace_path(data.local_path)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    workspace_id = f"ws_{uuid.uuid4().hex[:8]}"
    now = datetime.now().isoformat()
    collection_name = workspace_id

    workspace = {
        "id": workspace_id,
        "name": data.name,
        "description": data.description,
        "created_at": now,
        "updated_at": now,
        "document_count": 0,
        "vector_count": 0,
        "vector_collection_name": collection_name,
        "local_path": local_path,
        "status": "active",
        "owner_id": current_user.user_id,
    }

    def _create_collection():
        vector_store = get_vector_store()
        vector_store.get_or_create_collection(collection_name)

    try:
        await run_sync(_create_collection)
    except (ImportError, ModuleNotFoundError) as exc:
        logger.warning("Vector store unavailable; workspace created in degraded mode: %s", exc)
        workspace["status"] = "degraded"
        workspace["vector_store_error"] = str(exc)

    workspaces[workspace_id] = workspace
    await run_sync(_persist_workspaces)

    logger.info("Workspace created: %s (%s)", workspace_id, data.name)
    return Workspace(**workspace)


@router.get("/workspaces", response_model=list[Workspace])
async def list_workspaces(current_user: TokenPayload = Depends(get_workspace_user)):
    """List workspaces."""
    result: list[Workspace] = []
    default_workspace = _default_workspace_payload()
    default_path = default_workspace["local_path"]
    has_default_path = False
    has_registered_default = False
    for workspace in workspaces.values():
        if not _can_access_workspace(workspace, current_user.user_id, _is_admin(current_user)):
            continue
        if workspace.get("local_path") == default_path:
            has_default_path = True
        if workspace.get("status") == "default" and workspace.get("local_path"):
            has_registered_default = True
        result.append(await _refresh_workspace_counts_async(workspace))
    if not has_default_path and not has_registered_default:
        result.insert(0, Workspace(**default_workspace))
    result.sort(key=lambda item: 0 if item.status == "default" else 1)
    await run_sync(_persist_workspaces)
    return result


@router.get("", response_model=list[Workspace])
async def list_workspaces_compat(current_user: TokenPayload = Depends(get_workspace_user)):
    """Compatibility endpoint for GET /workspace."""
    return await list_workspaces(current_user)


@router.get("/workspaces/{workspace_id}", response_model=Workspace)
async def get_workspace(workspace_id: str, current_user: TokenPayload = Depends(get_workspace_user)):
    """Get workspace details."""
    workspace = _require_accessible_workspace(workspace_id, current_user)
    refreshed = await _refresh_workspace_counts_async(workspace)
    await run_sync(_persist_workspaces)
    return refreshed


@router.put("/workspaces/{workspace_id}", response_model=Workspace)
async def update_workspace(
    workspace_id: str,
    data: WorkspaceUpdate,
    current_user: TokenPayload = Depends(get_workspace_user),
):
    """Update workspace metadata."""
    workspace = _require_accessible_workspace(workspace_id, current_user)

    if data.name is not None:
        workspace["name"] = data.name
    if data.description is not None:
        workspace["description"] = data.description
    if data.local_path is not None:
        try:
            workspace["local_path"] = normalize_local_workspace_path(data.local_path)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    workspace["updated_at"] = datetime.now().isoformat()
    await run_sync(_persist_workspaces)

    return Workspace(**workspace)


@router.delete("/workspaces/{workspace_id}")
async def delete_workspace(workspace_id: str, current_user: TokenPayload = Depends(get_workspace_user)):
    """Delete a workspace."""
    workspace = _require_accessible_workspace(workspace_id, current_user)
    collection_name = workspace.get("vector_collection_name", workspace_id)

    try:
        def _delete_collection():
            vector_store = get_vector_store()
            vector_store.delete_collection(collection_name)

        await run_sync(_delete_collection)
    except Exception as exc:
        logger.error("Failed to delete vector collection %s: %s", collection_name, exc)

    del workspaces[workspace_id]
    await run_sync(_persist_workspaces)

    logger.info("Workspace deleted: %s", workspace_id)
    return {"message": "Deleted successfully", "workspace_id": workspace_id}


@router.get("/workspaces/{workspace_id}/stats")
async def get_workspace_stats(workspace_id: str, current_user: TokenPayload = Depends(get_workspace_user)):
    """Get workspace statistics."""
    workspace = _require_accessible_workspace(workspace_id, current_user)
    collection_name = workspace.get("vector_collection_name", workspace_id)

    try:
        def _fetch_stats():
            vector_store = get_vector_store()
            stats = vector_store.get_collection_stats(collection_name)
            documents = vector_store.list_documents(collection_name)
            return stats, documents

        stats, documents = await run_sync(_fetch_stats)
        workspace["vector_count"] = stats.get("count", 0)
        workspace["document_count"] = len(documents)
        workspace["updated_at"] = datetime.now().isoformat()
        await run_sync(_persist_workspaces)

        return {
            "workspace_id": workspace_id,
            "vector_count": workspace["vector_count"],
            "document_count": workspace["document_count"],
            "documents": documents,
        }
    except Exception as exc:
        logger.error("Failed to get workspace stats for %s: %s", workspace_id, exc)
        return {
            "workspace_id": workspace_id,
            "vector_count": 0,
            "document_count": 0,
            "documents": [],
        }


@router.get("/tree", response_model=WorkspaceTreeResponse)
async def get_workspace_tree(
    workspace_id: str | None = None,
    project_path: str | None = None,
    max_depth: int = 3,
    limit: int = 240,
    current_user: TokenPayload = Depends(get_workspace_user),
):
    """Return a shallow local file tree for the selected workspace."""
    root = _resolve_workspace_path(
        workspace_id=workspace_id,
        project_path=project_path,
        current_user=current_user,
    )
    max_depth = max(1, min(max_depth, 6))
    limit = max(20, min(limit, 800))
    budget = {"remaining": limit}
    nodes = _build_tree(root, root, depth=0, max_depth=max_depth, budget=budget)
    return WorkspaceTreeResponse(root=str(root), nodes=nodes, truncated=budget["remaining"] <= 0)


class WorkspacePathValidateRequest(BaseModel):
    path: str | None = Field(default=None, description="Candidate project path (empty = default)")


@router.get("/allowed-roots")
async def get_allowed_workspace_roots_endpoint(current_user: TokenPayload = Depends(get_workspace_user)):
    """List default project path and allowed workspace roots for Agent/UI pickers."""
    roots = list_allowed_roots(
        settings,
        extra_roots=_accessible_workspace_roots(current_user.user_id, _is_admin(current_user)),
        include_registered=False,
    )
    return {
        "default_project_path": resolve_default_project_path(settings),
        "roots": [item.as_dict() for item in roots],
    }


@router.post("/validate-path")
async def validate_workspace_path(
    data: WorkspacePathValidateRequest,
    current_user: TokenPayload = Depends(get_workspace_user),
):
    """Validate a candidate Agent project path (existence, directory, allowlist)."""
    result = validate_agent_project_path(
        data.path,
        settings,
        extra_roots=_accessible_workspace_roots(current_user.user_id, _is_admin(current_user)),
        include_registered=False,
    )
    return result.as_dict()


@router.get("/browse-folder")
async def browse_folder(
    initial_path: str | None = None,
    current_user: TokenPayload = Depends(get_workspace_user),
):
    """Open a native OS directory chooser dialog and return the selected path."""
    import os
    import platform
    import queue
    import subprocess
    import threading

    # Try Windows PowerShell first
    if platform.system() == "Windows":
        try:
            if initial_path:
                # Normalise and escape single quotes for PowerShell single-quoted string literal
                escaped_path = os.path.abspath(initial_path).replace("'", "''")
                init_path_setter = f"$initial_path = '{escaped_path}'"
            else:
                init_path_setter = "$initial_path = $null"

            ps_code = f"""
            Add-Type -AssemblyName System.Windows.Forms
            {init_path_setter}
            $dialog = New-Object System.Windows.Forms.FolderBrowserDialog
            $dialog.Description = "Select Workspace Folder"
            $dialog.ShowNewFolderButton = $true
            if ($initial_path -and (Test-Path $initial_path)) {{
                $dialog.SelectedPath = $initial_path
            }}
            $form = New-Object System.Windows.Forms.Form
            $form.TopMost = $true
            $form.Width = 1
            $form.Height = 1
            $form.ShowInTaskbar = $false
            $form.WindowState = [System.Windows.Forms.FormWindowState]::Minimized
            $form.Show()
            $form.Activate()
            $result = $dialog.ShowDialog($form)
            $form.Dispose()
            if ($result -eq [System.Windows.Forms.DialogResult]::OK) {{
                Write-Output $dialog.SelectedPath
            }}
            """
            cmd = ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_code]

            # Hide flashing console window on Windows
            startupinfo = None
            if hasattr(subprocess, "STARTUPINFO"):
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startupinfo.wShowWindow = subprocess.SW_HIDE

            # Run powershell with a generous 120s timeout
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                startupinfo=startupinfo,
                timeout=120.0
            )

            if result.returncode == 0:
                selected_path = result.stdout.strip()
                if selected_path:
                    return {"status": "success", "path": selected_path}
                else:
                    return {"status": "cancelled", "path": None, "message": "用户取消了文件夹选择"}
            else:
                logger.warning("PowerShell folder dialog failed (returncode %d): %s", result.returncode, result.stderr)
        except Exception as exc:
            logger.warning("PowerShell folder dialog failed: %s", exc)

    # Cross-platform fallback: Tkinter thread dialog
    logger.info("Falling back to Tkinter dialog for folder selection")
    q = queue.Queue()

    def picker_thread(q_out, init_dir):
        try:
            import tkinter as tk
            from tkinter import filedialog

            root = tk.Tk()
            root.withdraw()
            root.attributes("-topmost", True)
            folder = filedialog.askdirectory(initialdir=init_dir, parent=root)
            root.destroy()
            if folder:
                q_out.put({"status": "success", "path": folder})
            else:
                q_out.put({"status": "cancelled", "path": None, "message": "用户取消了文件夹选择"})
        except Exception as e:
            q_out.put({"status": "error", "message": str(e)})

    t = threading.Thread(target=picker_thread, args=(q, initial_path))
    t.start()
    t.join(timeout=60.0)

    if t.is_alive():
        return {"status": "timeout", "path": None, "message": "文件夹选择超时"}

    try:
        res = q.get_nowait()
        return res
    except queue.Empty:
        return {"status": "error", "path": None, "message": "无法激活文件夹选择，请手动输入路径"}


# ── Workspace file read / write ────────────────────────────────────────────────

class FileWriteRequest(BaseModel):
    """Request payload for writing a file."""

    file_path: str = Field(..., description="Absolute path to the file to write")
    content: str = Field(..., description="New text content of the file")
    workspace_id: str | None = Field(default=None, description="Workspace ID for sandbox validation")
    project_path: str | None = Field(default=None, description="Project root for sandbox validation")


def _validate_file_path_in_workspace(
    file_path: str,
    workspace_id: str | None,
    project_path: str | None,
    current_user: TokenPayload,
) -> Path:
    """Resolve the file path and assert it lives inside an allowed workspace root."""
    try:
        raw_path = str(file_path or "").strip().replace("\\", "/")
        project_root = Path(require_valid_project_path(
            project_path,
            settings,
            extra_roots=_accessible_workspace_roots(current_user.user_id, _is_admin(current_user)),
            include_registered=False,
        )).resolve() if project_path else None
        if raw_path == "/workspace":
            raw_path = ""
        elif raw_path.startswith("/workspace/"):
            raw_path = raw_path[len("/workspace/"):]
        elif raw_path.startswith("workspace/"):
            raw_path = raw_path[len("workspace/"):]

        candidate = Path(raw_path).expanduser()
        if not candidate.is_absolute() and project_root is not None:
            candidate = project_root / candidate
        resolved = candidate.resolve()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid file path: {exc}") from exc

    # Build allowed roots: from project_path hint, from workspace metadata, from env
    extra_roots: set[Path] = set()
    if project_root:
        extra_roots.add(project_root)
    if workspace_id:
        ws = _require_accessible_workspace(workspace_id, current_user)
        if ws.get("local_path"):
            extra_roots.add(Path(ws["local_path"]).expanduser().resolve())
    extra_roots.add(Path(_default_project_path()).resolve())

    allowed_roots = get_allowed_workspace_roots(extra_roots, include_registered=False)
    if not allowed_roots:
        raise HTTPException(status_code=400, detail="No allowed workspace roots configured")

    for root in allowed_roots:
        try:
            resolved.relative_to(root)
            return resolved  # inside this root – OK
        except ValueError:
            continue

    raise HTTPException(
        status_code=403,
        detail=f"File path is outside all allowed workspace roots: {file_path}",
    )


@router.get("/read-file")
async def read_workspace_file(
    file_path: str,
    workspace_id: str | None = None,
    project_path: str | None = None,
    current_user: TokenPayload = Depends(get_workspace_user),
):
    """Read a text file from the local workspace and return its content."""
    resolved = _validate_file_path_in_workspace(file_path, workspace_id, project_path, current_user)
    if not resolved.exists():
        raise HTTPException(status_code=404, detail="File not found")
    if not resolved.is_file():
        raise HTTPException(status_code=400, detail="Path is not a file")

    try:
        content = resolved.read_text(encoding="utf-8", errors="replace")
    except Exception as exc:
        logger.error("Failed to read workspace file %s: %s", resolved, exc)
        raise HTTPException(status_code=500, detail=f"Failed to read file: {exc}") from exc

    return {"path": str(resolved), "content": content}


@router.post("/write-file")
async def write_workspace_file(
    data: FileWriteRequest,
    current_user: TokenPayload = Depends(get_workspace_user),
):
    """Write text content to a file in the local workspace (creates the file if absent)."""
    resolved = _validate_file_path_in_workspace(
        data.file_path,
        data.workspace_id,
        data.project_path,
        current_user,
    )
    if resolved.is_dir():
        raise HTTPException(status_code=400, detail="Path is a directory, not a file")

    try:
        resolved.parent.mkdir(parents=True, exist_ok=True)
        resolved.write_text(data.content, encoding="utf-8")
    except Exception as exc:
        logger.error("Failed to write workspace file %s: %s", resolved, exc)
        raise HTTPException(status_code=500, detail=f"Failed to write file: {exc}") from exc

    logger.info("Workspace file written: %s", resolved)
    context_refresh = None
    try:
        from context.service import get_context_service
        context_refresh = get_context_service().refresh_file(data.project_path, str(resolved))
    except Exception as exc:
        logger.warning("Failed to refresh context index for %s: %s", resolved, exc)
    return {"status": "saved", "path": str(resolved), "context_refresh": context_refresh}
