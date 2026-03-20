"""
技能执行安全沙箱模�?
功能�?- 执行环境隔离
- 资源限制（内存、CPU、时间）
- 危险操作拦截
- 执行权限控制
- 系统调用过滤
"""
import asyncio
import os
import sys
import threading
import traceback
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Union

if sys.platform != "win32":
    import resource
else:
    resource = None


class SandboxPermission(str, Enum):
    """沙箱权限"""
    FILE_READ = "file_read"
    FILE_WRITE = "file_write"
    FILE_DELETE = "file_delete"
    NETWORK = "network"
    SUBPROCESS = "subprocess"
    ENVIRONMENT = "environment"
    SYSTEM_INFO = "system_info"


class SandboxViolationType(str, Enum):
    """沙箱违规类型"""
    FORBIDDEN_PATH = "forbidden_path"
    FORBIDDEN_OPERATION = "forbidden_operation"
    RESOURCE_LIMIT = "resource_limit"
    TIME_LIMIT = "time_limit"
    MEMORY_LIMIT = "memory_limit"
    FORBIDDEN_IMPORT = "forbidden_import"
    FORBIDDEN_SYSCALL = "forbidden_syscall"


@dataclass
class SandboxViolation:
    """沙箱违规记录"""
    violation_type: SandboxViolationType
    message: str
    details: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class ResourceLimits:
    """资源限制配置"""
    max_memory_mb: int = 512
    max_cpu_seconds: int = 30
    max_file_size_mb: int = 10
    max_open_files: int = 100
    max_subprocesses: int = 0
    network_access: bool = False


@dataclass
class SandboxConfig:
    """沙箱配置"""
    enabled: bool = True
    permissions: Set[SandboxPermission] = field(default_factory=lambda: {
        SandboxPermission.FILE_READ,
        SandboxPermission.SYSTEM_INFO,
    })
    allowed_paths: Set[Path] = field(default_factory=set)
    forbidden_paths: Set[Path] = field(default_factory=set)
    forbidden_modules: Set[str] = field(default_factory=lambda: {
        "os.system",
        "subprocess",
        "socket",
        "ctypes",
        "multiprocessing",
    })
    resource_limits: ResourceLimits = field(default_factory=ResourceLimits)
    working_directory: Optional[Path] = None
    environment_vars: Dict[str, str] = field(default_factory=dict)


@dataclass
class SandboxResult:
    """沙箱执行结果"""
    success: bool
    result: Any = None
    error: Optional[str] = None
    error_type: Optional[str] = None
    violations: List[SandboxViolation] = field(default_factory=list)
    resource_usage: Dict[str, Any] = field(default_factory=dict)
    execution_time: float = 0.0


class SandboxViolationError(Exception):
    """沙箱违规异常"""
    
    def __init__(self, violation: SandboxViolation):
        self.violation = violation
        super().__init__(violation.message)


class ExecutionSandbox:
    """执行沙箱"""
    
    DEFAULT_FORBIDDEN_PATHS = {
        Path("/etc"),
        Path("/root"),
        Path("/var/log"),
        Path("C:/Windows"),
        Path("C:/Program Files"),
    }
    
    def __init__(self, config: Optional[SandboxConfig] = None):
        self._config = config or SandboxConfig()
        self._violations: List[SandboxViolation] = []
        self._original_limits: Dict[str, Any] = {}
        self._lock = threading.Lock()
        
        self._forbidden_paths = self.DEFAULT_FORBIDDEN_PATHS | self._config.forbidden_paths
    
    def _check_permission(self, permission: SandboxPermission) -> bool:
        """检查权�?""
        return permission in self._config.permissions
    
    def _record_violation(
        self,
        violation_type: SandboxViolationType,
        message: str,
        details: Optional[Dict[str, Any]] = None,
    ):
        """记录违规"""
        violation = SandboxViolation(
            violation_type=violation_type,
            message=message,
            details=details or {},
        )
        with self._lock:
            self._violations.append(violation)
        raise SandboxViolationError(violation)
    
    def validate_path(
        self,
        path: Union[str, Path],
        operation: str = "read",
    ) -> Path:
        """验证路径访问权限"""
        path = Path(path).resolve()
        
        for forbidden in self._forbidden_paths:
            try:
                path.relative_to(forbidden)
                self._record_violation(
                    SandboxViolationType.FORBIDDEN_PATH,
                    f"禁止访问路径: {path}",
                    {"path": str(path), "operation": operation},
                )
            except ValueError:
                pass
        
        if self._config.allowed_paths:
            allowed = False
            for allowed_path in self._config.allowed_paths:
                try:
                    path.relative_to(allowed_path)
                    allowed = True
                    break
                except ValueError:
                    pass
            
            if not allowed:
                self._record_violation(
                    SandboxViolationType.FORBIDDEN_PATH,
                    f"路径不在允许列表�? {path}",
                    {"path": str(path), "operation": operation},
                )
        
        if operation == "read" and not self._check_permission(SandboxPermission.FILE_READ):
            self._record_violation(
                SandboxViolationType.FORBIDDEN_OPERATION,
                f"禁止文件读取操作: {path}",
                {"path": str(path), "operation": operation},
            )
        
        if operation in ("write", "create") and not self._check_permission(SandboxPermission.FILE_WRITE):
            self._record_violation(
                SandboxViolationType.FORBIDDEN_OPERATION,
                f"禁止文件写入操作: {path}",
                {"path": str(path), "operation": operation},
            )
        
        if operation == "delete" and not self._check_permission(SandboxPermission.FILE_DELETE):
            self._record_violation(
                SandboxViolationType.FORBIDDEN_OPERATION,
                f"禁止文件删除操作: {path}",
                {"path": str(path), "operation": operation},
            )
        
        return path
    
    def validate_import(self, module_name: str):
        """验证模块导入"""
        for forbidden in self._config.forbidden_modules:
            if module_name.startswith(forbidden) or module_name == forbidden:
                self._record_violation(
                    SandboxViolationType.FORBIDDEN_IMPORT,
                    f"禁止导入模块: {module_name}",
                    {"module": module_name},
                )
    
    def validate_network_access(self, host: Optional[str] = None):
        """验证网络访问"""
        if not self._check_permission(SandboxPermission.NETWORK):
            self._record_violation(
                SandboxViolationType.FORBIDDEN_OPERATION,
                f"禁止网络访问",
                {"host": host},
            )
    
    def validate_subprocess(self, command: Optional[str] = None):
        """验证子进程创�?""
        if not self._check_permission(SandboxPermission.SUBPROCESS):
            self._record_violation(
                SandboxViolationType.FORBIDDEN_OPERATION,
                f"禁止创建子进�?,
                {"command": command},
            )
    
    @contextmanager
    def resource_context(self):
        """资源限制上下�?""
        if not self._config.enabled:
            yield
            return
        
        self._original_limits = {}
        
        try:
            if sys.platform != "win32" and resource is not None:
                limits = self._config.resource_limits
                
                try:
                    self._original_limits["RLIMIT_AS"] = resource.getrlimit(resource.RLIMIT_AS)
                    memory_bytes = limits.max_memory_mb * 1024 * 1024
                    resource.setrlimit(resource.RLIMIT_AS, (memory_bytes, memory_bytes))
                except (ValueError, OSError, AttributeError):
                    pass
                
                try:
                    self._original_limits["RLIMIT_CPU"] = resource.getrlimit(resource.RLIMIT_CPU)
                    resource.setrlimit(resource.RLIMIT_CPU, (limits.max_cpu_seconds, limits.max_cpu_seconds + 1))
                except (ValueError, OSError, AttributeError):
                    pass
                
                try:
                    self._original_limits["RLIMIT_NOFILE"] = resource.getrlimit(resource.RLIMIT_NOFILE)
                    resource.setrlimit(resource.RLIMIT_NOFILE, (limits.max_open_files, limits.max_open_files))
                except (ValueError, OSError, AttributeError):
                    pass
            
            yield
        
        finally:
            if sys.platform != "win32" and resource is not None:
                for limit_name, (soft, hard) in self._original_limits.items():
                    try:
                        rlimit = getattr(resource, limit_name)
                        resource.setrlimit(rlimit, (soft, hard))
                    except (ValueError, OSError, AttributeError):
                        pass
    
    def get_resource_usage(self) -> Dict[str, Any]:
        """获取资源使用情况"""
        usage = {}
        
        try:
            if sys.platform != "win32" and resource is not None:
                rusage = resource.getrusage(resource.RUSAGE_SELF)
                usage["memory_mb"] = rusage.ru_maxrss / 1024
                usage["cpu_time_user"] = rusage.ru_utime
                usage["cpu_time_system"] = rusage.ru_stime
                usage["page_faults"] = rusage.ru_majflt
            else:
                try:
                    import psutil
                    process = psutil.Process()
                    mem_info = process.memory_info()
                    usage["memory_mb"] = mem_info.rss / 1024 / 1024
                    usage["cpu_percent"] = process.cpu_percent()
                except ImportError:
                    pass
        except Exception:
            pass
        
        return usage
    
    def get_violations(self) -> List[SandboxViolation]:
        """获取违规记录"""
        with self._lock:
            return list(self._violations)
    
    def clear_violations(self):
        """清除违规记录"""
        with self._lock:
            self._violations.clear()
    
    def get_config(self) -> SandboxConfig:
        """获取沙箱配置"""
        return self._config
    
    def add_allowed_path(self, path: Union[str, Path]):
        """添加允许路径"""
        self._config.allowed_paths.add(Path(path).resolve())
    
    def add_forbidden_path(self, path: Union[str, Path]):
        """添加禁止路径"""
        self._forbidden_paths.add(Path(path).resolve())
    
    def grant_permission(self, permission: SandboxPermission):
        """授予权限"""
        self._config.permissions.add(permission)
    
    def revoke_permission(self, permission: SandboxPermission):
        """撤销权限"""
        self._config.permissions.discard(permission)


class SkillSandbox(ExecutionSandbox):
    """技能执行沙�?""
    
    def __init__(
        self,
        working_dir: Optional[Union[str, Path]] = None,
        permissions: Optional[Set[SandboxPermission]] = None,
        resource_limits: Optional[ResourceLimits] = None,
    ):
        config = SandboxConfig(
            enabled=True,
            permissions=permissions or {SandboxPermission.FILE_READ, SandboxPermission.SYSTEM_INFO},
            resource_limits=resource_limits or ResourceLimits(),
        )
        
        if working_dir:
            config.working_directory = Path(working_dir).resolve()
            config.allowed_paths.add(config.working_directory)
        
        super().__init__(config)
    
    def execute_sync(
        self,
        func: Callable,
        *args,
        timeout: Optional[float] = None,
        **kwargs,
    ) -> SandboxResult:
        """同步执行函数"""
        start_time = datetime.now()
        self.clear_violations()
        
        result = None
        error = None
        error_type = None
        
        timeout = timeout or self._config.resource_limits.max_cpu_seconds
        
        def run_with_timeout():
            nonlocal result, error, error_type
            try:
                with self.resource_context():
                    result = func(*args, **kwargs)
            except SandboxViolationError as e:
                error = str(e)
                error_type = "SandboxViolationError"
            except MemoryError:
                error = "内存不足"
                error_type = "MemoryError"
            except Exception as e:
                error = str(e)
                error_type = type(e).__name__
        
        thread = threading.Thread(target=run_with_timeout)
        thread.daemon = True
        thread.start()
        thread.join(timeout=timeout)
        
        if thread.is_alive():
            error = f"执行超时（超�?{timeout} 秒）"
            error_type = "TimeoutError"
            result = None
        
        execution_time = (datetime.now() - start_time).total_seconds()
        
        return SandboxResult(
            success=error is None,
            result=result,
            error=error,
            error_type=error_type,
            violations=self.get_violations(),
            resource_usage=self.get_resource_usage(),
            execution_time=execution_time,
        )
    
    async def execute_async(
        self,
        func: Callable,
        *args,
        timeout: Optional[float] = None,
        **kwargs,
    ) -> SandboxResult:
        """异步执行函数"""
        start_time = datetime.now()
        self.clear_violations()
        
        timeout = timeout or self._config.resource_limits.max_cpu_seconds
        
        try:
            with self.resource_context():
                if asyncio.iscoroutinefunction(func):
                    result = await asyncio.wait_for(
                        func(*args, **kwargs),
                        timeout=timeout,
                    )
                else:
                    loop = asyncio.get_event_loop()
                    result = await asyncio.wait_for(
                        loop.run_in_executor(None, func, *args, **kwargs),
                        timeout=timeout,
                    )
            
            error = None
            error_type = None
        
        except asyncio.TimeoutError:
            result = None
            error = f"执行超时（超�?{timeout} 秒）"
            error_type = "TimeoutError"
        
        except SandboxViolationError as e:
            result = None
            error = str(e)
            error_type = "SandboxViolationError"
        
        except MemoryError:
            result = None
            error = "内存不足"
            error_type = "MemoryError"
        
        except Exception as e:
            result = None
            error = str(e)
            error_type = type(e).__name__
        
        execution_time = (datetime.now() - start_time).total_seconds()
        
        return SandboxResult(
            success=error is None,
            result=result,
            error=error,
            error_type=error_type,
            violations=self.get_violations(),
            resource_usage=self.get_resource_usage(),
            execution_time=execution_time,
        )


def create_sandbox(
    working_dir: Optional[Union[str, Path]] = None,
    permissions: Optional[List[SandboxPermission]] = None,
    max_memory_mb: int = 512,
    max_cpu_seconds: int = 30,
    network_access: bool = False,
    allow_subprocess: bool = False,
) -> SkillSandbox:
    """创建技能沙�?""
    perms = set(permissions or [SandboxPermission.FILE_READ, SandboxPermission.SYSTEM_INFO])
    
    if network_access:
        perms.add(SandboxPermission.NETWORK)
    
    if allow_subprocess:
        perms.add(SandboxPermission.SUBPROCESS)
    
    resource_limits = ResourceLimits(
        max_memory_mb=max_memory_mb,
        max_cpu_seconds=max_cpu_seconds,
        network_access=network_access,
    )
    
    return SkillSandbox(
        working_dir=working_dir,
        permissions=perms,
        resource_limits=resource_limits,
    )


_default_sandbox: Optional[SkillSandbox] = None


def get_default_sandbox() -> SkillSandbox:
    """获取默认沙箱实例"""
    global _default_sandbox
    if _default_sandbox is None:
        _default_sandbox = create_sandbox()
    return _default_sandbox
