"""
动态批处理模块

实现请求队列和批处理：
- 请求队列管理
- 批处理超时机制
- 批处理结果分发
"""
import asyncio
import logging
import time
import uuid
from collections.abc import Awaitable, Callable
from contextlib import suppress
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class BatchRequestStatus(str, Enum):
    """请求状态"""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"


@dataclass
class BatchRequest:
    """批处理请求"""
    id: str
    prompt: str
    params: dict[str, Any]
    created_at: float = field(default_factory=time.time)
    started_at: float | None = None
    completed_at: float | None = None
    status: BatchRequestStatus = BatchRequestStatus.PENDING
    result: Any = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "prompt": self.prompt,
            "params": self.params,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "status": self.status.value,
            "result": self.result,
            "error": self.error,
        }


@dataclass
class BatchResult:
    """批处理结果"""
    batch_id: str
    requests: list[BatchRequest]
    total_time: float
    success_count: int
    failed_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "batch_id": self.batch_id,
            "requests": [r.to_dict() for r in self.requests],
            "total_time": self.total_time,
            "success_count": self.success_count,
            "failed_count": self.failed_count,
        }


class DynamicBatcher:
    """
    动态批处理器

    功能：
    - 请求队列管理
    - 自动批处理
    - 超时处理
    - 结果分发
    """

    def __init__(
        self,
        max_batch_size: int = 8,
        max_wait_time: float = 0.1,
        max_queue_size: int = 1000,
        timeout: float = 60.0,
    ):
        self.max_batch_size = max_batch_size
        self.max_wait_time = max_wait_time
        self.max_queue_size = max_queue_size
        self.timeout = timeout

        self._queue: asyncio.Queue[BatchRequest] = asyncio.Queue(maxsize=max_queue_size)
        self._pending: dict[str, asyncio.Future] = {}
        self._results: dict[str, BatchResult] = {}

        self._is_running = False
        self._worker_task: asyncio.Task | None = None
        self._processor: Callable | None = None

        self._stats = {
            "total_requests": 0,
            "total_batches": 0,
            "total_time": 0.0,
            "avg_batch_size": 0.0,
        }

    def set_processor(self, processor: Callable[[list[BatchRequest]], Awaitable[list[Any]]]):
        """设置批处理函数"""
        self._processor = processor

    async def start(self):
        """启动批处理器"""
        if self._is_running:
            logger.warning("批处理器已在运行")
            return

        self._is_running = True
        self._worker_task = asyncio.create_task(self._worker_loop())

        logger.info(f"动态批处理器已启动 (max_batch_size={self.max_batch_size}, max_wait_time={self.max_wait_time}s)")

    async def stop(self):
        """停止批处理器"""
        self._is_running = False

        if self._worker_task:
            self._worker_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._worker_task

        for future in self._pending.values():
            if not future.done():
                future.cancel()

        self._pending.clear()

        logger.info("动态批处理器已停止")

    async def submit(
        self,
        prompt: str,
        params: dict[str, Any] | None = None,
        timeout: float | None = None,
    ) -> Any:
        """
        提交请求

        返回处理结果
        """
        if self._queue.full():
            raise RuntimeError("批处理队列已满")

        request_id = str(uuid.uuid4())
        request = BatchRequest(
            id=request_id,
            prompt=prompt,
            params=params or {},
        )

        future: asyncio.Future = asyncio.get_event_loop().create_future()
        self._pending[request_id] = future

        await self._queue.put(request)
        self._stats["total_requests"] += 1

        try:
            timeout_val = timeout or self.timeout
            result = await asyncio.wait_for(future, timeout=timeout_val)
            return result
        except asyncio.TimeoutError:
            request.status = BatchRequestStatus.TIMEOUT
            request.error = "请求超时"
            return {"error": "timeout", "request_id": request_id}
        finally:
            self._pending.pop(request_id, None)

    async def _worker_loop(self):
        """工作循环"""
        while self._is_running:
            try:
                batch = await self._collect_batch()

                if batch:
                    await self._process_batch(batch)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"批处理工作循环错误: {e}", exc_info=True)
                await asyncio.sleep(0.1)

    async def _collect_batch(self) -> list[BatchRequest]:
        """收集一批请求"""
        batch = []
        deadline = time.time() + self.max_wait_time

        while len(batch) < self.max_batch_size:
            remaining_time = deadline - time.time()

            if remaining_time <= 0:
                break

            try:
                request = await asyncio.wait_for(
                    self._queue.get(),
                    timeout=remaining_time
                )
                batch.append(request)

            except asyncio.TimeoutError:
                break

        return batch

    async def _process_batch(self, batch: list[BatchRequest]):
        """处理一批请求"""
        if not batch:
            return

        batch_id = str(uuid.uuid4())
        start_time = time.time()

        for request in batch:
            request.status = BatchRequestStatus.PROCESSING
            request.started_at = start_time

        try:
            if self._processor:
                results = await self._processor(batch)
            else:
                results = await self._default_processor(batch)

            for request, result in zip(batch, results, strict=False):
                request.status = BatchRequestStatus.COMPLETED
                request.completed_at = time.time()
                request.result = result

                future = self._pending.get(request.id)
                if future and not future.done():
                    future.set_result(result)

        except Exception as e:
            logger.error(f"批处理失败: {e}", exc_info=True)

            for request in batch:
                request.status = BatchRequestStatus.FAILED
                request.completed_at = time.time()
                request.error = str(e)

                future = self._pending.get(request.id)
                if future and not future.done():
                    future.set_exception(e)

        total_time = time.time() - start_time
        self._stats["total_batches"] += 1
        self._stats["total_time"] += total_time
        self._stats["avg_batch_size"] = (
            (self._stats["avg_batch_size"] * (self._stats["total_batches"] - 1) + len(batch))
            / self._stats["total_batches"]
        )

        batch_result = BatchResult(
            batch_id=batch_id,
            requests=batch,
            total_time=total_time,
            success_count=sum(1 for r in batch if r.status == BatchRequestStatus.COMPLETED),
            failed_count=sum(1 for r in batch if r.status == BatchRequestStatus.FAILED),
        )
        self._results[batch_id] = batch_result

        logger.debug(f"批处理完成: {len(batch)} 个请求, 耗时 {total_time:.3f}s")

    async def _default_processor(self, batch: list[BatchRequest]) -> list[Any]:
        """默认处理器"""
        results = []
        for request in batch:
            results.append({
                "prompt": request.prompt,
                "response": f"Processed: {request.prompt[:50]}...",
                "params": request.params,
            })
        return results

    def get_stats(self) -> dict[str, Any]:
        """获取统计信息"""
        return {
            **self._stats,
            "queue_size": self._queue.qsize(),
            "pending_requests": len(self._pending),
            "is_running": self._is_running,
            "timeout_seconds": self.timeout,
            "max_wait_time_ms": round(self.max_wait_time * 1000, 2),
        }

    def get_queue_size(self) -> int:
        """获取队列大小"""
        return self._queue.qsize()

    def get_pending_count(self) -> int:
        """获取待处理请求数"""
        return len(self._pending)


class BatchScheduler:
    """
    批处理调度器

    管理多个批处理器实例
    """

    def __init__(self):
        self._batchers: dict[str, DynamicBatcher] = {}

    def create_batcher(
        self,
        name: str,
        max_batch_size: int = 8,
        max_wait_time: float = 0.1,
        **kwargs,
    ) -> DynamicBatcher:
        """创建批处理器"""
        if name in self._batchers:
            raise ValueError(f"批处理器已存在: {name}")

        batcher = DynamicBatcher(
            max_batch_size=max_batch_size,
            max_wait_time=max_wait_time,
            **kwargs,
        )
        self._batchers[name] = batcher
        return batcher

    def get_batcher(self, name: str) -> DynamicBatcher | None:
        """获取批处理器"""
        return self._batchers.get(name)

    async def start_all(self):
        """启动所有批处理器"""
        for batcher in self._batchers.values():
            await batcher.start()

    async def stop_all(self):
        """停止所有批处理器"""
        for batcher in self._batchers.values():
            await batcher.stop()

    def get_all_stats(self) -> dict[str, dict[str, Any]]:
        """获取所有批处理器统计"""
        return {name: batcher.get_stats() for name, batcher in self._batchers.items()}


_batch_scheduler: BatchScheduler | None = None


def get_batch_scheduler() -> BatchScheduler:
    """获取批处理调度器单例"""
    global _batch_scheduler
    if _batch_scheduler is None:
        _batch_scheduler = BatchScheduler()
    return _batch_scheduler
