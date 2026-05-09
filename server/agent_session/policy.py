from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import HTTPException

from agent_runtime.command_policy import command_allowed, normalize_command


AUTONOMY_SAFE_AUTO = "safe_auto"
AUTONOMY_CONFIRM_ALL = "confirm_all"
AUTONOMY_READ_ONLY = "read_only"
AUTONOMY_MODES = {AUTONOMY_SAFE_AUTO, AUTONOMY_CONFIRM_ALL, AUTONOMY_READ_ONLY}
SAFE_PATCH_MAX_FILES = 3
SAFE_PATCH_MAX_LINES_PER_FILE = 120
SAFE_PATCH_MAX_TOTAL_LINES = 240


def evaluate_agent_action_policy(
    session: dict[str, Any],
    part_type: str,
    payload: dict[str, Any],
    touched_paths: set[str],
) -> dict[str, str]:
    mode = _autonomy_mode(session)
    if mode == AUTONOMY_READ_ONLY and part_type in {"diff", "command"}:
        return _policy("blocked", "high", "只读模式已开启，Agent 不会写文件或执行命令")

    if part_type == "command":
        tool_name = str(payload.get("tool") or "")
        if tool_name == "stop_dev_server":
            if mode == AUTONOMY_CONFIRM_ALL:
                return _policy("approval_required", "low", "确认模式已开启，停止开发服务器需人工审批")
            return _policy("auto", "low", "停止开发服务器属于低风险命令，允许自动执行")
        command = payload.get("command")
        if isinstance(command, str):
            return _policy("blocked", "high", "命令必须使用 argv 数组，禁止 shell 字符串")
        try:
            argv = normalize_command(command)
        except HTTPException as exc:
            return _policy("blocked", "high", str(exc.detail))
        if not command_allowed(argv):
            return _policy("blocked", "high", "命令不在白名单内，已阻断")
        if payload.get("long_running") or tool_name == "run_dev_server" or (len(argv) >= 3 and argv[0].lower() == "npm" and argv[1].lower() == "run" and argv[2].lower() == "dev"):
            return _policy("approval_required", "medium", "开发服务器是长运行命令，需人工审批后启动")
        if len(argv) > 8:
            return _policy("approval_required", "medium", "命令参数较长，需人工审批")
        if mode == AUTONOMY_CONFIRM_ALL:
            return _policy("approval_required", "low", "确认模式已开启，白名单命令需人工审批")
        return _policy("auto", "low", "白名单短命令，已按安全自动模式执行")

    if part_type == "diff":
        files = payload.get("files") or payload.get("file_changes") or []
        if not isinstance(files, list) or not files:
            return _policy("approval_required", "medium", "补丁未包含可识别文件，需人工审批")
        if len(files) > 6:
            return _policy("approval_required", "medium", "补丁文件数量超出自动执行策略，需人工审批")

        safety = _evaluate_file_safety(files)
        if safety["execution_mode"] == "blocked":
            return safety
        if mode == AUTONOMY_CONFIRM_ALL:
            return _policy("approval_required", safety["risk_level"], "确认模式已开启，补丁需人工审批")

        safe_prefixes = ("tmp/", "docs/", "tests/", "server/tests/", "client/src/test/")
        if _is_low_risk_safe_prefix(files, safe_prefixes):
            return _policy("auto", "low", "安全小补丁，已按安全自动模式执行")

        source_policy = _evaluate_source_policy(files, touched_paths)
        return source_policy

    return _policy("approval_required", "medium", "未知动作类型，需人工审批")


def _autonomy_mode(session: dict[str, Any]) -> str:
    metadata = session.get("metadata") if isinstance(session.get("metadata"), dict) else {}
    mode = str(metadata.get("autonomy_mode") or AUTONOMY_SAFE_AUTO)
    return mode if mode in AUTONOMY_MODES else AUTONOMY_SAFE_AUTO


def _evaluate_file_safety(files: list[Any]) -> dict[str, str]:
    sensitive_names = {
        ".env",
        "package.json",
        "package-lock.json",
        "pnpm-lock.yaml",
        "yarn.lock",
        "pyproject.toml",
        "requirements.txt",
        "dockerfile",
    }
    sensitive_parts = {".git", "secrets", "keys", "migrations"}
    for item in files:
        if not isinstance(item, dict):
            return _policy("approval_required", "medium", "补丁格式异常，需人工审批")
        relative_path = str(item.get("path") or item.get("file_path") or "").replace("\\", "/")
        path = Path(relative_path)
        if not relative_path:
            return _policy("approval_required", "medium", "补丁缺少路径，需人工审批")
        if path.is_absolute() or ".." in path.parts:
            return _policy("blocked", "high", "补丁路径不安全，已阻断")
        if path.name.lower() in sensitive_names or any(part.lower() in sensitive_parts for part in path.parts):
            return _policy("blocked", "high", "补丁涉及敏感文件或目录，已阻断")
        if item.get("delete") or item.get("deleted") or item.get("rename") or item.get("old_path"):
            return _policy("blocked", "high", "删除、重命名类补丁已阻断")
    return _policy("approval_required", "medium", "补丁需策略继续评估")


def _is_low_risk_safe_prefix(files: list[Any], safe_prefixes: tuple[str, ...]) -> bool:
    for item in files:
        relative_path = str(item.get("path") or item.get("file_path") or "").replace("\\", "/")
        content = str(item.get("content") or "")
        if not relative_path.startswith(safe_prefixes) and not relative_path.endswith(".md"):
            return False
        if len(content.splitlines()) > SAFE_PATCH_MAX_LINES_PER_FILE:
            return False
    return True


def _evaluate_source_policy(files: list[Any], touched_paths: set[str]) -> dict[str, str]:
    allowed_suffixes = {".py", ".ts", ".tsx", ".css", ".md"}
    total_lines = 0
    multi_file_requires_approval = len(files) > SAFE_PATCH_MAX_FILES
    for item in files:
        relative_path = str(item.get("path") or item.get("file_path") or "").replace("\\", "/")
        content = str(item.get("content") or "")
        path = Path(relative_path)
        if path.suffix.lower() not in allowed_suffixes:
            return _policy("approval_required", "medium", "源码补丁文件类型不在自动执行策略内")
        line_count = len(content.splitlines())
        total_lines += line_count
        if line_count > SAFE_PATCH_MAX_LINES_PER_FILE:
            return _policy("approval_required", "medium", f"单文件源码补丁超过 {SAFE_PATCH_MAX_LINES_PER_FILE} 行，需人工审批")
        if relative_path not in touched_paths:
            return _policy("approval_required", "medium", "源码文件未在同一轮被读取或搜索命中，需人工审批")
    if total_lines > SAFE_PATCH_MAX_TOTAL_LINES:
        return _policy("approval_required", "medium", f"源码补丁总行数超过 {SAFE_PATCH_MAX_TOTAL_LINES} 行，需人工审批")
    if multi_file_requires_approval:
        return _policy("approval_required", "medium", "多文件源码补丁需人工审批后执行")
    return _policy("auto", "low", "低风险源码小改，已按安全自动模式执行")


def _policy(execution_mode: str, risk_level: str, reason: str) -> dict[str, str]:
    return {
        "execution_mode": execution_mode,
        "policy_decision": execution_mode,
        "risk_level": risk_level,
        "policy_reason": reason,
    }
