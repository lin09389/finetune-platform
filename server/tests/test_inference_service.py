import pytest

from api.inference.backends.base import GenerationResult
from inference_service.service import LocalInferenceService
from inference_service.types import LocalInferenceRequest


@pytest.mark.asyncio
async def test_local_inference_service_generate_cached_reuses_offline_cache(monkeypatch):
    call_count = {"value": 0}

    class FakeBackend:
        model_name = None

        async def generate(self, prompt, config):
            call_count["value"] += 1
            return GenerationResult(
                text=f"echo:{prompt}",
                tokens_generated=3,
                finish_reason="stop",
                prompt_tokens=2,
                total_tokens=5,
                latency_ms=10,
                model="demo",
                metadata={},
            )

    class FakeScheduler:
        async def get_backend(self, backend):
            return FakeBackend()

        def get_stats(self):
            return {"default_backend": "huggingface"}

        def resolve_model_path(self, model, backend=None):
            return model

        async def acquire_model(self, *args, **kwargs):
            return {"ok": True}

        async def release_model(self, model):
            return True

    monkeypatch.setattr("inference_service.service.get_scheduler", lambda: FakeScheduler())

    service = LocalInferenceService()
    request = LocalInferenceRequest(
        model="demo",
        backend="huggingface",
        prompt="hello",
        options={"temperature": 0.1},
    )

    first = await service.generate_cached(request)
    second = await service.generate_cached(request)

    assert first.content == "echo:hello"
    assert second.content == "echo:hello"
    assert call_count["value"] == 1
