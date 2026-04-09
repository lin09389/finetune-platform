"""
特性开关 - 支持灰度发布和回滚
"""
import json
import logging
import os
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from functools import wraps
from typing import Any

logger = logging.getLogger(__name__)


class FeatureStatus(str, Enum):
    ENABLED = "enabled"
    DISABLED = "disabled"
    PERCENTAGE = "percentage"
    CONDITIONAL = "conditional"


@dataclass
class FeatureDefinition:
    name: str
    description: str = ""
    status: FeatureStatus = FeatureStatus.DISABLED
    percentage: int = 0
    conditions: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class FeatureFlags:
    """
    特性开关配置

    支持从环境变量加载，用于灰度发布和回滚
    """
    use_new_agent_executor: bool = False
    use_inference_engine_factory: bool = False
    use_new_memory_service: bool = False
    use_event_bus: bool = False
    use_di_container: bool = False
    use_mirror_manager: bool = True
    use_new_rag_pipeline: bool = False
    enable_streaming_inference: bool = True
    enable_model_caching: bool = True
    enable_training_queue: bool = True
    enable_checkpoint_recovery: bool = True
    enable_rate_limiting: bool = True
    enable_audit_logging: bool = False
    enable_debug_mode: bool = False

    def __post_init__(self):
        self._load_from_env()

    def _load_from_env(self) -> None:
        """从环境变量加载特性开关"""
        env_mappings = {
            "FEATURE_NEW_AGENT": "use_new_agent_executor",
            "FEATURE_NEW_INFERENCE": "use_inference_engine_factory",
            "FEATURE_NEW_MEMORY": "use_new_memory_service",
            "FEATURE_EVENT_BUS": "use_event_bus",
            "FEATURE_DI_CONTAINER": "use_di_container",
            "FEATURE_MIRROR_MANAGER": "use_mirror_manager",
            "FEATURE_NEW_RAG": "use_new_rag_pipeline",
            "ENABLE_STREAMING": "enable_streaming_inference",
            "ENABLE_MODEL_CACHE": "enable_model_caching",
            "ENABLE_TRAINING_QUEUE": "enable_training_queue",
            "ENABLE_CHECKPOINT": "enable_checkpoint_recovery",
            "ENABLE_RATE_LIMIT": "enable_rate_limiting",
            "ENABLE_AUDIT_LOG": "enable_audit_logging",
            "DEBUG_MODE": "enable_debug_mode",
        }

        for env_key, attr_name in env_mappings.items():
            env_value = os.getenv(env_key)
            if env_value is not None:
                setattr(self, attr_name, env_value.lower() in ("true", "1", "yes"))

    @classmethod
    def from_env(cls) -> 'FeatureFlags':
        """从环境变量创建特性开关"""
        return cls()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> 'FeatureFlags':
        """从字典创建特性开关"""
        return cls(**{k: v for k, v in data.items() if hasattr(cls, k)})

    @classmethod
    def from_file(cls, file_path: str) -> 'FeatureFlags':
        """从文件加载特性开关"""
        with open(file_path) as f:
            data = json.load(f)
        return cls.from_dict(data)

    def to_dict(self) -> dict[str, Any]:
        """转换为字典"""
        return {
            "use_new_agent_executor": self.use_new_agent_executor,
            "use_inference_engine_factory": self.use_inference_engine_factory,
            "use_new_memory_service": self.use_new_memory_service,
            "use_event_bus": self.use_event_bus,
            "use_di_container": self.use_di_container,
            "use_mirror_manager": self.use_mirror_manager,
            "use_new_rag_pipeline": self.use_new_rag_pipeline,
            "enable_streaming_inference": self.enable_streaming_inference,
            "enable_model_caching": self.enable_model_caching,
            "enable_training_queue": self.enable_training_queue,
            "enable_checkpoint_recovery": self.enable_checkpoint_recovery,
            "enable_rate_limiting": self.enable_rate_limiting,
            "enable_audit_logging": self.enable_audit_logging,
            "enable_debug_mode": self.enable_debug_mode,
        }

    def save_to_file(self, file_path: str) -> None:
        """保存到文件"""
        with open(file_path, "w") as f:
            json.dump(self.to_dict(), f, indent=2)

    def is_enabled(self, feature_name: str) -> bool:
        """检查特性是否启用"""
        return getattr(self, feature_name, False)

    def enable(self, feature_name: str) -> None:
        """启用特性"""
        if hasattr(self, feature_name):
            setattr(self, feature_name, True)
            logger.info(f"特性已启用: {feature_name}")

    def disable(self, feature_name: str) -> None:
        """禁用特性"""
        if hasattr(self, feature_name):
            setattr(self, feature_name, False)
            logger.info(f"特性已禁用: {feature_name}")


class FeatureManager:
    """
    特性管理器

    提供更高级的特性控制功能：
    - 百分比灰度
    - 条件判断
    - 动态更新
    """

    def __init__(self, flags: FeatureFlags | None = None):
        self.flags = flags or FeatureFlags.from_env()
        self._features: dict[str, FeatureDefinition] = {}
        self._callbacks: dict[str, list[Callable[[bool], None]]] = {}
        self._initialize_features()

    def _initialize_features(self) -> None:
        """初始化特性定义"""
        feature_definitions = {
            "use_new_agent_executor": FeatureDefinition(
                name="use_new_agent_executor",
                description="使用重构后的 Agent 执行器",
                status=FeatureStatus.DISABLED,
            ),
            "use_inference_engine_factory": FeatureDefinition(
                name="use_inference_engine_factory",
                description="使用推理引擎工厂模式",
                status=FeatureStatus.DISABLED,
            ),
            "use_new_memory_service": FeatureDefinition(
                name="use_new_memory_service",
                description="使用重构后的记忆服务",
                status=FeatureStatus.DISABLED,
            ),
            "use_event_bus": FeatureDefinition(
                name="use_event_bus",
                description="使用事件总线进行模块间通信",
                status=FeatureStatus.DISABLED,
            ),
            "use_di_container": FeatureDefinition(
                name="use_di_container",
                description="使用依赖注入容器",
                status=FeatureStatus.DISABLED,
            ),
        }

        for name, definition in feature_definitions.items():
            definition.status = (
                FeatureStatus.ENABLED if getattr(self.flags, name, False)
                else FeatureStatus.DISABLED
            )
            self._features[name] = definition

    def is_enabled(self, feature_name: str) -> bool:
        """检查特性是否启用"""
        if feature_name in self._features:
            feature = self._features[feature_name]

            if feature.status == FeatureStatus.ENABLED:
                return True

            if feature.status == FeatureStatus.PERCENTAGE:
                import random
                return random.randint(1, 100) <= feature.percentage

            if feature.status == FeatureStatus.CONDITIONAL:
                return self._evaluate_conditions(feature.conditions)

        return self.flags.is_enabled(feature_name)

    def _evaluate_conditions(self, conditions: dict[str, Any]) -> bool:
        """评估条件"""
        for key, expected_value in conditions.items():
            actual_value = os.getenv(key)
            if actual_value != expected_value:
                return False
        return True

    def enable(self, feature_name: str) -> None:
        """启用特性"""
        if feature_name in self._features:
            self._features[feature_name].status = FeatureStatus.ENABLED
            self._features[feature_name].updated_at = datetime.now()

        self.flags.enable(feature_name)
        self._notify_callbacks(feature_name, True)

    def disable(self, feature_name: str) -> None:
        """禁用特性"""
        if feature_name in self._features:
            self._features[feature_name].status = FeatureStatus.DISABLED
            self._features[feature_name].updated_at = datetime.now()

        self.flags.disable(feature_name)
        self._notify_callbacks(feature_name, False)

    def set_percentage(self, feature_name: str, percentage: int) -> None:
        """设置灰度百分比"""
        if feature_name in self._features:
            self._features[feature_name].status = FeatureStatus.PERCENTAGE
            self._features[feature_name].percentage = min(100, max(0, percentage))
            self._features[feature_name].updated_at = datetime.now()
            logger.info(f"特性灰度设置: {feature_name} = {percentage}%")

    def set_conditions(self, feature_name: str, conditions: dict[str, Any]) -> None:
        """设置条件判断"""
        if feature_name in self._features:
            self._features[feature_name].status = FeatureStatus.CONDITIONAL
            self._features[feature_name].conditions = conditions
            self._features[feature_name].updated_at = datetime.now()

    def on_change(self, feature_name: str, callback: Callable[[bool], None]) -> None:
        """注册特性变更回调"""
        if feature_name not in self._callbacks:
            self._callbacks[feature_name] = []
        self._callbacks[feature_name].append(callback)

    def _notify_callbacks(self, feature_name: str, enabled: bool) -> None:
        """通知回调"""
        for callback in self._callbacks.get(feature_name, []):
            try:
                callback(enabled)
            except Exception as e:
                logger.warning(f"特性回调错误: {e}")

    def get_feature_info(self, feature_name: str) -> FeatureDefinition | None:
        """获取特性信息"""
        return self._features.get(feature_name)

    def get_all_features(self) -> dict[str, FeatureDefinition]:
        """获取所有特性"""
        return self._features.copy()

    def get_enabled_features(self) -> list[str]:
        """获取已启用的特性列表"""
        return [name for name in self._features if self.is_enabled(name)]


_flags: FeatureFlags | None = None
_feature_manager: FeatureManager | None = None


def get_flags() -> FeatureFlags:
    """获取特性开关单例"""
    global _flags
    if _flags is None:
        _flags = FeatureFlags.from_env()
    return _flags


def get_feature_manager() -> FeatureManager:
    """获取特性管理器单例"""
    global _feature_manager
    if _feature_manager is None:
        _feature_manager = FeatureManager(get_flags())
    return _feature_manager


def reset_flags() -> FeatureFlags:
    """重置特性开关"""
    global _flags, _feature_manager
    _flags = FeatureFlags.from_env()
    _feature_manager = None
    return _flags


def feature_enabled(feature_name: str) -> Callable:
    """
    特性开关装饰器

    用法:
        @feature_enabled("use_new_agent_executor")
        def new_executor():
            ...

        @feature_enabled("use_new_agent_executor", fallback=old_executor)
        def execute():
            ...
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            if get_flags().is_enabled(feature_name):
                return func(*args, **kwargs)
            return None
        return wrapper
    return decorator


def feature_toggle(
    feature_name: str,
    new_impl: Callable,
    old_impl: Callable,
) -> Callable:
    """
    特性切换装饰器

    根据特性开关选择不同的实现

    用法:
        def execute():
            return feature_toggle(
                "use_new_agent_executor",
                new_executor,
                old_executor
            )()
    """
    def wrapper(*args, **kwargs):
        if get_flags().is_enabled(feature_name):
            return new_impl(*args, **kwargs)
        return old_impl(*args, **kwargs)
    return wrapper
