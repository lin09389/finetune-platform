import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional

import psutil

from core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class DiskInfo:
    device: str = ""
    mountpoint: str = ""
    fstype: str = ""
    total_gb: float = 0.0
    used_gb: float = 0.0
    free_gb: float = 0.0
    percent: float = 0.0
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class DiskIOStats:
    read_bytes: int = 0
    write_bytes: int = 0
    read_count: int = 0
    write_count: int = 0
    read_time_ms: int = 0
    write_time_ms: int = 0
    read_speed_mbps: float = 0.0
    write_speed_mbps: float = 0.0
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


class DiskMonitor:
    def __init__(self, history_size: int = 60):
        self._history_size = history_size
        self._lock = asyncio.Lock()
        self._last_io_stats: Dict[str, DiskIOStats] = {}
        self._warning_threshold = 80.0
        self._critical_threshold = 95.0

    async def get_partitions(self) -> List[DiskInfo]:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._get_partitions_sync)

    def _get_partitions_sync(self) -> List[DiskInfo]:
        partitions = []
        try:
            for partition in psutil.disk_partitions():
                try:
                    usage = psutil.disk_usage(partition.mountpoint)
                    partitions.append(DiskInfo(
                        device=partition.device,
                        mountpoint=partition.mountpoint,
                        fstype=partition.fstype,
                        total_gb=usage.total / (1024 ** 3),
                        used_gb=usage.used / (1024 ** 3),
                        free_gb=usage.free / (1024 ** 3),
                        percent=usage.percent,
                    ))
                except (PermissionError, OSError) as e:
                    logger.debug(f"无法访问分区 {partition.mountpoint}: {e}")
                    continue
        except Exception as e:
            logger.error(f"获取磁盘分区信息失败: {e}")
        return partitions

    async def get_io_stats(self) -> Dict[str, DiskIOStats]:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._get_io_stats_sync)

    def _get_io_stats_sync(self) -> Dict[str, DiskIOStats]:
        stats = {}
        try:
            io_counters = psutil.disk_io_counters(perdisk=True)
            if not io_counters:
                return stats
            
            current_time = datetime.now()
            
            for disk_name, counter in io_counters.items():
                current_stats = DiskIOStats(
                    read_bytes=counter.read_bytes,
                    write_bytes=counter.write_bytes,
                    read_count=counter.read_count,
                    write_count=counter.write_count,
                    read_time_ms=counter.read_time if hasattr(counter, "read_time") else 0,
                    write_time_ms=counter.write_time if hasattr(counter, "write_time") else 0,
                )
                
                if disk_name in self._last_io_stats:
                    last_stats = self._last_io_stats[disk_name]
                    time_diff = (current_time - datetime.fromisoformat(last_stats.timestamp)).total_seconds()
                    
                    if time_diff > 0:
                        read_diff = current_stats.read_bytes - last_stats.read_bytes
                        write_diff = current_stats.write_bytes - last_stats.write_bytes
                        
                        current_stats.read_speed_mbps = (read_diff / time_diff) / (1024 ** 2)
                        current_stats.write_speed_mbps = (write_diff / time_diff) / (1024 ** 2)
                
                stats[disk_name] = current_stats
                self._last_io_stats[disk_name] = current_stats
            
        except Exception as e:
            logger.error(f"获取磁盘 IO 统计失败: {e}")
        return stats

    async def get_all_stats(self) -> Dict:
        partitions = await self.get_partitions()
        io_stats = await self.get_io_stats()
        
        return {
            "partitions": [
                {
                    "device": p.device,
                    "mountpoint": p.mountpoint,
                    "fstype": p.fstype,
                    "total_gb": round(p.total_gb, 2),
                    "used_gb": round(p.used_gb, 2),
                    "free_gb": round(p.free_gb, 2),
                    "percent": round(p.percent, 2),
                }
                for p in partitions
            ],
            "io_stats": {
                name: {
                    "read_bytes": stats.read_bytes,
                    "write_bytes": stats.write_bytes,
                    "read_count": stats.read_count,
                    "write_count": stats.write_count,
                    "read_speed_mbps": round(stats.read_speed_mbps, 2),
                    "write_speed_mbps": round(stats.write_speed_mbps, 2),
                }
                for name, stats in io_stats.items()
            },
            "timestamp": datetime.now().isoformat(),
        }

    async def check_disk_space(self) -> Dict:
        partitions = await self.get_partitions()
        
        warnings = []
        critical = []
        
        for partition in partitions:
            if partition.percent >= self._critical_threshold:
                critical.append({
                    "mountpoint": partition.mountpoint,
                    "percent": partition.percent,
                    "free_gb": round(partition.free_gb, 2),
                    "message": f"磁盘空间严重不足: {partition.mountpoint} ({partition.percent:.1f}%)",
                })
            elif partition.percent >= self._warning_threshold:
                warnings.append({
                    "mountpoint": partition.mountpoint,
                    "percent": partition.percent,
                    "free_gb": round(partition.free_gb, 2),
                    "message": f"磁盘空间不足: {partition.mountpoint} ({partition.percent:.1f}%)",
                })
        
        status = "normal"
        if critical:
            status = "critical"
        elif warnings:
            status = "warning"
        
        return {
            "status": status,
            "warnings": warnings,
            "critical": critical,
            "partitions_count": len(partitions),
        }

    async def get_partition_by_path(self, path: str) -> Optional[DiskInfo]:
        partitions = await self.get_partitions()
        
        for partition in partitions:
            if path.startswith(partition.mountpoint):
                return partition
        return None

    def set_thresholds(self, warning: float = 80.0, critical: float = 95.0):
        self._warning_threshold = warning
        self._critical_threshold = critical
