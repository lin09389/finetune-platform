# -*- coding: utf-8 -*-
"""
技能基类定义
"""
import asyncio
import time
import traceback
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from .models import (
    SkillCategory,
    SkillExecution,
    SkillMetadata,
    SkillParameter,
    SkillParameterType,
    SkillPriority,
    SkillResult,
    SkillStatus,
    SkillValidationResult,
)


class SkillBase(ABC):
    """技能抽象基类"""

    _metadata: Optional[SkillMetadata] = None
    _on_progress: Optional[Callable[[float, str], None]] = None
    _on_log: Optional[Callable[[str, str], None]] = None
    _cancelled: bool = False

    def __init__(self):
        self._metadata = None
        self._on_progress = None
        self._on_log = None
        self._cancelled = False

    @classmethod
    @abstractmethod
    def get_metadata(cls) -> SkillMetadata:
        """获取技能元数据（子类必须实现）"""
        pass

    @abstractmethod
    async def execute(self, **kwargs) -> SkillResult:
        """执行技能（子类必须实现）"""
        pass

    def set_progress_callback(self, callback: Callable[[float, str], None]):
        """设置进度回调"""
        self._on_progress = callback

    def set_log_callback(self, callback: Callable[[str, str], None]):
        """设置日志回调"""
        self._on_log = callback

    def report_progress(self, progress: float, message: str = ""):
        """报告执行进度"""
        if self._on_progress:
            self._on_progress(progress, message)

    def log(self, level: str, message: str):
        """记录日志"""
        if self._on_log:
            self._on_log(level, message)

    def cancel(self):
        """取消执行"""
        self._cancelled = True

    def is_cancelled(self) -> bool:
        """检查是否已取消"""
        return self._cancelled

    def validate_parameters(self, params: Dict[str, Any]) -> SkillValidationResult:
        """验证参数"""
        errors = []
        warnings = []
        normalized = {}

        metadata = self.get_metadata()
        param_defs = {p.name: p for p in metadata.parameters}

        for param_def in metadata.parameters:
            name = param_def.name
            value = params.get(name)

            if value is None:
                if param_def.required and param_def.default is None:
                    errors.append(f"缺少必需参数: {name}")
                else:
                    normalized[name] = param_def.default
                continue

            if param_def.enum and value not in param_def.enum:
                errors.append(f"参数 {name} 的值 {value} 不在允许的枚举值中: {param_def.enum}")

            if param_def.type == SkillParameterType.INTEGER:
                if not isinstance(value, int):
                    try:
                        value = int(value)
                    except (ValueError, TypeError):
                        errors.append(f"参数 {name} 必须是整数")
                        continue

                if param_def.min_value is not None and value < param_def.min_value:
                    errors.append(f"参数 {name} 的值 {value} 小于最小值 {param_def.min_value}")
                if param_def.max_value is not None and value > param_def.max_value:
                    errors.append(f"参数 {name} 的值 {value} 大于最大值 {param_def.max_value}")

            elif param_def.type == SkillParameterType.FLOAT:
                if not isinstance(value, (int, float)):
                    try:
                        value = float(value)
                    except (ValueError, TypeError):
                        errors.append(f"参数 {name} 必须是数字")
                        continue

                if param_def.min_value is not None and value < param_def.min_value:
                    errors.append(f"参数 {name} 的值 {value} 小于最小值 {param_def.min_value}")
                if param_def.max_value is not None and value > param_def.max_value:
                    errors.append(f"参数 {name} 的值 {value} 大于最大值 {param_def.max_value}")

            elif param_def.type == SkillParameterType.BOOLEAN:
                if not isinstance(value, bool):
                    if isinstance(value, str):
                        if value.lower() in ("true", "1", "yes"):
                            value = True
                        elif value.lower() in ("false", "0", "no"):
                            value = False
                        else:
                            errors.append(f"参数 {name} 必须是布尔值")
                            continue
                    else:
                        errors.append(f"参数 {name} 必须是布尔值")
                        continue

            elif param_def.type == SkillParameterType.STRING:
                value = str(value)
                if param_def.pattern:
                    import re
                    if not re.match(param_def.pattern, value):
                        errors.append(f"参数 {name} 的值 '{value}' 不匹配模式 {param_def.pattern}")

            elif param_def.type == SkillParameterType.ARRAY:
                if not isinstance(value, list):
                    if isinstance(value, str):
                        try:
                            import json
                            value = json.loads(value)
                        except:
                            errors.append(f"参数 {name} 必须是数组")
                            continue
                    else:
                        errors.append(f"参数 {name} 必须是数组")
                        continue

            elif param_def.type == SkillParameterType.OBJECT:
                if not isinstance(value, dict):
                    if isinstance(value, str):
                        try:
                            import json
                            value = json.loads(value)
                        except:
                            errors.append(f"参数 {name} 必须是对象")
                            continue
                    else:
                        errors.append(f"参数 {name} 必须是对象")
                        continue

            normalized[name] = value

        for name in params:
            if name not in param_defs:
                warnings.append(f"未知参数: {name}")

        return SkillValidationResult(
            valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
            normalized_params=normalized if len(errors) == 0 else None
        )

    async def run(
        self,
        parameters: Dict[str, Any],
        execution_id: Optional[str] = None,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        priority: SkillPriority = SkillPriority.NORMAL,
    ) -> SkillExecution:
        """运行技能（带完整执行记录）"""
        import uuid

        execution = SkillExecution(
            execution_id=execution_id or str(uuid.uuid4()),
            skill_name=self.get_metadata().name,
            parameters=parameters,
            status=SkillStatus.PENDING,
            priority=priority,
            user_id=user_id,
            session_id=session_id,
        )

        validation = self.validate_parameters(parameters)
        if not validation.valid:
            execution.status = SkillStatus.FAILED
            execution.result = SkillResult(
                success=False,
                error="参数验证失败: " + "; ".join(validation.errors),
                error_code="INVALID_PARAMETERS",
            )
            execution.completed_at = datetime.now()
            return execution

        normalized_params = validation.normalized_params or parameters
        execution.parameters = normalized_params
        execution.status = SkillStatus.RUNNING
        execution.started_at = datetime.now()

        start_time = time.time()

        try:
            result = await asyncio.wait_for(
                self.execute(**normalized_params),
                timeout=self.get_metadata().timeout
            )
            execution.result = result
            execution.status = SkillStatus.COMPLETED if result.success else SkillStatus.FAILED

        except asyncio.TimeoutError:
            execution.status = SkillStatus.FAILED
            execution.result = SkillResult(
                success=False,
                error=f"执行超时（超过 {self.get_metadata().timeout} 秒）",
                error_code="TIMEOUT",
            )

        except asyncio.CancelledError:
            execution.status = SkillStatus.CANCELLED
            execution.result = SkillResult(
                success=False,
                error="执行被取消",
                error_code="CANCELLED",
            )

        except Exception as e:
            execution.status = SkillStatus.FAILED
            execution.result = SkillResult(
                success=False,
                error=str(e),
                error_code="EXECUTION_ERROR",
                metadata={"traceback": traceback.format_exc()},
            )

        finally:
            execution.completed_at = datetime.now()
            if execution.result:
                execution.result.execution_time = time.time() - start_time

        return execution

    @classmethod
    def get_name(cls) -> str:
        """获取技能名称"""
        return cls.get_metadata().name

    @classmethod
    def get_description(cls) -> str:
        """获取技能描述"""
        return cls.get_metadata().description

    @classmethod
    def get_parameters(cls) -> List[SkillParameter]:
        """获取参数定义"""
        return cls.get_metadata().parameters

    @classmethod
    def get_category(cls) -> SkillCategory:
        """获取技能类别"""
        return cls.get_metadata().category

    def __repr__(self) -> str:
        metadata = self.get_metadata()
        return f"Skill(name={metadata.name}, category={metadata.category})"


class SkillContext:
    """技能执行上下文"""

    def __init__(
        self,
        execution_id: str,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        parent_context: Optional["SkillContext"] = None,
    ):
        self.execution_id = execution_id
        self.user_id = user_id
        self.session_id = session_id
        self.parent_context = parent_context
        self._data: Dict[str, Any] = {}
        self._start_time = time.time()

    def set(self, key: str, value: Any):
        """设置上下文数据"""
        self._data[key] = value

    def get(self, key: str, default: Any = None) -> Any:
        """获取上下文数据"""
        if key in self._data:
            return self._data[key]
        if self.parent_context:
            return self.parent_context.get(key, default)
        return default

    def get_execution_time(self) -> float:
        """获取已执行时间"""
        return time.time() - self._start_time

    def create_child(self, execution_id: str) -> "SkillContext":
        """创建子上下文"""
        return SkillContext(
            execution_id=execution_id,
            user_id=self.user_id,
            session_id=self.session_id,
            parent_context=self,
        )
