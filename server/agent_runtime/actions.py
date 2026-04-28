"""Workflow action proposals and approval-gated execution."""

from __future__ import annotations

import json
import subprocess
import time
import shutil
from pathlib import Path
from typing import Any

from fastapi import HTTPException
from core.config import settings


COMMAND_ALLOWLIST = (
    ("npm", "run", "typecheck"),
    ("npm", "test"),
    ("python", "-m", "pytest"),
    ("python", "-m", "py_compile"),
)


class WorkflowActionService:
    def __init__(self, repository: Any):
        self.repository = repository

    def extract_from_output(self, workflow_id: str, step_id: str, output: Any) -> list[dict[str, Any]]:
        artifacts = getattr(output, "artifacts", []) or []
        proposals: list[dict[str, Any]] = []
        for artifact in artifacts:
            if not isinstance(artifact, dict):
                continue
            action_type = artifact.get("action_type") or artifact.get("type") or artifact.get("kind")
            if action_type not in {"patch", "command"}:
                continue
            title = artifact.get("title") or ("文件补丁建议" if action_type == "patch" else "命令执行建议")
            description = artifact.get("description") or artifact.get("summary") or ""
            payload = artifact.get("payload") if isinstance(artifact.get("payload"), dict) else {
                key: value
                for key, value in artifact.items()
                if key not in {"type", "kind", "action_type", "title", "description", "summary"}
            }
            proposals.append(
                self.repository.add_action_proposal(
                    workflow_id=workflow_id,
                    step_id=step_id,
                    action_type=action_type,
                    title=title,
                    description=description,
                    payload=payload,
                )
            )
        return proposals

    def approve(self, action_id: str) -> dict[str, Any]:
        action = self._get_action(action_id)
        if action["status"] not in {"pending_approval", "rejected"}:
            return action
        approved = self.repository.update_action_status(action_id, "approved", approved_at=self._now())
        self.repository.add_event(approved["workflow_id"], approved.get("step_id"), "action_approved", "user", f"动作已审批：{approved['title']}", {"action_id": action_id})
        return approved

    def reject(self, action_id: str) -> dict[str, Any]:
        action = self._get_action(action_id)
        rejected = self.repository.update_action_status(action_id, "rejected", rejected_at=self._now())
        self.repository.add_event(action["workflow_id"], action.get("step_id"), "action_rejected", "user", f"动作已拒绝：{action['title']}", {"action_id": action_id})
        return rejected

    def execute(self, action_id: str) -> dict[str, Any]:
        action = self._get_action(action_id)
        if action["status"] != "approved":
            raise HTTPException(status_code=400, detail="Action must be approved before execution")
        project = self.repository.get_project(action["workflow_id"])
        if not project:
            raise HTTPException(status_code=404, detail="Workflow not found")

        start = time.perf_counter()
        try:
            if action["action_type"] == "patch":
                result = self._execute_patch(project, action)
            elif action["action_type"] == "command":
                result = self._execute_command(project, action)
            else:
                raise HTTPException(status_code=400, detail="Unsupported action type")
            duration_ms = int((time.perf_counter() - start) * 1000)
            execution = self.repository.add_action_execution(action_id, action["workflow_id"], duration_ms=duration_ms, **result)
            next_status = "executed" if result.get("status") == "completed" else "failed"
            self.repository.update_action_status(action_id, next_status, executed_at=self._now())
            self.repository.add_event(
                action["workflow_id"],
                action.get("step_id"),
                "action_executed" if next_status == "executed" else "action_failed",
                "system",
                f"动作已执行：{action['title']}" if next_status == "executed" else f"动作执行失败：{action['title']}",
                {"action_id": action_id, "execution": execution},
            )
            return self.repository.get_action_proposal(action_id) or action
        except HTTPException:
            raise
        except Exception as exc:
            duration_ms = int((time.perf_counter() - start) * 1000)
            execution = self.repository.add_action_execution(action_id, action["workflow_id"], "failed", duration_ms=duration_ms, error=str(exc))
            self.repository.update_action_status(action_id, "failed")
            self.repository.add_event(action["workflow_id"], action.get("step_id"), "action_failed", "system", f"动作执行失败：{exc}", {"action_id": action_id, "execution": execution})
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    def _execute_patch(self, project: dict[str, Any], action: dict[str, Any]) -> dict[str, Any]:
        payload = action.get("payload") or {}
        files = payload.get("files") or payload.get("file_changes") or []
        if not isinstance(files, list) or not files:
            raise HTTPException(status_code=400, detail="Patch action requires files/file_changes")
        root = self._allowed_root(project)
        written: list[str] = []
        for item in files:
            if not isinstance(item, dict):
                continue
            relative_path = item.get("path") or item.get("file_path")
            content = item.get("content")
            if not relative_path or content is None:
                raise HTTPException(status_code=400, detail="Each patch file requires path and content")
            target = (root / relative_path).resolve()
            if not (target == root or target.is_relative_to(root)):
                raise HTTPException(status_code=400, detail="Patch target must stay inside workflow project path")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(str(content), encoding="utf-8")
            written.append(str(target))
        return {"status": "completed", "stdout": "\n".join(written), "stderr": "", "exit_code": 0}

    def _execute_command(self, project: dict[str, Any], action: dict[str, Any]) -> dict[str, Any]:
        payload = action.get("payload") or {}
        command = payload.get("command")
        args = command if isinstance(command, list) else str(command or "").split()
        if not args:
            raise HTTPException(status_code=400, detail="Command action requires command")
        if not self._command_allowed(args):
            raise HTTPException(status_code=400, detail="Command is not in workflow allowlist")
        root = self._command_root(project, args)
        executable = shutil.which(args[0])
        resolved_args = [executable or args[0], *args[1:]]
        completed = subprocess.run(
            resolved_args,
            cwd=str(root),
            text=True,
            capture_output=True,
            timeout=int(payload.get("timeout_seconds") or 120),
            shell=False,
        )
        return {
            "status": "completed" if completed.returncode == 0 else "failed",
            "stdout": completed.stdout,
            "stderr": completed.stderr,
            "exit_code": completed.returncode,
        }

    def _allowed_root(self, project: dict[str, Any]) -> Path:
        raw = project.get("project_path") or Path.cwd()
        root = Path(raw).resolve()
        allowed_roots = self._workspace_roots()
        if not any(root == allowed or root.is_relative_to(allowed) for allowed in allowed_roots):
            raise HTTPException(status_code=400, detail="Workflow project path is outside the current workspace")
        root.mkdir(parents=True, exist_ok=True)
        return root

    def _command_allowed(self, args: list[str]) -> bool:
        lowered = tuple(self._normalize_executable(item) if index == 0 else item.lower() for index, item in enumerate(args))
        return any(lowered[: len(prefix)] == prefix for prefix in COMMAND_ALLOWLIST)

    def _command_root(self, project: dict[str, Any], args: list[str]) -> Path:
        root = self._allowed_root(project)
        command = self._normalize_executable(args[0]) if args else ""
        if command == "npm" and len(args) >= 3 and args[1] == "run":
            script = args[2]
            if self._package_has_script(root, script):
                return root
            for candidate in (root / "client", self._workspace_root() / "client"):
                if self._package_has_script(candidate, script):
                    return candidate.resolve()
        return root

    def _package_has_script(self, root: Path, script: str) -> bool:
        package_json = root / "package.json"
        if not package_json.exists():
            return False
        try:
            data = json.loads(package_json.read_text(encoding="utf-8"))
        except Exception:
            return False
        return script in (data.get("scripts") or {})

    def _normalize_executable(self, value: str) -> str:
        name = Path(value).name.lower()
        for suffix in (".cmd", ".exe", ".bat"):
            if name.endswith(suffix):
                return name[: -len(suffix)]
        return name

    def _workspace_root(self) -> Path:
        base_dir = settings.base_dir.resolve()
        return base_dir.parent if base_dir.name == "server" else base_dir

    def _workspace_roots(self) -> set[Path]:
        cwd = Path.cwd().resolve()
        base_dir = settings.base_dir.resolve()
        workspace = self._workspace_root()
        roots = {cwd, base_dir, workspace}
        client_dir = workspace / "client"
        if client_dir.exists():
            roots.add(client_dir.resolve())
        return roots

    def _get_action(self, action_id: str) -> dict[str, Any]:
        action = self.repository.get_action_proposal(action_id)
        if not action:
            raise HTTPException(status_code=404, detail="Workflow action not found")
        return action

    def _now(self) -> str:
        from datetime import datetime

        return datetime.now().isoformat()
