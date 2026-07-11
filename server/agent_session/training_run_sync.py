"""Bounded control-plane reconciliation for Agent-linked training runs.

This module deliberately reads the Worker store but never gives the Worker an
Agent repository.  It owns one service-level task, not one task per link.
"""

from __future__ import annotations

import asyncio
import logging
import math
from collections.abc import Callable
from contextlib import suppress
from typing import Any, Protocol

from agent_training.models import TrainingRunSummary, training_activity_for

from .repository import AgentSessionRepository

logger = logging.getLogger(__name__)

_TERMINAL_STATUSES = frozenset({"completed", "failed", "cancelled", "stopped", "interrupted", "missing"})
_VISIBLE_EVENT_KINDS = frozenset({
    "task_queued", "task_requeued", "task_leased", "task_started", "progress",
    "task_completed", "task_failed", "task_cancelled", "task_stopped", "task_interrupted",
    "task_cancellation_requested",
})


class TrainingEventSource(Protocol):
    """Read-only seam for task-scoped authoritative training progress."""

    def list_events(self, task_id: str, after_sequence: int, limit: int) -> list[Any]: ...

    def get_run_summary(self, task_id: str) -> TrainingRunSummary | None: ...


def _finite_non_negative(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) and parsed >= 0 else None


class LocalSQLiteTrainingEventSource:
    """Read-only adapter for the existing training worker SQLite repository."""

    def __init__(self, repository: Any):
        self.repository = repository

    def list_events(self, task_id: str, after_sequence: int, limit: int) -> list[Any]:
        return self.repository.list_events(task_id=task_id, after_sequence=after_sequence, limit=limit)

    def get_run_summary(self, task_id: str) -> TrainingRunSummary | None:
        job = self.repository.get_job(task_id)
        if job is None:
            return None
        record = job.record if isinstance(job.record, dict) else {}
        config = job.config if isinstance(job.config, dict) else {}
        latest = self.repository.latest_event(task_id)
        metric = record.get("metrics") if isinstance(record.get("metrics"), dict) else {}
        return TrainingRunSummary(
            task_id=job.task_id,
            status=str(job.status or record.get("status") or "queued"),
            model_id=str(record.get("base_model_id") or record.get("model_name") or config.get("model_id") or "unknown"),
            dataset_id=str(record.get("dataset_id") or record.get("dataset_name") or config.get("dataset_id") or "unknown"),
            method=str(record.get("method") or config.get("method") or "unknown"),
            task_goal=record.get("task_goal"),
            started_at=str(job.started_at or record.get("start_time") or job.created_at),
            completed_at=job.finished_at or record.get("end_time"),
            output_path=job.output_path,
            adapter_path=record.get("adapter_path"),
            checkpoint_path=record.get("checkpoint_path"),
            final_loss=_finite_non_negative(record.get("final_loss")),
            elapsed_time=_finite_non_negative(record.get("elapsed_time")),
            phase=str(getattr(latest, "phase", "") or "") or None,
            step=self._integer(metric.get("step", record.get("step"))),
            total_steps=self._positive_integer(metric.get("total_steps", record.get("total_steps"))),
            epoch=_finite_non_negative(metric.get("epoch", record.get("epoch"))),
            loss=_finite_non_negative(metric.get("loss", record.get("loss"))),
            eta=_finite_non_negative(metric.get("eta", record.get("eta"))),
            updated_at=job.updated_at,
            artifact_available=bool(job.status == "completed" and (record.get("adapter_path") or record.get("checkpoint_path"))),
        )

    @staticmethod
    def _integer(value: Any) -> int | None:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return None
        return parsed if parsed >= 0 else None

    @staticmethod
    def _positive_integer(value: Any) -> int | None:
        parsed = LocalSQLiteTrainingEventSource._integer(value)
        return parsed if parsed and parsed > 0 else None


class TrainingRunReconciler:
    """Single bounded reconciler, explicitly started and stopped by lifespan."""

    def __init__(
        self,
        *,
        repository: AgentSessionRepository,
        event_source: TrainingEventSource,
        publish: Callable[[str, dict[str, Any]], None] | None = None,
        batch_size: int = 50,
        event_limit: int = 100,
        interval_seconds: float = 1.0,
        max_backoff_seconds: float = 15.0,
    ) -> None:
        self.repository = repository
        self.event_source = event_source
        self.publish = publish
        self.batch_size = max(1, min(int(batch_size), 500))
        self.event_limit = max(1, min(int(event_limit), 1000))
        self.interval_seconds = max(0.05, float(interval_seconds))
        self.max_backoff_seconds = max(self.interval_seconds, float(max_backoff_seconds))
        self._task: asyncio.Task[None] | None = None
        self._closed = False

    def start(self) -> None:
        if self._closed or self._task is not None:
            return
        self._task = asyncio.create_task(self._run(), name="agent-training-reconciler")

    async def close(self) -> None:
        self._closed = True
        if self._task is None:
            return
        self._task.cancel()
        with suppress(asyncio.CancelledError):
            await self._task
        self._task = None

    async def _run(self) -> None:
        backoff = self.interval_seconds
        while not self._closed:
            try:
                await self.reconcile_once()
                backoff = self.interval_seconds
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.warning("Agent training reconciliation failed; retaining the last safe projection", exc_info=True)
                backoff = min(self.max_backoff_seconds, max(self.interval_seconds, backoff * 2))
            await asyncio.sleep(backoff)

    async def reconcile_once(self) -> int:
        return await asyncio.to_thread(self._reconcile_once)

    def _reconcile_once(self) -> int:
        updated_links = 0
        for link in self.repository.list_training_links_for_reconciliation(limit=self.batch_size):
            if self._reconcile_link(link):
                updated_links += 1
        return updated_links

    def _reconcile_link(self, link: dict[str, Any]) -> bool:
        task_id = str(link.get("task_id") or "")
        if not task_id:
            return False
        after_sequence = int(link.get("last_event_sequence") or 0)
        events = self.event_source.list_events(task_id, after_sequence, self.event_limit)
        if not events:
            return False
        summary = self.event_source.get_run_summary(task_id)
        if summary is None:
            # A potentially lagging worker store is retried; no invented failure
            # or path-bearing event payload is persisted.
            return False
        activity = training_activity_for(summary).model_dump()
        changed = False
        projected_status = str(link.get("status") or "queued")
        for event in events:
            sequence = int(getattr(event, "sequence", 0) or 0)
            if sequence <= after_sequence:
                continue
            visible = str(getattr(event, "kind", "") or "") in _VISIBLE_EVENT_KINDS
            advanced = self.repository.advance_training_link(
                task_id,
                sequence=sequence,
                # Unknown events acknowledge only their sequence. They must not
                # alter a card's status, payload, or terminal presentation.
                status=summary.status if visible else projected_status,
                activity=activity if visible else None,
            )
            if not advanced:
                continue
            changed = True
            after_sequence = sequence
            if visible:
                projected_status = summary.status
            if visible and self.publish is not None:
                part = self.repository.get_part(str(link.get("part_id") or ""))
                if part is not None:
                    self.publish(str(link.get("session_id") or ""), part)
        return changed


__all__ = ["LocalSQLiteTrainingEventSource", "TrainingEventSource", "TrainingRunReconciler"]
