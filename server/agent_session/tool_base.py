from __future__ import annotations

from pathlib import Path
from typing import Any

from core.config import settings
from workspace.local_paths import get_allowed_workspace_roots

from .tool_types import ToolResult


class ToolBaseMixin:
    def _root(self, context: dict[str, Any]) -> Path:
        raw = context.get("project_path") or self._workspace_root()
        root = Path(raw).resolve()
        if not any(root == allowed or root.is_relative_to(allowed) for allowed in self._workspace_roots()):
            raise ValueError("project_path must stay inside workspace")
        return root

    def _safe_path(self, root: Path, raw_path: str) -> Path:
        target = Path(raw_path)
        if not target.is_absolute():
            target = root / target
        target = target.resolve()
        if not (target == root or target.is_relative_to(root)):
            raise ValueError("path must stay inside project path")
        return target

    def _workspace_root(self) -> Path:
        base_dir = settings.base_dir.resolve()
        return base_dir.parent if base_dir.name == "server" else base_dir

    def _workspace_roots(self) -> set[Path]:
        return get_allowed_workspace_roots({Path.cwd().resolve(), settings.base_dir.resolve(), self._workspace_root()})

    def _normalize_tool_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        normalized = dict(payload)
        if "changed_files" in normalized and "artifacts" not in normalized:
            normalized["artifacts"] = {"changed_files": normalized.get("changed_files") or []}
        if "patch_summaries" in normalized and "details" not in normalized:
            normalized["details"] = normalized.get("patch_summaries") or []
        if "failure_summary" in normalized and "next_action" not in normalized:
            normalized["next_action"] = normalized.get("failure_summary") or ""
        return normalized
