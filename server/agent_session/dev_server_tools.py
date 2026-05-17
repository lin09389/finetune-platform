from __future__ import annotations

import logging
import re
import subprocess
import time
from typing import Any

from fastapi import HTTPException

from .command_policy import command_allowed, normalize_command, resolve_command_cwd

from .tool_host import ToolHostProtocol
from .tool_types import ToolResult

DEV_SERVER_PROCESSES: dict[str, dict[str, Any]] = {}
logger = logging.getLogger(__name__)


class DevServerToolsMixin(ToolHostProtocol):
    def _server_key(self, args: dict[str, Any], context: dict[str, Any]) -> str:
        session = context.get("session") or {}
        return f"{session.get('id') or 'default'}:{args.get('name') or 'dev'}"

    def _run_dev_server(self, args: dict[str, Any], context: dict[str, Any]) -> ToolResult:
        payload = args.get("payload") if isinstance(args.get("payload"), dict) else args
        command = payload.get("command") or ["npm", "run", "dev"]
        try:
            argv = normalize_command(command)
        except HTTPException as exc:
            return ToolResult("blocked", "开发服务器启动被阻断", {"command": command}, str(exc.detail))
        if not command_allowed(argv):
            return ToolResult("blocked", "开发服务器命令不在白名单内", {"command": argv}, "command is not allowlisted")
        root = self._root(context)
        command_root = resolve_command_cwd(root, argv)
        key = self._server_key(payload, context)
        existing = DEV_SERVER_PROCESSES.get(key)
        process = existing.get("process") if existing else None
        if process is not None and process.poll() is None:
            return ToolResult("completed", "开发服务器已在运行", {k: v for k, v in existing.items() if k not in {"process", "log_file"}})
        log_dir = root / "tmp" / "agent-dev-servers"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / f"{re.sub(r'[^a-zA-Z0-9_.-]+', '_', key)}.log"
        log_file = log_path.open("a", encoding="utf-8", errors="ignore")
        log_file.write(f"\n[{time.strftime('%Y-%m-%dT%H:%M:%S')}] starting: {' '.join(argv)}\n")
        log_file.flush()
        process = subprocess.Popen(argv, cwd=str(command_root), text=True, stdout=log_file, stderr=subprocess.STDOUT, shell=False)
        server_url = str(payload.get("server_url") or payload.get("url") or "http://localhost:5173")
        record = {
            "name": payload.get("name") or "dev",
            "command": argv,
            "cwd": str(command_root),
            "pid": process.pid,
            "server_url": server_url,
            "log_path": log_path.relative_to(root).as_posix(),
            "started_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "process": process,
            "log_file": log_file,
        }
        DEV_SERVER_PROCESSES[key] = record
        return ToolResult("completed", f"开发服务器已启动：{server_url}", {k: v for k, v in record.items() if k not in {"process", "log_file"}})

    def _stop_dev_server(self, args: dict[str, Any], context: dict[str, Any]) -> ToolResult:
        payload = args.get("payload") if isinstance(args.get("payload"), dict) else args
        key = self._server_key(payload, context)
        record = DEV_SERVER_PROCESSES.get(key)
        process = record.get("process") if record else None
        if process is None:
            return ToolResult("completed", "没有正在运行的开发服务器", {"running": False})
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
        log_file = record.get("log_file")
        if log_file:
            try:
                log_file.close()
            except Exception as e:
                logger.debug(f"Failed to close log file for dev server {key}: {e}")
                pass
        DEV_SERVER_PROCESSES.pop(key, None)
        return ToolResult("completed", "开发服务器已停止", {"running": False, "pid": record.get("pid")})

    def _get_server_status(self, args: dict[str, Any], context: dict[str, Any]) -> ToolResult:
        payload = args.get("payload") if isinstance(args.get("payload"), dict) else args
        key = self._server_key(payload, context)
        record = DEV_SERVER_PROCESSES.get(key)
        process = record.get("process") if record else None
        running = bool(process is not None and process.poll() is None)
        if not record:
            return ToolResult("completed", "开发服务器未启动", {"running": False})
        data = {k: v for k, v in record.items() if k not in {"process", "log_file"}}
        data["running"] = running
        data["exit_code"] = None if running else process.poll()
        return ToolResult("completed", "开发服务器正在运行" if running else "开发服务器已退出", data)
