"""
技能数据模型定义
"""
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class SkillStatus(str, Enum):
    """技能状态"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class SkillPriority(str, Enum):
    """技能执行优先级"""
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    CRITICAL = "critical"


class SkillCategory(str, Enum):
    """技能类别"""
    CODE = "code"
    FILE = "file"
    DATA = "data"
    SYSTEM = "system"
    TEXT = "text"
    UTILITY = "utility"
    DESIGN = "design"
    ANALYSIS = "analysis"
    COMMUNICATION = "communication"
    CUSTOM = "custom"


class SkillParameterType(str, Enum):
    """技能参数类型"""
    STRING = "string"
    INTEGER = "integer"
    FLOAT = "float"
    BOOLEAN = "boolean"
    ARRAY = "array"
    OBJECT = "object"
    FILE = "file"


class SkillParameter(BaseModel):
    """技能参数定义"""
    name: str = Field(..., description="参数名称")
    type: SkillParameterType = Field(..., description="参数类型")
    description: str = Field(default="", description="参数描述")
    required: bool = Field(default=True, description="是否必需")
    default: Any | None = Field(default=None, description="默认值")
    enum: list[Any] | None = Field(default=None, description="枚举值列表")
    min_value: int | float | None = Field(default=None, description="最小值（数值类型）")
    max_value: int | float | None = Field(default=None, description="最大值（数值类型）")
    pattern: str | None = Field(default=None, description="正则表达式验证（字符串类型）")
    example: Any | None = Field(default=None, description="示例值")


class SkillMetadata(BaseModel):
    """技能元数据"""
    name: str = Field(..., description="技能唯一标识名称")
    display_name: str = Field(..., description="技能显示名称")
    description: str = Field(..., description="技能详细描述")
    version: str = Field(default="1.0.0", description="技能版本")
    category: SkillCategory = Field(default=SkillCategory.CUSTOM, description="技能类别")
    tags: list[str] = Field(default_factory=list, description="技能标签")
    author: str | None = Field(default=None, description="作者")
    parameters: list[SkillParameter] = Field(default_factory=list, description="参数定义")
    examples: list[dict[str, Any]] = Field(default_factory=list, description="使用示例")
    dependencies: list[str] = Field(default_factory=list, description="依赖的其他技能")
    timeout: int = Field(default=300, ge=1, description="超时时间（秒）")
    retry_count: int = Field(default=0, ge=0, le=5, description="重试次数")
    retry_delay: float = Field(default=1.0, ge=0, description="重试延迟（秒）")
    enabled: bool = Field(default=True, description="是否启用")
    requires_auth: bool = Field(default=False, description="是否需要认证")
    requires_confirmation: bool = Field(default=False, description="是否需要用户确认")
    dangerous: bool = Field(default=False, description="是否为危险操作")
    created_at: datetime = Field(default_factory=datetime.now, description="创建时间")
    updated_at: datetime = Field(default_factory=datetime.now, description="更新时间")

    model_config = ConfigDict(use_enum_values=True)


class SkillResult(BaseModel):
    """技能执行结果"""
    success: bool = Field(..., description="执行是否成功")
    data: Any | None = Field(default=None, description="返回数据")
    error: str | None = Field(default=None, description="错误信息")
    error_code: str | None = Field(default=None, description="错误代码")
    message: str | None = Field(default=None, description="结果消息")
    metadata: dict[str, Any] = Field(default_factory=dict, description="额外元数据")
    execution_time: float = Field(default=0.0, ge=0, description="执行时间（秒）")
    memory_used: int | None = Field(default=None, description="使用的内存（字节）")
    tokens_used: int | None = Field(default=None, description="使用的 token 数量")
    created_at: datetime = Field(default_factory=datetime.now, description="创建时间")

    model_config = ConfigDict(arbitrary_types_allowed=True)


class SkillExecution(BaseModel):
    """技能执行记录"""
    execution_id: str = Field(..., description="执行ID")
    skill_name: str = Field(..., description="技能名称")
    parameters: dict[str, Any] = Field(default_factory=dict, description="执行参数")
    status: SkillStatus = Field(default=SkillStatus.PENDING, description="执行状态")
    priority: SkillPriority = Field(default=SkillPriority.NORMAL, description="执行优先级")
    result: SkillResult | None = Field(default=None, description="执行结果")
    started_at: datetime | None = Field(default=None, description="开始时间")
    completed_at: datetime | None = Field(default=None, description="完成时间")
    created_at: datetime = Field(default_factory=datetime.now, description="创建时间")
    user_id: str | None = Field(default=None, description="用户ID")
    session_id: str | None = Field(default=None, description="会话ID")
    parent_execution_id: str | None = Field(default=None, description="父执行ID（用于链式调用）")
    retry_count: int = Field(default=0, description="已重试次数")

    @property
    def duration_ms(self) -> int | None:
        """计算执行耗时（毫秒）"""
        if self.started_at and self.completed_at:
            delta = self.completed_at - self.started_at
            return int(delta.total_seconds() * 1000)
        return None

    model_config = ConfigDict(use_enum_values=True)


class SkillChain(BaseModel):
    """技能链（用于组合多个技能）"""
    chain_id: str = Field(..., description="链ID")
    name: str = Field(..., description="链名称")
    description: str = Field(default="", description="链描述")
    skills: list[str] = Field(..., description="技能名称列表（按执行顺序）")
    parameters_mapping: dict[str, dict[str, str]] = Field(
        default_factory=dict,
        description="参数映射：{skill_name: {param_name: source}}"
    )
    stop_on_error: bool = Field(default=True, description="遇到错误是否停止")
    parallel: bool = Field(default=False, description="是否并行执行")
    created_at: datetime = Field(default_factory=datetime.now, description="创建时间")


class SkillValidationResult(BaseModel):
    """技能参数验证结果"""
    valid: bool = Field(..., description="是否有效")
    errors: list[str] = Field(default_factory=list, description="错误列表")
    warnings: list[str] = Field(default_factory=list, description="警告列表")
    normalized_params: dict[str, Any] | None = Field(default=None, description="规范化后的参数")
