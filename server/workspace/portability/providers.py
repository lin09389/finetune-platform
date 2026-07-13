"""Adapters that project local Workspace state into the public v1 contract."""

from __future__ import annotations

import hashlib
import re
from datetime import UTC, datetime
from pathlib import PurePosixPath
from typing import Any

from agent_session.execution_plan import repair_execution_plan
from agent_session.repository import AgentSessionRepository

from .schemas import (
    PortableChangedFile,
    PortablePlanStep,
    PortableProjectReference,
    PortableTaskContext,
    PortableTaskResourceReference,
    PortableVerification,
    ProducerInfo,
    WorkspaceIdentity,
    WorkspaceManifestV1,
)

_WINDOWS_ABSOLUTE_RE = re.compile(r"^[A-Za-z]:[\\/]")
_TERMINAL_STATUS = {
    "completed": "completed",
    "failed": "failed",
    "cancelled": "cancelled",
    "interrupted": "stopped",
    "stopped": "stopped",
}
_PLAN_STATUS = {
    "pending": "pending",
    "running": "in_progress",
    "completed": "completed",
    "blocked": "blocked",
    "failed": "blocked",
    "interrupted": "blocked",
    "waiting_approval": "blocked",
    "waiting_permission": "blocked",
}
_VERIFICATION_CATEGORIES = {"build", "test", "lint", "train", "evaluation", "manual"}
_VERIFICATION_STATUSES = {"passed", "failed", "skipped", "not_run"}
_SAFE_SUMMARY_KEYS = ("summary", "completion_summary", "result_summary", "final_summary")


def _bounded_text(value: Any, limit: int = 2_000) -> str | None:
    if not isinstance(value, str):
        return None
    clean = value.strip()
    return clean[:limit] if clean else None


def _safe_relative_path(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    raw = value.strip()
    if not raw or raw.startswith(("/", "\\")) or _WINDOWS_ABSOLUTE_RE.match(raw):
        return None
    normalized = raw.replace("\\", "/")
    path = PurePosixPath(normalized)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        return None
    return normalized[:1_000]


def _fingerprint(session_id: str) -> str:
    return hashlib.sha256(session_id.encode("utf-8")).hexdigest()


def _portable_workspace_id(workspace_id: str) -> str:
    return "pws_" + hashlib.sha256(workspace_id.encode("utf-8")).hexdigest()[:32]


def _safe_changed_files(raw: Any) -> list[PortableChangedFile]:
    results: list[PortableChangedFile] = []
    for item in raw if isinstance(raw, list) else []:
        if isinstance(item, str):
            path, additions, deletions = _safe_relative_path(item), 0, 0
        elif isinstance(item, dict):
            path = _safe_relative_path(item.get("path") or item.get("file") or item.get("relative_path"))
            additions = item.get("additions") if isinstance(item.get("additions"), int) else 0
            deletions = item.get("deletions") if isinstance(item.get("deletions"), int) else 0
        else:
            continue
        if path:
            results.append(PortableChangedFile(path=path, additions=max(0, additions), deletions=max(0, deletions)))
        if len(results) >= 500:
            break
    return results


def _safe_plan(raw: Any, agent_id: str) -> list[PortablePlanStep]:
    if not isinstance(raw, dict):
        return []
    plan, _ = repair_execution_plan(raw, default_agent_id=agent_id)
    steps: list[PortablePlanStep] = []
    for node in plan.get("nodes") or []:
        if not isinstance(node, dict):
            continue
        title = _bounded_text(node.get("title") or node.get("id"), 500)
        if not title:
            continue
        steps.append(
            PortablePlanStep(
                title=title,
                status=_PLAN_STATUS.get(str(node.get("status") or "pending"), "pending"),
                summary=_bounded_text(node.get("description") or node.get("summary"), 2_000),
            )
        )
        if len(steps) >= 100:
            break
    return steps


def _safe_verifications(raw: Any) -> list[PortableVerification]:
    items = raw if isinstance(raw, list) else [raw] if isinstance(raw, dict) else []
    results: list[PortableVerification] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        category = str(item.get("category") or item.get("kind") or "manual")
        status = str(item.get("status") or ("passed" if item.get("success") is True else "failed" if item.get("success") is False else "not_run"))
        results.append(
            PortableVerification(
                category=category if category in _VERIFICATION_CATEGORIES else "manual",
                status=status if status in _VERIFICATION_STATUSES else "not_run",
                summary=_bounded_text(item.get("summary") or item.get("message"), 2_000),
            )
        )
        if len(results) >= 100:
            break
    return results


def _safe_resource_references(raw: Any) -> list[PortableTaskResourceReference]:
    results: list[PortableTaskResourceReference] = []
    for item in raw if isinstance(raw, list) else []:
        if not isinstance(item, dict):
            continue
        kind = str(item.get("kind") or "")
        reference_id = _bounded_text(item.get("reference_id") or item.get("id"), 200)
        display_name = _bounded_text(item.get("display_name") or item.get("name"), 200)
        if kind in {"artifact", "training_run"} and reference_id and display_name:
            results.append(PortableTaskResourceReference(kind=kind, reference_id=reference_id, display_name=display_name))
        if len(results) >= 100:
            break
    return results


def _as_utc(value: Any) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return datetime.now(UTC)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


class AgentSessionTaskContextProvider:
    """Project terminal Agent Sessions into authority-free task summaries."""

    def __init__(self, repository: AgentSessionRepository) -> None:
        self.repository = repository

    def list_task_contexts(self, workspace_id: str, owner_id: str, limit: int = 100) -> list[PortableTaskContext]:
        contexts: list[PortableTaskContext] = []
        for session in self.repository.list_sessions_for_workspace(workspace_id, owner_id, limit):
            metadata = dict(session.get("metadata") or {})
            summary = next(
                (_bounded_text(metadata.get(key), 4_000) for key in _SAFE_SUMMARY_KEYS if _bounded_text(metadata.get(key), 4_000)),
                None,
            )
            contexts.append(
                PortableTaskContext(
                    source_task_fingerprint=_fingerprint(str(session.get("id") or "")),
                    title=_bounded_text(session.get("title"), 300) or "Agent task",
                    mode=metadata.get("task_mode") if metadata.get("task_mode") in {"build", "train", "hybrid"} else "build",
                    status=_TERMINAL_STATUS.get(str(session.get("status") or ""), "stopped"),
                    execution_plan=_safe_plan(metadata.get("execution_plan"), str(session.get("agent_id") or "build")),
                    summary=summary,
                    changed_files=_safe_changed_files(metadata.get("changed_files")),
                    verifications=_safe_verifications(metadata.get("verification") or metadata.get("verifications")),
                    resource_references=_safe_resource_references(metadata.get("portable_resource_references")),
                    updated_at=_as_utc(session.get("updated_at")),
                )
            )
        return contexts


class LocalWorkspaceManifestProvider:
    """Bind one already-authorized local Workspace to the external manifest DTO."""

    def __init__(self, workspace: dict[str, Any], sessions: AgentSessionRepository | None = None) -> None:
        self.workspace = dict(workspace)
        self.tasks = AgentSessionTaskContextProvider(sessions or AgentSessionRepository())

    def build_manifest(self, *, workspace_id: str, owner_id: str) -> WorkspaceManifestV1:
        if str(self.workspace.get("id") or "") != workspace_id:
            raise ValueError("Workspace identity changed during export")
        name = _bounded_text(self.workspace.get("name"), 200) or "Workspace"
        local_path = str(self.workspace.get("local_path") or "").replace("\\", "/").rstrip("/")
        basename = local_path.rsplit("/", 1)[-1] if local_path else name
        return WorkspaceManifestV1(
            portable_workspace_id=_portable_workspace_id(workspace_id),
            exported_at=datetime.now(UTC),
            producer=ProducerInfo(name="finetune-platform", version="2.1.0"),
            workspace=WorkspaceIdentity(name=name, description=_bounded_text(self.workspace.get("description"), 1_000)),
            project=PortableProjectReference(display_name=_bounded_text(basename, 200) or name),
            resources=[],
            task_contexts=self.tasks.list_task_contexts(workspace_id, owner_id),
        )


__all__ = ["AgentSessionTaskContextProvider", "LocalWorkspaceManifestProvider"]
