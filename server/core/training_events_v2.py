"""
Training monitoring event protocol V2.

Provides a thread-safe in-memory event log with monotonic sequence numbers that
can be consumed by both SSE and WebSocket endpoints.
"""

from __future__ import annotations

import threading
import uuid
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Protocol

from pydantic import BaseModel, Field


TrainingPhaseV2 = str
SUPPORTED_PHASES_V2: tuple[str, ...] = (
    "queued",
    "loading",
    "running",
    "stopping",
    "stopped",
    "completed",
    "failed",
)

_PHASE_ALIASES: dict[str, str] = {
    "training": "running",
    "running": "running",
    "queued": "queued",
    "loading": "loading",
    "stopping": "stopping",
    "stopped": "stopped",
    "completed": "completed",
    "failed": "failed",
}


def normalize_phase_v2(status: str) -> str | None:
    normalized = _PHASE_ALIASES.get((status or "").strip().lower())
    if normalized in SUPPORTED_PHASES_V2:
        return normalized
    return None


class TrainingEventV2(BaseModel):
    event_id: str
    version: str = "v2"
    ts: str
    task_id: str
    phase: str
    kind: str
    payload: dict[str, Any] = Field(default_factory=dict)
    sequence: int


@dataclass
class _StoredEvent:
    sequence: int
    event: TrainingEventV2


class TrainingEventHubV2:
    """Thread-safe in-memory event hub with replay support."""

    MAX_LATEST_TASKS = 200

    def __init__(self, max_events: int = 8000):
        self._lock = threading.Lock()
        self._events: deque[_StoredEvent] = deque(maxlen=max_events)
        self._latest_by_task: dict[str, TrainingEventV2] = {}
        self._sequence = 0

    def publish(
        self,
        *,
        task_id: str,
        phase: str,
        kind: str,
        payload: dict[str, Any] | None = None,
    ) -> TrainingEventV2:
        with self._lock:
            self._sequence += 1
            sequence = self._sequence
            event = TrainingEventV2(
                event_id=f"tev2-{sequence}-{uuid.uuid4().hex[:8]}",
                ts=datetime.now(timezone.utc).isoformat(),
                task_id=task_id,
                phase=phase,
                kind=kind,
                payload=payload or {},
                sequence=sequence,
            )
            self._events.append(_StoredEvent(sequence=sequence, event=event))
            self._latest_by_task[task_id] = event
            if len(self._latest_by_task) > self.MAX_LATEST_TASKS:
                sorted_tasks = sorted(
                    self._latest_by_task.items(),
                    key=lambda item: item[1].sequence,
                )
                to_remove = len(sorted_tasks) - self.MAX_LATEST_TASKS // 2
                for key, _ in sorted_tasks[:to_remove]:
                    del self._latest_by_task[key]
            return event

    def list_since(self, sequence: int = 0, task_id: str | None = None) -> list[TrainingEventV2]:
        with self._lock:
            return [
                stored.event
                for stored in self._events
                if stored.sequence > sequence and (task_id is None or stored.event.task_id == task_id)
            ]

    def get_latest(self, task_id: str | None = None) -> TrainingEventV2 | None:
        with self._lock:
            if task_id is not None:
                return self._latest_by_task.get(task_id)
            if not self._events:
                return None
            return self._events[-1].event

    def parse_last_event_id(self, last_event_id: str | None) -> int:
        if not last_event_id:
            return 0
        try:
            if last_event_id.startswith("tev2-"):
                # tev2-{sequence}-{random}
                parts = last_event_id.split("-")
                if len(parts) >= 3:
                    return int(parts[1])
            return int(last_event_id)
        except Exception:
            return 0

    def current_sequence(self) -> int:
        with self._lock:
            return self._sequence


class TrainingEventHubProtocol(Protocol):
    def publish(self, *, task_id: str, phase: str, kind: str, payload=None) -> TrainingEventV2: ...
    def list_since(self, sequence: int = 0, task_id: str | None = None) -> list[TrainingEventV2]: ...
    def get_latest(self, task_id: str | None = None) -> TrainingEventV2 | None: ...
    def parse_last_event_id(self, last_event_id: str | None) -> int: ...
    def current_sequence(self) -> int: ...


_hub_v2: TrainingEventHubProtocol | None = None
_hub_lock = threading.Lock()


def get_training_event_hub_v2() -> TrainingEventHubProtocol:
    global _hub_v2
    with _hub_lock:
        if _hub_v2 is None:
            _hub_v2 = TrainingEventHubV2()
        return _hub_v2


def configure_training_event_hub_v2(hub: TrainingEventHubProtocol) -> None:
    """Replace the process-local hub, primarily with the SQLite-backed adapter."""
    global _hub_v2
    with _hub_lock:
        _hub_v2 = hub


def reset_training_event_hub_v2() -> None:
    global _hub_v2
    with _hub_lock:
        _hub_v2 = None
