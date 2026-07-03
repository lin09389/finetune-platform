from __future__ import annotations

from inference_provider.client import get_inference_service_client


class RemoteInferenceRuntimeFacade:
    async def list_backends(self):
        return await get_inference_service_client().get_json("/inference/backends")

    async def list_models(self, backend: str | None = None):
        params = {"backend": backend} if backend else None
        return await get_inference_service_client().get_json("/inference/models", params=params)

    async def get_ollama_status(self):
        return await get_inference_service_client().get_json("/inference/ollama/status")


inference_runtime_facade = RemoteInferenceRuntimeFacade()

__all__ = ["RemoteInferenceRuntimeFacade", "inference_runtime_facade"]
