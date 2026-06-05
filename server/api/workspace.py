"""Workspace management API with persisted metadata."""

from __future__ import annotations

import json
import logging
import uuid
import os
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from core.config import settings
from core.db_manager import run_sync
from rag.vector_store import get_vector_store
from workspace.local_paths import normalize_local_workspace_path, get_allowed_workspace_roots

logger = logging.getLogger(__name__)

router = APIRouter()

WORKSPACE_DATA_DIR = Path("data/workspaces")
WORKSPACE_DATA_DIR.mkdir(parents=True, exist_ok=True)
WORKSPACE_METADATA_FILE = WORKSPACE_DATA_DIR / "metadata.json"


def _load_workspace_store() -> dict[str, dict[str, Any]]:
    if not WORKSPACE_METADATA_FILE.exists():
        return {}

    try:
        with open(WORKSPACE_METADATA_FILE, encoding="utf-8") as handle:
            data = json.load(handle)
        if isinstance(data, dict):
            return {workspace_id: payload for workspace_id, payload in data.items() if isinstance(payload, dict)}
    except Exception as exc:
        logger.warning("Failed to load workspace metadata: %s", exc)

    return {}


def _save_workspace_store(workspaces: dict[str, dict[str, Any]]) -> None:
    with open(WORKSPACE_METADATA_FILE, "w", encoding="utf-8") as handle:
        json.dump(workspaces, handle, ensure_ascii=False, indent=2)


workspaces: dict[str, dict[str, Any]] = _load_workspace_store()
DEFAULT_WORKSPACE_ID = "current_project"


def _default_project_path() -> str:
    base_dir = settings.base_dir.resolve()
    workspace = base_dir.parent if base_dir.name == "server" else base_dir
    return str(workspace)


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
    vector_store = get_vector_store()
    collection_name = workspace.get("vector_collection_name", workspace["id"])

    try:
        stats = vector_store.get_collection_stats(collection_name)
        vector_count = stats.get("count", 0)
    except Exception:
        vector_count = 0

    workspace["vector_collection_name"] = collection_name
    workspace["vector_count"] = vector_count
    return Workspace(**workspace)


async def _refresh_workspace_counts_async(workspace: dict[str, Any]) -> Workspace:
    """Async-safe wrapper that offloads vector store I/O to a thread."""
    return await run_sync(_refresh_workspace_counts, workspace)


def _resolve_workspace_path(workspace_id: str | None = None, project_path: str | None = None) -> Path:
    if project_path and project_path.strip():
        try:
            return Path(normalize_local_workspace_path(project_path) or "").resolve()
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    if workspace_id:
        if workspace_id == DEFAULT_WORKSPACE_ID:
            return Path(_default_project_path()).resolve()
        workspace = _ensure_workspace_exists(workspace_id)
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
async def create_workspace(data: WorkspaceCreate):
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
    }

    def _create_collection():
        vector_store = get_vector_store()
        vector_store.get_or_create_collection(collection_name)

    await run_sync(_create_collection)

    workspaces[workspace_id] = workspace
    await run_sync(_persist_workspaces)

    logger.info("Workspace created: %s (%s)", workspace_id, data.name)
    return Workspace(**workspace)


@router.get("/workspaces", response_model=list[Workspace])
async def list_workspaces():
    """List workspaces."""
    result: list[Workspace] = []
    default_workspace = _default_workspace_payload()
    default_path = default_workspace["local_path"]
    has_default_path = False
    has_registered_default = False
    for workspace in workspaces.values():
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
async def list_workspaces_compat():
    """Compatibility endpoint for GET /workspace."""
    return await list_workspaces()


@router.get("/workspaces/{workspace_id}", response_model=Workspace)
async def get_workspace(workspace_id: str):
    """Get workspace details."""
    workspace = _ensure_workspace_exists(workspace_id)
    refreshed = await _refresh_workspace_counts_async(workspace)
    await run_sync(_persist_workspaces)
    return refreshed


@router.put("/workspaces/{workspace_id}", response_model=Workspace)
async def update_workspace(workspace_id: str, data: WorkspaceUpdate):
    """Update workspace metadata."""
    workspace = _ensure_workspace_exists(workspace_id)

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
async def delete_workspace(workspace_id: str):
    """Delete a workspace."""
    workspace = _ensure_workspace_exists(workspace_id)
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
async def get_workspace_stats(workspace_id: str):
    """Get workspace statistics."""
    workspace = _ensure_workspace_exists(workspace_id)
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
):
    """Return a shallow local file tree for the selected workspace."""
    root = _resolve_workspace_path(workspace_id=workspace_id, project_path=project_path)
    max_depth = max(1, min(max_depth, 6))
    limit = max(20, min(limit, 800))
    budget = {"remaining": limit}
    nodes = _build_tree(root, root, depth=0, max_depth=max_depth, budget=budget)
    return WorkspaceTreeResponse(root=str(root), nodes=nodes, truncated=budget["remaining"] <= 0)


@router.get("/browse-folder")
async def browse_folder(initial_path: str | None = None):
    """Open a native OS directory chooser dialog and return the selected path."""
    import platform
    import subprocess
    import os
    import queue
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


def _validate_file_path_in_workspace(file_path: str, workspace_id: str | None, project_path: str | None) -> Path:
    """Resolve the file path and assert it lives inside an allowed workspace root."""
    try:
        resolved = Path(file_path).expanduser().resolve()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid file path: {exc}") from exc

    # Build allowed roots: from project_path hint, from workspace metadata, from env
    extra_roots: set[Path] = set()
    if project_path:
        extra_roots.add(Path(project_path).expanduser().resolve())
    if workspace_id:
        ws = workspaces.get(workspace_id)
        if ws and ws.get("local_path"):
            extra_roots.add(Path(ws["local_path"]).expanduser().resolve())
    extra_roots.add(Path(_default_project_path()).resolve())

    allowed_roots = get_allowed_workspace_roots(extra_roots)
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
):
    """Read a text file from the local workspace and return its content."""
    resolved = _validate_file_path_in_workspace(file_path, workspace_id, project_path)
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
async def write_workspace_file(data: FileWriteRequest):
    """Write text content to a file in the local workspace (creates the file if absent)."""
    resolved = _validate_file_path_in_workspace(data.file_path, data.workspace_id, data.project_path)
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
