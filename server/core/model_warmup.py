"""模型预热管理。"""
from __future__ import annotations

import asyncio
import time
from typing import Any


class ModelWarmupManager:
    def __init__(self):
        self._results: dict[str, dict[str, Any]] = {}
        self._lock = asyncio.Lock()

    async def warmup_model(self, *, model_name: str, backend: Any, prompt: str) -> dict[str, Any]:
        async with self._lock:
            result = self._results.get(model_name)
            if result and result.get("success"):
                return result

            started_at = time.perf_counter()
            success = False
            error = None
            try:
                success = await backend.warmup(prompt=prompt)
            except Exception as exc:
                error = str(exc)

            payload = {
                "success": success,
                "latency_ms": round((time.perf_counter() - started_at) * 1000, 2),
                "error": error,
                "timestamp": time.time(),
            }
            self._results[model_name] = payload
            return payload

    def get_result(self, model_name: str) -> dict[str, Any] | None:
        return self._results.get(model_name)

    def get_all_results(self) -> dict[str, dict[str, Any]]:
        return dict(self._results)


_warmup_manager: ModelWarmupManager | None = None


def get_model_warmup_manager() -> ModelWarmupManager:
    global _warmup_manager
    if _warmup_manager is None:
        _warmup_manager = ModelWarmupManager()
    return _warmup_manager
