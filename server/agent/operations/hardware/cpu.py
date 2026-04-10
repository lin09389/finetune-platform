import asyncio
from dataclasses import dataclass, field
from datetime import datetime

import psutil

from core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class CPUInfo:
    percent_total: float = 0.0
    percent_per_cpu: list[float] = field(default_factory=list)
    frequency_current: float = 0.0
    frequency_min: float = 0.0
    frequency_max: float = 0.0
    temperature: float | None = None
    load_avg_1: float = 0.0
    load_avg_5: float = 0.0
    load_avg_15: float = 0.0
    physical_cores: int = 0
    logical_cores: int = 0
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class CPUHistory:
    timestamps: list[str] = field(default_factory=list)
    percent_total: list[float] = field(default_factory=list)
    percent_per_cpu: list[list[float]] = field(default_factory=list)
    temperatures: list[float | None] = field(default_factory=list)
    frequencies: list[float] = field(default_factory=list)


class CPUMonitor:
    def __init__(self, history_size: int = 60):
        self._history_size = history_size
        self._history: CPUHistory = CPUHistory()
        self._lock = asyncio.Lock()

    async def get_info(self) -> CPUInfo:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._get_info_sync)

    def _get_info_sync(self) -> CPUInfo:
        try:
            percent_total = psutil.cpu_percent(interval=0.1)
            percent_per_cpu = psutil.cpu_percent(interval=0.1, percpu=True)

            freq = psutil.cpu_freq()
            frequency_current = freq.current if freq else 0.0
            frequency_min = freq.min if freq else 0.0
            frequency_max = freq.max if freq else 0.0

            temperature = self._get_cpu_temperature()
            load_avg = self._get_load_average()

            return CPUInfo(
                percent_total=percent_total,
                percent_per_cpu=list(percent_per_cpu) if percent_per_cpu else [],
                frequency_current=frequency_current,
                frequency_min=frequency_min,
                frequency_max=frequency_max,
                temperature=temperature,
                load_avg_1=load_avg[0] if load_avg else 0.0,
                load_avg_5=load_avg[1] if load_avg else 0.0,
                load_avg_15=load_avg[2] if load_avg else 0.0,
                physical_cores=psutil.cpu_count(logical=False) or 0,
                logical_cores=psutil.cpu_count(logical=True) or 0,
            )
        except Exception as e:
            logger.error(f"Failed to get CPU info: {e}")
            return CPUInfo()

    def _get_cpu_temperature(self) -> float | None:
        try:
            temps = psutil.sensors_temperatures()
            if not temps:
                return None

            for name, entries in temps.items():
                for entry in entries:
                    if any(keyword in name.lower() for keyword in ["cpu", "core", "package"]):
                        return entry.current
                    if entry.label and any(keyword in entry.label.lower() for keyword in ["cpu", "core", "package"]):
                        return entry.current

            for _name, entries in temps.items():
                if entries:
                    return entries[0].current
        except Exception:
            pass
        return None

    def _get_load_average(self) -> tuple | None:
        try:
            if hasattr(psutil, "getloadavg"):
                return psutil.getloadavg()
        except Exception:
            pass
        return None

    async def update_history(self) -> CPUInfo:
        info = await self.get_info()

        async with self._lock:
            self._history.timestamps.append(info.timestamp)
            self._history.percent_total.append(info.percent_total)
            self._history.percent_per_cpu.append(info.percent_per_cpu.copy())
            self._history.temperatures.append(info.temperature)
            self._history.frequencies.append(info.frequency_current)

            while len(self._history.timestamps) > self._history_size:
                self._history.timestamps.pop(0)
                self._history.percent_total.pop(0)
                self._history.percent_per_cpu.pop(0)
                self._history.temperatures.pop(0)
                self._history.frequencies.pop(0)

        return info

    async def get_history(self) -> CPUHistory:
        async with self._lock:
            return CPUHistory(
                timestamps=self._history.timestamps.copy(),
                percent_total=self._history.percent_total.copy(),
                percent_per_cpu=[cpu.copy() for cpu in self._history.percent_per_cpu],
                temperatures=self._history.temperatures.copy(),
                frequencies=self._history.frequencies.copy(),
            )

    async def get_stats(self) -> dict:
        info = await self.get_info()
        return {
            "cpu_percent": info.percent_total,
            "cpu_per_core": info.percent_per_cpu,
            "cpu_freq_mhz": info.frequency_current,
            "cpu_temp_c": info.temperature,
            "load_avg": {
                "1min": info.load_avg_1,
                "5min": info.load_avg_5,
                "15min": info.load_avg_15,
            },
            "cores": {
                "physical": info.physical_cores,
                "logical": info.logical_cores,
            },
            "timestamp": info.timestamp,
        }

    def clear_history(self):
        self._history = CPUHistory()
