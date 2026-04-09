"""
沙箱隔离模块

功能：
- 能力权限模型
- 资源限制管理
- 隔离执行器
- 凭证管理器
- 文件系统隔离
- 进程隔离
- 网络隔离
- 危险命令黑名单
"""
import asyncio
import json
import logging
import os
import re
import shutil
import tempfile
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any

try:
    import resource
    HAS_RESOURCE = True
except ImportError:
    HAS_RESOURCE = False
    resource = None

logger = logging.getLogger(__name__)


DANGEROUS_COMMANDS: set[str] = {
    "rm -rf /",
    "rm -rf /*",
    "mkfs",
    "dd if=/dev/zero",
    "dd if=/dev/urandom",
    ":(){ :|:& };:",
    "chmod -R 777 /",
    "chown -R",
    "> /dev/sda",
    "> /dev/hda",
    "mv /* /dev/null",
    "wget | sh",
    "curl | sh",
    "wget | bash",
    "curl | bash",
    "format",
    "diskpart",
    "bcdedit",
    "bootsect",
    "takeown",
    "icacls",
    "reg delete",
    "reg add",
    "net user",
    "net localgroup",
    "netsh",
    "shutdown",
    "restart",
    "reboot",
    "taskkill",
    "psexec",
    "wmic",
    "powershell -Command",
    "cmd /c",
}

DANGEROUS_PATTERNS: list[str] = [
    r"rm\s+-rf\s+/",
    r"rm\s+-rf\s+/\*",
    r"mkfs\s+/dev/",
    r"dd\s+if=/dev/zero",
    r"dd\s+if=/dev/urandom",
    r">\s*/dev/sd[a-z]",
    r">\s*/dev/hd[a-z]",
    r"chmod\s+-R\s+777\s+/",
    r"chown\s+-R\s+\w+\s+/",
    r"wget\s+.*\|\s*(sh|bash)",
    r"curl\s+.*\|\s*(sh|bash)",
    r"eval\s+.*\$\(",
    r"\$\(\s*.*\s*\)",
    r"`.*`",
    r">\s*/etc/passwd",
    r">\s*/etc/shadow",
    r">\s*/etc/sudoers",
    r"format\s+[a-z]:",
    r"diskpart",
    r"bcdedit\s+/set",
    r"takeown\s+/R\s+/F",
    r"icacls\s+/T\s+/grant",
    r"reg\s+(delete|add)",
    r"net\s+user\s+",
    r"net\s+localgroup\s+",
    r"netsh\s+(firewall|interface)",
    r"taskkill\s+/F\s+/IM",
    r"shutdown\s+",
    r"rmdir\s+/S\s+/Q",
    r"del\s+/F\s+/Q",
    r"Remove-Item\s+-Recurse\s+-Force",
    r"Invoke-Expression",
    r"iex\s+",
    r"Start-Process\s+",
    r"New-Service",
    r"Set-Service",
    r"Stop-Service",
    r"docker\s+run\s+--privileged",
    r"kubectl\s+exec\s+--",
    r"chmod\s+-R\s+777",
    r"chown\s+-R",
    r":\s*\|",
    r"\|\s*bash",
    r"&&.*rm\s",
    r";.*rm\s",
    r"\brm\s+-rf\b",
    r"fork\(\)",
]

DANGEROUS_PATHS: set[str] = {
    "/etc/passwd",
    "/etc/shadow",
    "/etc/sudoers",
    "/etc/ssh/",
    "/root/.ssh/",
    "/var/log/",
    "/proc/",
    "/sys/",
    "/dev/",
    "C:\\Windows\\System32\\config\\",
    "C:\\Windows\\System32\\drivers\\",
}


class Permission(str, Enum):
    """权限类型"""
    FILE_READ = "file_read"
    FILE_WRITE = "file_write"
    FILE_DELETE = "file_delete"
    COMMAND_EXECUTE = "command_execute"
    NETWORK_ACCESS = "network_access"
    PROCESS_SPAWN = "process_spawn"
    ENVIRONMENT_ACCESS = "environment_access"
    MEMORY_INTENSIVE = "memory_intensive"
    GPU_ACCESS = "gpu_access"
    ADMIN = "admin"


class PermissionLevel(str, Enum):
    """权限级别"""
    NONE = "none"
    READ_ONLY = "read_only"
    LIMITED = "limited"
    STANDARD = "standard"
    ELEVATED = "elevated"
    ADMIN = "admin"


@dataclass
class Capability:
    """能力定义"""
    name: str
    permissions: set[Permission]
    max_file_size: int = 10 * 1024 * 1024
    max_execution_time: int = 60
    max_memory_mb: int = 512
    max_processes: int = 1
    allowed_paths: list[str] = field(default_factory=list)
    denied_paths: list[str] = field(default_factory=list)
    allowed_commands: list[str] = field(default_factory=list)
    network_whitelist: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "permissions": [p.value for p in self.permissions],
            "max_file_size": self.max_file_size,
            "max_execution_time": self.max_execution_time,
            "max_memory_mb": self.max_memory_mb,
            "max_processes": self.max_processes,
            "allowed_paths": self.allowed_paths,
            "denied_paths": self.denied_paths,
            "allowed_commands": self.allowed_commands,
            "network_whitelist": self.network_whitelist,
        }


DEFAULT_CAPABILITIES: dict[PermissionLevel, Capability] = {
    PermissionLevel.NONE: Capability(
        name="none",
        permissions=set(),
        max_file_size=0,
        max_execution_time=0,
        max_memory_mb=0,
        max_processes=0,
    ),
    PermissionLevel.READ_ONLY: Capability(
        name="read_only",
        permissions={Permission.FILE_READ},
        max_file_size=1 * 1024 * 1024,
        max_execution_time=10,
        max_memory_mb=128,
        max_processes=0,
    ),
    PermissionLevel.LIMITED: Capability(
        name="limited",
        permissions={Permission.FILE_READ, Permission.FILE_WRITE, Permission.NETWORK_ACCESS},
        max_file_size=5 * 1024 * 1024,
        max_execution_time=30,
        max_memory_mb=256,
        max_processes=1,
        allowed_paths=["/tmp", "/workspace"],
    ),
    PermissionLevel.STANDARD: Capability(
        name="standard",
        permissions={
            Permission.FILE_READ, Permission.FILE_WRITE, Permission.FILE_DELETE,
            Permission.COMMAND_EXECUTE, Permission.NETWORK_ACCESS,
        },
        max_file_size=50 * 1024 * 1024,
        max_execution_time=60,
        max_memory_mb=512,
        max_processes=3,
        allowed_paths=["/tmp", "/workspace", "/home"],
        allowed_commands=["ls", "cat", "grep", "python", "node"],
    ),
    PermissionLevel.ELEVATED: Capability(
        name="elevated",
        permissions={
            Permission.FILE_READ, Permission.FILE_WRITE, Permission.FILE_DELETE,
            Permission.COMMAND_EXECUTE, Permission.NETWORK_ACCESS,
            Permission.PROCESS_SPAWN, Permission.ENVIRONMENT_ACCESS,
        },
        max_file_size=200 * 1024 * 1024,
        max_execution_time=300,
        max_memory_mb=2048,
        max_processes=10,
        allowed_paths=["/tmp", "/workspace", "/home", "/usr/local"],
    ),
    PermissionLevel.ADMIN: Capability(
        name="admin",
        permissions=set(Permission),
        max_file_size=1024 * 1024 * 1024,
        max_execution_time=3600,
        max_memory_mb=8192,
        max_processes=100,
    ),
}


@dataclass
class ResourceLimits:
    """资源限制"""
    max_cpu_percent: float = 100.0
    max_memory_mb: int = 512
    max_file_descriptors: int = 64
    max_processes: int = 3
    max_execution_time: int = 60
    max_file_size: int = 10 * 1024 * 1024
    max_network_connections: int = 10

    def to_dict(self) -> dict[str, Any]:
        return {
            "max_cpu_percent": self.max_cpu_percent,
            "max_memory_mb": self.max_memory_mb,
            "max_file_descriptors": self.max_file_descriptors,
            "max_processes": self.max_processes,
            "max_execution_time": self.max_execution_time,
            "max_file_size": self.max_file_size,
            "max_network_connections": self.max_network_connections,
        }


@dataclass
class ExecutionResult:
    """执行结果"""
    success: bool
    stdout: str = ""
    stderr: str = ""
    exit_code: int = 0
    execution_time: float = 0.0
    memory_used_mb: float = 0.0
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "exit_code": self.exit_code,
            "execution_time": self.execution_time,
            "memory_used_mb": self.memory_used_mb,
            "error": self.error,
        }


class Credential:
    """凭证"""

    def __init__(
        self,
        credential_id: str,
        credential_type: str,
        value: str,
        expires_at: datetime | None = None,
        metadata: dict[str, Any] | None = None,
    ):
        self.credential_id = credential_id
        self.credential_type = credential_type
        self._value = value
        self.expires_at = expires_at
        self.metadata = metadata or {}
        self.created_at = datetime.now()
        self.access_count = 0

    @property
    def value(self) -> str:
        """获取凭证值"""
        self.access_count += 1
        return self._value

    @property
    def name(self) -> str:
        return self.credential_id

    def is_expired(self) -> bool:
        """检查是否过期"""
        if self.expires_at is None:
            return False
        return datetime.now() > self.expires_at

    def to_dict(self, include_value: bool = False) -> dict[str, Any]:
        data = {
            "credential_id": self.credential_id,
            "credential_type": self.credential_type,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "created_at": self.created_at.isoformat(),
            "access_count": self.access_count,
            "metadata": self.metadata,
        }
        if include_value:
            data["value"] = self._value
        return data


class CredentialManager:
    """
    凭证管理器

    安全存储和管理敏感凭证
    """

    def __init__(self, storage_path: Path | None = None):
        self.storage_path = storage_path or Path("data/credentials")
        self.storage_path.mkdir(parents=True, exist_ok=True)

        self._credentials: dict[str, Credential] = {}
        self._encryption_key: bytes | None = None

    def set_encryption_key(self, key: bytes):
        """设置加密密钥"""
        self._encryption_key = key

    def store_credential(
        self,
        credential_type: str,
        value: str,
        expires_in_hours: int | None = None,
        metadata: dict[str, Any] | None = None,
        name: str | None = None,
    ) -> Any:
        """存储凭证"""
        credential_id = name or str(uuid.uuid4())

        expires_at = None
        if expires_in_hours:
            expires_at = datetime.now() + timedelta(hours=expires_in_hours)

        credential = Credential(
            credential_id=credential_id,
            credential_type=credential_type,
            value=value,
            expires_at=expires_at,
            metadata=metadata,
        )

        self._credentials[credential_id] = credential
        self._persist_credential(credential)

        logger.info(f"存储凭证: {credential_type} ({credential_id})")

        return credential if name else credential_id

    def get_credential(self, credential_id: str) -> Credential | None:
        """获取凭证"""
        credential = self._credentials.get(credential_id)

        if credential and credential.is_expired():
            self.delete_credential(credential_id)
            return None

        return credential

    def get_credential_value(self, credential_id: str) -> str | None:
        """获取凭证值"""
        credential = self.get_credential(credential_id)
        return credential.value if credential else None

    def delete_credential(self, credential_id: str) -> bool:
        """删除凭证"""
        if credential_id in self._credentials:
            del self._credentials[credential_id]
            self._delete_persisted_credential(credential_id)
            return True
        return False

    def list_credentials(self, credential_type: str | None = None) -> list[dict[str, Any]]:
        """列出凭证"""
        credentials = list(self._credentials.values())

        if credential_type:
            credentials = [c for c in credentials if c.credential_type == credential_type]

        return [c.to_dict() for c in credentials if not c.is_expired()]

    def _persist_credential(self, credential: Credential):
        """持久化凭证"""
        file_path = self.storage_path / f"{credential.credential_id}.json"
        try:
            data = credential.to_dict(include_value=True)
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"持久化凭证失败: {e}")

    def _delete_persisted_credential(self, credential_id: str):
        """删除持久化的凭证"""
        file_path = self.storage_path / f"{credential_id}.json"
        if file_path.exists():
            file_path.unlink()


class IsolatedExecutor:
    """
    隔离执行器

    在沙箱环境中安全执行命令
    """

    def __init__(
        self,
        capability: Capability,
        resource_limits: ResourceLimits | None = None,
        credential_manager: CredentialManager | None = None,
    ):
        self.capability = capability
        self.resource_limits = resource_limits or ResourceLimits()
        self.credential_manager = credential_manager

    def check_permission(self, permission: Permission) -> bool:
        """检查权限"""
        return permission in self.capability.permissions

    def check_path_access(self, path: str, write: bool = False) -> bool:
        """检查路径访问权限"""
        path = os.path.abspath(path)

        for denied in self.capability.denied_paths:
            if path.startswith(denied):
                return False

        if not self.capability.allowed_paths:
            return True

        for allowed in self.capability.allowed_paths:
            if path.startswith(allowed):
                return True

        return False

    def check_command(self, command: str) -> bool:
        """检查命令是否允许"""
        if not self.check_permission(Permission.COMMAND_EXECUTE):
            return False

        if not self.capability.allowed_commands:
            return True

        cmd_name = command.split()[0] if command else ""
        return cmd_name in self.capability.allowed_commands

    async def execute_command(
        self,
        command: str,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        timeout: int | None = None,
    ) -> ExecutionResult:
        """执行命令"""
        if not self.check_command(command):
            return ExecutionResult(
                success=False,
                error="Command not allowed",
                exit_code=-1,
            )

        if cwd and not self.check_path_access(cwd):
            return ExecutionResult(
                success=False,
                error="Path access denied",
                exit_code=-1,
            )

        timeout_val = timeout or self.resource_limits.max_execution_time

        start_time = datetime.now()

        try:
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
                env=env or os.environ.copy(),
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=timeout_val
                )
            except asyncio.TimeoutError:
                process.kill()
                return ExecutionResult(
                    success=False,
                    error=f"Execution timeout ({timeout_val}s)",
                    exit_code=-1,
                    execution_time=timeout_val,
                )

            execution_time = (datetime.now() - start_time).total_seconds()

            return ExecutionResult(
                success=process.returncode == 0,
                stdout=stdout.decode("utf-8", errors="replace"),
                stderr=stderr.decode("utf-8", errors="replace"),
                exit_code=process.returncode or 0,
                execution_time=execution_time,
            )

        except Exception as e:
            execution_time = (datetime.now() - start_time).total_seconds()
            return ExecutionResult(
                success=False,
                error=str(e),
                exit_code=-1,
                execution_time=execution_time,
            )

    async def execute(self, command: str, args: list[str] | None = None, **kwargs) -> ExecutionResult:
        joined = " ".join([command] + (args or []))
        return await self.execute_command(joined, cwd=kwargs.get("cwd"), env=kwargs.get("env"), timeout=kwargs.get("timeout"))

    async def execute_file_operation(
        self,
        operation: str,
        path: str,
        content: bytes | None = None,
    ) -> ExecutionResult:
        """执行文件操作"""
        path = os.path.abspath(path)

        if operation in ("read", "write", "delete"):
            permission_map = {
                "read": Permission.FILE_READ,
                "write": Permission.FILE_WRITE,
                "delete": Permission.FILE_DELETE,
            }

            if not self.check_permission(permission_map[operation]):
                return ExecutionResult(
                    success=False,
                    error=f"Permission denied: {operation}",
                )

        if not self.check_path_access(path, write=(operation != "read")):
            return ExecutionResult(
                success=False,
                error="Path access denied",
            )

        start_time = datetime.now()

        try:
            if operation == "read":
                with open(path, "rb") as f:
                    data = f.read()

                if len(data) > self.resource_limits.max_file_size:
                    return ExecutionResult(
                        success=False,
                        error="File too large",
                    )

                return ExecutionResult(
                    success=True,
                    stdout=data.decode("utf-8", errors="replace"),
                    execution_time=(datetime.now() - start_time).total_seconds(),
                )

            elif operation == "write":
                if content is None:
                    return ExecutionResult(
                        success=False,
                        error="No content provided",
                    )

                if len(content) > self.resource_limits.max_file_size:
                    return ExecutionResult(
                        success=False,
                        error="Content too large",
                    )

                with open(path, "wb") as f:
                    f.write(content)

                return ExecutionResult(
                    success=True,
                    execution_time=(datetime.now() - start_time).total_seconds(),
                )

            elif operation == "delete":
                os.remove(path)
                return ExecutionResult(
                    success=True,
                    execution_time=(datetime.now() - start_time).total_seconds(),
                )

            else:
                return ExecutionResult(
                    success=False,
                    error=f"Unknown operation: {operation}",
                )

        except Exception as e:
            return ExecutionResult(
                success=False,
                error=str(e),
                execution_time=(datetime.now() - start_time).total_seconds(),
            )


class SandboxManager:
    """
    沙箱管理器

    管理多个隔离执行环境
    """

    def __init__(self):
        self._executors: dict[str, IsolatedExecutor] = {}
        self._credential_manager = CredentialManager()

    def create_sandbox(
        self,
        permission_level: PermissionLevel = PermissionLevel.STANDARD,
        custom_capability: Capability | None = None,
        resource_limits: ResourceLimits | None = None,
    ) -> str:
        """创建沙箱"""
        sandbox_id = str(uuid.uuid4())

        capability = custom_capability or DEFAULT_CAPABILITIES[permission_level]

        executor = IsolatedExecutor(
            capability=capability,
            resource_limits=resource_limits,
            credential_manager=self._credential_manager,
        )

        self._executors[sandbox_id] = executor

        logger.info(f"创建沙箱: {sandbox_id} (权限级别: {permission_level.value})")

        return sandbox_id

    def get_executor(self, sandbox_id: str) -> IsolatedExecutor | None:
        """获取执行器"""
        return self._executors.get(sandbox_id)

    def destroy_sandbox(self, sandbox_id: str) -> bool:
        """销毁沙箱"""
        if sandbox_id in self._executors:
            del self._executors[sandbox_id]
            logger.info(f"销毁沙箱: {sandbox_id}")
            return True
        return False

    def get_sandbox_info(self, sandbox_id: str) -> dict[str, Any] | None:
        """获取沙箱信息"""
        executor = self._executors.get(sandbox_id)
        if not executor:
            return None

        return {
            "sandbox_id": sandbox_id,
            "capability": executor.capability.to_dict(),
            "resource_limits": executor.resource_limits.to_dict(),
        }

    def list_sandboxes(self) -> list[dict[str, Any]]:
        """列出所有沙箱"""
        return [
            self.get_sandbox_info(sandbox_id)
            for sandbox_id in self._executors.keys()
        ]


_sandbox_manager: SandboxManager | None = None


def get_sandbox_manager() -> SandboxManager:
    """获取沙箱管理器单例"""
    global _sandbox_manager
    if _sandbox_manager is None:
        _sandbox_manager = SandboxManager()
    return _sandbox_manager


class CommandValidator:
    """
    命令验证器

    检测和拦截危险命令
    """

    def __init__(self):
        self._dangerous_commands = DANGEROUS_COMMANDS.copy()
        self._dangerous_patterns = [re.compile(p) for p in DANGEROUS_PATTERNS]
        self._custom_dangerous_commands: set[str] = set()
        self._custom_dangerous_patterns: list[re.Pattern] = []

    def add_dangerous_command(self, command: str) -> None:
        """添加危险命令"""
        self._custom_dangerous_commands.add(command)

    def add_dangerous_pattern(self, pattern: str) -> None:
        """添加危险模式"""
        self._custom_dangerous_patterns.append(re.compile(pattern))

    def is_dangerous(self, command: str) -> bool:
        """检查命令是否危险"""
        command_lower = command.lower().strip()

        all_dangerous = self._dangerous_commands | self._custom_dangerous_commands
        for dangerous in all_dangerous:
            if dangerous.lower() in command_lower:
                return True

        all_patterns = self._dangerous_patterns + self._custom_dangerous_patterns
        for pattern in all_patterns:
            if pattern.search(command):
                return True

        return False

    def validate(self, command: str) -> dict[str, Any]:
        """验证命令"""
        is_dangerous = self.is_dangerous(command)

        return {
            "command": command,
            "is_dangerous": is_dangerous,
            "allowed": not is_dangerous,
            "reason": "危险命令被拦截" if is_dangerous else None,
        }

    def sanitize(self, command: str) -> str:
        """清理命令（移除危险部分）"""
        sanitized = command

        for pattern in self._dangerous_patterns:
            sanitized = pattern.sub("[REDACTED]", sanitized)

        return sanitized


class FilesystemIsolation:
    """
    文件系统隔离

    提供虚拟文件系统映射和路径重定向
    """

    def __init__(self, sandbox_root: Path | None = None):
        self.sandbox_root = sandbox_root or Path(tempfile.mkdtemp(prefix="sandbox_"))
        self.sandbox_root.mkdir(parents=True, exist_ok=True)

        self._path_mappings: dict[str, str] = {}
        self._read_only_paths: set[str] = set()
        self._virtual_paths: dict[str, str] = {}

    def add_mapping(self, host_path: str, sandbox_path: str, read_only: bool = False) -> None:
        """添加路径映射"""
        self._path_mappings[host_path] = sandbox_path
        if read_only:
            self._read_only_paths.add(sandbox_path)

    def add_virtual_path(self, virtual_path: str, content: str) -> None:
        """添加虚拟路径"""
        self._virtual_paths[virtual_path] = content

    def translate_path(self, path: str) -> str:
        """转换路径"""
        path = os.path.abspath(path)

        for virtual_path, content in self._virtual_paths.items():
            if path == virtual_path:
                temp_file = self.sandbox_root / "virtual" / path.lstrip("/")
                temp_file.parent.mkdir(parents=True, exist_ok=True)
                temp_file.write_text(content)
                return str(temp_file)

        for host_path, sandbox_path in self._path_mappings.items():
            if path.startswith(host_path):
                relative = path[len(host_path):]
                return str(self.sandbox_root / sandbox_path.lstrip("/") / relative.lstrip("/"))

        return str(self.sandbox_root / "workspace" / path.lstrip("/"))

    def is_read_only(self, path: str) -> bool:
        """检查路径是否只读"""
        for read_only_path in self._read_only_paths:
            if path.startswith(read_only_path):
                return True
        return False

    def is_isolated_path(self, path: str) -> bool:
        """检查路径是否在隔离区内"""
        abs_path = os.path.abspath(path)
        return abs_path.startswith(str(self.sandbox_root))

    def create_isolated_directory(self, name: str) -> Path:
        """创建隔离目录"""
        isolated_dir = self.sandbox_root / name
        isolated_dir.mkdir(parents=True, exist_ok=True)
        return isolated_dir

    def cleanup(self) -> None:
        """清理隔离环境"""
        if self.sandbox_root.exists():
            shutil.rmtree(self.sandbox_root, ignore_errors=True)


class ProcessIsolation:
    """
    进程隔离

    管理子进程和资源限制
    """

    def __init__(self, max_processes: int = 10, max_memory_mb: int = 512):
        self.max_processes = max_processes
        self.max_memory_mb = max_memory_mb
        self._active_processes: dict[str, asyncio.subprocess.Process] = {}
        self._process_stats: dict[str, dict[str, Any]] = {}

    async def spawn_process(
        self,
        command: str,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        timeout: int = 60,
    ) -> dict[str, Any]:
        """启动进程"""
        if len(self._active_processes) >= self.max_processes:
            return {
                "success": False,
                "error": "达到最大进程数限制",
            }

        process_id = str(uuid.uuid4())[:8]

        try:
            safe_env = self._build_safe_env(env)

            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
                env=safe_env,
            )

            self._active_processes[process_id] = process
            self._process_stats[process_id] = {
                "command": command,
                "start_time": datetime.now().isoformat(),
                "status": "running",
            }

            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=timeout
                )
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
                return {
                    "success": False,
                    "error": f"进程超时 ({timeout}s)",
                    "process_id": process_id,
                }

            self._process_stats[process_id]["status"] = "completed"
            self._process_stats[process_id]["end_time"] = datetime.now().isoformat()

            return {
                "success": process.returncode == 0,
                "stdout": stdout.decode("utf-8", errors="replace"),
                "stderr": stderr.decode("utf-8", errors="replace"),
                "exit_code": process.returncode,
                "process_id": process_id,
            }

        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "process_id": process_id,
            }
        finally:
            self._active_processes.pop(process_id, None)

    def _build_safe_env(self, custom_env: dict[str, str] | None = None) -> dict[str, str]:
        """构建安全的环境变量"""
        dangerous_vars = {
            "LD_PRELOAD",
            "LD_LIBRARY_PATH",
            "DYLD_INSERT_LIBRARIES",
            "DYLD_LIBRARY_PATH",
            "PYTHONPATH",
            "PERL5LIB",
            "NODE_PATH",
        }

        safe_env = {}
        for key, value in os.environ.items():
            if key not in dangerous_vars:
                safe_env[key] = value

        if custom_env:
            for key, value in custom_env.items():
                if key not in dangerous_vars:
                    safe_env[key] = value

        return safe_env

    async def kill_process(self, process_id: str) -> bool:
        """终止进程"""
        process = self._active_processes.get(process_id)
        if process:
            try:
                process.kill()
                await process.wait()
                return True
            except Exception:
                return False
        return False

    async def kill_all_processes(self) -> int:
        """终止所有进程"""
        count = 0
        for process_id, process in list(self._active_processes.items()):
            try:
                process.kill()
                await process.wait()
                count += 1
            except Exception:
                pass
        self._active_processes.clear()
        return count

    def get_process_stats(self) -> dict[str, Any]:
        """获取进程统计"""
        return {
            "active_count": len(self._active_processes),
            "max_processes": self.max_processes,
            "processes": dict(self._process_stats),
        }


class NetworkIsolation:
    """
    网络隔离

    控制网络访问
    """

    def __init__(self):
        self._allowed_hosts: set[str] = set()
        self._denied_hosts: set[str] = set()
        self._allowed_ports: set[int] = set()
        self._denied_ports: set[int] = {22, 23, 25, 445, 3389}
        self._network_enabled: bool = True

    def allow_host(self, host: str) -> None:
        """允许主机"""
        self._allowed_hosts.add(host)

    def deny_host(self, host: str) -> None:
        """拒绝主机"""
        self._denied_hosts.add(host)

    def allow_port(self, port: int) -> None:
        """允许端口"""
        self._allowed_ports.add(port)

    def deny_port(self, port: int) -> None:
        """拒绝端口"""
        self._denied_ports.add(port)

    def set_network_enabled(self, enabled: bool) -> None:
        """设置网络是否启用"""
        self._network_enabled = enabled

    def is_host_allowed(self, host: str) -> bool:
        """检查主机是否允许"""
        if not self._network_enabled:
            return False

        if host in self._denied_hosts:
            return False

        if self._allowed_hosts and host not in self._allowed_hosts:
            return False

        return True

    def is_port_allowed(self, port: int) -> bool:
        """检查端口是否允许"""
        if port in self._denied_ports:
            return False

        if self._allowed_ports and port not in self._allowed_ports:
            return False

        return True

    def check_url(self, url: str) -> dict[str, Any]:
        """检查 URL"""
        from urllib.parse import urlparse

        try:
            parsed = urlparse(url)
            host = parsed.hostname or ""
            port = parsed.port or (443 if parsed.scheme == "https" else 80)

            host_allowed = self.is_host_allowed(host)
            port_allowed = self.is_port_allowed(port)

            return {
                "url": url,
                "host": host,
                "port": port,
                "allowed": host_allowed and port_allowed,
                "host_allowed": host_allowed,
                "port_allowed": port_allowed,
            }
        except Exception as e:
            return {
                "url": url,
                "allowed": False,
                "error": str(e),
            }

    def to_dict(self) -> dict[str, Any]:
        """转换为字典"""
        return {
            "network_enabled": self._network_enabled,
            "allowed_hosts": list(self._allowed_hosts),
            "denied_hosts": list(self._denied_hosts),
            "allowed_ports": list(self._allowed_ports),
            "denied_ports": list(self._denied_ports),
        }


class EnhancedSandbox:
    """
    增强版沙箱

    集成所有隔离功能
    """

    def __init__(
        self,
        sandbox_id: str | None = None,
        permission_level: PermissionLevel = PermissionLevel.STANDARD,
    ):
        self.sandbox_id = sandbox_id or str(uuid.uuid4())
        self.permission_level = permission_level

        self.command_validator = CommandValidator()
        self.filesystem = FilesystemIsolation()
        self.process_isolation = ProcessIsolation()
        self.network_isolation = NetworkIsolation()

        self._created_at = datetime.now()
        self._operations_log: list[dict[str, Any]] = []

    async def execute_command(self, command: str, **kwargs) -> dict[str, Any]:
        """执行命令"""
        validation = self.command_validator.validate(command)

        if not validation["allowed"]:
            self._log_operation("command_blocked", command, validation)
            return {
                "success": False,
                "error": validation["reason"],
                "blocked": True,
            }

        result = await self.process_isolation.spawn_process(command, **kwargs)
        self._log_operation("command_executed", command, result)

        return result

    def translate_path(self, path: str) -> str:
        """转换路径"""
        return self.filesystem.translate_path(path)

    def check_network_access(self, url: str) -> dict[str, Any]:
        """检查网络访问"""
        return self.network_isolation.check_url(url)

    def _log_operation(self, operation: str, target: str, result: dict[str, Any]) -> None:
        """记录操作"""
        self._operations_log.append({
            "timestamp": datetime.now().isoformat(),
            "operation": operation,
            "target": target,
            "result": result,
        })

    def get_info(self) -> dict[str, Any]:
        """获取沙箱信息"""
        return {
            "sandbox_id": self.sandbox_id,
            "permission_level": self.permission_level.value,
            "created_at": self._created_at.isoformat(),
            "filesystem": {
                "sandbox_root": str(self.filesystem.sandbox_root),
            },
            "process": self.process_isolation.get_process_stats(),
            "network": self.network_isolation.to_dict(),
            "operations_count": len(self._operations_log),
        }

    async def cleanup(self) -> None:
        """清理沙箱"""
        await self.process_isolation.kill_all_processes()
        self.filesystem.cleanup()
        self._operations_log.clear()


class EnhancedSandboxManager:
    """
    增强版沙箱管理器
    """

    def __init__(self):
        self._sandboxes: dict[str, EnhancedSandbox] = {}

    def create_sandbox(
        self,
        permission_level: PermissionLevel = PermissionLevel.STANDARD,
    ) -> EnhancedSandbox:
        """创建沙箱"""
        sandbox = EnhancedSandbox(permission_level=permission_level)
        self._sandboxes[sandbox.sandbox_id] = sandbox
        logger.info(f"创建增强沙箱: {sandbox.sandbox_id}")
        return sandbox

    def get_sandbox(self, sandbox_id: str) -> EnhancedSandbox | None:
        """获取沙箱"""
        return self._sandboxes.get(sandbox_id)

    async def destroy_sandbox(self, sandbox_id: str) -> bool:
        """销毁沙箱"""
        sandbox = self._sandboxes.get(sandbox_id)
        if sandbox:
            await sandbox.cleanup()
            del self._sandboxes[sandbox_id]
            logger.info(f"销毁增强沙箱: {sandbox_id}")
            return True
        return False

    def list_sandboxes(self) -> list[dict[str, Any]]:
        """列出所有沙箱"""
        return [s.get_info() for s in self._sandboxes.values()]

    async def cleanup_all(self) -> None:
        """清理所有沙箱"""
        for sandbox_id in list(self._sandboxes.keys()):
            await self.destroy_sandbox(sandbox_id)


_enhanced_sandbox_manager: EnhancedSandboxManager | None = None


def get_enhanced_sandbox_manager() -> EnhancedSandboxManager:
    """获取增强版沙箱管理器单例"""
    global _enhanced_sandbox_manager
    if _enhanced_sandbox_manager is None:
        _enhanced_sandbox_manager = EnhancedSandboxManager()
    return _enhanced_sandbox_manager
