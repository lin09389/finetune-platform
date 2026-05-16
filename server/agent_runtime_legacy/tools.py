"""Safe built-in tools used by workflow agents."""

from __future__ import annotations

import fnmatch
import logging
from pathlib import Path
from typing import Any, Callable, Dict

from core.config import settings

from .actions import WorkflowActionService
from .command_policy import detect_project_commands, run_git, summarize_failure
from .permission import PermissionAction, PermissionRule, default_rules_for_agent, evaluate
from .tool_models import AgentToolRequest, AgentToolResult

logger = logging.getLogger(__name__)

# 全局工具处理器映射
_TOOL_HANDLERS: Dict[str, Callable] = {}

def register_tool(tool_name: str):
    """工具注册装饰器 (外部定义以避免 classmethod 调用问题)"""
    def decorator(func: Callable):
        _TOOL_HANDLERS[tool_name] = func
        return func
    return decorator

IGNORED_DIRS = {".git", "node_modules", "dist", "build", ".venv", "__pycache__"}
TEXT_SUFFIXES = {
    ".py", ".ts", ".tsx", ".js", ".jsx", ".json", ".md", ".css", ".scss", ".html", ".yml", ".yaml", ".toml", ".txt", ".sql",
}

class AgentToolExecutor:
    def __init__(
        self,
        repository: Any,
        action_service: WorkflowActionService,
        max_read_chars: int = 20_000,
    ):
        self.repository = repository
        self.action_service = action_service
        self.max_read_chars = max_read_chars

    def execute(
        self,
        request: AgentToolRequest,
        *,
        workflow_id: str,
        step_id: str | None,
        agent_id: str,
        project: dict[str, Any],
        permission_rules: list[PermissionRule] | None = None,
        replay_of_call_id: str | None = None,
    ) -> AgentToolResult:
        # 1. 权限与模式提取
        pattern = self._extract_pattern(request.tool, request.arguments)
        permission_rules = permission_rules or default_rules_for_agent(agent_id)
        permission_name = f"tool.{request.tool}"
        decision = self._resolve_decision(project, permission_name, pattern, permission_rules)

        if decision == PermissionAction.DENY:
            return AgentToolResult(
                tool=request.tool, status="blocked",
                summary=f"权限拒绝：{request.tool}",
                error=f"permission denied for {request.tool} on {pattern}",
                permission_decision="deny",
                blocked_reason=f"权限规则拒绝 {request.tool} ({pattern})",
            )

        if decision == PermissionAction.ASK:
            action = self.repository.add_action_proposal(
                workflow_id=workflow_id, step_id=step_id,
                action_type="permission_request",
                title=f"权限请求：{request.tool}",
                description=f"Agent 请求执行 {request.tool}，目标：{pattern}",
                payload={
                    "permission": permission_name, "pattern": pattern,
                    "tool_name": request.tool, "tool_arguments": request.arguments,
                    "agent_id": agent_id, "replay_of_call_id": replay_of_call_id,
                },
            )
            return AgentToolResult(
                tool=request.tool, status="blocked",
                summary="权限请求已创建，等待用户审批",
                payload={"action_id": action.get("id"), "action": action},
                permission_decision="ask",
                blocked_reason=f"需要审批 {request.tool} ({pattern})",
                replay_of_call_id=replay_of_call_id,
            )

        # 2. 动态分发
        handler = _TOOL_HANDLERS.get(request.tool)
        if not handler:
            return AgentToolResult(tool=request.tool, status="failed", error=f"Unknown tool: {request.tool}")

        try:
            # 注意：handler 是未绑定函数，需要手动传入 self
            result = handler(self, request, project, workflow_id, step_id, agent_id)
            if result.permission_decision is None:
                result.permission_decision = "allow"
            return result
        except Exception as exc:
            logger.exception("Tool execution failed: %s", request.tool)
            return AgentToolResult(tool=request.tool, status="failed", summary="工具执行失败", error=str(exc))

    # --- 工具处理器定义 ---

    @register_tool("list_files")
    def _handle_list_files(self, request, project, workflow_id, step_id, agent_id) -> AgentToolResult:
        args = request.arguments
        root = self._allowed_root(project)
        limit = int(args.get("limit") or 200)
        path_glob = str(args.get("path_glob") or "**/*")
        files: list[str] = []
        for path in self._iter_files(root, path_glob):
            files.append(path.relative_to(root).as_posix())
            if len(files) >= limit:
                break
        return AgentToolResult(
            tool="list_files", status="completed",
            summary=f"列出 {len(files)} 个文件",
            payload={"root": str(root), "files": files},
        )

    @register_tool("search_code")
    def _handle_search_code(self, request, project, workflow_id, step_id, agent_id) -> AgentToolResult:
        args = request.arguments
        query = str(args.get("query") or "").strip()
        if not query:
            return AgentToolResult(tool="search_code", status="failed", error="query is required")
        root = self._allowed_root(project)
        path_glob = str(args.get("path_glob") or "**/*")
        limit = int(args.get("limit") or 20)
        matches: list[dict[str, Any]] = []
        lowered = query.lower()
        for path in self._iter_files(root, path_glob):
            if not self._is_text_file(path):
                continue
            try:
                lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
            except Exception:
                continue
            for line_no, line in enumerate(lines, 1):
                if lowered in line.lower():
                    matches.append({
                        "path": path.relative_to(root).as_posix(),
                        "line": line_no,
                        "preview": line.strip()[:300],
                    })
                    if len(matches) >= limit:
                        return AgentToolResult(
                            tool="search_code", status="completed",
                            summary=f"找到 {len(matches)} 条匹配",
                            payload={"query": query, "matches": matches},
                        )
        return AgentToolResult(
            tool="search_code", status="completed",
            summary=f"找到 {len(matches)} 条匹配",
            payload={"query": query, "matches": matches},
        )

    @register_tool("read_file")
    def _handle_read_file(self, request, project, workflow_id, step_id, agent_id) -> AgentToolResult:
        args = request.arguments
        raw_path = str(args.get("path") or args.get("file_path") or "").strip()
        if not raw_path:
            return AgentToolResult(tool="read_file", status="failed", error="path is required")
        root = self._allowed_root(project)
        target = self._safe_path(root, raw_path)
        if not target.exists() or not target.is_file():
            return AgentToolResult(tool="read_file", status="failed", error="file not found")
        content = target.read_text(encoding="utf-8", errors="ignore")
        truncated = len(content) > self.max_read_chars
        if truncated:
            content = content[: self.max_read_chars]
        return AgentToolResult(
            tool="read_file", status="completed",
            summary=f"读取文件 {target.relative_to(root).as_posix()}{'（已截断）' if truncated else ''}",
            payload={
                "path": target.relative_to(root).as_posix(),
                "content": content,
                "truncated": truncated,
                "char_count": len(content),
            },
        )

    @register_tool("inspect_project")
    def _handle_inspect_project(self, request, project, workflow_id, step_id, agent_id) -> AgentToolResult:
        root = self._allowed_root(project)
        markers = {
            "package_json": (root / "package.json").exists(),
            "client_package_json": (root / "client" / "package.json").exists(),
            "pyproject": (root / "pyproject.toml").exists(),
            "requirements": (root / "requirements.txt").exists(),
            "server_dir": (root / "server").exists(),
            "client_dir": (root / "client").exists(),
        }
        files = [path.relative_to(root).as_posix() for path in self._iter_files(root, "**/*")][:80]
        return AgentToolResult(
            tool="inspect_project", status="completed",
            summary="已检查项目结构",
            payload={"root": str(root), "markers": markers, "sample_files": files},
        )

    @register_tool("detect_project_commands")
    def _handle_detect_project_commands(self, request, project, workflow_id, step_id, agent_id) -> AgentToolResult:
        root = self._allowed_root(project)
        commands = detect_project_commands(root)
        return AgentToolResult(
            tool="detect_project_commands", status="completed",
            summary=f"识别到 {len(commands)} 个候选验证命令",
            payload={"commands": commands},
        )

    @register_tool("get_git_status")
    def _handle_get_git_status(self, request, project, workflow_id, step_id, agent_id) -> AgentToolResult:
        root = self._allowed_root(project)
        result = run_git(["status", "--short"], root)
        return AgentToolResult(
            tool="get_git_status", status=result["status"],
            summary="读取 git status" if result["status"] == "completed" else "读取 git status 失败",
            payload=result,
            error=result["stderr"] if result["status"] == "failed" else None,
        )

    @register_tool("get_git_diff")
    def _handle_get_git_diff(self, request, project, workflow_id, step_id, agent_id) -> AgentToolResult:
        args = request.arguments
        root = self._allowed_root(project)
        path = str(args.get("path") or "").strip()
        git_args = ["diff", "--", path] if path else ["diff", "--"]
        result = run_git(git_args, root)
        diff = result["stdout"][:20_000]
        return AgentToolResult(
            tool="get_git_diff", status=result["status"],
            summary=f"读取 git diff{'（已截断）' if len(result['stdout']) > len(diff) else ''}",
            payload={**result, "stdout": diff, "truncated": len(result["stdout"]) > len(diff)},
            error=result["stderr"] if result["status"] == "failed" else None,
        )

    @register_tool("list_changed_files")
    def _handle_list_changed_files(self, request, project, workflow_id, step_id, agent_id) -> AgentToolResult:
        root = self._allowed_root(project)
        result = run_git(["status", "--short"], root)
        files: list[str] = []
        for line in result["stdout"].splitlines():
            if len(line) > 3:
                files.append(line[3:].strip())
        return AgentToolResult(
            tool="list_changed_files", status=result["status"],
            summary=f"发现 {len(files)} 个变更文件",
            payload={**result, "files": files},
            error=result["stderr"] if result["status"] == "failed" else None,
        )

    @register_tool("propose_patch")
    def _handle_propose_patch(self, request, project, workflow_id, step_id, agent_id) -> AgentToolResult:
        if agent_id == "reviewer":
            return AgentToolResult(tool=request.tool, status="failed", error="reviewer cannot propose patch")
        if not self._has_project_context(project, workflow_id):
            return AgentToolResult(
                tool=request.tool, status="failed",
                summary="需要先读取项目上下文",
                error="请先调用 inspect_project、search_code 或 read_file，再提出补丁建议。",
                payload={
                    "required_tools": ["inspect_project", "search_code", "read_file"],
                    "next_action": "先读取项目结构或目标文件，再重新提出补丁。",
                },
            )
        context_check = self._check_patch_context(project, workflow_id, request.arguments)
        if context_check:
            return context_check
        return self._propose_action(workflow_id, step_id, request, "patch")

    @register_tool("propose_command")
    def _handle_propose_command(self, request, project, workflow_id, step_id, agent_id) -> AgentToolResult:
        if agent_id in {"build", "implementer"} and not self._has_detected_project_commands(project, workflow_id):
            return AgentToolResult(
                tool=request.tool, status="failed",
                summary="需要先识别项目验证命令",
                error="请先调用 detect_project_commands，再提出验证命令建议。",
                payload={
                    "required_tool": "detect_project_commands",
                    "next_tool": {"tool": "detect_project_commands", "arguments": {}},
                },
            )
        return self._propose_action(workflow_id, step_id, request, "command")

    @register_tool("read_execution_result")
    def _handle_read_execution_result(self, request, project, workflow_id, step_id, agent_id) -> AgentToolResult:
        args = request.arguments
        action_id = args.get("action_id")
        if action_id:
            action = self.repository.get_action_proposal(str(action_id))
            if not action:
                return AgentToolResult(tool="read_execution_result", status="failed", error="action not found")
            return AgentToolResult(
                tool="read_execution_result", status="completed",
                summary=f"读取动作 {action_id} 的执行结果",
                payload={"action": action, "executions": action.get("executions") or []},
            )
        actions = self.repository.list_action_proposals(project["id"])
        return AgentToolResult(
            tool="read_execution_result", status="completed",
            summary=f"读取 {len(actions)} 个动作建议和执行结果",
            payload={"actions": actions},
        )

    @register_tool("read_test_failures")
    def _handle_read_test_failures(self, request, project, workflow_id, step_id, agent_id) -> AgentToolResult:
        args = request.arguments
        action_id = args.get("action_id")
        actions = [self.repository.get_action_proposal(str(action_id))] if action_id else self.repository.list_action_proposals(project["id"])
        failures: list[dict[str, Any]] = []
        for action in actions:
            if not action: continue
            for execution in action.get("executions") or []:
                if execution.get("status") == "failed" or execution.get("exit_code") not in (None, 0):
                    failures.append({
                        "action_id": action.get("id"),
                        "title": action.get("title"),
                        "exit_code": execution.get("exit_code"),
                        "failure_summary": summarize_failure(
                            execution.get("stdout") or "",
                            execution.get("stderr") or "",
                            execution.get("error"),
                        ),
                    })
        return AgentToolResult(
            tool="read_test_failures", status="completed",
            summary=f"读取到 {len(failures)} 条失败摘要",
            payload={"failures": failures},
        )

    @register_tool("delegate_agent")
    def _handle_delegate_agent(self, request, project, workflow_id, step_id, agent_id) -> AgentToolResult:
        if not request.arguments.get("agent_id"):
            return AgentToolResult(
                tool=request.tool, status="failed",
                error="delegate_agent requires 'agent_id' argument",
            )
        return AgentToolResult(
            tool=request.tool, status="failed",
            summary="delegate_agent 需要 runtime 委派器执行",
            error="delegate_agent must be handled by the async runtime delegate path",
            payload={
                "agent_id": request.arguments.get("agent_id"),
                "task": request.arguments.get("task"),
                "runtime_delegate_required": True,
            },
        )

    @register_tool("finalize")
    def _handle_finalize(self, request, project, workflow_id, step_id, agent_id) -> AgentToolResult:
        return AgentToolResult(
            tool=request.tool, status="completed",
            summary="Agent 已完成工具循环",
            payload=request.arguments,
        )

    # --- 辅助方法 ---

    def _resolve_decision(self, project: dict[str, Any], permission: str, pattern: str, rules: list[PermissionRule]) -> PermissionAction:
        if self._consume_permission_override(project, permission, pattern):
            return PermissionAction.ALLOW
        return evaluate(permission, pattern, rules)

    def _consume_permission_override(self, project: dict[str, Any], permission: str, pattern: str) -> bool:
        metadata = dict(project.get("metadata") or {})
        overrides = list(metadata.get("permission_overrides") or [])
        remaining: list[dict[str, Any]] = []
        matched = False
        for item in overrides:
            if not matched and str(item.get("permission")) == permission and fnmatch.fnmatch(pattern, str(item.get("pattern") or "*")):
                matched = True
                continue
            remaining.append(item)
        if matched:
            metadata["permission_overrides"] = remaining
            self.repository.update_project(project["id"], metadata=metadata)
            project["metadata"] = metadata
        return matched

    def _extract_pattern(self, tool_name: str, args: dict[str, Any]) -> str:
        if tool_name in {"read_file", "propose_patch"}:
            if tool_name == "propose_patch":
                files = args.get("payload", {}).get("files") if isinstance(args.get("payload"), dict) else None
                if isinstance(files, list) and files:
                    file_item = files[0] if isinstance(files[0], dict) else {}
                    return str(file_item.get("path") or file_item.get("file_path") or "*")
            return str(args.get("path") or args.get("file_path") or "*")
        if tool_name in {"search_code", "list_files"}:
            return str(args.get("path_glob") or "**/*")
        if tool_name == "propose_command":
            payload = args.get("payload")
            if isinstance(payload, dict):
                cmd = payload.get("command")
                if isinstance(cmd, list):
                    return " ".join(str(item) for item in cmd)
                return str(cmd or "*")
            return str(args.get("command") or "*")
        if tool_name == "delegate_agent":
            return str(args.get("agent_id") or "*")
        return "*"

    def _allowed_root(self, project: dict[str, Any]) -> Path:
        raw = project.get("project_path") or self._workspace_root()
        root = Path(raw).resolve()
        allowed_roots = self._workspace_roots()
        if not any(root == allowed or root.is_relative_to(allowed) for allowed in allowed_roots):
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

    def _iter_files(self, root: Path, path_glob: str):
        pattern = path_glob.replace("\\", "/")
        for path in root.rglob("*"):
            if any(part in IGNORED_DIRS for part in path.parts): continue
            if not path.is_file(): continue
            rel = path.relative_to(root).as_posix()
            if pattern and not fnmatch.fnmatch(rel, pattern): continue
            yield path

    def _is_text_file(self, path: Path) -> bool:
        return path.suffix.lower() in TEXT_SUFFIXES or not path.suffix

    def _workspace_root(self) -> Path:
        base_dir = settings.base_dir.resolve()
        return base_dir.parent if base_dir.name == "server" else base_dir

    def _workspace_roots(self) -> set[Path]:
        return {Path.cwd().resolve(), settings.base_dir.resolve(), self._workspace_root()}

    def _has_project_context(self, project: dict[str, Any], workflow_id: str) -> bool:
        calls = self.repository.list_tool_calls(workflow_id)
        return any(call.get("status") == "completed" and call.get("tool_name") in {"inspect_project", "search_code", "read_file", "list_files"} for call in calls)

    def _has_detected_project_commands(self, project: dict[str, Any], workflow_id: str) -> bool:
        calls = self.repository.list_tool_calls(workflow_id)
        return any(call.get("status") == "completed" and call.get("tool_name") == "detect_project_commands" for call in calls)

    def _check_patch_context(self, project: dict[str, Any], workflow_id: str, arguments: dict[str, Any]) -> AgentToolResult | None:
        payload = arguments.get("payload") if isinstance(arguments.get("payload"), dict) else arguments
        patch_paths = self._patch_paths(payload)
        source_paths = [path for path in patch_paths if self._is_source_path(path)]
        if len(source_paths) < 2:
            return None
        touched = self._context_touched_paths(workflow_id)
        missing = [path for path in source_paths if path not in touched]
        if not missing:
            return None
        return AgentToolResult(
            tool="propose_patch",
            status="failed",
            summary="需要补充读取相关文件",
            error="功能级多文件补丁需要先读取或搜索命中所有目标源码文件。",
            payload={
                "required_tools": ["search_code", "read_file"],
                "missing_related_files": missing,
                "touched_files": sorted(touched),
                "next_action": "先读取或搜索缺失的相关文件，再重新提出补丁。",
            },
        )

    def _patch_paths(self, payload: dict[str, Any]) -> list[str]:
        files = payload.get("files") or payload.get("file_changes") or []
        paths: list[str] = []
        if isinstance(files, list):
            for item in files:
                if isinstance(item, dict):
                    raw_path = str(item.get("path") or item.get("file_path") or "").replace("\\", "/")
                    if raw_path:
                        paths.append(raw_path)
        diff = str(payload.get("diff") or "")
        if payload.get("format") == "unified_diff" or diff:
            for line in diff.splitlines():
                if not line.startswith("+++ "):
                    continue
                path = line[4:].strip().split("\t", 1)[0]
                if path == "/dev/null":
                    continue
                if path.startswith("a/") or path.startswith("b/"):
                    path = path[2:]
                paths.append(path.replace("\\", "/"))
        return list(dict.fromkeys(paths))

    def _context_touched_paths(self, workflow_id: str) -> set[str]:
        touched: set[str] = set()
        for call in self.repository.list_tool_calls(workflow_id):
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

    def _is_source_path(self, path: str) -> bool:
        suffix = Path(path).suffix.lower()
        return suffix in {".py", ".ts", ".tsx", ".css", ".md"}

    def _propose_action(self, workflow_id: str, step_id: str | None, request: AgentToolRequest, action_type: str) -> AgentToolResult:
        payload = request.arguments.get("payload")
        if not isinstance(payload, dict):
            payload = {k: v for k, v in request.arguments.items() if k not in {"title", "description", "summary"}}
        action = self.repository.add_action_proposal(
            workflow_id=workflow_id, step_id=step_id, action_type=action_type,
            title=str(request.arguments.get("title") or ("文件补丁建议" if action_type == "patch" else "命令执行建议")),
            description=str(request.arguments.get("description") or request.thought or ""),
            payload=payload,
        )
        project = self.repository.get_project(workflow_id)
        if project and hasattr(self.action_service, "_evaluate_policy"):
            policy = self.action_service._evaluate_policy(project, action_type, payload)
            action_payload = dict(action.get("payload") or {})
            action_payload.update(
                {
                    "_execution_mode": policy["execution_mode"],
                    "_policy_decision": policy["execution_mode"],
                    "_policy_reason": policy["policy_reason"],
                    "_risk_level": policy.get("risk_level"),
                }
            )
            next_action_status = "blocked" if policy["execution_mode"] == "blocked" else action["status"]
            action = self.repository.update_action_status(action["id"], next_action_status, payload=action_payload)
            if policy["execution_mode"] == "auto":
                from datetime import datetime
                action = self.repository.update_action_status(action["id"], "approved", approved_at=datetime.now().isoformat())
                action = self.action_service.execute(action["id"])
                payload_after_execute = dict(action.get("payload") or {})
                payload_after_execute["_auto_executed_at"] = action.get("executed_at")
                action = self.repository.update_action_status(action["id"], action["status"], payload=payload_after_execute)
        return AgentToolResult(
            tool=request.tool, status="completed",
            summary=f"已生成 {action_type} 动作建议",
            payload={"action_id": action.get("id"), "status": action.get("status")},
        )
