import asyncio
import socket
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional

import psutil

from core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class NetworkInfo:
    bytes_sent: int = 0
    bytes_recv: int = 0
    packets_sent: int = 0
    packets_recv: int = 0
    errin: int = 0
    errout: int = 0
    dropin: int = 0
    dropout: int = 0
    upload_speed_mbps: float = 0.0
    download_speed_mbps: float = 0.0
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class NetworkInterface:
    name: str = ""
    is_up: bool = False
    speed_mbps: int = 0
    mtu: int = 0
    addresses: List[str] = field(default_factory=list)
    mac_address: str = ""


@dataclass
class NetworkStats:
    info: NetworkInfo = field(default_factory=NetworkInfo)
    interfaces: List[NetworkInterface] = field(default_factory=list)
    connections_count: int = 0
    connections_by_status: Dict[str, int] = field(default_factory=dict)
    latency_ms: Optional[float] = None


class NetworkMonitor:
    def __init__(self, history_size: int = 60):
        self._history_size = history_size
        self._lock = asyncio.Lock()
        self._last_net_io: Optional[psutil._pswindows.snetio] = None
        self._last_io_time: Optional[datetime] = None
        self._latency_host = "8.8.8.8"

    async def get_info(self) -> NetworkInfo:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._get_info_sync)

    def _get_info_sync(self) -> NetworkInfo:
        try:
            net_io = psutil.net_io_counters()
            current_time = datetime.now()
            
            upload_speed = 0.0
            download_speed = 0.0
            
            if self._last_net_io and self._last_io_time:
                time_diff = (current_time - self._last_io_time).total_seconds()
                if time_diff > 0:
                    bytes_sent_diff = net_io.bytes_sent - self._last_net_io.bytes_sent
                    bytes_recv_diff = net_io.bytes_recv - self._last_net_io.bytes_recv
                    
                    upload_speed = (bytes_sent_diff / time_diff) / (1024 ** 2)
                    download_speed = (bytes_recv_diff / time_diff) / (1024 ** 2)
            
            self._last_net_io = net_io
            self._last_io_time = current_time
            
            return NetworkInfo(
                bytes_sent=net_io.bytes_sent,
                bytes_recv=net_io.bytes_recv,
                packets_sent=net_io.packets_sent,
                packets_recv=net_io.packets_recv,
                errin=net_io.errin,
                errout=net_io.errout,
                dropin=net_io.dropin,
                dropout=net_io.dropout,
                upload_speed_mbps=upload_speed,
                download_speed_mbps=download_speed,
            )
        except Exception as e:
            logger.error(f"获取网络信息失败: {e}")
            return NetworkInfo()

    async def get_interfaces(self) -> List[NetworkInterface]:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._get_interfaces_sync)

    def _get_interfaces_sync(self) -> List[NetworkInterface]:
        interfaces = []
        try:
            net_if_addrs = psutil.net_if_addrs()
            net_if_stats = psutil.net_if_stats()
            
            for name, addrs in net_if_addrs.items():
                addresses = []
                mac_address = ""
                
                for addr in addrs:
                    if addr.family == socket.AF_INET:
                        addresses.append(addr.address)
                    elif addr.family == socket.AF_INET6:
                        addresses.append(f"[{addr.address}]")
                    elif hasattr(socket, "AF_LINK") and addr.family == socket.AF_LINK:
                        mac_address = addr.address
                
                stats = net_if_stats.get(name)
                is_up = stats.isup if stats else False
                speed = stats.speed if stats else 0
                mtu = stats.mtu if stats else 0
                
                interfaces.append(NetworkInterface(
                    name=name,
                    is_up=is_up,
                    speed_mbps=speed,
                    mtu=mtu,
                    addresses=addresses,
                    mac_address=mac_address,
                ))
        except Exception as e:
            logger.error(f"获取网络接口信息失败: {e}")
        return interfaces

    async def get_connections_count(self) -> Dict[str, int]:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._get_connections_count_sync)

    def _get_connections_count_sync(self) -> Dict[str, int]:
        try:
            connections = psutil.net_connections(kind="inet")
            
            status_count: Dict[str, int] = {}
            for conn in connections:
                status = conn.status if conn.status else "UNKNOWN"
                status_count[status] = status_count.get(status, 0) + 1
            
            return {
                "total": len(connections),
                "by_status": status_count,
            }
        except (psutil.AccessDenied, Exception) as e:
            logger.debug(f"获取网络连接数失败: {e}")
            return {"total": 0, "by_status": {}}

    async def check_latency(self, host: Optional[str] = None) -> Optional[float]:
        target_host = host or self._latency_host
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._check_latency_sync, target_host)

    def _check_latency_sync(self, host: str) -> Optional[float]:
        try:
            if psutil.WINDOWS:
                result = subprocess.run(
                    ["ping", "-n", "1", "-w", "1000", host],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                output = result.stdout
                if "time=" in output or "time<" in output:
                    for part in output.split():
                        if part.startswith("time=") or part.startswith("time<"):
                            time_str = part.split("=")[-1].replace("ms", "").replace("<", "")
                            return float(time_str)
            else:
                result = subprocess.run(
                    ["ping", "-c", "1", "-W", "1", host],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                output = result.stdout
                if "time=" in output:
                    for part in output.split():
                        if "time=" in part:
                            time_str = part.split("=")[-1].replace("ms", "")
                            return float(time_str)
        except Exception as e:
            logger.debug(f"检测网络延迟失败: {e}")
        return None

    async def get_all_stats(self) -> NetworkStats:
        info = await self.get_info()
        interfaces = await self.get_interfaces()
        connections = await self.get_connections_count()
        latency = await self.check_latency()
        
        return NetworkStats(
            info=info,
            interfaces=interfaces,
            connections_count=connections["total"],
            connections_by_status=connections["by_status"],
            latency_ms=latency,
        )

    async def get_stats_dict(self) -> Dict:
        stats = await self.get_all_stats()
        
        return {
            "traffic": {
                "bytes_sent": stats.info.bytes_sent,
                "bytes_recv": stats.info.bytes_recv,
                "packets_sent": stats.info.packets_sent,
                "packets_recv": stats.info.packets_recv,
                "upload_speed_mbps": round(stats.info.upload_speed_mbps, 2),
                "download_speed_mbps": round(stats.info.download_speed_mbps, 2),
                "errors": {
                    "in": stats.info.errin,
                    "out": stats.info.errout,
                },
                "drops": {
                    "in": stats.info.dropin,
                    "out": stats.info.dropout,
                },
            },
            "interfaces": [
                {
                    "name": iface.name,
                    "is_up": iface.is_up,
                    "speed_mbps": iface.speed_mbps,
                    "mtu": iface.mtu,
                    "addresses": iface.addresses,
                    "mac_address": iface.mac_address,
                }
                for iface in stats.interfaces
            ],
            "connections": {
                "total": stats.connections_count,
                "by_status": stats.connections_by_status,
            },
            "latency_ms": stats.latency_ms,
            "timestamp": datetime.now().isoformat(),
        }

    def set_latency_host(self, host: str):
        self._latency_host = host
