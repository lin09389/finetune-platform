"""
操作注册机制
支持装饰器方式注册操作，替代硬编码的 action_map
"""
import logging
from typing import Dict, Any, Optional, List, Callable, Awaitable, Union
from dataclasses import dataclass, field
from enum import Enum
from functools import wraps
import asyncio

logger = logging.getLogger(__name__)


class ActionCategory(str, Enum):
    """操作分类"""
    FILE_OPERATION = "file_operation"
    SYSTEM_CONTROL = "system_control"
    APPLICATION = "application"
    CUA_OPERATION = "cua_operation"
    NETWORK = "network"
    CLIPBOARD = "clipboard"
    HARDWARE = "hardware"
    CUSTOM = "custom"


class ActionRiskLevel(str, Enum):
    """操作风险等级"""
    SAFE = "safe"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class ActionMetadata:
    """操作元数据"""
    name: str
    description: str = ""
    category: ActionCategory = ActionCategory.CUSTOM
    risk_level: ActionRiskLevel = ActionRiskLevel.LOW
    requires_confirmation: bool = False
    requires_elevation: bool = False
    params_schema: Dict[str, Any] = field(default_factory=dict)
    examples: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    version: str = "1.0.0"
    author: str = ""
    deprecated: bool = False
    replacement: Optional[str] = None


@dataclass
class ActionHandler:
    """操作处理器"""
    action: str
    handler: Callable
    metadata: ActionMetadata
    is_async: bool = False


class ActionRegistry:
    """操作注册表"""
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self._handlers: Dict[str, ActionHandler] = {}
        self._metadata: Dict[str, ActionMetadata] = {}
        self._categories: Dict[ActionCategory, List[str]] = {}
        self._aliases: Dict[str, str] = {}
        self._initialized = True
    
    def register(
        self,
        action: str,
        handler: Callable,
        metadata: Optional[ActionMetadata] = None,
        aliases: Optional[List[str]] = None
    ) -> None:
        if action in self._handlers:
            logger.warning(f"操作 '{action}' 已存在，将被覆盖")
        
        if metadata is None:
            metadata = ActionMetadata(name=action)
        
        is_async = asyncio.iscoroutinefunction(handler)
        
        self._handlers[action] = ActionHandler(
            action=action,
            handler=handler,
            metadata=metadata,
            is_async=is_async
        )
        self._metadata[action] = metadata
        
        if metadata.category not in self._categories:
            self._categories[metadata.category] = []
        if action not in self._categories[metadata.category]:
            self._categories[metadata.category].append(action)
        
        if aliases:
            for alias in aliases:
                self._aliases[alias] = action
        
        logger.debug(f"注册操作: {action} (类别: {metadata.category.value}, 异步: {is_async})")
    
    def unregister(self, action: str) -> bool:
        if action not in self._handlers:
            return False
        
        handler = self._handlers[action]
        category = handler.metadata.category
        
        del self._handlers[action]
        del self._metadata[action]
        
        if category in self._categories and action in self._categories[category]:
            self._categories[category].remove(action)
        
        aliases_to_remove = [k for k, v in self._aliases.items() if v == action]
        for alias in aliases_to_remove:
            del self._aliases[alias]
        
        return True
    
    def get_handler(self, action: str) -> Optional[Callable]:
        actual_action = self._aliases.get(action, action)
        handler_info = self._handlers.get(actual_action)
        return handler_info.handler if handler_info else None
    
    def get_metadata(self, action: str) -> Optional[ActionMetadata]:
        actual_action = self._aliases.get(action, action)
        return self._metadata.get(actual_action)
    
    def get_handler_info(self, action: str) -> Optional[ActionHandler]:
        actual_action = self._aliases.get(action, action)
        return self._handlers.get(actual_action)
    
    def is_async(self, action: str) -> bool:
        actual_action = self._aliases.get(action, action)
        handler_info = self._handlers.get(actual_action)
        return handler_info.is_async if handler_info else False
    
    def has_action(self, action: str) -> bool:
        actual_action = self._aliases.get(action, action)
        return actual_action in self._handlers
    
    def list_actions(self) -> List[str]:
        return list(self._handlers.keys())
    
    def list_actions_by_category(self, category: ActionCategory) -> List[str]:
        return self._categories.get(category, [])
    
    def list_all_metadata(self) -> Dict[str, ActionMetadata]:
        return self._metadata.copy()
    
    def get_actions_requiring_confirmation(self) -> List[str]:
        return [
            action for action, meta in self._metadata.items()
            if meta.requires_confirmation
        ]
    
    def get_actions_by_risk_level(self, risk_level: ActionRiskLevel) -> List[str]:
        return [
            action for action, meta in self._metadata.items()
            if meta.risk_level == risk_level
        ]


def action_handler(
    action: str,
    description: str = "",
    category: ActionCategory = ActionCategory.CUSTOM,
    risk_level: ActionRiskLevel = ActionRiskLevel.LOW,
    requires_confirmation: bool = False,
    requires_elevation: bool = False,
    params_schema: Optional[Dict[str, Any]] = None,
    examples: Optional[List[str]] = None,
    tags: Optional[List[str]] = None,
    aliases: Optional[List[str]] = None
):
    """
    操作处理器装饰器
    
    使用示例:
        @action_handler(
            action="file_create",
            description="创建文件",
            category=ActionCategory.FILE_OPERATION,
            params_schema={
                "file_path": {"type": "string", "required": True},
                "content": {"type": "string", "required": False}
            }
        )
        async def create_file(params: Dict[str, Any]) -> Dict[str, Any]:
            # 实现逻辑
            pass
    """
    def decorator(func: Callable) -> Callable:
        metadata = ActionMetadata(
            name=action,
            description=description,
            category=category,
            risk_level=risk_level,
            requires_confirmation=requires_confirmation,
            requires_elevation=requires_elevation,
            params_schema=params_schema or {},
            examples=examples or [],
            tags=tags or []
        )
        
        registry = get_action_registry()
        registry.register(action, func, metadata, aliases)
        
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            return await func(*args, **kwargs)
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            return func(*args, **kwargs)
        
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper
    
    return decorator


def get_action_registry() -> ActionRegistry:
    """获取操作注册表单例"""
    return ActionRegistry()


def register_action(
    action: str,
    handler: Callable,
    **metadata_kwargs
) -> None:
    """便捷注册函数"""
    metadata = ActionMetadata(name=action, **metadata_kwargs)
    get_action_registry().register(action, handler, metadata)
