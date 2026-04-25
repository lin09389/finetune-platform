"""Background worker for durable storage outbox tasks."""

from __future__ import annotations

import asyncio
import logging

from core.storage import (
    APP_DB_PATH,
    process_storage_outbox,
    storage_outbox_worker_batch_size,
    storage_outbox_worker_enabled,
    storage_outbox_worker_interval,
)

logger = logging.getLogger(__name__)


class StorageOutboxWorker:
    """Small asyncio worker that periodically drains the SQLite outbox."""

    def __init__(
        self,
        db_path: str = APP_DB_PATH,
        interval_seconds: float | None = None,
        batch_size: int | None = None,
    ):
        self.db_path = db_path
        self.interval_seconds = interval_seconds if interval_seconds is not None else storage_outbox_worker_interval()
        self.batch_size = batch_size if batch_size is not None else storage_outbox_worker_batch_size()
        self._task: asyncio.Task | None = None
        self._stop_event = asyncio.Event()
        self.last_result: dict | None = None

    async def start(self) -> None:
        if not storage_outbox_worker_enabled():
            logger.info("Storage outbox worker disabled")
            return
        if self._task and not self._task.done():
            return
        self._stop_event.clear()
        self._task = asyncio.create_task(self._run(), name="storage-outbox-worker")
        logger.info(
            "Storage outbox worker started interval=%ss batch_size=%s",
            self.interval_seconds,
            self.batch_size,
        )

    async def stop(self) -> None:
        self._stop_event.set()
        if not self._task:
            return
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        logger.info("Storage outbox worker stopped")

    async def process_once(self) -> dict:
        result = await asyncio.to_thread(
            process_storage_outbox,
            db_path=self.db_path,
            limit=self.batch_size,
        )
        self.last_result = result
        return result

    async def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                await self.process_once()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning("Storage outbox worker pass failed: %s", exc, exc_info=True)

            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=self.interval_seconds)
            except asyncio.TimeoutError:
                continue


_storage_outbox_worker: StorageOutboxWorker | None = None


def get_storage_outbox_worker(db_path: str = APP_DB_PATH) -> StorageOutboxWorker:
    global _storage_outbox_worker
    if _storage_outbox_worker is None:
        _storage_outbox_worker = StorageOutboxWorker(db_path=db_path)
    return _storage_outbox_worker
