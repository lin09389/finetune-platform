"""
统一训练事件总线

将 TrainingState 进度更新、TrainingEventHubV2 事件发布
统一到一个入口，消除模块间对具体事件实现的直接依赖。
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable

from core.logging import get_logger
from core.training_events_v2 import get_training_event_hub_v2, normalize_phase_v2
from core.training_state import TrainingState

logger = get_logger(__name__)


@dataclass
class TrainingEvent:
    """内部训练事件"""
    task_id: str
    phase: str
    kind: str
    payload: dict[str, Any] = field(default_factory=dict)
    ts: str = field(default_factory=lambda: datetime.now().isoformat())


class TrainingEventBus:
    """
    训练事件总线 - 统一封装状态更新、V2 事件

    使用方式:
        bus = TrainingEventBus(state, task_id="xxx")
        bus.publish_progress(epoch=1, step=10, loss=0.5, status="running", message="...")
        bus.publish_event(phase="loading", kind="model_loaded", payload={...})
    """

    def __init__(
        self,
        state: TrainingState,
        task_id: str,
        event_loop: asyncio.AbstractEventLoop | None = None,
    ):
        self.state = state
        self.task_id = task_id
        self._event_loop = event_loop
        self._hub = get_training_event_hub_v2()
        self._subscribers: list[Callable[[TrainingEvent], None]] = []

    def subscribe(self, callback: Callable[[TrainingEvent], None]) -> None:
        """订阅内部事件（用于测试或额外处理）"""
        self._subscribers.append(callback)

    def unsubscribe(self, callback: Callable[[TrainingEvent], None]) -> None:
        """取消订阅"""
        if callback in self._subscribers:
            self._subscribers.remove(callback)

    def publish_progress(
        self,
        *,
        status: str,
        message: str,
        **kwargs: Any,
    ) -> None:
        """统一发布训练进度（同时更新 TrainingState + V2 Hub）"""
        self.state.queue_progress_update(status=status, message=message, **kwargs)

        phase = normalize_phase_v2(status)
        if phase:
            payload = {"status": status, "message": message, **kwargs}
            self._hub.publish(
                task_id=self.task_id,
                phase=phase,
                kind="progress_updated",
                payload=payload,
            )

        event = TrainingEvent(
            task_id=self.task_id,
            phase=phase or status,
            kind="progress_updated",
            payload={"status": status, "message": message, **kwargs},
        )
        self._notify_subscribers(event)

    def publish_event(
        self,
        phase: str,
        kind: str,
        payload: dict[str, Any] | None = None,
    ) -> None:
        """发布通用事件（同时更新 V2 Hub）"""
        self._hub.publish(
            task_id=self.task_id,
            phase=phase,
            kind=kind,
            payload=payload or {},
        )

        event = TrainingEvent(
            task_id=self.task_id,
            phase=phase,
            kind=kind,
            payload=payload or {},
        )
        self._notify_subscribers(event)

    def publish_training_state(self, is_training: bool) -> None:
        """发布训练状态变更"""
        self.state.queue_training_state(is_training)

    def _notify_subscribers(self, event: TrainingEvent) -> None:
        for cb in self._subscribers:
            try:
                cb(event)
            except Exception as e:
                logger.debug(f"事件订阅者回调失败：{e}")


class _NullState:
    """避免 NullTrainingEventBus 意外调用父类方法时崩溃"""
    def queue_progress_update(self, **kwargs): pass
    def queue_training_state(self, value): pass
    def queue_record_update(self, record): pass
    def queue_history_add(self, record): pass


class _NullHub:
    """避免 NullTrainingEventBus 意外调用父类方法时崩溃"""
    def publish(self, **kwargs): pass


class NullTrainingEventBus(TrainingEventBus):
    """空实现的事件总线，用于测试或禁用事件上报的场景"""

    def __init__(self):
        self.state = _NullState()
        self.task_id = "null"
        self._event_loop = None
        self._hub = _NullHub()
        self._subscribers = []

    def publish_progress(self, *, status: str, message: str, **kwargs: Any) -> None:
        pass

    def publish_event(self, phase: str, kind: str, payload: dict[str, Any] | None = None) -> None:
        pass

    def publish_training_state(self, is_training: bool) -> None:
        pass

    def subscribe(self, callback: Callable[[TrainingEvent], None]) -> None:
        pass

    def unsubscribe(self, callback: Callable[[TrainingEvent], None]) -> None:
        pass
