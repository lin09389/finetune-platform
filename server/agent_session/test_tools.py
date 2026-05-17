from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .command_policy import command_allowed, resolve_command_cwd, summarize_failure

from .tool_host import ToolHostProtocol
from .tool_types import ToolResult


class TestToolsMixin(ToolHostProtocol):
    def _run_targeted_test(self, args: dict[str, Any], context: dict[str, Any]) -> ToolResult:
        root = self._root(context)
        payload = args.get("payload") if isinstance(args.get("payload"), dict) else dict(args)
        framework = str(payload.get("framework") or "").strip().lower()
        target = str(payload.get("target") or payload.get("path") or "").strip()
        test_name = str(payload.get("test_name") or payload.get("name") or "").strip()
        if not framework:
            framework = self._infer_test_framework(root, target)
        if framework not in {"pytest", "vitest", "npm_test"}:
            return ToolResult("blocked", "无法识别测试框架", {"framework": framework, "target": target}, "unsupported test framework")
        command = self._build_targeted_test_command(root, framework, target, test_name)
        if not command_allowed(command):
            return ToolResult("blocked", "精准测试命令不在白名单内", {"command": command, "framework": framework, "target": target}, "command is not allowlisted")
        return ToolResult(
            "completed",
            "已生成精准测试命令",
            {
                "command": command,
                "framework": framework,
                "target": target,
                "test_name": test_name or None,
                "cwd": str(resolve_command_cwd(root, command)),
            },
        )

    def _summarize_test_results(self, args: dict[str, Any], context: dict[str, Any]) -> ToolResult:
        stdout = str(args.get("stdout") or "")
        stderr = str(args.get("stderr") or "")
        exit_code = args.get("exit_code")
        framework = str(args.get("framework") or "").strip().lower()
        session = context.get("session") or {}
        if (not stdout and not stderr and exit_code is None) and self.repository is not None and session.get("id"):
            parts = self.repository.list_parts(str(session["id"]))
            latest_command = next((part for part in reversed(parts) if part.get("type") == "command"), None)
            payload = (latest_command or {}).get("payload") if isinstance((latest_command or {}).get("payload"), dict) else {}
            stdout = str(payload.get("stdout") or "")
            stderr = str(payload.get("stderr") or "")
            exit_code = payload.get("exit_code")
            framework = framework or self._infer_test_framework(self._root(context), " ".join(payload.get("command") or []))
        summary = self._parse_test_result_summary(stdout, stderr, framework)
        summary["exit_code"] = exit_code
        summary["framework"] = framework or summary.get("framework") or ""
        return ToolResult(
            "completed" if (stdout or stderr or exit_code is not None) else "failed",
            "测试结果已汇总" if (stdout or stderr or exit_code is not None) else "未找到测试结果",
            summary,
            None if (stdout or stderr or exit_code is not None) else "no test output available",
        )

    def _collect_test_failures(self, args: dict[str, Any], context: dict[str, Any]) -> ToolResult:
        stdout = str(args.get("stdout") or "")
        stderr = str(args.get("stderr") or "")
        failure_summary = str(args.get("failure_summary") or "")
        session = context.get("session") or {}
        if not stdout and not stderr and self.repository is not None and session.get("id"):
            parts = self.repository.list_parts(str(session["id"]))
            latest_command = next((part for part in reversed(parts) if part.get("type") == "command"), None)
            payload = (latest_command or {}).get("payload") if isinstance((latest_command or {}).get("payload"), dict) else {}
            stdout = str(payload.get("stdout") or "")
            stderr = str(payload.get("stderr") or "")
            failure_summary = failure_summary or str(payload.get("failure_summary") or "")
        failures = self._parse_test_failures(stdout, stderr)
        return ToolResult(
            "completed" if (failures or failure_summary or stdout or stderr) else "failed",
            f"提取到 {len(failures)} 条测试失败信息" if (failures or failure_summary or stdout or stderr) else "未找到测试失败信息",
            self._normalize_tool_payload(
                {
                    "failure_summary": failure_summary,
                    "failures": failures[:12],
                    "stdout_excerpt": stdout[-1600:],
                    "stderr_excerpt": stderr[-1600:],
                }
            ),
            None if (failures or failure_summary or stdout or stderr) else "no test failure information available",
        )

    def _parse_test_failures(self, stdout: str, stderr: str) -> list[dict[str, Any]]:
        text = "\n".join(part for part in (stdout, stderr) if part).splitlines()
        failures: list[dict[str, Any]] = []
        current: dict[str, Any] | None = None
        for line in text:
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.startswith("FAILED ") or stripped.startswith("ERROR "):
                current = {"headline": stripped[:300], "details": []}
                failures.append(current)
                continue
            if current is not None and len(current["details"]) < 6:
                if stripped.startswith(("E ", "AssertionError", "RuntimeError", "TypeError", "ValueError", "Expected ", "Received ")):
                    current["details"].append(stripped[:300])
        return failures

    def _infer_test_framework(self, root: Path, target: str) -> str:
        normalized = target.replace("\\", "/").lower()
        if normalized.endswith(".py") or normalized.startswith("server/tests"):
            return "pytest"
        if any(normalized.endswith(ext) for ext in (".ts", ".tsx", ".js", ".jsx")) or normalized.startswith("client/"):
            if (root / "client" / "package.json").exists():
                return "vitest"
        if (root / "server" / "tests").exists():
            return "pytest"
        if (root / "client" / "package.json").exists():
            return "vitest"
        return ""

    def _build_targeted_test_command(self, root: Path, framework: str, target: str, test_name: str) -> list[str]:
        if framework == "pytest":
            command = ["python", "-m", "pytest"]
            if target:
                command.append(self._safe_path(root, target).relative_to(root).as_posix())
            if test_name:
                command.extend(["-k", test_name])
            return command
        if framework == "vitest":
            command = ["npx", "vitest", "run"]
            if target:
                command.append(self._safe_path(root, target).relative_to(root).as_posix())
            if test_name:
                command.extend(["-t", test_name])
            return command
        command = ["npm", "test"]
        if target:
            command.extend(["--", self._safe_path(root, target).relative_to(root).as_posix()])
        return command

    def _parse_test_result_summary(self, stdout: str, stderr: str, framework: str) -> dict[str, Any]:
        text = "\n".join(part for part in (stdout, stderr) if part)
        summary: dict[str, Any] = {
            "framework": framework,
            "passed": 0,
            "failed": 0,
            "skipped": 0,
            "collected": 0,
            "duration": "",
            "headline": "",
        }
        for line in reversed([item.strip() for item in text.splitlines() if item.strip()]):
            if not summary["headline"] and any(token in line.lower() for token in ("passed", "failed", "error", "collected", "duration", "warnings")):
                summary["headline"] = line[:300]
            passed = re.search(r"(\d+)\s+passed", line, flags=re.IGNORECASE)
            failed = re.search(r"(\d+)\s+failed", line, flags=re.IGNORECASE)
            skipped = re.search(r"(\d+)\s+skipped", line, flags=re.IGNORECASE)
            collected = re.search(r"collected\s+(\d+)\s+items", line, flags=re.IGNORECASE)
            duration = re.search(r"in\s+([0-9.]+s|\d+:\d+\.\d+)", line, flags=re.IGNORECASE)
            if passed:
                summary["passed"] = int(passed.group(1))
            if failed:
                summary["failed"] = int(failed.group(1))
            if skipped:
                summary["skipped"] = int(skipped.group(1))
            if collected:
                summary["collected"] = int(collected.group(1))
            if duration and not summary["duration"]:
                summary["duration"] = duration.group(1)
        if not summary["headline"]:
            summary["headline"] = summarize_failure(stdout, stderr, limit=300)
        return summary
