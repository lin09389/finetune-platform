"""Storage adapters that expose only safe Workspace portability references.

These adapters deliberately return plain, bounded dictionaries.  The manifest
domain owns validation and turns them into its public Pydantic DTOs; keeping the
SQLite rows out of that domain prevents its external format becoming coupled to
the Agent Session schema.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import PurePosixPath
from typing import Any, Protocol

from agent_session.execution_plan import repair_execution_plan
from agent_session.repository import AgentSessionRepository

_UNSAFE_KEYS = frozenset(
    {
        "approval",
        "approvals",
        "approval_payload",
        "checkpoint",
        "deepagents_checkpoint",
        "deepagents_thread_id",
        "prompt",
        "raw_prompt",
        "terminal_output",
        "tool_arguments",
        "tool_output",
        "session_tool_trust",
        "provider_credentials",
        "api_key",
        "authorization",
        "diff",
        "full_diff",
    }
)
_TERMINAL_STATUSES = frozenset({"completed", "failed", "cancelled", "interrupted"})
_SAFE_SUMMARY_KEYS = ("summary", "completion_summary", "result_summary", "final_summary")


class TaskContextProvider(Protocol):
    """Supplies validated-safe input for the manifest service."""

    def list_task_contexts(self, workspace_id: str, owner_id: str, limit: int = 100) -> list[dict[str, Any]]: ...


class ResourceReferenceProvider(Protocol):
    """Supplies reference-only resources for a Workspace export."""

    def list_resource_references(self, workspace: dict[str, Any], owner_id: str) -> list[dict[str, Any]]: ...


def _bounded_text(value: Any, limit: int = 2_000) -> str | None:
    if not isinstance(value, str):
        return None
    clean = value.strip()
    return clean[:limit] if clean else None


def _safe_relative_path(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.replace("\\", "/").strip().lstrip("/")
    path = PurePosixPath(normalized)
    if not normalized or path.is_absolute() or ".." in path.parts:
        return None
    return normalized[:512]


def _fingerprint(session_id: str) -> str:
    # The source id is intentionally irreversible outside the originating DB.
    return hashlib.sha256(session_id.encode("utf-8")).hexdigest()


def _safe_changed_files(raw: Any) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for item in raw if isinstance(raw, list) else []:
        if isinstance(item, str):
            path, additions, deletions = _safe_relative_path(item), None, None
        elif isinstance(item, dict):
            path = _safe_relative_path(item.get("path") or item.get("file") or item.get("relative_path"))
            additions, deletions = item.get("additions"), item.get("deletions")
        else:
            continue
        if path:
            results.append(
                {
                    "path": path,
                    "additions": int(additions) if isinstance(additions, int) and additions >= 0 else None,
                    "deletions": int(deletions) if isinstance(deletions, int) and deletions >= 0 else None,
                }
            )
        if len(results) >= 100:
            break
    return results


def _safe_plan(raw: Any, agent_id: str) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return {}
    plan, _ = repair_execution_plan(raw, default_agent_id=agent_id)
    # Plans may carry runtime IDs through future schema additions; retain the
    # structural plan but remove all authority-bearing/runtime fields.
    return _remove_unsafe(plan, depth=0) if isinstance(plan, dict) else {}


def _remove_unsafe(value: Any, *, depth: int) -> Any:
    if depth > 8:
        return None
    if isinstance(value, dict):
        return {
            str(key)[:100]: _remove_unsafe(item, depth=depth + 1)
            for key, item in value.items()
            if str(key).lower() not in _UNSAFE_KEYS
        }
    if isinstance(value, list):
        return [_remove_unsafe(item, depth=depth + 1) for item in value[:100]]
    if isinstance(value, str):
        return value[:2_000]
    return value if value is None or isinstance(value, (int, float, bool)) else None


class AgentSessionTaskContextProvider:
    """Projects Agent Sessions into non-runnable continuation context."""

    def __init__(self, repository: AgentSessionRepository) -> None:
        self.repository = repository

    def list_task_contexts(self, workspace_id: str, owner_id: str, limit: int = 100) -> list[dict[str, Any]]:
        contexts: list[dict[str, Any]] = []
        for session in self.repository.list_sessions_for_workspace(workspace_id, owner_id, limit):
            metadata = dict(session.get("metadata") or {})
            summary = next((_bounded_text(metadata.get(key)) for key in _SAFE_SUMMARY_KEYS if _bounded_text(metadata.get(key))), None)
            status = str(session.get("status") or "unknown")
            contexts.append(
                {
                    "source_task_fingerprint": _fingerprint(str(session.get("id") or "")),
                    "title": _bounded_text(session.get("title"), 200) or "Agent task",
                    "task_mode": metadata.get("task_mode") if metadata.get("task_mode") in {"build", "train", "hybrid"} else "build",
                    "status": status if status in _TERMINAL_STATUSES else "interrupted",
                    "execution_plan": _safe_plan(metadata.get("execution_plan"), str(session.get("agent_id") or "build")),
                    "completion_summary": summary,
                    "changed_files": _safe_changed_files(metadata.get("changed_files")),
                    "verification": _remove_unsafe(metadata.get("verification") or {}, depth=0),
                    "resource_references": _remove_unsafe(metadata.get("portable_resource_references") or [], depth=0),
                    "updated_at": str(session.get("updated_at") or ""),
                }
            )
        return contexts


class LocalWorkspaceResourceReferenceProvider:
    """Minimal local-first resource adapter; resource managers may extend it."""

    def list_resource_references(self, workspace: dict[str, Any], owner_id: str) -> list[dict[str, Any]]:
        del owner_id
        name = _bounded_text(workspace.get("name"), 200) or "Workspace"
        # Never copy local_path into a portable reference.  Its basename is
        # useful for rebinding while revealing no absolute-machine location.
        path_value = workspace.get("local_path")
        basename = ""
        if isinstance(path_value, str):
            basename = path_value.replace("\\", "/").rstrip("/").split("/")[-1]
        return [{"kind": "project", "display_name": basename or name, "git_head": None, "remote_hint": None}]


__all__ = [
    "AgentSessionTaskContextProvider",
    "LocalWorkspaceResourceReferenceProvider",
    "ResourceReferenceProvider",
    "TaskContextProvider",
]
