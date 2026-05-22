from __future__ import annotations

import asyncio
import logging
import threading
from typing import Any

logger = logging.getLogger(__name__)


class AgentSessionEventBus:
    """In-process event fanout for agent session SSE subscribers."""

    _queues: dict[str, list[asyncio.Queue[dict[str, Any]]]] = {}
    _lock = threading.Lock()

    def subscribe(self, session_id: str) -> asyncio.Queue[dict[str, Any]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=512)
        with self._lock:
            self._queues.setdefault(session_id, []).append(queue)
        return queue

    def unsubscribe(self, session_id: str, queue: asyncio.Queue[dict[str, Any]]) -> None:
        with self._lock:
            queues = self._queues.get(session_id)
            if not queues:
                return
            try:
                queues.remove(queue)
            except ValueError:
                pass
            if not queues:
                self._queues.pop(session_id, None)

    def notify(self, session_id: str, event: dict[str, Any]) -> None:
        with self._lock:
            queues = list(self._queues.get(session_id, []))

        dead: list[asyncio.Queue[dict[str, Any]]] = []
        for queue in queues:
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                logger.warning("agent_session event queue full for session %s, dropping event", session_id)
            except Exception:
                dead.append(queue)

        if dead:
            with self._lock:
                active = self._queues.get(session_id)
                if active:
                    for queue in dead:
                        try:
                            active.remove(queue)
                        except ValueError:
                            pass
                    if not active:
                        self._queues.pop(session_id, None)
