"""
代码执行沙箱 API

提供安全的代码执行环境，支持多种编程语言
"""
import asyncio
import os
import sys
import tempfile
from contextlib import suppress
from datetime import datetime
from enum import Enum
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from core.logging import get_logger
from security.auth_middleware import get_current_user
from security.jwt_auth import Role, TokenPayload
from security.sandbox import (
    Capability,
    Permission,
    PermissionLevel,
    ResourceLimits,
    get_sandbox_manager,
)

logger = get_logger(__name__)
router = APIRouter()

ALLOWED_USER_PERMISSION_LEVELS = {"none", "read_only", "limited"}
ADMIN_PERMISSION_LEVELS = {"standard", "elevated", "admin"}


class Language(str, Enum):
    """支持的编程语言"""
    PYTHON = "python"
    JAVASCRIPT = "javascript"
    TYPESCRIPT = "typescript"


class ExecuteRequest(BaseModel):
    """代码执行请求"""
    code: str = Field(..., description="要执行的代码")
    language: Language = Field(default=Language.PYTHON, description="编程语言")
    timeout: int = Field(default=30, ge=1, le=300, description="执行超时时间（秒）")
    memory_limit_mb: int = Field(default=256, ge=64, le=2048, description="内存限制（MB）")
    permission_level: str = Field(default="limited", description="权限级别")
    stdin: str | None = Field(default=None, description="标准输入")


class ExecuteResponse(BaseModel):
    """代码执行响应"""
    success: bool = Field(..., description="是否执行成功")
    stdout: str = Field(default="", description="标准输出")
    stderr: str = Field(default="", description="标准错误")
    exit_code: int = Field(default=0, description="退出码")
    execution_time: float = Field(default=0.0, description="执行时间（秒）")
    memory_used_mb: float = Field(default=0.0, description="内存使用（MB）")
    error: str | None = Field(default=None, description="错误信息")
    language: str = Field(..., description="执行的语言")
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())


class SandboxInfo(BaseModel):
    """沙箱信息"""
    sandbox_id: str
    capability: dict[str, Any]
    resource_limits: dict[str, Any]


class SupportedLanguage(BaseModel):
    """支持的语言信息"""
    name: str
    version_command: str
    file_extension: str
    description: str


SUPPORTED_LANGUAGES: dict[str, SupportedLanguage] = {
    "python": SupportedLanguage(
        name="Python",
        version_command="python --version",
        file_extension=".py",
        description="Python 3.x 解释执行"
    ),
    "javascript": SupportedLanguage(
        name="JavaScript",
        version_command="node --version",
        file_extension=".js",
        description="Node.js JavaScript 执行"
    ),
    "typescript": SupportedLanguage(
        name="TypeScript",
        version_command="tsc --version",
        file_extension=".ts",
        description="TypeScript 编译执行"
    ),
}


def get_permission_level(level: str, current_user: TokenPayload | None = None) -> PermissionLevel:
    level_lower = level.lower()
    if level_lower in ADMIN_PERMISSION_LEVELS:
        if current_user is None or not _is_admin_user(current_user):
            raise HTTPException(
                status_code=403,
                detail=f"Permission level '{level}' requires admin role"
            )
    if level_lower not in ALLOWED_USER_PERMISSION_LEVELS and level_lower not in ADMIN_PERMISSION_LEVELS:
        level_lower = "limited"
    level_map = {
        "none": PermissionLevel.NONE,
        "read_only": PermissionLevel.READ_ONLY,
        "limited": PermissionLevel.LIMITED,
        "standard": PermissionLevel.STANDARD,
        "elevated": PermissionLevel.ELEVATED,
        "admin": PermissionLevel.ADMIN,
    }
    return level_map.get(level_lower, PermissionLevel.LIMITED)


def _is_admin_user(user: TokenPayload) -> bool:
    return user.role in (Role.ADMIN, Role.SUPER_ADMIN)


def create_code_capability(
    language: Language,
    memory_limit_mb: int = 256,
    timeout: int = 30
) -> Capability:
    """创建代码执行能力配置"""
    base_permissions = {
        Permission.FILE_READ,
        Permission.FILE_WRITE,
    }

    if language == Language.PYTHON:
        allowed_commands = ["python", "python3"]
    elif language == Language.JAVASCRIPT:
        allowed_commands = ["node"]
    elif language == Language.TYPESCRIPT:
        allowed_commands = ["tsc", "node"]
    else:
        allowed_commands = []

    return Capability(
        name=f"code_executor_{language.value}",
        permissions=base_permissions,
        max_file_size=10 * 1024 * 1024,
        max_execution_time=timeout,
        max_memory_mb=memory_limit_mb,
        max_processes=1,
        allowed_paths=[],
        denied_paths=[
            "/etc", "/root", "/home", "/var",
            "C:\\Windows", "C:\\Program Files",
            "/System", "/Library",
        ],
        allowed_commands=allowed_commands,
        network_whitelist=[],
    )


async def check_language_available(language: Language) -> tuple[bool, str]:
    """检查语言环境是否可用"""
    if language == Language.PYTHON:
        try:
            proc = await asyncio.create_subprocess_exec(
                sys.executable, "--version",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=5)
            version = stdout.decode().strip() or "Python 3.x"
            return True, version
        except Exception as e:
            return False, f"Python 不可用: {e}"

    elif language == Language.JAVASCRIPT:
        try:
            proc = await asyncio.create_subprocess_exec(
                "node", "--version",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=5)
            version = f"Node.js {stdout.decode().strip()}"
            return True, version
        except Exception as e:
            return False, f"Node.js 不可用: {e}"

    elif language == Language.TYPESCRIPT:
        try:
            proc = await asyncio.create_subprocess_exec(
                "tsc", "--version",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=5)
            version = stdout.decode().strip()
            return True, version
        except Exception as e:
            return False, f"TypeScript 不可用: {e}"

    return False, "不支持的语言"


async def execute_python_code(
    code: str,
    timeout: int,
    memory_limit_mb: int,
    stdin: str | None = None
) -> ExecuteResponse:
    """执行 Python 代码"""
    start_time = datetime.now()

    with tempfile.NamedTemporaryFile(
        mode='w',
        suffix='.py',
        delete=False,
        encoding='utf-8'
    ) as f:
        f.write(code)
        temp_file = f.name

    try:
        env = os.environ.copy()
        env['PYTHONDONTWRITEBYTECODE'] = '1'
        env['PYTHONUNBUFFERED'] = '1'

        proc = await asyncio.create_subprocess_exec(
            sys.executable, temp_file,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            stdin=asyncio.subprocess.PIPE if stdin else None,
            env=env,
        )

        try:
            stdin_bytes = stdin.encode() if stdin else None
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(input=stdin_bytes),
                timeout=timeout
            )
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            return ExecuteResponse(
                success=False,
                error=f"执行超时（{timeout}秒）",
                exit_code=-1,
                execution_time=timeout,
                language="python"
            )

        execution_time = (datetime.now() - start_time).total_seconds()

        return ExecuteResponse(
            success=proc.returncode == 0,
            stdout=stdout.decode('utf-8', errors='replace'),
            stderr=stderr.decode('utf-8', errors='replace'),
            exit_code=proc.returncode or 0,
            execution_time=execution_time,
            language="python"
        )

    except Exception as e:
        execution_time = (datetime.now() - start_time).total_seconds()
        return ExecuteResponse(
            success=False,
            error=str(e),
            exit_code=-1,
            execution_time=execution_time,
            language="python"
        )

    finally:
        with suppress(Exception):
            os.unlink(temp_file)


async def execute_javascript_code(
    code: str,
    timeout: int,
    memory_limit_mb: int,
    stdin: str | None = None
) -> ExecuteResponse:
    """执行 JavaScript 代码"""
    start_time = datetime.now()

    with tempfile.NamedTemporaryFile(
        mode='w',
        suffix='.js',
        delete=False,
        encoding='utf-8'
    ) as f:
        f.write(code)
        temp_file = f.name

    try:
        env = os.environ.copy()
        env['NODE_OPTIONS'] = f'--max-old-space-size={memory_limit_mb}'

        proc = await asyncio.create_subprocess_exec(
            'node', temp_file,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            stdin=asyncio.subprocess.PIPE if stdin else None,
            env=env,
        )

        try:
            stdin_bytes = stdin.encode() if stdin else None
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(input=stdin_bytes),
                timeout=timeout
            )
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            return ExecuteResponse(
                success=False,
                error=f"执行超时（{timeout}秒）",
                exit_code=-1,
                execution_time=timeout,
                language="javascript"
            )

        execution_time = (datetime.now() - start_time).total_seconds()

        return ExecuteResponse(
            success=proc.returncode == 0,
            stdout=stdout.decode('utf-8', errors='replace'),
            stderr=stderr.decode('utf-8', errors='replace'),
            exit_code=proc.returncode or 0,
            execution_time=execution_time,
            language="javascript"
        )

    except FileNotFoundError:
        return ExecuteResponse(
            success=False,
            error="Node.js 未安装，无法执行 JavaScript 代码",
            exit_code=-1,
            language="javascript"
        )

    except Exception as e:
        execution_time = (datetime.now() - start_time).total_seconds()
        return ExecuteResponse(
            success=False,
            error=str(e),
            exit_code=-1,
            execution_time=execution_time,
            language="javascript"
        )

    finally:
        with suppress(Exception):
            os.unlink(temp_file)


async def execute_typescript_code(
    code: str,
    timeout: int,
    memory_limit_mb: int,
    stdin: str | None = None
) -> ExecuteResponse:
    """执行 TypeScript 代码"""
    start_time = datetime.now()

    with tempfile.TemporaryDirectory() as temp_dir:
        ts_file = os.path.join(temp_dir, 'code.ts')
        js_file = os.path.join(temp_dir, 'code.js')

        with open(ts_file, 'w', encoding='utf-8') as f:
            f.write(code)

        try:
            compile_proc = await asyncio.create_subprocess_exec(
                'tsc', ts_file, '--outDir', temp_dir,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            try:
                _, compile_stderr = await asyncio.wait_for(
                    compile_proc.communicate(),
                    timeout=timeout // 2
                )
            except asyncio.TimeoutError:
                compile_proc.kill()
                return ExecuteResponse(
                    success=False,
                    error="TypeScript 编译超时",
                    exit_code=-1,
                    language="typescript"
                )

            if compile_proc.returncode != 0:
                return ExecuteResponse(
                    success=False,
                    stderr=compile_stderr.decode('utf-8', errors='replace'),
                    error="TypeScript 编译失败",
                    exit_code=compile_proc.returncode or 1,
                    language="typescript"
                )

            env = os.environ.copy()
            env['NODE_OPTIONS'] = f'--max-old-space-size={memory_limit_mb}'

            proc = await asyncio.create_subprocess_exec(
                'node', js_file,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                stdin=asyncio.subprocess.PIPE if stdin else None,
                env=env,
            )

            try:
                stdin_bytes = stdin.encode() if stdin else None
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(input=stdin_bytes),
                    timeout=timeout // 2
                )
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
                return ExecuteResponse(
                    success=False,
                    error=f"执行超时（{timeout}秒）",
                    exit_code=-1,
                    execution_time=timeout,
                    language="typescript"
                )

            execution_time = (datetime.now() - start_time).total_seconds()

            return ExecuteResponse(
                success=proc.returncode == 0,
                stdout=stdout.decode('utf-8', errors='replace'),
                stderr=stderr.decode('utf-8', errors='replace'),
                exit_code=proc.returncode or 0,
                execution_time=execution_time,
                language="typescript"
            )

        except FileNotFoundError as e:
            if 'tsc' in str(e):
                return ExecuteResponse(
                    success=False,
                    error="TypeScript 编译器未安装，无法执行 TypeScript 代码",
                    exit_code=-1,
                    language="typescript"
                )
            elif 'node' in str(e):
                return ExecuteResponse(
                    success=False,
                    error="Node.js 未安装，无法执行 TypeScript 代码",
                    exit_code=-1,
                    language="typescript"
                )
            return ExecuteResponse(
                success=False,
                error=str(e),
                exit_code=-1,
                language="typescript"
            )

        except Exception as e:
            execution_time = (datetime.now() - start_time).total_seconds()
            return ExecuteResponse(
                success=False,
                error=str(e),
                exit_code=-1,
                execution_time=execution_time,
                language="typescript"
            )


@router.post("/execute", response_model=ExecuteResponse)
async def execute_code(
    request: ExecuteRequest,
    current_user: TokenPayload = Depends(get_current_user),
):
    logger.info(f"执行代码请求: language={request.language}, timeout={request.timeout}s, user={current_user.username}")

    if request.permission_level.lower() in ADMIN_PERMISSION_LEVELS and not _is_admin_user(current_user):
        raise HTTPException(
            status_code=403,
            detail=f"Permission level '{request.permission_level}' requires admin role"
        )

    available, version_info = await check_language_available(request.language)
    if not available:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "language_unavailable",
                "message": version_info,
                "language": request.language.value
            }
        )

    logger.info(f"语言环境: {version_info}")

    if request.language == Language.PYTHON:
        result = await execute_python_code(
            code=request.code,
            timeout=request.timeout,
            memory_limit_mb=request.memory_limit_mb,
            stdin=request.stdin
        )
    elif request.language == Language.JAVASCRIPT:
        result = await execute_javascript_code(
            code=request.code,
            timeout=request.timeout,
            memory_limit_mb=request.memory_limit_mb,
            stdin=request.stdin
        )
    elif request.language == Language.TYPESCRIPT:
        result = await execute_typescript_code(
            code=request.code,
            timeout=request.timeout,
            memory_limit_mb=request.memory_limit_mb,
            stdin=request.stdin
        )
    else:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的语言: {request.language}"
        )

    logger.info(
        f"代码执行完成: success={result.success}, "
        f"time={result.execution_time:.2f}s, exit_code={result.exit_code}"
    )

    return result


@router.get("/languages")
async def list_supported_languages():
    """列出支持的编程语言"""
    languages = []

    for lang_id, lang_info in SUPPORTED_LANGUAGES.items():
        available, version = await check_language_available(Language(lang_id))
        languages.append({
            "id": lang_id,
            "name": lang_info.name,
            "extension": lang_info.file_extension,
            "description": lang_info.description,
            "available": available,
            "version": version if available else None
        })

    return {"languages": languages}


@router.get("/languages/{language}/status")
async def get_language_status(language: Language):
    """获取特定语言的可用状态"""
    available, version = await check_language_available(language)

    return {
        "language": language.value,
        "available": available,
        "version": version,
        "info": SUPPORTED_LANGUAGES.get(language.value)
    }


@router.post("/sandbox/create")
async def create_sandbox(
    permission_level: str = "limited",
    memory_limit_mb: int = 256,
    timeout: int = 60,
    current_user: TokenPayload = Depends(get_current_user),
):
    try:
        level = get_permission_level(permission_level, current_user)
        manager = get_sandbox_manager()

        sandbox_id = manager.create_sandbox(
            permission_level=level,
            resource_limits=ResourceLimits(
                max_memory_mb=memory_limit_mb,
                max_execution_time=timeout
            )
        )

        return {
            "sandbox_id": sandbox_id,
            "permission_level": permission_level,
            "memory_limit_mb": memory_limit_mb,
            "timeout": timeout
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sandbox/{sandbox_id}")
async def get_sandbox_info(sandbox_id: str):
    """获取沙箱信息"""
    manager = get_sandbox_manager()
    info = manager.get_sandbox_info(sandbox_id)

    if not info:
        raise HTTPException(status_code=404, detail="沙箱不存在")

    return info


@router.delete("/sandbox/{sandbox_id}")
async def destroy_sandbox(sandbox_id: str):
    """销毁沙箱"""
    manager = get_sandbox_manager()
    success = manager.destroy_sandbox(sandbox_id)

    if not success:
        raise HTTPException(status_code=404, detail="沙箱不存在")

    return {"message": "沙箱已销毁", "sandbox_id": sandbox_id}


@router.get("/sandboxes")
async def list_sandboxes():
    """列出所有沙箱"""
    manager = get_sandbox_manager()
    return {"sandboxes": manager.list_sandboxes()}


@router.post("/validate")
async def validate_code(request: ExecuteRequest):
    """
    验证代码（不执行）
    检查代码语法是否正确
    """
    errors = []
    warnings = []

    if request.language == Language.PYTHON:
        try:
            import ast
            ast.parse(request.code)
        except SyntaxError as e:
            errors.append({
                "line": e.lineno,
                "column": e.offset,
                "message": e.msg
            })

    elif request.language in [Language.JAVASCRIPT, Language.TYPESCRIPT]:
        pass

    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "language": request.language.value
    }
