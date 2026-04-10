import asyncio
import json
from contextlib import suppress
from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from core.logging import get_logger

from .cpu import CPUMonitor
from .disk import DiskMonitor
from .memory import MemoryMonitor
from .network import NetworkMonitor

logger = get_logger(__name__)

router = APIRouter()


class HardwareStatus(BaseModel):
    cpu_percent: float = 0.0
    cpu_temp: float | None = None
    cpu_freq_mhz: float = 0.0
    memory_percent: float = 0.0
    memory_used_gb: float = 0.0
    memory_available_gb: float = 0.0
    disk_percent: float = 0.0
    disk_free_gb: float = 0.0
    network_upload_mbps: float = 0.0
    network_download_mbps: float = 0.0
    network_latency_ms: float | None = None
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())


class SSEConnection:
    def __init__(self, connection_id: str, queue: asyncio.Queue):
        self.connection_id = connection_id
        self.queue = queue
        self.created_at = datetime.now()
        self.last_activity = datetime.now()
        self.is_active = True

    async def send(self, data: dict[str, Any]) -> bool:
        if not self.is_active:
            return False
        try:
            self.queue.put_nowait(data)
            self.last_activity = datetime.now()
            return True
        except asyncio.QueueFull:
            return False

    def close(self):
        self.is_active = False


class HardwareMonitor:
    _instance: Optional["HardwareMonitor"] = None

    def __new__(cls, *_args, **_kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(
        self,
        history_size: int = 60,
        default_interval: float = 1.0,
    ):
        if hasattr(self, "_initialized") and self._initialized:
            return

        self._initialized = True
        self._cpu_monitor = CPUMonitor(history_size=history_size)
        self._memory_monitor = MemoryMonitor(history_size=history_size)
        self._disk_monitor = DiskMonitor(history_size=history_size)
        self._network_monitor = NetworkMonitor(history_size=history_size)

        self._connections: dict[str, SSEConnection] = {}
        self._lock = asyncio.Lock()
        self._default_interval = default_interval
        self._monitoring_task: asyncio.Task | None = None
        self._is_monitoring = False
        self._max_connections = 100
        self._max_queue_size = 100

    async def start_monitoring(self, interval: float | None = None):
        if self._is_monitoring:
            return

        self._is_monitoring = True
        self._monitoring_task = asyncio.create_task(
            self._monitoring_loop(interval or self._default_interval)
        )
        logger.info("硬件监控已启动")

    async def stop_monitoring(self):
        self._is_monitoring = False
        if self._monitoring_task:
            self._monitoring_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._monitoring_task
            self._monitoring_task = None
        logger.info("硬件监控已停止")

    async def _monitoring_loop(self, interval: float):
        while self._is_monitoring:
            try:
                status = await self._collect_status()
                await self._broadcast(status)
                await asyncio.sleep(interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"监控循环错误: {e}")
                await asyncio.sleep(1)

    async def _collect_status(self) -> HardwareStatus:
        cpu_info = await self._cpu_monitor.get_info()
        memory_info = await self._memory_monitor.get_info()
        disk_partitions = await self._disk_monitor.get_partitions()
        network_info = await self._network_monitor.get_info()

        disk_percent = 0.0
        disk_free_gb = 0.0
        if disk_partitions:
            main_partition = disk_partitions[0]
            disk_percent = main_partition.percent
            disk_free_gb = main_partition.free_gb

        return HardwareStatus(
            cpu_percent=cpu_info.percent_total,
            cpu_temp=cpu_info.temperature,
            cpu_freq_mhz=cpu_info.frequency_current,
            memory_percent=memory_info.percent,
            memory_used_gb=memory_info.used_gb,
            memory_available_gb=memory_info.available_gb,
            disk_percent=disk_percent,
            disk_free_gb=disk_free_gb,
            network_upload_mbps=network_info.upload_speed_mbps,
            network_download_mbps=network_info.download_speed_mbps,
            network_latency_ms=None,
        )

    async def _broadcast(self, status: HardwareStatus):
        async with self._lock:
            connection_ids = list(self._connections.keys())

        disconnected = []
        for conn_id in connection_ids:
            async with self._lock:
                connection = self._connections.get(conn_id)

            if connection and connection.is_active:
                success = await connection.send(status.model_dump())
                if not success:
                    disconnected.append(conn_id)
            else:
                disconnected.append(conn_id)

        for conn_id in disconnected:
            await self.close_connection(conn_id)

    async def create_connection(self, connection_id: str) -> asyncio.Queue:
        async with self._lock:
            if len(self._connections) >= self._max_connections:
                await self._cleanup_stale_connections()

                if len(self._connections) >= self._max_connections:
                    raise RuntimeError("达到最大连接数限制")

            queue = asyncio.Queue(maxsize=self._max_queue_size)
            connection = SSEConnection(connection_id, queue)
            self._connections[connection_id] = connection

            return queue

    async def close_connection(self, connection_id: str):
        async with self._lock:
            if connection_id in self._connections:
                self._connections[connection_id].close()
                del self._connections[connection_id]

    async def _cleanup_stale_connections(self):
        now = datetime.now()
        stale_connections = []

        async with self._lock:
            for conn_id, connection in self._connections.items():
                inactive_seconds = (now - connection.last_activity).total_seconds()
                if inactive_seconds > 300:
                    stale_connections.append(conn_id)

        for conn_id in stale_connections:
            await self.close_connection(conn_id)

    def create_stream_response(
        self,
        connection_id: str,
        queue: asyncio.Queue,
        heartbeat_interval: int = 30,
    ) -> StreamingResponse:
        async def event_generator():
            try:
                while True:
                    try:
                        data = await asyncio.wait_for(
                            queue.get(),
                            timeout=heartbeat_interval
                        )
                        yield self._format_sse_event("hardware_status", data)
                    except asyncio.TimeoutError:
                        yield self._format_sse_event("heartbeat", {
                            "timestamp": datetime.now().isoformat()
                        })
            except asyncio.CancelledError:
                pass
            finally:
                await self.close_connection(connection_id)

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            }
        )

    def _format_sse_event(self, event: str, data: dict[str, Any]) -> str:
        lines = [f"event: {event}"]
        data_str = json.dumps(data, ensure_ascii=False)
        for line in data_str.split("\n"):
            lines.append(f"data: {line}")
        lines.append("")
        lines.append("")
        return "\n".join(lines)

    async def get_all_stats(self) -> dict[str, Any]:
        cpu_stats = await self._cpu_monitor.get_stats()
        memory_stats = await self._memory_monitor.get_stats()
        disk_stats = await self._disk_monitor.get_all_stats()
        network_stats = await self._network_monitor.get_stats_dict()

        return {
            "cpu": cpu_stats,
            "memory": memory_stats,
            "disk": disk_stats,
            "network": network_stats,
            "timestamp": datetime.now().isoformat(),
        }

    async def get_cpu_history(self):
        return await self._cpu_monitor.get_history()

    async def get_memory_history(self):
        return await self._memory_monitor.get_history()

    async def check_system_health(self) -> dict[str, Any]:
        memory_pressure = await self._memory_monitor.check_memory_pressure()
        disk_space = await self._disk_monitor.check_disk_space()

        status = "healthy"
        if memory_pressure["status"] == "critical" or disk_space["status"] == "critical":
            status = "critical"
        elif memory_pressure["status"] == "warning" or disk_space["status"] == "warning":
            status = "warning"

        return {
            "status": status,
            "memory": memory_pressure,
            "disk": disk_space,
            "timestamp": datetime.now().isoformat(),
        }

    @property
    def cpu_monitor(self) -> CPUMonitor:
        return self._cpu_monitor

    @property
    def memory_monitor(self) -> MemoryMonitor:
        return self._memory_monitor

    @property
    def disk_monitor(self) -> DiskMonitor:
        return self._disk_monitor

    @property
    def network_monitor(self) -> NetworkMonitor:
        return self._network_monitor


hardware_monitor = HardwareMonitor()


@router.get("/status")
async def get_hardware_status():
    return await hardware_monitor.get_all_stats()


@router.get("/stream")
async def stream_hardware_status(
    interval: float = Query(default=1.0, ge=0.5, le=60.0, description="推送间隔(秒)")
):
    import uuid
    connection_id = str(uuid.uuid4())

    try:
        queue = await hardware_monitor.create_connection(connection_id)

        if not hardware_monitor._is_monitoring:
            await hardware_monitor.start_monitoring(interval)

        return hardware_monitor.create_stream_response(connection_id, queue)
    except Exception as e:
        logger.error(f"创建 SSE 连接失败: {e}")
        await hardware_monitor.close_connection(connection_id)
        raise


@router.get("/cpu")
async def get_cpu_info():
    return await hardware_monitor.cpu_monitor.get_stats()


@router.get("/cpu/history")
async def get_cpu_history():
    history = await hardware_monitor.get_cpu_history()
    return {
        "timestamps": history.timestamps,
        "percent_total": history.percent_total,
        "percent_per_cpu": history.percent_per_cpu,
        "temperatures": history.temperatures,
        "frequencies": history.frequencies,
    }


@router.get("/memory")
async def get_memory_info():
    return await hardware_monitor.memory_monitor.get_stats()


@router.get("/memory/history")
async def get_memory_history():
    history = await hardware_monitor.get_memory_history()
    return {
        "timestamps": history.timestamps,
        "percent": history.percent,
        "used_gb": history.used_gb,
        "available_gb": history.available_gb,
        "swap_percent": history.swap_percent,
    }


@router.get("/memory/pressure")
async def check_memory_pressure():
    return await hardware_monitor.memory_monitor.check_memory_pressure()


@router.get("/disk")
async def get_disk_info():
    return await hardware_monitor.disk_monitor.get_all_stats()


@router.get("/disk/check")
async def check_disk_space():
    return await hardware_monitor.disk_monitor.check_disk_space()


@router.get("/network")
async def get_network_info():
    return await hardware_monitor.network_monitor.get_stats_dict()


@router.get("/health")
async def check_system_health():
    return await hardware_monitor.check_system_health()


@router.post("/start")
async def start_monitoring(interval: float = Query(default=1.0, ge=0.5, le=60.0)):
    await hardware_monitor.start_monitoring(interval)
    return {"status": "started", "interval": interval}


@router.post("/stop")
async def stop_monitoring():
    await hardware_monitor.stop_monitoring()
    return {"status": "stopped"}
