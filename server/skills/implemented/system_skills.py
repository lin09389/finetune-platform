"""
系统工具技能
"""
import asyncio
import platform
import time
from datetime import datetime

from skills.base import SkillBase
from skills.models import (
    SkillCategory,
    SkillMetadata,
    SkillParameter,
    SkillParameterType,
    SkillResult,
)


class SystemInfoSkill(SkillBase):
    """获取系统信息"""

    @classmethod
    def get_metadata(cls) -> SkillMetadata:
        return SkillMetadata(
            name="system_info",
            display_name="系统信息",
            description="获取系统基本信息",
            version="1.0.0",
            category=SkillCategory.UTILITY,
            tags=["system", "info", "platform"],
            parameters=[],
            examples=[{}],
        )

    async def execute(self, **kwargs) -> SkillResult:
        try:
            info = {
                "platform": platform.system(),
                "platform_version": platform.version(),
                "platform_release": platform.release(),
                "architecture": platform.machine(),
                "processor": platform.processor(),
                "python_version": platform.python_version(),
                "hostname": platform.node(),
                "timestamp": datetime.now().isoformat(),
            }

            return SkillResult(
                success=True,
                data=info,
            )

        except Exception as e:
            return SkillResult(
                success=False,
                error=f"获取系统信息失败: {str(e)}",
                error_code="SYSTEM_INFO_ERROR",
            )


class CommandExecuteSkill(SkillBase):
    """执行系统命令"""

    @classmethod
    def get_metadata(cls) -> SkillMetadata:
        return SkillMetadata(
            name="command_execute",
            display_name="执行命令",
            description="执行系统命令并返回结果",
            version="1.0.0",
            category=SkillCategory.SYSTEM,
            tags=["system", "command", "shell"],
            parameters=[
                SkillParameter(
                    name="command",
                    type=SkillParameterType.STRING,
                    description="要执行的命令",
                    required=True,
                ),
                SkillParameter(
                    name="timeout",
                    type=SkillParameterType.INTEGER,
                    description="超时时间（秒）",
                    required=False,
                    default=30,
                ),
                SkillParameter(
                    name="shell",
                    type=SkillParameterType.BOOLEAN,
                    description="是否使用 shell 执行",
                    required=False,
                    default=True,
                ),
            ],
            examples=[
                {"command": "echo Hello"},
                {"command": "dir", "timeout": 10},
            ],
            requires_confirmation=True,
        )

    async def execute(self, **kwargs) -> SkillResult:
        command = kwargs.get("command")
        timeout = kwargs.get("timeout", 30)
        shell = kwargs.get("shell", True)

        try:
            start_time = time.time()

            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                shell=shell,
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=timeout
                )
            except asyncio.TimeoutError:
                process.kill()
                return SkillResult(
                    success=False,
                    error=f"命令执行超时（{timeout}秒）",
                    error_code="TIMEOUT",
                )

            duration = time.time() - start_time

            return SkillResult(
                success=process.returncode == 0,
                data={
                    "stdout": stdout.decode("utf-8", errors="replace"),
                    "stderr": stderr.decode("utf-8", errors="replace"),
                    "return_code": process.returncode,
                    "duration": round(duration, 3),
                },
            )

        except Exception as e:
            return SkillResult(
                success=False,
                error=f"命令执行失败: {str(e)}",
                error_code="COMMAND_ERROR",
            )


class DelaySkill(SkillBase):
    """延迟执行"""

    @classmethod
    def get_metadata(cls) -> SkillMetadata:
        return SkillMetadata(
            name="delay",
            display_name="延迟",
            description="延迟指定时间后继续执行",
            version="1.0.0",
            category=SkillCategory.UTILITY,
            tags=["delay", "sleep", "utility"],
            parameters=[
                SkillParameter(
                    name="seconds",
                    type=SkillParameterType.FLOAT,
                    description="延迟秒数",
                    required=True,
                    min_value=0.1,
                    max_value=60,
                ),
            ],
            examples=[
                {"seconds": 1},
                {"seconds": 2.5},
            ],
        )

    async def execute(self, **kwargs) -> SkillResult:
        seconds = kwargs.get("seconds", 1)

        try:
            start_time = time.time()
            await asyncio.sleep(seconds)
            actual_duration = time.time() - start_time

            return SkillResult(
                success=True,
                data={
                    "requested_seconds": seconds,
                    "actual_seconds": round(actual_duration, 3),
                },
            )

        except Exception as e:
            return SkillResult(
                success=False,
                error=f"延迟失败: {str(e)}",
                error_code="DELAY_ERROR",
            )


class CalculatorSkill(SkillBase):
    """数学计算"""

    @classmethod
    def get_metadata(cls) -> SkillMetadata:
        return SkillMetadata(
            name="calculator",
            display_name="计算器",
            description="执行数学表达式计算",
            version="1.0.0",
            category=SkillCategory.UTILITY,
            tags=["math", "calculate", "utility"],
            parameters=[
                SkillParameter(
                    name="expression",
                    type=SkillParameterType.STRING,
                    description="数学表达式",
                    required=True,
                ),
            ],
            examples=[
                {"expression": "2 + 3 * 4"},
                {"expression": "sqrt(16) + pow(2, 3)"},
                {"expression": "sin(pi/2)"},
            ],
        )

    async def execute(self, **kwargs) -> SkillResult:
        expression = kwargs.get("expression")

        allowed_names = {
            "abs": abs,
            "round": round,
            "min": min,
            "max": max,
            "sum": sum,
            "pow": pow,
            "len": len,
        }

        try:
            import math
            for name in dir(math):
                if not name.startswith("_"):
                    allowed_names[name] = getattr(math, name)

            result = eval(expression, {"__builtins__": {}}, allowed_names)

            return SkillResult(
                success=True,
                data={
                    "expression": expression,
                    "result": result,
                    "type": type(result).__name__,
                },
            )

        except Exception as e:
            return SkillResult(
                success=False,
                error=f"计算失败: {str(e)}",
                error_code="CALC_ERROR",
            )
