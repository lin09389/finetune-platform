import asyncio
import platform
import socket
import psutil
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class InfoType(str, Enum):
    OS = "os"
    CPU = "cpu"
    MEMORY = "memory"
    DISK = "disk"
    NETWORK = "network"
    ALL = "all"


@dataclass
class OSInfo:
    system: str
    node: str
    release: str
    version: str
    machine: str
    processor: str
    boot_time: datetime
    hostname: str
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "system": self.system,
            "node": self.node,
            "release": self.release,
            "version": self.version,
            "machine": self.machine,
            "processor": self.processor,
            "boot_time": self.boot_time.isoformat(),
            "hostname": self.hostname,
        }


@dataclass
class CPUInfo:
    physical_cores: int
    logical_cores: int
    current_freq_mhz: float
    max_freq_mhz: float
    min_freq_mhz: float
    cpu_percent: float
    per_cpu_percent: List[float] = field(default_factory=list)
    brand: str = ""
    architecture: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "physical_cores": self.physical_cores,
            "logical_cores": self.logical_cores,
            "current_freq_mhz": round(self.current_freq_mhz, 2),
            "max_freq_mhz": round(self.max_freq_mhz, 2),
            "min_freq_mhz": round(self.min_freq_mhz, 2),
            "cpu_percent": round(self.cpu_percent, 2),
            "per_cpu_percent": [round(p, 2) for p in self.per_cpu_percent],
            "brand": self.brand,
            "architecture": self.architecture,
        }


@dataclass
class MemoryInfo:
    total_gb: float
    available_gb: float
    used_gb: float
    percent: float
    swap_total_gb: float
    swap_used_gb: float
    swap_free_gb: float
    swap_percent: float
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_gb": round(self.total_gb, 2),
            "available_gb": round(self.available_gb, 2),
            "used_gb": round(self.used_gb, 2),
            "percent": round(self.percent, 2),
            "swap_total_gb": round(self.swap_total_gb, 2),
            "swap_used_gb": round(self.swap_used_gb, 2),
            "swap_free_gb": round(self.swap_free_gb, 2),
            "swap_percent": round(self.swap_percent, 2),
        }


@dataclass
class DiskPartition:
    device: str
    mountpoint: str
    fstype: str
    total_gb: float
    used_gb: float
    free_gb: float
    percent: float
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "device": self.device,
            "mountpoint": self.mountpoint,
            "fstype": self.fstype,
            "total_gb": round(self.total_gb, 2),
            "used_gb": round(self.used_gb, 2),
            "free_gb": round(self.free_gb, 2),
            "percent": round(self.percent, 2),
        }


@dataclass
class DiskInfo:
    partitions: List[DiskPartition] = field(default_factory=list)
    total_read_gb: float = 0.0
    total_write_gb: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "partitions": [p.to_dict() for p in self.partitions],
            "total_read_gb": round(self.total_read_gb, 2),
            "total_write_gb": round(self.total_write_gb, 2),
        }


@dataclass
class NetworkInterface:
    name: str
    addresses: List[Dict[str, str]]
    bytes_sent_mb: float
    bytes_recv_mb: float
    packets_sent: int
    packets_recv: int
    is_up: bool
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "addresses": self.addresses,
            "bytes_sent_mb": round(self.bytes_sent_mb, 2),
            "bytes_recv_mb": round(self.bytes_recv_mb, 2),
            "packets_sent": self.packets_sent,
            "packets_recv": self.packets_recv,
            "is_up": self.is_up,
        }


@dataclass
class NetworkInfo:
    interfaces: List[NetworkInterface] = field(default_factory=list)
    hostname: str = ""
    default_gateway: Optional[str] = None
    dns_servers: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "interfaces": [i.to_dict() for i in self.interfaces],
            "hostname": self.hostname,
            "default_gateway": self.default_gateway,
            "dns_servers": self.dns_servers,
        }


class SystemInfoOperations:
    def __init__(self):
        self._is_windows = platform.system() == "Windows"
    
    async def get_os_info(self) -> Dict[str, Any]:
        try:
            boot_timestamp = psutil.boot_time()
            boot_time = datetime.fromtimestamp(boot_timestamp)
            
            info = OSInfo(
                system=platform.system(),
                node=platform.node(),
                release=platform.release(),
                version=platform.version(),
                machine=platform.machine(),
                processor=platform.processor() or "Unknown",
                boot_time=boot_time,
                hostname=socket.gethostname(),
            )
            
            return info.to_dict()
            
        except Exception as e:
            return {"error": str(e)}
    
    async def get_cpu_info(self) -> Dict[str, Any]:
        try:
            cpu_percent = psutil.cpu_percent(interval=0.5)
            per_cpu_percent = psutil.cpu_percent(interval=0.5, percpu=True)
            
            freq = psutil.cpu_freq()
            
            if self._is_windows:
                import subprocess
                try:
                    result = subprocess.run(
                        ["wmic", "cpu", "get", "name"],
                        capture_output=True,
                        text=True,
                        timeout=5,
                    )
                    lines = result.stdout.strip().split("\n")
                    brand = lines[1].strip() if len(lines) > 1 else ""
                except Exception:
                    brand = platform.processor() or ""
            else:
                try:
                    with open("/proc/cpuinfo", "r", encoding="utf-8") as f:
                        for line in f:
                            if "model name" in line:
                                brand = line.split(":")[1].strip()
                                break
                        else:
                            brand = ""
                except Exception:
                    brand = platform.processor() or ""
            
            info = CPUInfo(
                physical_cores=psutil.cpu_count(logical=False) or 1,
                logical_cores=psutil.cpu_count(logical=True) or 1,
                current_freq_mhz=freq.current if freq else 0.0,
                max_freq_mhz=freq.max if freq else 0.0,
                min_freq_mhz=freq.min if freq else 0.0,
                cpu_percent=cpu_percent,
                per_cpu_percent=list(per_cpu_percent),
                brand=brand,
                architecture=platform.machine(),
            )
            
            return info.to_dict()
            
        except Exception as e:
            return {"error": str(e)}
    
    async def get_memory_info(self) -> Dict[str, Any]:
        try:
            virtual_mem = psutil.virtual_memory()
            swap_mem = psutil.swap_memory()
            
            gb = 1024 ** 3
            
            info = MemoryInfo(
                total_gb=virtual_mem.total / gb,
                available_gb=virtual_mem.available / gb,
                used_gb=virtual_mem.used / gb,
                percent=virtual_mem.percent,
                swap_total_gb=swap_mem.total / gb,
                swap_used_gb=swap_mem.used / gb,
                swap_free_gb=swap_mem.free / gb,
                swap_percent=swap_mem.percent,
            )
            
            return info.to_dict()
            
        except Exception as e:
            return {"error": str(e)}
    
    async def get_disk_info(self) -> Dict[str, Any]:
        try:
            partitions = []
            gb = 1024 ** 3
            
            for partition in psutil.disk_partitions():
                try:
                    usage = psutil.disk_usage(partition.mountpoint)
                    
                    partitions.append(DiskPartition(
                        device=partition.device,
                        mountpoint=partition.mountpoint,
                        fstype=partition.fstype,
                        total_gb=usage.total / gb,
                        used_gb=usage.used / gb,
                        free_gb=usage.free / gb,
                        percent=usage.percent,
                    ))
                except PermissionError:
                    continue
            
            disk_io = psutil.disk_io_counters()
            
            info = DiskInfo(
                partitions=partitions,
                total_read_gb=disk_io.read_bytes / gb if disk_io else 0.0,
                total_write_gb=disk_io.write_bytes / gb if disk_io else 0.0,
            )
            
            return info.to_dict()
            
        except Exception as e:
            return {"error": str(e)}
    
    async def get_network_info(self) -> Dict[str, Any]:
        try:
            interfaces = []
            mb = 1024 ** 2
            
            net_io = psutil.net_io_counters(pernic=True)
            net_if_addrs = psutil.net_if_addrs()
            net_if_stats = psutil.net_if_stats()
            
            for name, addrs in net_if_addrs.items():
                addresses = []
                for addr in addrs:
                    addresses.append({
                        "family": str(addr.family),
                        "address": addr.address,
                        "netmask": addr.netmask or "",
                        "broadcast": addr.broadcast or "",
                    })
                
                io = net_io.get(name)
                stats = net_if_stats.get(name)
                
                interfaces.append(NetworkInterface(
                    name=name,
                    addresses=addresses,
                    bytes_sent_mb=io.bytes_sent / mb if io else 0.0,
                    bytes_recv_mb=io.bytes_recv / mb if io else 0.0,
                    packets_sent=io.packets_sent if io else 0,
                    packets_recv=io.packets_recv if io else 0,
                    is_up=stats.isup if stats else False,
                ))
            
            default_gateway = None
            dns_servers = []
            
            if self._is_windows:
                try:
                    result = await asyncio.create_subprocess_exec(
                        "powershell",
                        "-Command",
                        "Get-DnsClientServerAddress -AddressFamily IPv4 | Select-Object -First 10",
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                    )
                    stdout, _ = await result.communicate()
                    
                    for line in stdout.decode().strip().split("\n"):
                        if ":" in line:
                            parts = line.split(":")
                            if len(parts) >= 2:
                                ip = parts[-1].strip()
                                if ip and ip != "IPAddress":
                                    dns_servers.append(ip)
                except Exception:
                    pass
            else:
                try:
                    with open("/etc/resolv.conf", "r", encoding="utf-8") as f:
                        for line in f:
                            if line.startswith("nameserver"):
                                dns_servers.append(line.split()[1])
                except Exception:
                    pass
            
            info = NetworkInfo(
                interfaces=interfaces,
                hostname=socket.gethostname(),
                default_gateway=default_gateway,
                dns_servers=dns_servers[:5],
            )
            
            return info.to_dict()
            
        except Exception as e:
            return {"error": str(e)}
    
    async def get_all_info(self) -> Dict[str, Any]:
        os_task = self.get_os_info()
        cpu_task = self.get_cpu_info()
        memory_task = self.get_memory_info()
        disk_task = self.get_disk_info()
        network_task = self.get_network_info()
        
        os_info, cpu_info, memory_info, disk_info, network_info = await asyncio.gather(
            os_task, cpu_task, memory_task, disk_task, network_task
        )
        
        return {
            "os": os_info,
            "cpu": cpu_info,
            "memory": memory_info,
            "disk": disk_info,
            "network": network_info,
            "collected_at": datetime.now().isoformat(),
        }
    
    async def get_info(self, info_type: InfoType) -> Dict[str, Any]:
        handlers = {
            InfoType.OS: self.get_os_info,
            InfoType.CPU: self.get_cpu_info,
            InfoType.MEMORY: self.get_memory_info,
            InfoType.DISK: self.get_disk_info,
            InfoType.NETWORK: self.get_network_info,
            InfoType.ALL: self.get_all_info,
        }
        
        handler = handlers.get(info_type)
        if handler:
            return await handler()
        
        return {"error": f"Unknown info type: {info_type}"}
    
    async def get_uptime(self) -> Dict[str, Any]:
        try:
            boot_timestamp = psutil.boot_time()
            boot_time = datetime.fromtimestamp(boot_timestamp)
            now = datetime.now()
            
            uptime = now - boot_time
            total_seconds = int(uptime.total_seconds())
            
            days = total_seconds // 86400
            hours = (total_seconds % 86400) // 3600
            minutes = (total_seconds % 3600) // 60
            seconds = total_seconds % 60
            
            return {
                "boot_time": boot_time.isoformat(),
                "uptime_seconds": total_seconds,
                "uptime_human": f"{days}天 {hours}小时 {minutes}分钟 {seconds}秒",
                "days": days,
                "hours": hours,
                "minutes": minutes,
                "seconds": seconds,
            }
            
        except Exception as e:
            return {"error": str(e)}
    
    async def get_battery_info(self) -> Dict[str, Any]:
        try:
            if not hasattr(psutil, "sensors_battery"):
                return {"error": "Battery information not available on this system"}
            
            battery = psutil.sensors_battery()
            
            if battery is None:
                return {"error": "No battery detected"}
            
            return {
                "percent": battery.percent,
                "power_plugged": battery.power_plugged,
                "secs_left": battery.secs_left,
                "status": "charging" if battery.power_plugged else "discharging",
            }
            
        except Exception as e:
            return {"error": str(e)}
    
    async def get_temperature_info(self) -> Dict[str, Any]:
        try:
            if not hasattr(psutil, "sensors_temperatures"):
                return {"error": "Temperature information not available on this system"}
            
            temps = psutil.sensors_temperatures()
            
            if not temps:
                return {"error": "No temperature sensors available"}
            
            result = {}
            for name, entries in temps.items():
                result[name] = [
                    {
                        "label": entry.label or f"Sensor {i}",
                        "current": entry.current,
                        "high": entry.high,
                        "critical": entry.critical,
                    }
                    for i, entry in enumerate(entries)
                ]
            
            return result
            
        except Exception as e:
            return {"error": str(e)}
