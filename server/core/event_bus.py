"""
事件总线 - 模块间解耦通信机制
用于解决循环依赖问题，实现发布-订阅模式
"""
import asyncio
import logging
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class EventType(str, Enum):
    TRAINING_STARTED = "training.started"
    TRAINING_PROGRESS = "training.progress"
    TRAINING_COMPLETED = "training.completed"
    TRAINING_FAILED = "training.failed"
    MODEL_LOADED = "model.loaded"
    MODEL_UNLOADED = "model.unloaded"
    MEMORY_UPDATED = "memory.updated"
    MEMORY_RECALLED = "memory.recalled"
    AGENT_ACTION_EXECUTED = "agent.action.executed"
    AGENT_ACTION_FAILED = "agent.action.failed"
    FILE_OPERATION = "file.operation"
    CHAT_MESSAGE = "chat.message"
    SYSTEM_ALERT = "system.alert"
    CACHE_CLEARED = "cache.cleared"
    CONFIG_CHANGED = "config.changed"


@dataclass
class Event:
    type: EventType
    payload: dict[str, Any]
    source: str
    timestamp: datetime = field(default_factory=datetime.now)
    event_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "type": self.type.value,
            "source": self.source,
            "timestamp": self.timestamp.isoformat(),
            "payload": self.payload,
            "metadata": self.metadata,
        }


EventHandler = Callable[[Event], Any]
AsyncEventHandler = Callable[[Event], Any]


class EventBus:
    """
    事件总线实现
    
    特性:
    - 支持同步和异步事件处理器
    - 支持事件过滤
    - 支持一次性订阅
    - 支持事件历史记录
    - 线程安全
    """

    def __init__(self, max_history: int = 100):
        self._handlers: dict[EventType, list[EventHandler]] = {}
        self._async_handlers: dict[EventType, list[AsyncEventHandler]] = {}
        self._once_handlers: dict[EventType, set[EventHandler]] = {}
        self._filters: list[Callable[[Event], bool]] = []
        self._history: list[Event] = []
        self._max_history = max_history
        self._lock = asyncio.Lock()
        self._middleware: list[Callable[[Event], Event | None]] = []

    def subscribe(
        self,
        event_type: EventType,
        handler: EventHandler,
        once: bool = False
    ) -> 'EventBus':
        """
        订阅事件
        
        Args:
            event_type: 事件类型
            handler: 事件处理器
            once: 是否只处理一次
            
        Returns:
            self (支持链式调用)
        """
        if asyncio.iscoroutinefunction(handler):
            if event_type not in self._async_handlers:
                self._async_handlers[event_type] = []
            self._async_handlers[event_type].append(handler)
        else:
            if event_type not in self._handlers:
                self._handlers[event_type] = []
            self._handlers[event_type].append(handler)

        if once:
            if event_type not in self._once_handlers:
                self._once_handlers[event_type] = set()
            self._once_handlers[event_type].add(handler)

        logger.debug(f"订阅事件: {event_type.value} -> {handler.__name__}")
        return self

    def subscribe_once(self, event_type: EventType, handler: EventHandler) -> 'EventBus':
        """订阅事件（只处理一次）"""
        return self.subscribe(event_type, handler, once=True)

    def unsubscribe(self, event_type: EventType, handler: EventHandler) -> bool:
        """
        取消订阅
        
        Args:
            event_type: 事件类型
            handler: 事件处理器
            
        Returns:
            是否成功取消
        """
        removed = False

        if event_type in self._handlers and handler in self._handlers[event_type]:
            self._handlers[event_type].remove(handler)
            removed = True

        if event_type in self._async_handlers and handler in self._async_handlers[event_type]:
            self._async_handlers[event_type].remove(handler)
            removed = True

        if event_type in self._once_handlers and handler in self._once_handlers[event_type]:
            self._once_handlers[event_type].remove(handler)

        if removed:
            logger.debug(f"取消订阅: {event_type.value} -> {handler.__name__}")

        return removed

    def add_filter(self, filter_func: Callable[[Event], bool]) -> 'EventBus':
        """
        添加事件过滤器
        
        Args:
            filter_func: 过滤函数，返回 True 表示允许事件通过
            
        Returns:
            self
        """
        self._filters.append(filter_func)
        return self

    def add_middleware(
        self,
        middleware: Callable[[Event], Event | None]
    ) -> 'EventBus':
        """
        添加中间件
        
        Args:
            middleware: 中间件函数，可以修改或拦截事件
                       返回 None 表示拦截事件
                       
        Returns:
            self
        """
        self._middleware.append(middleware)
        return self

    def publish(self, event: Event) -> None:
        """
        同步发布事件
        
        Args:
            event: 事件对象
        """
        for filter_func in self._filters:
            if not filter_func(event):
                logger.debug(f"事件被过滤: {event.event_id}")
                return

        for middleware in self._middleware:
            event = middleware(event)
            if event is None:
                logger.debug(f"事件被中间件拦截: {event.event_id if event else 'unknown'}")
                return

        self._add_to_history(event)

        handlers = self._handlers.get(event.type, [])
        once_handlers = self._once_handlers.get(event.type, set())

        handlers_to_remove = []

        for handler in handlers:
            try:
                handler(event)
                if handler in once_handlers:
                    handlers_to_remove.append(handler)
            except Exception as e:
                logger.error(f"事件处理器错误 [{handler.__name__}]: {e}", exc_info=True)

        for handler in handlers_to_remove:
            self.unsubscribe(event.type, handler)

        logger.debug(f"事件已发布: {event.type.value} (ID: {event.event_id})")

    async def publish_async(self, event: Event) -> None:
        """
        异步发布事件
        
        Args:
            event: 事件对象
        """
        for filter_func in self._filters:
            if not filter_func(event):
                logger.debug(f"事件被过滤: {event.event_id}")
                return

        for middleware in self._middleware:
            if asyncio.iscoroutinefunction(middleware):
                event = await middleware(event)
            else:
                event = middleware(event)

            if event is None:
                logger.debug("事件被中间件拦截")
                return

        self._add_to_history(event)

        sync_handlers = self._handlers.get(event.type, [])
        async_handlers = self._async_handlers.get(event.type, [])
        once_handlers = self._once_handlers.get(event.type, set())

        handlers_to_remove = []

        for handler in sync_handlers:
            try:
                handler(event)
                if handler in once_handlers:
                    handlers_to_remove.append(handler)
            except Exception as e:
                logger.error(f"同步处理器错误 [{handler.__name__}]: {e}", exc_info=True)

        for handler in async_handlers:
            try:
                await handler(event)
                if handler in once_handlers:
                    handlers_to_remove.append(handler)
            except Exception as e:
                logger.error(f"异步处理器错误 [{handler.__name__}]: {e}", exc_info=True)

        for handler in handlers_to_remove:
            self.unsubscribe(event.type, handler)

        logger.debug(f"事件已异步发布: {event.type.value} (ID: {event.event_id})")

    def _add_to_history(self, event: Event) -> None:
        """添加事件到历史记录"""
        self._history.append(event)
        if len(self._history) > self._max_history:
            self._history.pop(0)

    def get_history(
        self,
        event_type: EventType | None = None,
        limit: int = 10
    ) -> list[Event]:
        """
        获取事件历史
        
        Args:
            event_type: 过滤事件类型（可选）
            limit: 返回数量限制
            
        Returns:
            事件列表
        """
        if event_type:
            events = [e for e in self._history if e.type == event_type]
        else:
            events = self._history.copy()

        return events[-limit:]

    def clear_history(self) -> None:
        """清空事件历史"""
        self._history.clear()

    def get_stats(self) -> dict[str, Any]:
        """获取事件总线统计信息"""
        return {
            "total_handlers": sum(len(h) for h in self._handlers.values()) +
                            sum(len(h) for h in self._async_handlers.values()),
            "event_types_registered": list(set(
                list(self._handlers.keys()) + list(self._async_handlers.keys())
            )),
            "history_size": len(self._history),
            "filters_count": len(self._filters),
            "middleware_count": len(self._middleware),
        }

    def clear_all(self) -> None:
        """清空所有订阅"""
        self._handlers.clear()
        self._async_handlers.clear()
        self._once_handlers.clear()
        self._filters.clear()
        self._middleware.clear()
        self._history.clear()
        logger.info("事件总线已清空")


_event_bus: EventBus | None = None


def get_event_bus() -> EventBus:
    """获取事件总线单例"""
    global _event_bus
    if _event_bus is None:
        _event_bus = EventBus()
    return _event_bus


def reset_event_bus() -> EventBus:
    """重置事件总线"""
    global _event_bus
    _event_bus = EventBus()
    return _event_bus


def subscribe(event_type: EventType) -> Callable:
    """
    事件订阅装饰器
    
    用法:
        @subscribe(EventType.TRAINING_COMPLETED)
        def on_training_completed(event: Event):
            print(f"训练完成: {event.payload}")
    """
    def decorator(func: EventHandler) -> EventHandler:
        get_event_bus().subscribe(event_type, func)
        return func
    return decorator


def emit(event_type: EventType, payload: dict[str, Any], source: str = "unknown") -> Event:
    """
    快捷发布事件
    
    Args:
        event_type: 事件类型
        payload: 事件数据
        source: 事件来源
        
    Returns:
        创建的事件对象
    """
    event = Event(
        type=event_type,
        payload=payload,
        source=source
    )
    get_event_bus().publish(event)
    return event


async def emit_async(
    event_type: EventType,
    payload: dict[str, Any],
    source: str = "unknown"
) -> Event:
    """
    快捷异步发布事件
    
    Args:
        event_type: 事件类型
        payload: 事件数据
        source: 事件来源
        
    Returns:
        创建的事件对象
    """
    event = Event(
        type=event_type,
        payload=payload,
        source=source
    )
    await get_event_bus().publish_async(event)
    return event
