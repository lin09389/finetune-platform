import asyncio

import pytest

from api.inference.backends.base import GenerationResult
from api.inference.pipeline import LocalInferencePipeline


@pytest.mark.asyncio
async def test_local_inference_pipeline_attaches_queue_metadata():
    pipeline = LocalInferencePipeline()

    async def make_result():
        await asyncio.sleep(0.01)
        return GenerationResult(
            text="ok",
            tokens_generated=2,
            finish_reason="stop",
            model="demo",
            metadata={},
        )

    results = await asyncio.gather(
        pipeline.submit(
            pipeline_key="huggingface:demo:generate",
            prompt="hello",
            max_batch_size=4,
            max_wait_ms=20,
            timeout=5.0,
            executor=make_result,
        ),
        pipeline.submit(
            pipeline_key="huggingface:demo:generate",
            prompt="world",
            max_batch_size=4,
            max_wait_ms=20,
            timeout=5.0,
            executor=make_result,
        ),
    )

    assert all(isinstance(item, GenerationResult) for item in results)
    assert all("queue_wait_ms" in item.metadata for item in results)
    assert all(item.metadata["batch_size"] >= 1 for item in results)

    stats = pipeline.get_stats()
    assert "huggingface:demo:generate" in stats
    assert stats["huggingface:demo:generate"]["total_requests"] == 2

    await pipeline.shutdown()
