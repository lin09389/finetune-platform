"""
事件总线单元测试
"""
import asyncio

import pytest

from core.event_bus import (
    Event,
    EventBus,
    EventType,
    emit,
    get_event_bus,
    reset_event_bus,
    subscribe,
)


class TestEventBus:
    """事件总线测试"""

    def test_create_event_bus(self):
        """测试创建事件总线"""
        bus = EventBus()
        assert bus is not None
        assert bus.get_stats()["total_handlers"] == 0

    def test_subscribe_handler(self):
        """测试订阅处理器"""
        bus = EventBus()

        def handler(event: Event):
            pass

        bus.subscribe(EventType.TRAINING_STARTED, handler)

        stats = bus.get_stats()
        assert stats["total_handlers"] == 1
        assert EventType.TRAINING_STARTED in stats["event_types_registered"]

    def test_subscribe_once(self):
        """测试一次性订阅"""
        bus = EventBus()
        call_count = [0]

        def handler(event: Event):
            call_count[0] += 1

        bus.subscribe_once(EventType.TRAINING_COMPLETED, handler)

        event = Event(
            type=EventType.TRAINING_COMPLETED,
            payload={"test": "data"},
            source="test"
        )

        bus.publish(event)
        bus.publish(event)

        assert call_count[0] == 1

    def test_unsubscribe(self):
        """测试取消订阅"""
        bus = EventBus()

        def handler(event: Event):
            pass

        bus.subscribe(EventType.MODEL_LOADED, handler)
        assert bus.get_stats()["total_handlers"] == 1

        result = bus.unsubscribe(EventType.MODEL_LOADED, handler)
        assert result is True
        assert bus.get_stats()["total_handlers"] == 0

    def test_publish_event(self):
        """测试发布事件"""
        bus = EventBus()
        received = []

        def handler(event: Event):
            received.append(event)

        bus.subscribe(EventType.MEMORY_UPDATED, handler)

        event = Event(
            type=EventType.MEMORY_UPDATED,
            payload={"key": "value"},
            source="test"
        )

        bus.publish(event)

        assert len(received) == 1
        assert received[0].payload["key"] == "value"

    def test_event_history(self):
        """测试事件历史"""
        bus = EventBus(max_history=10)

        for i in range(15):
            event = Event(
                type=EventType.TRAINING_PROGRESS,
                payload={"step": i},
                source="test"
            )
            bus.publish(event)

        history = bus.get_history()
        assert len(history) == 10

    def test_event_filter(self):
        """测试事件过滤器"""
        bus = EventBus()
        received = []

        def handler(event: Event):
            received.append(event)

        def filter_fn(event: Event) -> bool:
            return event.payload.get("allowed", False)

        bus.subscribe(EventType.AGENT_ACTION_EXECUTED, handler)
        bus.add_filter(filter_fn)

        allowed_event = Event(
            type=EventType.AGENT_ACTION_EXECUTED,
            payload={"allowed": True},
            source="test"
        )
        blocked_event = Event(
            type=EventType.AGENT_ACTION_EXECUTED,
            payload={"allowed": False},
            source="test"
        )

        bus.publish(allowed_event)
        bus.publish(blocked_event)

        assert len(received) == 1
        assert received[0].payload["allowed"] is True

    def test_middleware(self):
        """测试中间件"""
        bus = EventBus()
        received = []

        def handler(event: Event):
            received.append(event)

        def middleware(event: Event):
            if event.payload.get("block", False):
                return None
            event.payload["modified"] = True
            return event

        bus.subscribe(EventType.CHAT_MESSAGE, handler)
        bus.add_middleware(middleware)

        normal_event = Event(
            type=EventType.CHAT_MESSAGE,
            payload={"text": "hello"},
            source="test"
        )
        blocked_event = Event(
            type=EventType.CHAT_MESSAGE,
            payload={"block": True},
            source="test"
        )

        bus.publish(normal_event)
        bus.publish(blocked_event)

        assert len(received) == 1
        assert received[0].payload["modified"] is True


class TestEventBusAsync:
    """事件总线异步测试"""

    @pytest.mark.asyncio
    async def test_async_handler(self):
        """测试异步处理器"""
        bus = EventBus()
        received = []

        async def async_handler(event: Event):
            await asyncio.sleep(0.01)
            received.append(event)

        bus.subscribe(EventType.TRAINING_STARTED, async_handler)

        event = Event(
            type=EventType.TRAINING_STARTED,
            payload={"async": True},
            source="test"
        )

        await bus.publish_async(event)

        assert len(received) == 1

    @pytest.mark.asyncio
    async def test_multiple_async_handlers(self):
        """测试多个异步处理器"""
        bus = EventBus()
        results = []

        async def handler1(event: Event):
            await asyncio.sleep(0.01)
            results.append("handler1")

        async def handler2(event: Event):
            await asyncio.sleep(0.01)
            results.append("handler2")

        bus.subscribe(EventType.MODEL_LOADED, handler1)
        bus.subscribe(EventType.MODEL_LOADED, handler2)

        event = Event(
            type=EventType.MODEL_LOADED,
            payload={},
            source="test"
        )

        await bus.publish_async(event)

        assert len(results) == 2
        assert "handler1" in results
        assert "handler2" in results


class TestEventBusSingleton:
    """事件总线单例测试"""

    def test_get_event_bus(self):
        """测试获取事件总线单例"""
        bus1 = get_event_bus()
        bus2 = get_event_bus()

        assert bus1 is bus2

    def test_reset_event_bus(self):
        """测试重置事件总线"""
        bus1 = get_event_bus()
        bus1.subscribe(EventType.TRAINING_STARTED, lambda e: None)

        bus2 = reset_event_bus()

        assert bus1 is not bus2
        assert bus2.get_stats()["total_handlers"] == 0


class TestEventBusDecorator:
    """事件总线装饰器测试"""

    def test_subscribe_decorator(self):
        """测试订阅装饰器"""
        received = []

        @subscribe(EventType.TRAINING_COMPLETED)
        def handler(event: Event):
            received.append(event)

        event = Event(
            type=EventType.TRAINING_COMPLETED,
            payload={},
            source="test"
        )

        get_event_bus().publish(event)

        assert len(received) == 1

    def test_emit_function(self):
        """测试 emit 函数"""
        received = []

        def handler(event: Event):
            received.append(event)

        get_event_bus().subscribe(EventType.MEMORY_UPDATED, handler)

        event = emit(
            EventType.MEMORY_UPDATED,
            {"test": "data"},
            "test_source"
        )

        assert len(received) == 1
        assert event.payload["test"] == "data"
