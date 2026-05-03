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

AUTONOMY_SAFE_AUTO = "safe_auto"
AUTONOMY_CONFIRM_ALL = "confirm_all"
AUTONOMY_READ_ONLY = "read_only"
AUTONOMY_MODES = {AUTONOMY_SAFE_AUTO, AUTONOMY_CONFIRM_ALL, AUTONOMY_READ_ONLY}


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
            action_payload["_policy_decision"] = policy["execution_mode"]
            action_payload["_policy_reason"] = policy["policy_reason"]
            action_payload["_risk_level"] = policy["risk_level"]
            next_action_status = "blocked" if policy["execution_mode"] == "blocked" else action["status"]
            action = self.repository.update_action_status(action["id"], next_action_status, payload=action_payload)
            self.repository.add_event(
                workflow_id,
                step_id,
                "auto_action_executed" if policy["execution_mode"] == "auto" else "auto_action_blocked",
                "system",
                policy["policy_reason"],
                {
                    "action_id": action["id"],
                    "action_type": action_type,
                    "execution_mode": policy["execution_mode"],
                    "risk_level": policy["risk_level"],
                },
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
                    "_patch_summaries": result.get("patch_summaries") or [],
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
            "patch_summaries": result.summaries,
            "failure_summary": "",
        }

    def _evaluate_policy(self, project: dict[str, Any], action_type: str, payload: dict[str, Any]) -> dict[str, str]:
        autonomy_mode = self._autonomy_mode(project)
        if autonomy_mode == AUTONOMY_READ_ONLY and action_type in {"patch", "command"}:
            return self._policy("blocked", "high", "只读模式已开启，Agent 不会写文件或执行命令")

        if action_type == "command":
            command = payload.get("command")
            if isinstance(command, str):
                return self._policy("blocked", "high", "命令必须使用 argv 数组，禁止 shell 字符串")
            try:
                args = normalize_command(command)
            except HTTPException as exc:
                return self._policy("blocked", "high", str(exc.detail))
            if args and command_allowed(args):
                if autonomy_mode == AUTONOMY_CONFIRM_ALL:
                    return self._policy("approval_required", "low", "确认模式已开启，白名单命令需人工审批")
                return self._policy("auto", "low", "白名单短命令，已按安全自动模式执行")
            return self._policy("approval_required", "medium", "命令不在自动执行策略内，需人工审批")

        if action_type == "patch":
            if payload.get("format") == "unified_diff" or payload.get("diff"):
                diff_policy = self._evaluate_source_diff_policy(project, str(payload.get("diff") or ""))
                if autonomy_mode == AUTONOMY_CONFIRM_ALL and diff_policy["execution_mode"] != "blocked":
                    return self._policy("approval_required", diff_policy["risk_level"], "确认模式已开启，diff 补丁需人工审批")
                return diff_policy
            files = payload.get("files") or payload.get("file_changes") or []
            if not isinstance(files, list) or not files or len(files) > 5:
                return self._confirm_or_approval("补丁文件数量超出自动执行策略，需人工审批")
            safety = self._evaluate_patch_safety(files)
            if safety["execution_mode"] == "blocked":
                return safety
            safe_prefixes = ("tmp/", "tmp\\", "docs/", "docs\\", "tests/", "tests\\", "server/tests/", "client/src/test/")
            if autonomy_mode == AUTONOMY_CONFIRM_ALL:
                risk_level = "low" if self._is_low_risk_file_write(files, safe_prefixes) else safety["risk_level"]
                return self._policy("approval_required", risk_level, "确认模式已开启，补丁需人工审批")

            source_policy = self._evaluate_source_patch_policy(project, files)
            used_source_policy = False
            for item in files:
                if not isinstance(item, dict):
                    return self._confirm_or_approval("补丁格式异常，需人工审批")
                relative_path = str(item.get("path") or item.get("file_path") or "")
                content = str(item.get("content") or "")
                if not relative_path or len(content) > 20_000:
                    return self._confirm_or_approval("补丁内容超出自动执行策略，需人工审批")
                normalized_path = relative_path.replace("\\", "/")
                if not normalized_path.startswith(tuple(prefix.replace("\\", "/") for prefix in safe_prefixes)) and not normalized_path.endswith(".md"):
                    if source_policy["execution_mode"] == "auto":
                        used_source_policy = True
                        continue
                    return source_policy
            if used_source_policy:
                return source_policy
            return self._policy("auto", "low", "安全小补丁，已按安全自动模式执行")

        return self._policy("approval_required", "medium", "未知动作类型，需人工审批")

    def _evaluate_source_patch_policy(self, project: dict[str, Any], files: list[Any]) -> dict[str, str]:
        if not files:
            return self._policy("approval_required", "medium", "源码补丁为空，需人工审批")
        if len(files) > 5:
            return self._policy("approval_required", "medium", "源码补丁文件数量超出自动执行策略，需人工审批")
        multi_file_requires_approval = len(files) > 2
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
                return self._policy("approval_required", "medium", "源码补丁格式异常，需人工审批")
            relative_path = str(item.get("path") or item.get("file_path") or "").replace("\\", "/")
            content = str(item.get("content") or "")
            if not relative_path:
                return self._policy("approval_required", "medium", "源码补丁缺少路径，需人工审批")
            path = Path(relative_path)
            if path.is_absolute() or ".." in path.parts:
                return self._policy("blocked", "high", "源码补丁路径不安全，已阻断")
            if path.name in sensitive_names or any(part in sensitive_parts for part in path.parts):
                return self._policy("blocked", "high", "源码补丁涉及敏感文件或目录，已阻断")
            if path.suffix.lower() not in allowed_suffixes:
                return self._policy("approval_required", "medium", "源码补丁文件类型不在自动执行策略内")
            line_count = len(content.splitlines())
            total_lines += line_count
            if line_count > 80:
                return self._policy("approval_required", "medium", "单文件源码补丁超过 80 行，需人工审批")
            if relative_path not in read_paths:
                return self._policy("approval_required", "medium", "源码文件未在同一轮被读取或搜索命中，需人工审批")
        if total_lines > 160:
            return self._policy("approval_required", "medium", "源码补丁总行数超过 160 行，需人工审批")
        if multi_file_requires_approval:
            return self._policy("approval_required", "medium", "多文件源码补丁需人工审批后执行")
        return self._policy("auto", "low", "低风险源码小改，已按安全自动模式执行")

    def _evaluate_source_diff_policy(self, project: dict[str, Any], diff: str) -> dict[str, str]:
        if not diff.strip():
            return self._policy("approval_required", "medium", "diff 补丁为空，需人工审批")
        lowered = diff.lower()
        if "binary files " in lowered or "\nrename from " in lowered or "\nrename to " in lowered:
            return self._policy("blocked", "high", "二进制或重命名 diff 已阻断")

        files = self._source_diff_files(diff)
        if not files:
            return self._policy("approval_required", "medium", "diff 补丁未包含可识别文件，需人工审批")
        if len(files) > 5:
            return self._policy("approval_required", "medium", "源码 diff 文件数量超出自动执行策略，需人工审批")
        multi_file_requires_approval = len(files) > 2

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
        total_changed_lines = 0

        for item in files:
            relative_path = str(item.get("path") or "").replace("\\", "/")
            old_path = str(item.get("old_path") or "").replace("\\", "/")
            changed_lines = int(item.get("changed_lines") or 0)
            if relative_path == "/dev/null":
                return self._policy("blocked", "high", "删除类 diff 已阻断")
            if not relative_path:
                return self._policy("approval_required", "medium", "源码 diff 缺少路径，需人工审批")
            path = Path(relative_path)
            if path.is_absolute() or ".." in path.parts:
                return self._policy("blocked", "high", "源码 diff 路径不安全，已阻断")
            if path.name in sensitive_names or any(part in sensitive_parts for part in path.parts):
                return self._policy("blocked", "high", "源码 diff 涉及敏感文件或目录，已阻断")
            if path.suffix.lower() not in allowed_suffixes:
                return self._policy("approval_required", "medium", "源码 diff 文件类型不在自动执行策略内")
            total_changed_lines += changed_lines
            if changed_lines > 80:
                return self._policy("approval_required", "medium", "单文件源码 diff 超过 80 行，需人工审批")
            if relative_path not in read_paths:
                return self._policy("approval_required", "medium", "源码文件未在同一轮被读取或搜索命中，需人工审批")

        if total_changed_lines > 160:
            return self._policy("approval_required", "medium", "源码 diff 总变更行数超过 160 行，需人工审批")
        if multi_file_requires_approval:
            return self._policy("approval_required", "medium", "多文件源码 diff 需人工审批后执行")
        return self._policy("auto", "low", "低风险源码 diff 小改，已按安全自动模式执行")

    def _source_diff_files(self, diff: str) -> list[dict[str, Any]]:
        files: list[dict[str, Any]] = []
        current_old: str | None = None
        current_new: str | None = None
        changed_lines = 0

        def flush() -> None:
            nonlocal current_old, current_new, changed_lines
            if current_new is not None:
                files.append(
                    {
                        "old_path": current_old or "",
                        "path": current_new,
                        "changed_lines": changed_lines,
                    }
                )
            current_old = None
            current_new = None
            changed_lines = 0

        for line in diff.splitlines():
            if line.startswith("--- "):
                flush()
                current_old = self._clean_diff_path(line[4:])
                continue
            if line.startswith("+++ "):
                current_new = self._clean_diff_path(line[4:])
                continue
            if current_new is None:
                continue
            if line.startswith("@@"):
                continue
            if (line.startswith("+") and not line.startswith("+++")) or (line.startswith("-") and not line.startswith("---")):
                changed_lines += 1
        flush()
        return files

    def _clean_diff_path(self, value: str) -> str:
        path = value.strip().split("\t", 1)[0].strip()
        if path == "/dev/null":
            return path
        if path.startswith("a/") or path.startswith("b/"):
            return path[2:]
        return path

    def _evaluate_patch_safety(self, files: list[Any]) -> dict[str, str]:
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
        for item in files:
            if not isinstance(item, dict):
                return self._policy("approval_required", "medium", "补丁格式异常，需人工审批")
            relative_path = str(item.get("path") or item.get("file_path") or "").replace("\\", "/")
            if not relative_path:
                return self._policy("approval_required", "medium", "补丁缺少路径，需人工审批")
            path = Path(relative_path)
            if path.is_absolute() or ".." in path.parts:
                return self._policy("blocked", "high", "补丁路径不安全，已阻断")
            if path.name in sensitive_names or any(part in sensitive_parts for part in path.parts):
                return self._policy("blocked", "high", "补丁涉及敏感文件或目录，已阻断")
            if item.get("delete") or item.get("deleted") or item.get("rename") or item.get("old_path"):
                return self._policy("blocked", "high", "删除、重命名类补丁已阻断")
        return self._policy("approval_required", "medium", "补丁需策略继续评估")

    def _is_low_risk_file_write(self, files: list[Any], safe_prefixes: tuple[str, ...]) -> bool:
        normalized_prefixes = tuple(prefix.replace("\\", "/") for prefix in safe_prefixes)
        for item in files:
            if not isinstance(item, dict):
                return False
            relative_path = str(item.get("path") or item.get("file_path") or "").replace("\\", "/")
            content = str(item.get("content") or "")
            if not relative_path or len(content) > 20_000:
                return False
            if not relative_path.startswith(normalized_prefixes) and not relative_path.endswith(".md"):
                return False
        return True

    def _autonomy_mode(self, project: dict[str, Any]) -> str:
        metadata = project.get("metadata") if isinstance(project.get("metadata"), dict) else {}
        mode = str(metadata.get("autonomy_mode") or AUTONOMY_SAFE_AUTO)
        return mode if mode in AUTONOMY_MODES else AUTONOMY_SAFE_AUTO

    def _confirm_or_approval(self, reason: str) -> dict[str, str]:
        return self._policy("approval_required", "medium", reason)

    def _policy(self, execution_mode: str, risk_level: str, reason: str) -> dict[str, str]:
        return {
            "execution_mode": execution_mode,
            "policy_decision": execution_mode,
            "risk_level": risk_level,
            "policy_reason": reason,
        }

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
