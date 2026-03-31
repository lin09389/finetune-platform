import asyncio
import os
import shutil
import tempfile
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from ..types import ErrorCode, ExecutionResult, ExecutionStatus
from .resource_limiter import ResourceConfig, ResourceLimiter


class Permission(str, Enum):
    FILE_READ = "file_read"
    FILE_WRITE = "file_write"
    FILE_DELETE = "file_delete"
    COMMAND_EXECUTE = "command_execute"
    NETWORK_ACCESS = "network_access"
    PROCESS_SPAWN = "process_spawn"
    ENVIRONMENT_ACCESS = "environment_access"


class SandboxLevel(str, Enum):
    STRICT = "strict"
    STANDARD = "standard"
    PERMISSIVE = "permissive"
    UNRESTRICTED = "unrestricted"


@dataclass
class SandboxConfig:
    level: SandboxLevel = SandboxLevel.STANDARD
    allowed_paths: list[str] = None
    denied_paths: list[str] = None
    allowed_commands: list[str] = None
    denied_commands: list[str] = None
    allowed_env_vars: list[str] = None
    max_file_size_mb: int = 10
    max_execution_time_seconds: int = 60
    max_memory_mb: int = 512
    allow_network: bool = False
    isolated_filesystem: bool = False
    temp_dir: str | None = None

    def __post_init__(self):
        if self.allowed_paths is None:
            self.allowed_paths = []
        if self.denied_paths is None:
            self.denied_paths = []
        if self.allowed_commands is None:
            self.allowed_commands = []
        if self.denied_commands is None:
            self.denied_commands = []
        if self.allowed_env_vars is None:
            self.allowed_env_vars = []

    def to_dict(self) -> dict[str, Any]:
        return {
            "level": self.level.value,
            "allowed_paths": self.allowed_paths,
            "denied_paths": self.denied_paths,
            "allowed_commands": self.allowed_commands,
            "denied_commands": self.denied_commands,
            "allowed_env_vars": self.allowed_env_vars,
            "max_file_size_mb": self.max_file_size_mb,
            "max_execution_time_seconds": self.max_execution_time_seconds,
            "max_memory_mb": self.max_memory_mb,
            "allow_network": self.allow_network,
            "isolated_filesystem": self.isolated_filesystem,
            "temp_dir": self.temp_dir,
        }


DANGEROUS_COMMANDS: set[str] = {
    "rm", "rmdir", "del", "format", "fdisk", "mkfs",
    "dd", "shred", "wipe", "sudo", "su", "chmod", "chown",
    "passwd", "useradd", "userdel", "groupadd", "groupdel",
    "shutdown", "reboot", "halt", "poweroff", "init",
    "systemctl", "service", "iptables", "ufw", "firewall-cmd",
    "curl", "wget", "nc", "netcat", "telnet", "ssh", "scp", "rsync",
    "python -m http.server", "php -S", "ruby -run -ehttpd",
    "eval", "exec", "source", ".",
    "crontab", "at", "batch",
    "docker", "kubectl", "helm",
}

DANGEROUS_PATTERNS: set[str] = {
    "rm -rf", "rm -r", "del /s", "del /q",
    "sudo rm", "sudo dd", "> /dev/", "mkfs.",
    ":(){ :|:& };:", "chmod 777", "chown root",
    "curl | bash", "wget | bash", "curl | sh", "wget | sh",
    "dd if=", "dd of=",
}


class SandboxCheckResult(BaseModel):
    allowed: bool = Field(default=True)
    reason: str = Field(default="")
    sanitized_value: str | None = Field(default=None)
    risk_level: str = Field(default="low")


class SandboxExecutor:
    def __init__(
        self,
        config: SandboxConfig | None = None,
        resource_limiter: ResourceLimiter | None = None,
    ):
        self.config = config or SandboxConfig()
        self.resource_limiter = resource_limiter or ResourceLimiter(
            ResourceConfig(
                max_file_size_mb=self.config.max_file_size_mb,
                max_execution_time_seconds=self.config.max_execution_time_seconds,
                max_memory_mb=self.config.max_memory_mb,
            )
        )
        self._isolated_dir: str | None = None
        self._permissions: set[Permission] = self._get_default_permissions()
        self._processes: dict[str, asyncio.subprocess.Process] = {}
        self._lock = asyncio.Lock()

    def _get_default_permissions(self) -> set[Permission]:
        permissions = {
            SandboxLevel.STRICT: {Permission.FILE_READ},
            SandboxLevel.STANDARD: {
                Permission.FILE_READ,
                Permission.FILE_WRITE,
                Permission.COMMAND_EXECUTE,
            },
            SandboxLevel.PERMISSIVE: {
                Permission.FILE_READ,
                Permission.FILE_WRITE,
                Permission.FILE_DELETE,
                Permission.COMMAND_EXECUTE,
                Permission.PROCESS_SPAWN,
            },
            SandboxLevel.UNRESTRICTED: set(Permission),
        }
        return permissions.get(self.config.level, {Permission.FILE_READ})

    async def initialize(self) -> None:
        if self.config.isolated_filesystem:
            self._isolated_dir = self.config.temp_dir or tempfile.mkdtemp(prefix="sandbox_")
            os.makedirs(self._isolated_dir, exist_ok=True)
        await self.resource_limiter.start_monitoring()

    async def cleanup(self) -> None:
        await self.resource_limiter.stop_monitoring()

        async with self._lock:
            for proc in self._processes.values():
                try:
                    proc.terminate()
                    await asyncio.wait_for(proc.wait(), timeout=5.0)
                except Exception:
                    try:
                        proc.kill()
                    except Exception:
                        pass
            self._processes.clear()

        if self._isolated_dir and os.path.exists(self._isolated_dir):
            try:
                shutil.rmtree(self._isolated_dir)
            except Exception:
                pass
            self._isolated_dir = None

    def check_permission(self, permission: Permission) -> bool:
        return permission in self._permissions

    def check_path_access(self, path: str, write: bool = False) -> SandboxCheckResult:
        try:
            abs_path = os.path.abspath(path)
        except Exception:
            return SandboxCheckResult(
                allowed=False,
                reason="Invalid path",
                risk_level="high",
            )

        if self._isolated_dir:
            if not abs_path.startswith(self._isolated_dir):
                return SandboxCheckResult(
                    allowed=False,
                    reason="Path outside isolated filesystem",
                    risk_level="high",
                )
            return SandboxCheckResult(allowed=True, sanitized_value=abs_path)

        for denied in self.config.denied_paths:
            try:
                denied_abs = os.path.abspath(denied)
                if abs_path.startswith(denied_abs):
                    return SandboxCheckResult(
                        allowed=False,
                        reason=f"Path in denied list: {denied}",
                        risk_level="high",
                    )
            except Exception:
                continue

        if self.config.allowed_paths:
            allowed = False
            for allowed_path in self.config.allowed_paths:
                try:
                    allowed_abs = os.path.abspath(allowed_path)
                    if abs_path.startswith(allowed_abs):
                        allowed = True
                        break
                except Exception:
                    continue

            if not allowed:
                return SandboxCheckResult(
                    allowed=False,
                    reason="Path not in allowed list",
                    risk_level="medium",
                )

        if write and not self.check_permission(Permission.FILE_WRITE):
            return SandboxCheckResult(
                allowed=False,
                reason="Write permission denied",
                risk_level="medium",
            )

        if not write and not self.check_permission(Permission.FILE_READ):
            return SandboxCheckResult(
                allowed=False,
                reason="Read permission denied",
                risk_level="medium",
            )

        return SandboxCheckResult(allowed=True, sanitized_value=abs_path)

    def check_command(self, command: str) -> SandboxCheckResult:
        if not self.check_permission(Permission.COMMAND_EXECUTE):
            return SandboxCheckResult(
                allowed=False,
                reason="Command execution not permitted",
                risk_level="high",
            )

        cmd_lower = command.lower().strip()

        for pattern in DANGEROUS_PATTERNS:
            if pattern.lower() in cmd_lower:
                return SandboxCheckResult(
                    allowed=False,
                    reason=f"Dangerous pattern detected: {pattern}",
                    risk_level="critical",
                )

        cmd_parts = command.split()
        if not cmd_parts:
            return SandboxCheckResult(allowed=False, reason="Empty command", risk_level="low")

        cmd_name = os.path.basename(cmd_parts[0])

        if cmd_name.lower() in DANGEROUS_COMMANDS or cmd_name.lower() in {c.lower() for c in self.config.denied_commands}:
            return SandboxCheckResult(
                allowed=False,
                reason=f"Dangerous command: {cmd_name}",
                risk_level="critical",
            )

        if self.config.allowed_commands:
            if cmd_name.lower() not in {c.lower() for c in self.config.allowed_commands}:
                return SandboxCheckResult(
                    allowed=False,
                    reason=f"Command not in allowed list: {cmd_name}",
                    risk_level="medium",
                )

        return SandboxCheckResult(allowed=True, risk_level="low")

    def check_file_size(self, size_bytes: int) -> SandboxCheckResult:
        size_mb = size_bytes / (1024 * 1024)
        if size_mb > self.config.max_file_size_mb:
            return SandboxCheckResult(
                allowed=False,
                reason=f"File size {size_mb:.2f}MB exceeds limit {self.config.max_file_size_mb}MB",
                risk_level="medium",
            )
        return SandboxCheckResult(allowed=True)

    async def execute_command(
        self,
        command: str,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        timeout: int | None = None,
    ) -> ExecutionResult:
        check = self.check_command(command)
        if not check.allowed:
            return ExecutionResult(
                status=ExecutionStatus.FAILED,
                error_code=ErrorCode.PERMISSION_DENIED,
                error_message=check.reason,
            )

        if cwd:
            path_check = self.check_path_access(cwd, write=False)
            if not path_check.allowed:
                return ExecutionResult(
                    status=ExecutionStatus.FAILED,
                    error_code=ErrorCode.PERMISSION_DENIED,
                    error_message=path_check.reason,
                )
            cwd = path_check.sanitized_value

        timeout_val = timeout or self.config.max_execution_time_seconds

        safe_env = self._build_safe_env(env)

        start_time = datetime.now()
        process_id = f"proc_{id(command)}_{start_time.timestamp()}"

        try:
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
                env=safe_env,
            )

            async with self._lock:
                self._processes[process_id] = process

            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=timeout_val
                )
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
                return ExecutionResult(
                    status=ExecutionStatus.FAILED,
                    error_code=ErrorCode.TIMEOUT_ERROR,
                    error_message=f"Execution timeout ({timeout_val}s)",
                    execution_time_ms=timeout_val * 1000,
                )
            finally:
                async with self._lock:
                    self._processes.pop(process_id, None)

            execution_time = (datetime.now() - start_time).total_seconds() * 1000

            if process.returncode == 0:
                return ExecutionResult(
                    status=ExecutionStatus.SUCCESS,
                    output={
                        "stdout": stdout.decode("utf-8", errors="replace"),
                        "stderr": stderr.decode("utf-8", errors="replace"),
                        "exit_code": process.returncode,
                    },
                    execution_time_ms=execution_time,
                )
            else:
                return ExecutionResult(
                    status=ExecutionStatus.FAILED,
                    error_code=ErrorCode.EXECUTION_ERROR,
                    error_message=stderr.decode("utf-8", errors="replace") or f"Exit code: {process.returncode}",
                    output={
                        "stdout": stdout.decode("utf-8", errors="replace"),
                        "stderr": stderr.decode("utf-8", errors="replace"),
                        "exit_code": process.returncode,
                    },
                    execution_time_ms=execution_time,
                )

        except Exception as e:
            execution_time = (datetime.now() - start_time).total_seconds() * 1000
            return ExecutionResult(
                status=ExecutionStatus.FAILED,
                error_code=ErrorCode.INTERNAL_ERROR,
                error_message=str(e),
                execution_time_ms=execution_time,
            )

    async def execute_file_operation(
        self,
        operation: str,
        path: str,
        content: bytes | None = None,
    ) -> ExecutionResult:
        write_ops = {"write", "create", "delete", "append"}
        is_write = operation.lower() in write_ops

        path_check = self.check_path_access(path, write=is_write)
        if not path_check.allowed:
            return ExecutionResult(
                status=ExecutionStatus.FAILED,
                error_code=ErrorCode.PERMISSION_DENIED,
                error_message=path_check.reason,
            )

        target_path = path_check.sanitized_value

        if self._isolated_dir:
            target_path = os.path.join(self._isolated_dir, os.path.basename(target_path))

        start_time = datetime.now()

        try:
            if operation.lower() == "read":
                if not os.path.exists(target_path):
                    return ExecutionResult(
                        status=ExecutionStatus.FAILED,
                        error_code=ErrorCode.RESOURCE_NOT_FOUND,
                        error_message=f"File not found: {path}",
                    )

                with open(target_path, "rb") as f:
                    data = f.read()

                size_check = self.check_file_size(len(data))
                if not size_check.allowed:
                    return ExecutionResult(
                        status=ExecutionStatus.FAILED,
                        error_code=ErrorCode.VALIDATION_ERROR,
                        error_message=size_check.reason,
                    )

                return ExecutionResult(
                    status=ExecutionStatus.SUCCESS,
                    output={"content": data.decode("utf-8", errors="replace"), "size": len(data)},
                    execution_time_ms=(datetime.now() - start_time).total_seconds() * 1000,
                )

            elif operation.lower() in ("write", "create"):
                if content is None:
                    return ExecutionResult(
                        status=ExecutionStatus.FAILED,
                        error_code=ErrorCode.VALIDATION_ERROR,
                        error_message="No content provided",
                    )

                size_check = self.check_file_size(len(content))
                if not size_check.allowed:
                    return ExecutionResult(
                        status=ExecutionStatus.FAILED,
                        error_code=ErrorCode.VALIDATION_ERROR,
                        error_message=size_check.reason,
                    )

                os.makedirs(os.path.dirname(target_path), exist_ok=True)
                with open(target_path, "wb") as f:
                    f.write(content)

                return ExecutionResult(
                    status=ExecutionStatus.SUCCESS,
                    output={"path": target_path, "size": len(content)},
                    execution_time_ms=(datetime.now() - start_time).total_seconds() * 1000,
                )

            elif operation.lower() == "delete":
                if not self.check_permission(Permission.FILE_DELETE):
                    return ExecutionResult(
                        status=ExecutionStatus.FAILED,
                        error_code=ErrorCode.PERMISSION_DENIED,
                        error_message="Delete permission denied",
                    )

                if not os.path.exists(target_path):
                    return ExecutionResult(
                        status=ExecutionStatus.FAILED,
                        error_code=ErrorCode.RESOURCE_NOT_FOUND,
                        error_message=f"File not found: {path}",
                    )

                os.remove(target_path)
                return ExecutionResult(
                    status=ExecutionStatus.SUCCESS,
                    output={"deleted": target_path},
                    execution_time_ms=(datetime.now() - start_time).total_seconds() * 1000,
                )

            elif operation.lower() == "append":
                if content is None:
                    return ExecutionResult(
                        status=ExecutionStatus.FAILED,
                        error_code=ErrorCode.VALIDATION_ERROR,
                        error_message="No content provided",
                    )

                with open(target_path, "ab") as f:
                    f.write(content)

                return ExecutionResult(
                    status=ExecutionStatus.SUCCESS,
                    output={"path": target_path, "appended_size": len(content)},
                    execution_time_ms=(datetime.now() - start_time).total_seconds() * 1000,
                )

            else:
                return ExecutionResult(
                    status=ExecutionStatus.FAILED,
                    error_code=ErrorCode.VALIDATION_ERROR,
                    error_message=f"Unknown operation: {operation}",
                )

        except Exception as e:
            return ExecutionResult(
                status=ExecutionStatus.FAILED,
                error_code=ErrorCode.INTERNAL_ERROR,
                error_message=str(e),
                execution_time_ms=(datetime.now() - start_time).total_seconds() * 1000,
            )

    def _build_safe_env(self, custom_env: dict[str, str] | None = None) -> dict[str, str]:
        safe_env = {}

        if self.config.allowed_env_vars:
            for var in self.config.allowed_env_vars:
                if var in os.environ:
                    safe_env[var] = os.environ[var]
        else:
            safe_env = {
                "PATH": os.environ.get("PATH", ""),
                "HOME": os.environ.get("HOME", ""),
                "USER": os.environ.get("USER", ""),
                "TEMP": os.environ.get("TEMP", ""),
                "TMP": os.environ.get("TMP", ""),
            }

        if custom_env:
            for key, value in custom_env.items():
                if key in self.config.allowed_env_vars or not self.config.allowed_env_vars:
                    safe_env[key] = value

        if self._isolated_dir:
            safe_env["SANDBOX_DIR"] = self._isolated_dir

        return safe_env

    async def kill_process(self, process_id: str) -> bool:
        async with self._lock:
            process = self._processes.get(process_id)
            if process:
                try:
                    process.terminate()
                    await asyncio.wait_for(process.wait(), timeout=5.0)
                except Exception:
                    try:
                        process.kill()
                    except Exception:
                        pass
                self._processes.pop(process_id, None)
                return True
        return False

    def get_isolated_dir(self) -> str | None:
        return self._isolated_dir

    def get_config(self) -> dict[str, Any]:
        return self.config.to_dict()

    def get_active_processes(self) -> list[str]:
        return list(self._processes.keys())

    def set_permission(self, permission: Permission, granted: bool) -> None:
        if granted:
            self._permissions.add(permission)
        else:
            self._permissions.discard(permission)

    def get_permissions(self) -> set[Permission]:
        return self._permissions.copy()
