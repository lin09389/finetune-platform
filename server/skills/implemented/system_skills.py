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
        import shlex

        command = kwargs.get("command")
        timeout = kwargs.get("timeout", 30)

        # 危险命令黑名单
        DANGEROUS_TOKENS = {
            "rm", "rmdir", "del", "format", "mkfs", "dd",
            "chmod", "chown", "chgrp", "sudo", "su",
            "wget", "curl", "nc", "ncat", "netcat",
            "python", "python3", "node", "ruby", "perl",
            "eval", "exec", "source", "bash", "sh", "cmd", "powershell",
        }

        # Shell 元字符检测
        SHELL_META = set("&|;`$(){}[]!#~<>")

        try:
            start_time = time.time()

            # 检测 shell 元字符
            if any(c in SHELL_META for c in command):
                return SkillResult(
                    success=False,
                    error="命令包含不允许的特殊字符",
                    error_code="FORBIDDEN_CHARS",
                )

            # 解析命令
            try:
                args = shlex.split(command)
            except ValueError as e:
                return SkillResult(
                    success=False,
                    error=f"命令解析失败: {str(e)}",
                    error_code="PARSE_ERROR",
                )

            if not args:
                return SkillResult(
                    success=False,
                    error="空命令",
                    error_code="EMPTY_COMMAND",
                )

            # 检查危险命令
            cmd_name = args[0].lower()
            if cmd_name in DANGEROUS_TOKENS:
                return SkillResult(
                    success=False,
                    error=f"不允许执行危险命令: {cmd_name}",
                    error_code="FORBIDDEN_COMMAND",
                )

            process = await asyncio.create_subprocess_exec(
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
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
        import ast
        import math
        import operator

        expression = kwargs.get("expression")

        # 安全的运算符映射
        SAFE_OPERATORS = {
            ast.Add: operator.add,
            ast.Sub: operator.sub,
            ast.Mult: operator.mul,
            ast.Div: operator.truediv,
            ast.FloorDiv: operator.floordiv,
            ast.Mod: operator.mod,
            ast.Pow: operator.pow,
            ast.USub: operator.neg,
            ast.UAdd: operator.pos,
        }

        # 安全的函数映射
        SAFE_FUNCTIONS = {
            "abs": abs,
            "round": round,
            "min": min,
            "max": max,
            "sum": sum,
            "pow": pow,
        }
        for name in dir(math):
            if not name.startswith("_"):
                SAFE_FUNCTIONS[name] = getattr(math, name)

        def _safe_eval(node):
            """递归安全求值 AST 节点"""
            if isinstance(node, ast.Expression):
                return _safe_eval(node.body)
            elif isinstance(node, ast.Constant):
                if isinstance(node.value, (int, float, complex)):
                    return node.value
                raise ValueError(f"不支持的常量类型: {type(node.value)}")
            elif isinstance(node, ast.BinOp):
                op_type = type(node.op)
                if op_type not in SAFE_OPERATORS:
                    raise ValueError(f"不支持的运算符: {op_type.__name__}")
                left = _safe_eval(node.left)
                right = _safe_eval(node.right)
                return SAFE_OPERATORS[op_type](left, right)
            elif isinstance(node, ast.UnaryOp):
                op_type = type(node.op)
                if op_type not in SAFE_OPERATORS:
                    raise ValueError(f"不支持的一元运算符: {op_type.__name__}")
                operand = _safe_eval(node.operand)
                return SAFE_OPERATORS[op_type](operand)
            elif isinstance(node, ast.Call):
                if not isinstance(node.func, ast.Name):
                    raise ValueError("不支持的函数调用方式")
                func_name = node.func.id
                if func_name not in SAFE_FUNCTIONS:
                    raise ValueError(f"不允许的函数: {func_name}")
                args = [_safe_eval(arg) for arg in node.args]
                return SAFE_FUNCTIONS[func_name](*args)
            else:
                raise ValueError(f"不支持的表达式类型: {type(node).__name__}")

        try:
            # 解析为 AST，只允许表达式
            tree = ast.parse(expression, mode='eval')
            result = _safe_eval(tree)

            return SkillResult(
                success=True,
                data={
                    "expression": expression,
                    "result": result,
                    "type": type(result).__name__,
                },
            )

        except (ValueError, TypeError, ZeroDivisionError, OverflowError) as e:
            return SkillResult(
                success=False,
                error=f"计算失败: {str(e)}",
                error_code="CALC_ERROR",
            )
        except Exception as e:
            return SkillResult(
                success=False,
                error=f"表达式格式错误: {str(e)}",
                error_code="CALC_ERROR",
            )
