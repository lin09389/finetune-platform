"""本地推理异步流水线与动态批处理接入。"""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from core.batching import BatchRequest, BatchScheduler


class LocalInferencePipeline:
    def __init__(self):
        self._scheduler = BatchScheduler()
        self._started: set[str] = set()

    async def submit(
        self,
        *,
        pipeline_key: str,
        prompt: str,
        max_batch_size: int,
        max_wait_ms: int,
        timeout: float,
        executor: Callable[[], Awaitable[Any]],
    ) -> Any:
        batcher = self._scheduler.get_batcher(pipeline_key)
        if batcher is None:
            batcher = self._scheduler.create_batcher(
                pipeline_key,
                max_batch_size=max_batch_size,
                max_wait_time=max_wait_ms / 1000.0,
                timeout=timeout,
            )
            batcher.set_processor(self._build_processor())

        if pipeline_key not in self._started:
            await batcher.start()
            self._started.add(pipeline_key)

        return await batcher.submit(prompt, params={"executor": executor})

    def _build_processor(self) -> Callable[[list[BatchRequest]], Awaitable[list[Any]]]:
        async def processor(batch: list[BatchRequest]) -> list[Any]:
            results: list[Any] = []
            batch_size = len(batch)
            for request in batch:
                queue_wait_ms = max(0.0, (request.started_at or 0.0) - request.created_at) * 1000
                result = await request.params["executor"]()
                metadata = getattr(result, "metadata", None)
                if isinstance(metadata, dict):
                    metadata.setdefault("queue_wait_ms", round(queue_wait_ms, 2))
                    metadata.setdefault("batch_size", batch_size)
                results.append(result)
            return results

        return processor

    def get_stats(self) -> dict[str, dict[str, Any]]:
        return self._scheduler.get_all_stats()

    async def shutdown(self) -> None:
        await self._scheduler.stop_all()
        self._started.clear()


_pipeline: LocalInferencePipeline | None = None


def get_local_inference_pipeline() -> LocalInferencePipeline:
    global _pipeline
    if _pipeline is None:
        _pipeline = LocalInferencePipeline()
    return _pipeline
