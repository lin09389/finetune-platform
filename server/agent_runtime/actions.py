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

from .command_policy import command_allowed, normalize_command, normalize_executable, summarize_failure
from .execution_state import APPLYING_PATCH, COMPLETED, FAILED, VERIFYING, set_workflow_state
from .patch_engine import SafePatchEngine


class WorkflowActionService:
    def __init__(self, repository: Any):
        self.repository = repository

    def extract_from_output(self, workflow_id: str, step_id: str, output: Any) -> list[dict[str, Any]]:
        artifacts = getattr(output, "artifacts", []) or []
        proposals: list[dict[str, Any]] = []
        project = self.repository.get_project(workflow_id) if self.repository else None
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
            action = self.repository.add_action_proposal(
                workflow_id=workflow_id,
                step_id=step_id,
                action_type=action_type,
                title=title,
                description=description,
                payload=payload,
            )
            policy = self._evaluate_policy(project or {}, action_type, payload)
            action_payload = dict(action.get("payload") or {})
            action_payload["_execution_mode"] = policy["execution_mode"]
            action_payload["_policy_reason"] = policy["policy_reason"]
            action = self.repository.update_action_status(action["id"], action["status"], payload=action_payload)
            self.repository.add_event(
                workflow_id,
                step_id,
                "auto_action_executed" if policy["execution_mode"] == "auto" else "auto_action_blocked",
                "system",
                policy["policy_reason"],
                {"action_id": action["id"], "action_type": action_type, "execution_mode": policy["execution_mode"]},
            )
            if policy["execution_mode"] == "auto":
                action = self.repository.update_action_status(action["id"], "approved", approved_at=self._now())
                action = self.execute(action["id"])
                payload = dict(action.get("payload") or {})
                payload["_auto_executed_at"] = action.get("executed_at")
                action = self.repository.update_action_status(action["id"], action["status"], payload=payload)
            proposals.append(action)
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
        if action["status"] == "executed":
            return action
        if action["status"] != "approved":
            raise HTTPException(status_code=400, detail="Action must be approved before execution")
        project = self.repository.get_project(action["workflow_id"])
        if not project:
            raise HTTPException(status_code=404, detail="Workflow not found")

        start = time.perf_counter()
        try:
            if action["action_type"] == "patch":
                set_workflow_state(self.repository, project, APPLYING_PATCH, f"正在应用补丁：{action['title']}", step_id=action.get("step_id"), actor="agent")
            elif action["action_type"] == "command":
                set_workflow_state(self.repository, project, VERIFYING, f"正在执行验证命令：{action['title']}", step_id=action.get("step_id"), actor="agent")
            if action["action_type"] == "patch":
                result = self._execute_patch(project, action)
            elif action["action_type"] == "command":
                result = self._execute_command(project, action)
            else:
                raise HTTPException(status_code=400, detail="Unsupported action type")
            duration_ms = int((time.perf_counter() - start) * 1000)
            execution_result = {
                key: result.get(key)
                for key in ("status", "stdout", "stderr", "exit_code", "error")
                if key in result
            }
            execution = self.repository.add_action_execution(action_id, action["workflow_id"], duration_ms=duration_ms, **execution_result)
            next_status = "executed" if result.get("status") == "completed" else "failed"
            self._merge_action_payload(
                action_id,
                action,
                {
                    "_changed_files": result.get("changed_files") or [],
                    "_failure_summary": result.get("failure_summary") or "",
                    "_execution_state": "completed" if next_status == "executed" else FAILED,
                    "_applied_hunks": result.get("applied_hunks"),
                },
            )
            self.repository.update_action_status(action_id, next_status, executed_at=self._now())
            if next_status == "executed":
                if action["action_type"] == "patch":
                    set_workflow_state(
                        self.repository,
                        project,
                        VERIFYING,
                        f"补丁已应用：{action['title']}，可以继续执行验证命令。",
                        step_id=action.get("step_id"),
                        actor="agent",
                    )
                elif action["action_type"] == "command":
                    set_workflow_state(
                        self.repository,
                        project,
                        COMPLETED,
                        f"验证命令已通过：{action['title']}",
                        step_id=action.get("step_id"),
                        actor="agent",
                    )
            else:
                set_workflow_state(
                    self.repository,
                    project,
                    FAILED,
                    result.get("failure_summary") or f"动作执行失败：{action['title']}",
                    step_id=action.get("step_id"),
                    actor="agent",
                )
            self.repository.add_event(
                action["workflow_id"],
                action.get("step_id"),
                "action_executed" if next_status == "executed" else "action_failed",
                "system",
                f"动作已执行：{action['title']}" if next_status == "executed" else f"动作执行失败：{action['title']}",
                {"action_id": action_id, "execution": execution},
            )
            return self.repository.get_action_proposal(action_id) or action
        except HTTPException as exc:
            duration_ms = int((time.perf_counter() - start) * 1000)
            detail = str(exc.detail)
            execution = self.repository.add_action_execution(action_id, action["workflow_id"], "failed", duration_ms=duration_ms, error=detail)
            self._merge_action_payload(action_id, action, {"_failure_summary": detail, "_execution_state": FAILED})
            self.repository.update_action_status(action_id, "failed")
            self.repository.add_event(action["workflow_id"], action.get("step_id"), "action_failed", "system", f"动作执行失败：{detail}", {"action_id": action_id, "execution": execution})
            set_workflow_state(self.repository, project, FAILED, f"动作执行失败：{detail}", step_id=action.get("step_id"), actor="agent")
            raise
        except Exception as exc:
            duration_ms = int((time.perf_counter() - start) * 1000)
            execution = self.repository.add_action_execution(action_id, action["workflow_id"], "failed", duration_ms=duration_ms, error=str(exc))
            self._merge_action_payload(action_id, action, {"_failure_summary": str(exc), "_execution_state": FAILED})
            self.repository.update_action_status(action_id, "failed")
            self.repository.add_event(action["workflow_id"], action.get("step_id"), "action_failed", "system", f"动作执行失败：{exc}", {"action_id": action_id, "execution": execution})
            set_workflow_state(self.repository, project, FAILED, f"动作执行失败：{exc}", step_id=action.get("step_id"), actor="agent")
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    def _execute_patch(self, project: dict[str, Any], action: dict[str, Any]) -> dict[str, Any]:
        payload = action.get("payload") or {}
        root = self._allowed_root(project)
        result = SafePatchEngine(root).apply_payload(payload)
        return {
            "status": "completed",
            "stdout": result.stdout,
            "stderr": "",
            "exit_code": 0,
            "changed_files": result.changed_files,
            "applied_hunks": len(result.summaries),
            "failure_summary": "",
        }

    def _evaluate_policy(self, project: dict[str, Any], action_type: str, payload: dict[str, Any]) -> dict[str, str]:
        if action_type == "command":
            command = payload.get("command")
            try:
                args = normalize_command(command)
            except HTTPException as exc:
                return {"execution_mode": "approval_required", "policy_reason": str(exc.detail)}
            if args and command_allowed(args):
                return {"execution_mode": "auto", "policy_reason": "白名单短命令，已自动执行"}
            return {"execution_mode": "approval_required", "policy_reason": "命令不在自动执行策略内，需人工审批"}

        if action_type == "patch":
            if payload.get("format") == "unified_diff" or payload.get("diff"):
                return {"execution_mode": "approval_required", "policy_reason": "diff 补丁需人工确认后执行"}
            files = payload.get("files") or payload.get("file_changes") or []
            if not isinstance(files, list) or not files or len(files) > 3:
                return {"execution_mode": "approval_required", "policy_reason": "补丁文件数量超出自动执行策略，需人工审批"}
            safe_prefixes = ("tmp/", "tmp\\", "tests/", "tests\\", "server/tests/", "client/src/test/")
            source_policy = self._evaluate_source_patch_policy(project, files)
            used_source_policy = False
            for item in files:
                if not isinstance(item, dict):
                    return {"execution_mode": "approval_required", "policy_reason": "补丁格式异常，需人工审批"}
                relative_path = str(item.get("path") or item.get("file_path") or "")
                content = str(item.get("content") or "")
                if not relative_path or len(content) > 20_000:
                    return {"execution_mode": "approval_required", "policy_reason": "补丁内容超出自动执行策略，需人工审批"}
                if not relative_path.startswith(safe_prefixes):
                    if source_policy["execution_mode"] == "auto":
                        used_source_policy = True
                        continue
                    return source_policy
            if used_source_policy:
                return source_policy
            return {"execution_mode": "auto", "policy_reason": "安全小补丁，已自动执行"}

        return {"execution_mode": "approval_required", "policy_reason": "未知动作类型，需人工审批"}

    def _evaluate_source_patch_policy(self, project: dict[str, Any], files: list[Any]) -> dict[str, str]:
        if not files or len(files) > 2:
            return {"execution_mode": "approval_required", "policy_reason": "源码自动修改最多允许 2 个文件"}
        allowed_suffixes = {".py", ".ts", ".tsx", ".css", ".md"}
        sensitive_names = {
            ".env",
            ".env.local",
            "package.json",
            "package-lock.json",
            "pnpm-lock.yaml",
            "yarn.lock",
            "requirements.txt",
            "pyproject.toml",
            "alembic.ini",
            "docker-compose.yml",
            "Dockerfile",
        }
        sensitive_parts = {".git", "migrations", "secrets", "keys"}
        read_paths = self._context_touched_paths(project.get("id") or project.get("workflow_id"))
        total_lines = 0
        for item in files:
            if not isinstance(item, dict):
                return {"execution_mode": "approval_required", "policy_reason": "源码补丁格式异常，需人工审批"}
            relative_path = str(item.get("path") or item.get("file_path") or "").replace("\\", "/")
            content = str(item.get("content") or "")
            if not relative_path:
                return {"execution_mode": "approval_required", "policy_reason": "源码补丁缺少路径，需人工审批"}
            path = Path(relative_path)
            if path.is_absolute() or ".." in path.parts:
                return {"execution_mode": "approval_required", "policy_reason": "源码补丁路径不安全，需人工审批"}
            if path.name in sensitive_names or any(part in sensitive_parts for part in path.parts):
                return {"execution_mode": "approval_required", "policy_reason": "源码补丁涉及敏感文件或目录，需人工审批"}
            if path.suffix.lower() not in allowed_suffixes:
                return {"execution_mode": "approval_required", "policy_reason": "源码补丁文件类型不在自动执行策略内"}
            line_count = len(content.splitlines())
            total_lines += line_count
            if line_count > 80:
                return {"execution_mode": "approval_required", "policy_reason": "单文件源码补丁超过 80 行，需人工审批"}
            if relative_path not in read_paths:
                return {"execution_mode": "approval_required", "policy_reason": "源码文件未在同一轮被读取或搜索命中，需人工审批"}
        if total_lines > 160:
            return {"execution_mode": "approval_required", "policy_reason": "源码补丁总行数超过 160 行，需人工审批"}
        return {"execution_mode": "auto", "policy_reason": "低风险源码小改，已按策略自动执行"}

    def _context_touched_paths(self, workflow_id: str | None) -> set[str]:
        if not workflow_id:
            return set()
        touched: set[str] = set()
        try:
            calls = self.repository.list_tool_calls(workflow_id)
        except Exception:
            return touched
        for call in calls:
            if call.get("status") != "completed":
                continue
            payload = call.get("result_payload") or {}
            if call.get("tool_name") == "read_file" and payload.get("path"):
                touched.add(str(payload["path"]).replace("\\", "/"))
            if call.get("tool_name") == "search_code":
                for match in payload.get("matches") or []:
                    if isinstance(match, dict) and match.get("path"):
                        touched.add(str(match["path"]).replace("\\", "/"))
        return touched

    def _execute_command(self, project: dict[str, Any], action: dict[str, Any]) -> dict[str, Any]:
        payload = action.get("payload") or {}
        command = payload.get("command")
        args = normalize_command(command)
        if not command_allowed(args):
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
            "changed_files": [],
            "failure_summary": summarize_failure(completed.stdout, completed.stderr) if completed.returncode != 0 else "",
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
        return command_allowed(args)

    def _command_root(self, project: dict[str, Any], args: list[str]) -> Path:
        root = self._allowed_root(project)
        command = normalize_executable(args[0]) if args else ""
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
        return normalize_executable(value)

    def _merge_action_payload(self, action_id: str, action: dict[str, Any], updates: dict[str, Any]) -> dict[str, Any]:
        payload = dict(action.get("payload") or {})
        payload.update(updates)
        return self.repository.update_action_status(action_id, action.get("status", "approved"), payload=payload)

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
