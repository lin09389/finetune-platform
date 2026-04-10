"""
内存压力监控模块
实时监控内存使用，支持自动清理和告警
"""
import asyncio
import logging
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class PressureLevel(Enum):
    NORMAL = "normal"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass
class MemoryStatus:
    level: PressureLevel
    vram_used_percent: float
    ram_used_percent: float
    vram_available_gb: float
    ram_available_gb: float
    vram_total_gb: float
    ram_total_gb: float
    timestamp: datetime


class MemoryMonitor:
    """内存压力监控器"""

    def __init__(
        self,
        warning_threshold: float = 0.8,
        critical_threshold: float = 0.9,
        check_interval: int = 30,
        auto_cleanup: bool = True
    ):
        self.warning_threshold = warning_threshold
        self.critical_threshold = critical_threshold
        self.check_interval = check_interval
        self.auto_cleanup = auto_cleanup

        self._callbacks: list[Callable[[MemoryStatus], None]] = []
        self._running = False
        self._task: asyncio.Task | None = None
        self._last_status: MemoryStatus | None = None
        self._history: list[MemoryStatus] = []
        self._max_history = 100

    def register_callback(self, callback: Callable[[MemoryStatus], None]):
        self._callbacks.append(callback)

    def unregister_callback(self, callback: Callable[[MemoryStatus], None]):
        if callback in self._callbacks:
            self._callbacks.remove(callback)

    async def start(self):
        if self._running:
            return

        self._running = True
        self._task = asyncio.create_task(self._monitor_loop())
        logger.info(f"内存监控启动 (警告阈值: {self.warning_threshold:.0%}, 临界阈值: {self.critical_threshold:.0%})")

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
            with suppress(asyncio.CancelledError):
                await self._task
        logger.info("内存监控停止")

    async def _monitor_loop(self):
        while self._running:
            try:
                status = await self.check_pressure()
                self._last_status = status

                self._history.append(status)
                if len(self._history) > self._max_history:
                    self._history.pop(0)

                if status.level != PressureLevel.NORMAL:
                    await self._handle_pressure(status)

                await asyncio.sleep(self.check_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"内存监控错误: {e}")
                await asyncio.sleep(5)

    async def check_pressure(self) -> MemoryStatus:
        import psutil

        ram = psutil.virtual_memory()
        ram_used_percent = ram.percent / 100
        ram_available_gb = ram.available / (1024 ** 3)
        ram_total_gb = ram.total / (1024 ** 3)

        vram_used_percent = 0.0
        vram_available_gb = 0.0
        vram_total_gb = 0.0

        try:
            import torch
            if torch.cuda.is_available():
                vram_total_gb = torch.cuda.get_device_properties(0).total_memory / (1024 ** 3)
                vram_used = torch.cuda.memory_allocated(0)
                vram_reserved = torch.cuda.memory_reserved(0)
                vram_used_percent = vram_used / (vram_total_gb * 1024 ** 3) if vram_total_gb > 0 else 0
                vram_available_gb = vram_total_gb - (vram_reserved / (1024 ** 3))
        except Exception as e:
            logger.debug(f"GPU 内存检查失败: {e}")

        max_usage = max(ram_used_percent, vram_used_percent)
        if max_usage >= self.critical_threshold:
            level = PressureLevel.CRITICAL
        elif max_usage >= self.warning_threshold:
            level = PressureLevel.WARNING
        else:
            level = PressureLevel.NORMAL

        return MemoryStatus(
            level=level,
            vram_used_percent=vram_used_percent,
            ram_used_percent=ram_used_percent,
            vram_available_gb=vram_available_gb,
            ram_available_gb=ram_available_gb,
            vram_total_gb=vram_total_gb,
            ram_total_gb=ram_total_gb,
            timestamp=datetime.now()
        )

    async def _handle_pressure(self, status: MemoryStatus):
        level_emoji = "⚠️" if status.level == PressureLevel.WARNING else "🔴"
        logger.warning(
            f"{level_emoji} 内存压力: {status.level.value}, "
            f"VRAM: {status.vram_used_percent:.1%}, "
            f"RAM: {status.ram_used_percent:.1%}"
        )

        for callback in self._callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(status)
                else:
                    callback(status)
            except Exception as e:
                logger.error(f"内存压力回调失败: {e}")

        if self.auto_cleanup and status.level == PressureLevel.CRITICAL:
            await self._emergency_cleanup()

    async def _emergency_cleanup(self):
        logger.warning("执行紧急内存清理...")

        try:
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                torch.cuda.synchronize()
                logger.info("GPU 缓存已清理")
        except Exception as e:
            logger.error(f"GPU 缓存清理失败: {e}")

        import gc
        collected = gc.collect()
        logger.info(f"Python GC 回收了 {collected} 个对象")

        try:
            from api.inference.scheduler import get_scheduler
            scheduler = get_scheduler()
            if hasattr(scheduler, 'unload_least_used'):
                await scheduler.unload_least_used()
                logger.info("已卸载最少使用的模型")
        except Exception as e:
            logger.debug(f"模型卸载失败: {e}")

        try:
            from core.distributed_cache import get_cache
            cache = get_cache()
            if hasattr(cache, '_memory_cache'):
                cache._memory_cache.clear()
                cache._access_order.clear()
                logger.info("内存缓存已清理")
        except Exception as e:
            logger.debug(f"缓存清理失败: {e}")

        logger.info("紧急内存清理完成")

    def get_status(self) -> MemoryStatus | None:
        return self._last_status

    def get_history(self, limit: int = 10) -> list[MemoryStatus]:
        return self._history[-limit:]

    def get_stats(self) -> dict[str, Any]:
        if not self._history:
            return {"status": "no_data"}

        avg_ram = sum(s.ram_used_percent for s in self._history) / len(self._history)
        avg_vram = sum(s.vram_used_percent for s in self._history) / len(self._history)

        return {
            "current_level": self._last_status.level.value if self._last_status else "unknown",
            "avg_ram_usage": f"{avg_ram:.1%}",
            "avg_vram_usage": f"{avg_vram:.1%}",
            "warning_threshold": f"{self.warning_threshold:.0%}",
            "critical_threshold": f"{self.critical_threshold:.0%}",
            "check_interval": self.check_interval,
            "history_count": len(self._history),
            "callbacks_count": len(self._callbacks)
        }


_memory_monitor: MemoryMonitor | None = None


def get_memory_monitor() -> MemoryMonitor:
    global _memory_monitor
    if _memory_monitor is None:
        from core.config import get_settings
        settings = get_settings()
        _memory_monitor = MemoryMonitor(
            warning_threshold=getattr(settings, 'memory_warning_threshold', 0.8),
            critical_threshold=getattr(settings, 'memory_critical_threshold', 0.9),
            check_interval=getattr(settings, 'memory_check_interval', 30)
        )
    return _memory_monitor


async def auto_cleanup_callback(status: MemoryStatus):
    """默认自动清理回调"""
    if status.level == PressureLevel.CRITICAL:
        logger.warning("触发自动清理回调")


get_memory_monitor().register_callback(auto_cleanup_callback)
