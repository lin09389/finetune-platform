"""统一本地推理服务层回调与取消令牌。"""
from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

from inference_service.types import LocalInferenceProgress

ProgressCallback = Callable[[LocalInferenceProgress], Awaitable[None] | None]


class CancellationToken:
    def __init__(self):
        self._event = asyncio.Event()

    def cancel(self) -> None:
        self._event.set()

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()

    async def wait(self) -> None:
        await self._event.wait()
