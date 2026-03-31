import asyncio
from dataclasses import dataclass, field
from datetime import datetime

import psutil

from core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class MemoryInfo:
    total_gb: float = 0.0
    used_gb: float = 0.0
    available_gb: float = 0.0
    free_gb: float = 0.0
    percent: float = 0.0
    swap_total_gb: float = 0.0
    swap_used_gb: float = 0.0
    swap_free_gb: float = 0.0
    swap_percent: float = 0.0
    cached_gb: float = 0.0
    buffers_gb: float = 0.0
    shared_gb: float = 0.0
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class MemoryHistory:
    timestamps: list[str] = field(default_factory=list)
    percent: list[float] = field(default_factory=list)
    used_gb: list[float] = field(default_factory=list)
    available_gb: list[float] = field(default_factory=list)
    swap_percent: list[float] = field(default_factory=list)


class MemoryMonitor:
    def __init__(self, history_size: int = 60):
        self._history_size = history_size
        self._history: MemoryHistory = MemoryHistory()
        self._lock = asyncio.Lock()
        self._warning_threshold = 80.0
        self._critical_threshold = 95.0

    async def get_info(self) -> MemoryInfo:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._get_info_sync)

    def _get_info_sync(self) -> MemoryInfo:
        try:
            mem = psutil.virtual_memory()
            swap = psutil.swap_memory()

            cached = getattr(mem, "cached", 0) / (1024 ** 3)
            buffers = getattr(mem, "buffers", 0) / (1024 ** 3)
            shared = getattr(mem, "shared", 0) / (1024 ** 3)

            return MemoryInfo(
                total_gb=mem.total / (1024 ** 3),
                used_gb=mem.used / (1024 ** 3),
                available_gb=mem.available / (1024 ** 3),
                free_gb=mem.free / (1024 ** 3),
                percent=mem.percent,
                swap_total_gb=swap.total / (1024 ** 3),
                swap_used_gb=swap.used / (1024 ** 3),
                swap_free_gb=swap.free / (1024 ** 3),
                swap_percent=swap.percent,
                cached_gb=cached,
                buffers_gb=buffers,
                shared_gb=shared,
            )
        except Exception as e:
            logger.error(f"获取内存信息失败: {e}")
            return MemoryInfo()

    async def update_history(self) -> MemoryInfo:
        info = await self.get_info()

        async with self._lock:
            self._history.timestamps.append(info.timestamp)
            self._history.percent.append(info.percent)
            self._history.used_gb.append(info.used_gb)
            self._history.available_gb.append(info.available_gb)
            self._history.swap_percent.append(info.swap_percent)

            while len(self._history.timestamps) > self._history_size:
                self._history.timestamps.pop(0)
                self._history.percent.pop(0)
                self._history.used_gb.pop(0)
                self._history.available_gb.pop(0)
                self._history.swap_percent.pop(0)

        return info

    async def get_history(self) -> MemoryHistory:
        async with self._lock:
            return MemoryHistory(
                timestamps=self._history.timestamps.copy(),
                percent=self._history.percent.copy(),
                used_gb=self._history.used_gb.copy(),
                available_gb=self._history.available_gb.copy(),
                swap_percent=self._history.swap_percent.copy(),
            )

    async def get_stats(self) -> dict:
        info = await self.get_info()
        return {
            "virtual": {
                "total_gb": round(info.total_gb, 2),
                "used_gb": round(info.used_gb, 2),
                "available_gb": round(info.available_gb, 2),
                "free_gb": round(info.free_gb, 2),
                "percent": round(info.percent, 2),
                "cached_gb": round(info.cached_gb, 2),
                "buffers_gb": round(info.buffers_gb, 2),
                "shared_gb": round(info.shared_gb, 2),
            },
            "swap": {
                "total_gb": round(info.swap_total_gb, 2),
                "used_gb": round(info.swap_used_gb, 2),
                "free_gb": round(info.swap_free_gb, 2),
                "percent": round(info.swap_percent, 2),
            },
            "timestamp": info.timestamp,
        }

    async def check_memory_pressure(self) -> dict:
        info = await self.get_info()

        status = "normal"
        warnings = []

        if info.percent >= self._critical_threshold:
            status = "critical"
            warnings.append(f"内存使用率过高: {info.percent:.1f}%")
        elif info.percent >= self._warning_threshold:
            status = "warning"
            warnings.append(f"内存使用率较高: {info.percent:.1f}%")

        if info.swap_percent > 50:
            warnings.append(f"交换空间使用较高: {info.swap_percent:.1f}%")
            if status == "normal":
                status = "warning"

        return {
            "status": status,
            "memory_percent": info.percent,
            "swap_percent": info.swap_percent,
            "warnings": warnings,
            "available_gb": round(info.available_gb, 2),
        }

    def set_thresholds(self, warning: float = 80.0, critical: float = 95.0):
        self._warning_threshold = warning
        self._critical_threshold = critical

    def clear_history(self):
        self._history = MemoryHistory()
