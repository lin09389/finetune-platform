from __future__ import annotations

import asyncio
import logging
import threading
from contextlib import suppress
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

_TERMINAL_EVENT_TYPES = {"session_completed", "session_failed", "session_interrupted"}


@dataclass(frozen=True)
class _EventSubscriber:
    queue: asyncio.Queue[dict[str, Any]]
    loop: asyncio.AbstractEventLoop


class AgentSessionEventBus:
    """In-process event fanout for agent session SSE subscribers."""

    _queues: dict[str, list[_EventSubscriber]] = {}
    _global_subscribers: list[_EventSubscriber] = []
    _lock = threading.Lock()

    def subscribe(self, session_id: str) -> asyncio.Queue[dict[str, Any]]:
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=512)
        with self._lock:
            self._queues.setdefault(session_id, []).append(_EventSubscriber(queue=queue, loop=loop))
        return queue

    def subscribe_global(self) -> asyncio.Queue[dict[str, Any]]:
        """Subscribe to events across **all** sessions (for multi-session awareness)."""
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=1024)
        with self._lock:
            self._global_subscribers.append(_EventSubscriber(queue=queue, loop=loop))
        return queue

    def unsubscribe_global(self, queue: asyncio.Queue[dict[str, Any]]) -> None:
        with self._lock:
            self._global_subscribers = [
                sub for sub in self._global_subscribers if sub.queue is not queue
            ]

    def unsubscribe(self, session_id: str, queue: asyncio.Queue[dict[str, Any]]) -> None:
        with self._lock:
            subscribers = self._queues.get(session_id)
            if not subscribers:
                return
            self._queues[session_id] = [subscriber for subscriber in subscribers if subscriber.queue is not queue]
            if not self._queues[session_id]:
                self._queues.pop(session_id, None)

    def notify(self, session_id: str, event: dict[str, Any]) -> None:
        with self._lock:
            subscribers = list(self._queues.get(session_id, []))
            global_subscribers = list(self._global_subscribers)
        for subscriber in subscribers:
            if subscriber.loop.is_closed():
                self._remove_subscriber(session_id, subscriber)
                continue
            try:
                subscriber.loop.call_soon_threadsafe(self._put_event, session_id, subscriber, event)
            except RuntimeError:
                self._remove_subscriber(session_id, subscriber)
        for subscriber in global_subscribers:
            if subscriber.loop.is_closed():
                self._remove_global_subscriber(subscriber)
                continue
            try:
                subscriber.loop.call_soon_threadsafe(self._put_event_global, session_id, subscriber, event)
            except RuntimeError:
                self._remove_global_subscriber(subscriber)

    def _put_event(self, session_id: str, subscriber: _EventSubscriber, event: dict[str, Any]) -> None:
        try:
            subscriber.queue.put_nowait(event)
        except asyncio.QueueFull:
            event_type = str(event.get("event_type") or "")
            if event_type in _TERMINAL_EVENT_TYPES:
                with suppress(asyncio.QueueEmpty):
                    subscriber.queue.get_nowait()
                with suppress(asyncio.QueueFull):
                    subscriber.queue.put_nowait(event)
            logger.warning("agent_session event queue full for session %s, event_type=%s", session_id, event_type)
        except Exception:
            self._remove_subscriber(session_id, subscriber)

    def _remove_subscriber(self, session_id: str, subscriber: _EventSubscriber) -> None:
        with self._lock:
            subscribers = self._queues.get(session_id)
            if not subscribers:
                return
            with suppress(ValueError):
                subscribers.remove(subscriber)
            if not subscribers:
                self._queues.pop(session_id, None)

    def _put_event_global(self, session_id: str, subscriber: _EventSubscriber, event: dict[str, Any]) -> None:
        """Deliver event to a global subscriber, tagged with session_id."""
        try:
            subscriber.queue.put_nowait({"session_id": session_id, **event})
        except asyncio.QueueFull:
            event_type = str(event.get("event_type") or "")
            if event_type in _TERMINAL_EVENT_TYPES:
                with suppress(asyncio.QueueEmpty):
                    subscriber.queue.get_nowait()
                with suppress(asyncio.QueueFull):
                    subscriber.queue.put_nowait({"session_id": session_id, **event})
            logger.warning("agent_session global event queue full, event_type=%s", event_type)
        except Exception:
            self._remove_global_subscriber(subscriber)

    def _remove_global_subscriber(self, subscriber: _EventSubscriber) -> None:
        with self._lock:
            with suppress(ValueError):
                self._global_subscribers.remove(subscriber)
