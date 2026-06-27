from __future__ import annotations

import ast
import asyncio
import json
import re
import shutil
import subprocess
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

import yaml
from langchain.agents.middleware.types import AgentMiddleware
from langchain_core.messages import ToolMessage
from langgraph.prebuilt.tool_node import ToolCallRequest
from langgraph.types import Command

from .execution_context import AgentDefinition

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10 compatibility
    import tomli as tomllib


TRAJECTORY_STATE_VERSION = 1
WRITE_TOOLS = {"write_file", "edit_file"}
OBSERVATION_TOOLS = {"ls", "read_file", "glob", "grep"}
DOCUMENT_EXTENSIONS = {".md", ".mdx", ".rst", ".txt", ".adoc"}
VERIFICATION_PATTERNS = (
    r"(?:^|\s)(?:python|py)\s+-m\s+pytest(?:\s|$)",
    r"(?:^|\s)(?:python|py)\s+-m\s+(?:compileall|py_compile)(?:\s|$)",
    r"(?:^|\s)pytest(?:\s|$)",
    r"(?:^|\s)(?:npm|pnpm|yarn)\s+(?:run\s+)?(?:test|test:[\w-]+|typecheck|lint|build)(?:\s|$)",
    r"(?:^|\s)npx\s+(?:vitest|tsc|eslint)(?:\s|$)",
    r"(?:^|\s)(?:tsc|eslint|ruff\s+check|mypy)(?:\s|$)",
    r"(?:^|\s)(?:cargo\s+(?:test|check)|go\s+test|dotnet\s+(?:test|build))(?:\s|$)",
    r"(?:^|\s)(?:mvn|gradle|gradlew)\s+(?:test|check|build)(?:\s|$)",
)


def trajectory_policy_for_agent(agent: AgentDefinition | None) -> dict[str, Any]:
    policy = dict(agent.trajectory_policy or {}) if agent else {}
    return {
        "enabled": bool(policy.get("enabled")),
        "require_read_before_write": bool(policy.get("require_read_before_write")),
        "require_context_before_create": bool(policy.get("require_context_before_create")),
        "validate_after_write": bool(policy.get("validate_after_write")),
        "rollback_on_validation_failure": bool(policy.get("rollback_on_validation_failure")),
        "require_verification_after_write": bool(policy.get("require_verification_after_write")),
        "max_auto_corrections": max(0, int(policy.get("max_auto_corrections") or 0)),
    }


def is_verification_command(command: str) -> bool:
    normalized = re.sub(r"\s+", " ", str(command)).strip().lower()
    return any(re.search(pattern, normalized) for pattern in VERIFICATION_PATTERNS)


def is_successful_tool_result(result: ToolMessage | Command[Any]) -> bool:
    if isinstance(result, Command):
        return True
    if getattr(result, "status", None) == "error":
        return False
    content = str(getattr(result, "content", "") or "").strip().lower()
    return not content.startswith(("error:", "toolerror:", "failed:"))


@dataclass(frozen=True)
class StaticValidationResult:
    supported: bool
    valid: bool
    validator: str
    message: str = ""
    line: int | None = None
    column: int | None = None


@dataclass(frozen=True)
class FileSnapshot:
    existed: bool
    content: bytes = b""


def validate_file_syntax(path: Path, *, project_root: Path) -> StaticValidationResult:
    suffix = path.suffix.lower()
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return StaticValidationResult(False, True, "binary")
    except OSError as exc:
        return StaticValidationResult(True, False, "read", str(exc))

    try:
        if suffix == ".py":
            ast.parse(text, filename=str(path))
            return StaticValidationResult(True, True, "python_ast")
        if suffix == ".json":
            json.loads(text)
            return StaticValidationResult(True, True, "json")
        if suffix in {".yaml", ".yml"}:
            yaml.safe_load(text)
            return StaticValidationResult(True, True, "yaml")
        if suffix == ".toml":
            tomllib.loads(text)
            return StaticValidationResult(True, True, "toml")
    except SyntaxError as exc:
        return StaticValidationResult(
            True,
            False,
            "python_ast",
            str(exc.msg),
            line=exc.lineno,
            column=exc.offset,
        )
    except json.JSONDecodeError as exc:
        return StaticValidationResult(True, False, "json", exc.msg, line=exc.lineno, column=exc.colno)
    except yaml.YAMLError as exc:
        mark = getattr(exc, "problem_mark", None)
        return StaticValidationResult(
            True,
            False,
            "yaml",
            str(getattr(exc, "problem", None) or exc),
            line=(mark.line + 1) if mark is not None else None,
            column=(mark.column + 1) if mark is not None else None,
        )
    except tomllib.TOMLDecodeError as exc:
        return StaticValidationResult(True, False, "toml", str(exc))

    if suffix in {".js", ".mjs", ".cjs"}:
        return _validate_javascript(path)
    if suffix in {".ts", ".tsx", ".mts", ".cts", ".jsx"}:
        return _validate_typescript(path, project_root)
    return StaticValidationResult(False, True, "unsupported")


def _validate_javascript(path: Path) -> StaticValidationResult:
    node = shutil.which("node")
    if not node:
        return StaticValidationResult(False, True, "node_check_unavailable")
    completed = subprocess.run(
        [node, "--check", str(path)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=10,
        check=False,
    )
    if completed.returncode == 0:
        return StaticValidationResult(True, True, "node_check")
    output = (completed.stderr or completed.stdout).strip()
    line = _line_from_node_error(output)
    return StaticValidationResult(True, False, "node_check", output[-1200:], line=line)


def _validate_typescript(path: Path, project_root: Path) -> StaticValidationResult:
    node = shutil.which("node")
    typescript = _find_typescript_runtime(path, project_root)
    if not node or typescript is None:
        return StaticValidationResult(False, True, "typescript_unavailable")
    script = (
        "const ts=require(process.argv[1]);const fs=require('fs');const file=process.argv[2];"
        "const text=fs.readFileSync(file,'utf8');"
        "const result=ts.transpileModule(text,{fileName:file,reportDiagnostics:true,"
        "compilerOptions:{target:ts.ScriptTarget.ES2020,jsx:ts.JsxEmit.ReactJSX}});"
        "const errors=(result.diagnostics||[]).filter(d=>d.category===ts.DiagnosticCategory.Error);"
        "if(errors.length){const d=errors[0];const pos=d.file&&d.start!=null?"
        "d.file.getLineAndCharacterOfPosition(d.start):null;"
        "console.error(JSON.stringify({message:ts.flattenDiagnosticMessageText(d.messageText,' '),"
        "line:pos?pos.line+1:null,column:pos?pos.character+1:null}));process.exit(1);}"
    )
    completed = subprocess.run(
        [node, "-e", script, str(typescript), str(path)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=10,
        check=False,
    )
    if completed.returncode == 0:
        return StaticValidationResult(True, True, "typescript_transpile")
    raw = (completed.stderr or completed.stdout).strip()
    try:
        payload = json.loads(raw.splitlines()[-1])
    except (json.JSONDecodeError, IndexError):
        payload = {"message": raw[-1200:]}
    return StaticValidationResult(
        True,
        False,
        "typescript_transpile",
        str(payload.get("message") or "TypeScript syntax validation failed."),
        line=payload.get("line"),
        column=payload.get("column"),
    )


def _find_typescript_runtime(path: Path, project_root: Path) -> Path | None:
    for base in [path.parent, *path.parents, project_root]:
        candidate = base / "node_modules" / "typescript" / "lib" / "typescript.js"
        if candidate.is_file():
            return candidate
        client_candidate = base / "client" / "node_modules" / "typescript" / "lib" / "typescript.js"
        if client_candidate.is_file():
            return client_candidate
        if base == project_root:
            break
    return None


def _line_from_node_error(output: str) -> int | None:
    match = re.search(r":(\d+)\s*$", output.splitlines()[0] if output else "")
    return int(match.group(1)) if match else None


def score_trajectory(steps: list[dict[str, Any]]) -> dict[str, Any]:
    ordered = sorted(
        (dict(step) for step in steps if isinstance(step, dict)),
        key=lambda step: int(step.get("sequence") or 0),
    )
    reads: dict[str, int] = {}
    successful_writes: list[dict[str, Any]] = []
    reread_required: set[str] = set()
    violations: list[dict[str, Any]] = []
    read_before_write = True
    failure_recovery = True

    for step in ordered:
        kind = str(step.get("kind") or "")
        path = str(step.get("path") or "")
        success = bool(step.get("success", True))
        sequence = int(step.get("sequence") or 0)
        details = step.get("details") if isinstance(step.get("details"), dict) else {}
        if kind == "read" and success and path:
            reads[path] = sequence
            reread_required.discard(path)
        elif kind == "write":
            if success:
                is_new = bool(details.get("new_file"))
                context_satisfied = bool(details.get("context_satisfied"))
                if path in reread_required:
                    failure_recovery = False
                    violations.append(
                        {
                            "sequence": sequence,
                            "reason_code": "write_without_reread_after_failure",
                            "path": path,
                        }
                    )
                if not ((is_new and context_satisfied) or path in reads):
                    read_before_write = False
                    violations.append(
                        {
                            "sequence": sequence,
                            "reason_code": "write_without_context",
                            "path": path,
                        }
                    )
                successful_writes.append(step)
            elif path:
                reread_required.add(path)
        elif kind == "verification" and not success:
            reread_required.update(str(item.get("path") or "") for item in successful_writes if item.get("path"))

    final_verification = True
    if successful_writes:
        last_write_sequence = max(int(step.get("sequence") or 0) for step in successful_writes)
        non_document_writes = [
            step
            for step in successful_writes
            if not bool((step.get("details") or {}).get("document"))
        ]
        successful_verifications = [
            step
            for step in ordered
            if step.get("kind") == "verification"
            and bool(step.get("success", True))
            and int(step.get("sequence") or 0) > last_write_sequence
        ]
        document_verifications = {
            str(step.get("path") or "")
            for step in ordered
            if step.get("kind") == "document_verification"
            and bool(step.get("success", True))
            and int(step.get("sequence") or 0) > last_write_sequence
        }
        documents = {
            str(step.get("path") or "")
            for step in successful_writes
            if bool((step.get("details") or {}).get("document"))
        }
        final_verification = bool(successful_verifications) or (
            not non_document_writes and bool(documents) and documents <= document_verifications
        )
        if not final_verification:
            violations.append(
                {
                    "sequence": last_write_sequence,
                    "reason_code": "missing_final_verification",
                    "paths": sorted(str(step.get("path") or "") for step in successful_writes),
                }
            )

    criteria = [read_before_write, final_verification, failure_recovery]
    return {
        "read_before_write": read_before_write,
        "final_verification": final_verification,
        "failure_recovery": failure_recovery,
        "violations": violations,
        "score": round(sum(1 for value in criteria if value) / len(criteria) * 100),
    }


def normalize_workspace_path(value: Any) -> str:
    raw = str(value or "").replace("\\", "/").strip()
    if not raw:
        return ""
    if raw == "/workspace":
        return "/workspace"
    if raw.startswith("/workspace/"):
        relative = raw.removeprefix("/workspace/")
    else:
        relative = raw.lstrip("/")
    parts: list[str] = []
    for part in PurePosixPath(relative).parts:
        if part in {"", ".", "/"}:
            continue
        if part == "..":
            if not parts:
                return ""
            parts.pop()
            continue
        parts.append(part)
    return "/workspace" + (f"/{'/'.join(parts)}" if parts else "")


class TrajectoryStateStore:
    def __init__(self, repository: Any, notify_event: Callable[[str, dict[str, Any]], None], session_id: str):
        self.repository = repository
        self.notify_event = notify_event
        self.session_id = session_id

    def begin_run(self) -> dict[str, Any]:
        state = self._empty_state()
        self._save(state)
        return state

    def load(self) -> dict[str, Any]:
        session = self.repository.get_session(self.session_id) or {}
        metadata = dict(session.get("metadata") or {})
        state = dict(metadata.get("trajectory_guard") or {})
        if state.get("version") != TRAJECTORY_STATE_VERSION:
            state = self._empty_state()
        return state

    def record_step(
        self,
        kind: str,
        *,
        tool: str,
        path: str = "",
        command: str = "",
        success: bool = True,
        details: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        state = self.load()
        sequence = int(state.get("sequence") or 0) + 1
        state["sequence"] = sequence
        step = {
            "sequence": sequence,
            "kind": kind,
            "tool": tool,
            "path": path,
            "command": command,
            "success": success,
        }
        if details:
            step["details"] = details
        steps = [dict(item) for item in state.get("steps") or [] if isinstance(item, dict)]
        steps.append(step)
        state["steps"] = steps[-200:]

        if kind == "read" and success and path:
            reads = dict(state.get("reads") or {})
            reads[path] = sequence
            state["reads"] = reads
            required = set(state.get("reread_required") or [])
            required.discard(path)
            state["reread_required"] = sorted(required)
        elif kind == "directory" and success and path:
            directories = dict(state.get("directories") or {})
            directories[path] = sequence
            state["directories"] = directories
        elif kind == "write" and success and path:
            writes = dict(state.get("writes") or {})
            writes[path] = sequence
            state["writes"] = writes
            state["last_write_sequence"] = sequence
            state["last_verification_sequence"] = 0
            state["verified_paths"] = []
        elif kind == "write" and not success and path and not bool((details or {}).get("rolled_back_to_absent")):
            required = set(state.get("reread_required") or [])
            required.add(path)
            state["reread_required"] = sorted(required)
        elif kind == "verification":
            if success:
                state["last_verification_sequence"] = sequence
                state["verified_paths"] = sorted((state.get("writes") or {}).keys())
            else:
                required = set(state.get("reread_required") or [])
                required.update((state.get("writes") or {}).keys())
                state["reread_required"] = sorted(required)

        self._save(state)
        self._publish(
            "trajectory_step_recorded",
            f"轨迹步骤已记录：{kind}",
            {"step": step, "trajectory_guard": self.public_summary(state)},
        )
        return state

    def block(self, tool: str, path: str, reason_code: str, message: str) -> ToolMessage:
        state = self.load()
        violations = [dict(item) for item in state.get("violations") or [] if isinstance(item, dict)]
        violation = {
            "tool": tool,
            "path": path,
            "reason_code": reason_code,
            "message": message,
            "sequence": int(state.get("sequence") or 0) + 1,
        }
        state["sequence"] = violation["sequence"]
        violations.append(violation)
        state["violations"] = violations[-50:]
        state["last_block_reason"] = violation
        self._save(state)
        part = self.repository.add_part(
            self.session_id,
            "error",
            status="blocked",
            title="轨迹门控",
            content=message,
            payload={"guard": "trajectory_guard", **violation},
        )
        self._publish(
            "trajectory_guard_blocked",
            message,
            {
                "part_id": part.get("id"),
                "part_type": "error",
                "status": "blocked",
                "guard": "trajectory_guard",
                "violation": violation,
                "part": part,
            },
        )
        return ToolMessage(
            content=json.dumps(
                {
                    "status": "blocked",
                    "guard": "trajectory_guard",
                    "reason_code": reason_code,
                    "message": message,
                    "required_next_action": self._required_action(reason_code, path),
                },
                ensure_ascii=False,
            ),
            tool_call_id="trajectory_guard",
            status="error",
        )

    def static_validation_failed(
        self,
        *,
        tool: str,
        path: str,
        validation: StaticValidationResult,
        rollback_success: bool,
        rolled_back_to_absent: bool,
        tool_call_id: str,
    ) -> ToolMessage:
        location = ""
        if validation.line is not None:
            location = f"（第 {validation.line} 行"
            if validation.column is not None:
                location += f"，第 {validation.column} 列"
            location += "）"
        rollback_text = "已恢复写入前内容" if rollback_success else "自动回滚失败，文件可能仍处于无效状态"
        message = f"{path} 写入后静态检查失败{location}：{validation.message}；{rollback_text}。"
        self.record_step(
            "write",
            tool=tool,
            path=path,
            success=False,
            details={
                "validator": validation.validator,
                "line": validation.line,
                "column": validation.column,
                "rollback_success": rollback_success,
                "rolled_back_to_absent": rolled_back_to_absent,
                "reason_code": "static_validation_failed",
            },
        )
        part = self.repository.add_part(
            self.session_id,
            "error",
            status="failed",
            title="写入静态检查失败",
            content=message,
            payload={
                "guard": "trajectory_guard",
                "reason_code": "static_validation_failed",
                "tool": tool,
                "path": path,
                "validator": validation.validator,
                "line": validation.line,
                "column": validation.column,
                "rollback_success": rollback_success,
            },
        )
        self._publish(
            "trajectory_static_validation_failed",
            message,
            {
                "part_id": part.get("id"),
                "part_type": "error",
                "status": "failed",
                "guard": "trajectory_guard",
                "tool": tool,
                "path": path,
                "validator": validation.validator,
                "line": validation.line,
                "column": validation.column,
                "rollback_success": rollback_success,
                "part": part,
            },
        )
        return ToolMessage(
            content=json.dumps(
                {
                    "status": "error",
                    "guard": "trajectory_guard",
                    "reason_code": "static_validation_failed",
                    "path": path,
                    "validator": validation.validator,
                    "message": validation.message,
                    "line": validation.line,
                    "column": validation.column,
                    "rollback_success": rollback_success,
                    "required_next_action": (
                        f"重新读取 {path} 的当前内容，修正静态错误后再提交写入。"
                        if not rolled_back_to_absent
                        else "根据静态错误修正新文件内容后重新创建。"
                    ),
                },
                ensure_ascii=False,
            ),
            tool_call_id=tool_call_id,
            status="error",
        )

    def completion_issues(self, policy: dict[str, Any]) -> list[dict[str, Any]]:
        if not policy.get("enabled") or not policy.get("require_verification_after_write"):
            return []
        state = self.load()
        writes = dict(state.get("writes") or {})
        if not writes:
            return []
        last_write = int(state.get("last_write_sequence") or 0)
        verified = int(state.get("last_verification_sequence") or 0)
        doc_paths = {path for path in writes if Path(path).suffix.lower() in DOCUMENT_EXTENSIONS}
        reads = dict(state.get("reads") or {})
        docs_verified = doc_paths and all(int(reads.get(path) or 0) > int(writes[path]) for path in doc_paths)
        non_doc_paths = set(writes) - doc_paths
        command_verified = verified > last_write
        issues: list[dict[str, Any]] = []
        if non_doc_paths and not command_verified:
            issues.append(
                {
                    "reason_code": "verification_required",
                    "paths": sorted(non_doc_paths),
                    "message": "源码、测试或配置已修改，但最终写入后尚未运行成功的测试、构建、类型、lint 或语法检查。",
                }
            )
        if doc_paths and not (docs_verified or command_verified):
            issues.append(
                {
                    "reason_code": "document_reread_required",
                    "paths": sorted(doc_paths),
                    "message": "文档已修改，但最终写入后尚未重新读取确认，也没有运行专用检查。",
                }
            )
        return issues

    def increment_correction(self, issues: list[dict[str, Any]]) -> int:
        state = self.load()
        count = int(state.get("auto_corrections") or 0) + 1
        state["auto_corrections"] = count
        state["completion_issues"] = issues
        self._save(state)
        message = "；".join(str(issue.get("message") or "") for issue in issues)
        self._publish(
            "trajectory_validation_required",
            message,
            {
                "guard": "trajectory_guard",
                "auto_correction": count,
                "issues": issues,
                "trajectory_guard": self.public_summary(state),
            },
        )
        return count

    def public_summary(self, state: dict[str, Any] | None = None) -> dict[str, Any]:
        current = state or self.load()
        return {
            "version": current.get("version"),
            "run_id": current.get("run_id"),
            "read_paths": sorted((current.get("reads") or {}).keys()),
            "directory_paths": sorted((current.get("directories") or {}).keys()),
            "written_paths": sorted((current.get("writes") or {}).keys()),
            "verified_paths": list(current.get("verified_paths") or []),
            "reread_required": list(current.get("reread_required") or []),
            "auto_corrections": int(current.get("auto_corrections") or 0),
            "violation_count": len(current.get("violations") or []),
            "last_block_reason": current.get("last_block_reason"),
        }

    def _save(self, state: dict[str, Any]) -> None:
        session = self.repository.get_session(self.session_id) or {}
        metadata = dict(session.get("metadata") or {})
        metadata["trajectory_guard"] = state
        self.repository.update_session(self.session_id, metadata=metadata)

    def _publish(self, event_type: str, message: str, payload: dict[str, Any]) -> None:
        event = self.repository.add_event(
            self.session_id,
            event_type,
            message,
            {"session_id": self.session_id, **payload},
        )
        self.notify_event(self.session_id, event)

    @staticmethod
    def _empty_state() -> dict[str, Any]:
        import uuid

        return {
            "version": TRAJECTORY_STATE_VERSION,
            "run_id": f"traj_{uuid.uuid4().hex}",
            "sequence": 0,
            "reads": {},
            "directories": {},
            "writes": {},
            "verified_paths": [],
            "last_write_sequence": 0,
            "last_verification_sequence": 0,
            "reread_required": [],
            "auto_corrections": 0,
            "violations": [],
            "steps": [],
        }

    @staticmethod
    def _required_action(reason_code: str, path: str) -> str:
        if reason_code in {"read_before_write", "reread_required"}:
            return f"先读取 {path} 的当前真实内容，再重新提交修改。"
        if reason_code == "parent_directory_required":
            return f"先查看 {str(PurePosixPath(path).parent)} 目录。"
        if reason_code == "related_file_required":
            return "先读取目标目录中的同类文件，确认命名、结构和风格。"
        return "先补齐缺少的上下文证据，再继续。"


class TrajectoryGuardMiddleware(AgentMiddleware[Any, Any, Any]):
    def __init__(
        self,
        *,
        repository: Any,
        notify_event: Callable[[str, dict[str, Any]], None],
        session_id: str,
        project_path: str,
        policy: dict[str, Any],
    ):
        self.store = TrajectoryStateStore(repository, notify_event, session_id)
        self.project_path = Path(project_path).resolve()
        self.policy = policy

    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Awaitable[ToolMessage | Command[Any]]],
    ) -> ToolMessage | Command[Any]:
        tool = str(request.tool_call.get("name") or "")
        args = request.tool_call.get("args") if isinstance(request.tool_call.get("args"), dict) else {}
        path = self._tool_path(tool, args)
        try:
            local_path = self._local_path(path) if path else None
        except ValueError:
            blocked = self.store.block(
                tool,
                path,
                "invalid_workspace_path",
                f"{path} 不在当前项目工作区内，已阻止文件操作。",
            )
            blocked.tool_call_id = str(request.tool_call.get("id") or "trajectory_guard")
            return blocked
        existed_before = bool(local_path and local_path.exists()) if tool in WRITE_TOOLS else False
        if tool in WRITE_TOOLS:
            blocked = self._check_write_preconditions(tool, path)
            if blocked is not None:
                blocked.tool_call_id = str(request.tool_call.get("id") or "trajectory_guard")
                return blocked
        try:
            snapshot = self._snapshot(local_path) if tool in WRITE_TOOLS and local_path is not None else None
        except OSError as exc:
            blocked = self.store.block(
                tool,
                path,
                "snapshot_failed",
                f"无法创建 {path} 的写前快照：{exc}",
            )
            blocked.tool_call_id = str(request.tool_call.get("id") or "trajectory_guard")
            return blocked

        result = await handler(request)
        if isinstance(result, Command):
            return result
        success = is_successful_tool_result(result)
        static_validation: StaticValidationResult | None = None
        if (
            tool in WRITE_TOOLS
            and path
            and local_path is not None
            and snapshot is not None
            and success
            and self.policy.get("validate_after_write")
        ):
            static_validation = await asyncio.to_thread(
                validate_file_syntax,
                local_path,
                project_root=self.project_path,
            )
            if static_validation.supported and not static_validation.valid:
                rollback_success = False
                if self.policy.get("rollback_on_validation_failure"):
                    rollback_success = await asyncio.to_thread(self._restore_snapshot, local_path, snapshot)
                return self.store.static_validation_failed(
                    tool=tool,
                    path=path,
                    validation=static_validation,
                    rollback_success=rollback_success,
                    rolled_back_to_absent=not snapshot.existed and rollback_success,
                    tool_call_id=str(request.tool_call.get("id") or "trajectory_guard"),
                )
        if tool == "read_file" and path:
            state = self.store.record_step("read", tool=tool, path=path, success=success)
            if success:
                self._record_document_verification(path, state)
        elif tool == "ls" and path:
            self.store.record_step("directory", tool=tool, path=path, success=success)
        elif tool in {"glob", "grep"}:
            self.store.record_step("observation", tool=tool, path=path, success=success)
        elif tool in WRITE_TOOLS and path:
            self.store.record_step(
                "write",
                tool=tool,
                path=path,
                success=success,
                details={
                    "new_file": not existed_before,
                    "context_satisfied": True,
                    "document": Path(path).suffix.lower() in DOCUMENT_EXTENSIONS,
                    "static_validator": static_validation.validator if static_validation else None,
                    "static_validation_supported": static_validation.supported if static_validation else False,
                    "static_validation_passed": static_validation.valid if static_validation else None,
                },
            )
        elif tool == "execute":
            command = str(args.get("command") or "")
            if is_verification_command(command):
                self.store.record_step("verification", tool=tool, command=command, success=success)
            else:
                self.store.record_step("command", tool=tool, command=command, success=success)
        return result

    def _check_write_preconditions(self, tool: str, path: str) -> ToolMessage | None:
        if not path:
            return self.store.block(tool, path, "invalid_workspace_path", "写入缺少有效的工作区文件路径。")
        state = self.store.load()
        reads = dict(state.get("reads") or {})
        if path in set(state.get("reread_required") or []):
            return self.store.block(
                tool,
                path,
                "reread_required",
                f"{path} 在上次失败后尚未重新读取，已阻止继续修改。",
            )
        local_path = self._local_path(path)
        if local_path.exists():
            if self.policy.get("require_read_before_write") and path not in reads:
                return self.store.block(
                    tool,
                    path,
                    "read_before_write",
                    f"{path} 尚未读取当前内容，已阻止直接修改。",
                )
            return None
        if not self.policy.get("require_context_before_create"):
            return None
        parent = normalize_workspace_path(str(PurePosixPath(path).parent))
        directories = dict(state.get("directories") or {})
        if parent not in directories:
            return self.store.block(
                tool,
                path,
                "parent_directory_required",
                f"创建 {path} 前尚未查看父目录 {parent}。",
            )
        candidates = self._related_files(local_path)
        if candidates and not any(candidate in reads for candidate in candidates):
            return self.store.block(
                tool,
                path,
                "related_file_required",
                f"目标目录非空；创建 {path} 前需要读取一个同类文件确认项目约定。",
            )
        return None

    def _record_document_verification(self, path: str, state: dict[str, Any]) -> None:
        writes = dict(state.get("writes") or {})
        if path not in writes or Path(path).suffix.lower() not in DOCUMENT_EXTENSIONS:
            return
        if int((state.get("reads") or {}).get(path) or 0) <= int(writes[path]):
            return
        self.store.record_step(
            "document_verification",
            tool="read_file",
            path=path,
            success=True,
        )

    def _related_files(self, local_path: Path) -> set[str]:
        parent = local_path.parent
        if not parent.exists():
            return set()
        files = [item for item in parent.iterdir() if item.is_file()]
        if not files:
            return set()
        same_suffix = [item for item in files if item.suffix.lower() == local_path.suffix.lower()]
        selected = same_suffix or files
        return {self._virtual_path(item) for item in selected}

    def _local_path(self, path: str) -> Path:
        relative = path.removeprefix("/workspace").lstrip("/")
        resolved = (self.project_path / Path(relative)).resolve()
        try:
            resolved.relative_to(self.project_path)
        except ValueError as exc:
            raise ValueError(f"Workspace path escapes project root: {path}") from exc
        return resolved

    @staticmethod
    def _snapshot(path: Path) -> FileSnapshot:
        if not path.exists():
            return FileSnapshot(False)
        return FileSnapshot(True, path.read_bytes())

    @staticmethod
    def _restore_snapshot(path: Path, snapshot: FileSnapshot) -> bool:
        try:
            if snapshot.existed:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(snapshot.content)
            elif path.exists():
                path.unlink()
            return True
        except OSError:
            return False

    def _virtual_path(self, path: Path) -> str:
        relative = path.resolve().relative_to(self.project_path).as_posix()
        return normalize_workspace_path(relative)

    @staticmethod
    def _tool_path(tool: str, args: dict[str, Any]) -> str:
        if tool in {"read_file", "write_file", "edit_file"}:
            return normalize_workspace_path(args.get("file_path") or args.get("path"))
        if tool in {"ls", "glob", "grep"}:
            return normalize_workspace_path(args.get("path"))
        return ""


def build_trajectory_middleware(
    *,
    repository: Any,
    notify_event: Callable[[str, dict[str, Any]], None],
    session_id: str,
    project_path: str,
    agent: AgentDefinition | None,
) -> list[AgentMiddleware[Any, Any, Any]]:
    policy = trajectory_policy_for_agent(agent)
    if not policy["enabled"]:
        return []
    return [
        TrajectoryGuardMiddleware(
            repository=repository,
            notify_event=notify_event,
            session_id=session_id,
            project_path=project_path,
            policy=policy,
        )
    ]


__all__ = [
    "TrajectoryGuardMiddleware",
    "TrajectoryStateStore",
    "build_trajectory_middleware",
    "is_successful_tool_result",
    "is_verification_command",
    "normalize_workspace_path",
    "score_trajectory",
    "StaticValidationResult",
    "trajectory_policy_for_agent",
    "validate_file_syntax",
]
