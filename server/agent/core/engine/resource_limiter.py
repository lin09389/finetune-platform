import asyncio
import time
from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any

import psutil
from pydantic import BaseModel, Field


class ResourceType(str, Enum):
    CPU = "cpu"
    MEMORY = "memory"
    FILE_SIZE = "file_size"
    EXECUTION_TIME = "execution_time"
    CONCURRENT = "concurrent"
    NETWORK = "network"


class LimitAction(str, Enum):
    ALLOW = "allow"
    WARN = "warn"
    DENY = "deny"
    THROTTLE = "throttle"


@dataclass
class ResourceConfig:
    max_cpu_percent: float = 80.0
    max_memory_mb: int = 512
    max_file_size_mb: int = 10
    max_execution_time_seconds: int = 60
    max_concurrent_tasks: int = 5
    max_network_connections: int = 10
    cpu_throttle_threshold: float = 90.0
    memory_throttle_threshold: float = 90.0
    warning_threshold: float = 80.0
    check_interval_seconds: float = 1.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "max_cpu_percent": self.max_cpu_percent,
            "max_memory_mb": self.max_memory_mb,
            "max_file_size_mb": self.max_file_size_mb,
            "max_execution_time_seconds": self.max_execution_time_seconds,
            "max_concurrent_tasks": self.max_concurrent_tasks,
            "max_network_connections": self.max_network_connections,
            "cpu_throttle_threshold": self.cpu_throttle_threshold,
            "memory_throttle_threshold": self.memory_throttle_threshold,
            "warning_threshold": self.warning_threshold,
            "check_interval_seconds": self.check_interval_seconds,
        }


class ResourceUsage(BaseModel):
    cpu_percent: float = Field(default=0.0)
    memory_mb: float = Field(default=0.0)
    active_tasks: int = Field(default=0)
    network_connections: int = Field(default=0)
    timestamp: datetime = Field(default_factory=datetime.now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "cpu_percent": self.cpu_percent,
            "memory_mb": self.memory_mb,
            "active_tasks": self.active_tasks,
            "network_connections": self.network_connections,
            "timestamp": self.timestamp.isoformat(),
        }


class LimitCheckResult(BaseModel):
    allowed: bool = Field(default=True)
    resource_type: ResourceType = Field(default=ResourceType.CPU)
    action: LimitAction = Field(default=LimitAction.ALLOW)
    current_value: float = Field(default=0.0)
    limit_value: float = Field(default=0.0)
    message: str = Field(default="")
    metadata: dict[str, Any] = Field(default_factory=dict)


class ResourceLimiter:
    def __init__(self, config: ResourceConfig | None = None):
        self.config = config or ResourceConfig()
        self._current_usage = ResourceUsage()
        self._task_count = 0
        self._network_count = 0
        self._lock = asyncio.Lock()
        self._monitoring = False
        self._monitor_task: asyncio.Task | None = None
        self._start_time: float | None = None
        self._violations: list[dict[str, Any]] = []
        self._callbacks: dict[str, callable] = {}

    async def start_monitoring(self) -> None:
        if self._monitoring:
            return
        self._monitoring = True
        self._start_time = time.time()
        self._monitor_task = asyncio.create_task(self._monitor_loop())

    async def stop_monitoring(self) -> None:
        self._monitoring = False
        if self._monitor_task:
            self._monitor_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._monitor_task
            self._monitor_task = None

    async def _monitor_loop(self) -> None:
        while self._monitoring:
            try:
                await self._update_usage()
                await self._check_thresholds()
                await asyncio.sleep(self.config.check_interval_seconds)
            except asyncio.CancelledError:
                break
            except Exception:
                await asyncio.sleep(self.config.check_interval_seconds)

    async def _update_usage(self) -> None:
        cpu_percent = psutil.cpu_percent(interval=0.1)
        memory_info = psutil.virtual_memory()
        memory_mb = memory_info.used / (1024 * 1024)

        async with self._lock:
            self._current_usage = ResourceUsage(
                cpu_percent=cpu_percent,
                memory_mb=memory_mb,
                active_tasks=self._task_count,
                network_connections=self._network_count,
                timestamp=datetime.now(),
            )

    async def _check_thresholds(self) -> None:
        usage = self._current_usage

        if usage.cpu_percent > self.config.cpu_throttle_threshold:
            await self._handle_violation(
                ResourceType.CPU,
                usage.cpu_percent,
                self.config.cpu_throttle_threshold,
                LimitAction.THROTTLE,
            )
        elif usage.cpu_percent > self.config.max_cpu_percent:
            await self._handle_violation(
                ResourceType.CPU,
                usage.cpu_percent,
                self.config.max_cpu_percent,
                LimitAction.WARN,
            )

        memory_percent = (usage.memory_mb / self.config.max_memory_mb) * 100
        if memory_percent > self.config.memory_throttle_threshold:
            await self._handle_violation(
                ResourceType.MEMORY,
                usage.memory_mb,
                self.config.max_memory_mb,
                LimitAction.THROTTLE,
            )

    async def _handle_violation(
        self,
        resource_type: ResourceType,
        current: float,
        limit: float,
        action: LimitAction,
    ) -> None:
        violation = {
            "resource_type": resource_type.value,
            "current_value": current,
            "limit_value": limit,
            "action": action.value,
            "timestamp": datetime.now().isoformat(),
        }
        self._violations.append(violation)

        callback = self._callbacks.get(resource_type.value)
        if callback:
            with suppress(Exception):
                await callback(violation)

    def register_callback(self, resource_type: ResourceType, callback: callable) -> None:
        self._callbacks[resource_type.value] = callback

    def unregister_callback(self, resource_type: ResourceType) -> None:
        self._callbacks.pop(resource_type.value, None)

    async def check_cpu_limit(self) -> LimitCheckResult:
        usage = self._current_usage
        current = usage.cpu_percent
        limit = self.config.max_cpu_percent

        if current > self.config.cpu_throttle_threshold:
            return LimitCheckResult(
                allowed=True,
                resource_type=ResourceType.CPU,
                action=LimitAction.THROTTLE,
                current_value=current,
                limit_value=limit,
                message=f"CPU usage {current:.1f}% exceeds throttle threshold",
            )
        elif current > limit:
            return LimitCheckResult(
                allowed=True,
                resource_type=ResourceType.CPU,
                action=LimitAction.WARN,
                current_value=current,
                limit_value=limit,
                message=f"CPU usage {current:.1f}% exceeds limit",
            )

        return LimitCheckResult(
            allowed=True,
            resource_type=ResourceType.CPU,
            action=LimitAction.ALLOW,
            current_value=current,
            limit_value=limit,
        )

    async def check_memory_limit(self) -> LimitCheckResult:
        usage = self._current_usage
        current = usage.memory_mb
        limit = self.config.max_memory_mb

        if current > limit:
            return LimitCheckResult(
                allowed=False,
                resource_type=ResourceType.MEMORY,
                action=LimitAction.DENY,
                current_value=current,
                limit_value=limit,
                message=f"Memory usage {current:.1f}MB exceeds limit {limit}MB",
            )

        memory_percent = (current / limit) * 100
        if memory_percent > self.config.warning_threshold:
            return LimitCheckResult(
                allowed=True,
                resource_type=ResourceType.MEMORY,
                action=LimitAction.WARN,
                current_value=current,
                limit_value=limit,
                message=f"Memory usage at {memory_percent:.1f}% of limit",
            )

        return LimitCheckResult(
            allowed=True,
            resource_type=ResourceType.MEMORY,
            action=LimitAction.ALLOW,
            current_value=current,
            limit_value=limit,
        )

    async def check_file_size(self, size_bytes: int) -> LimitCheckResult:
        size_mb = size_bytes / (1024 * 1024)
        limit = self.config.max_file_size_mb

        if size_mb > limit:
            return LimitCheckResult(
                allowed=False,
                resource_type=ResourceType.FILE_SIZE,
                action=LimitAction.DENY,
                current_value=size_mb,
                limit_value=limit,
                message=f"File size {size_mb:.2f}MB exceeds limit {limit}MB",
            )

        return LimitCheckResult(
            allowed=True,
            resource_type=ResourceType.FILE_SIZE,
            action=LimitAction.ALLOW,
            current_value=size_mb,
            limit_value=limit,
        )

    async def check_execution_time(self, elapsed_seconds: float) -> LimitCheckResult:
        limit = self.config.max_execution_time_seconds

        if elapsed_seconds > limit:
            return LimitCheckResult(
                allowed=False,
                resource_type=ResourceType.EXECUTION_TIME,
                action=LimitAction.DENY,
                current_value=elapsed_seconds,
                limit_value=limit,
                message=f"Execution time {elapsed_seconds:.1f}s exceeds limit {limit}s",
            )

        if elapsed_seconds > limit * 0.8:
            return LimitCheckResult(
                allowed=True,
                resource_type=ResourceType.EXECUTION_TIME,
                action=LimitAction.WARN,
                current_value=elapsed_seconds,
                limit_value=limit,
                message="Execution time approaching limit",
            )

        return LimitCheckResult(
            allowed=True,
            resource_type=ResourceType.EXECUTION_TIME,
            action=LimitAction.ALLOW,
            current_value=elapsed_seconds,
            limit_value=limit,
        )

    async def check_concurrent_limit(self) -> LimitCheckResult:
        async with self._lock:
            current = self._task_count
        limit = self.config.max_concurrent_tasks

        if current >= limit:
            return LimitCheckResult(
                allowed=False,
                resource_type=ResourceType.CONCURRENT,
                action=LimitAction.DENY,
                current_value=current,
                limit_value=limit,
                message=f"Concurrent task limit reached ({limit})",
            )

        return LimitCheckResult(
            allowed=True,
            resource_type=ResourceType.CONCURRENT,
            action=LimitAction.ALLOW,
            current_value=current,
            limit_value=limit,
        )

    async def acquire_task_slot(self) -> bool:
        check = await self.check_concurrent_limit()
        if not check.allowed:
            return False

        async with self._lock:
            self._task_count += 1
        return True

    async def release_task_slot(self) -> None:
        async with self._lock:
            self._task_count = max(0, self._task_count - 1)

    async def acquire_network_slot(self) -> bool:
        async with self._lock:
            if self._network_count >= self.config.max_network_connections:
                return False
            self._network_count += 1
        return True

    async def release_network_slot(self) -> None:
        async with self._lock:
            self._network_count = max(0, self._network_count - 1)

    def get_current_usage(self) -> ResourceUsage:
        return self._current_usage

    def get_violations(self, limit: int = 100) -> list[dict[str, Any]]:
        return self._violations[-limit:]

    def clear_violations(self) -> None:
        self._violations.clear()

    async def check_all_limits(self) -> dict[str, LimitCheckResult]:
        return {
            "cpu": await self.check_cpu_limit(),
            "memory": await self.check_memory_limit(),
            "concurrent": await self.check_concurrent_limit(),
        }

    def update_config(self, **kwargs) -> None:
        for key, value in kwargs.items():
            if hasattr(self.config, key):
                setattr(self.config, key, value)

    def get_stats(self) -> dict[str, Any]:
        return {
            "config": self.config.to_dict(),
            "current_usage": self._current_usage.to_dict(),
            "task_count": self._task_count,
            "network_count": self._network_count,
            "monitoring": self._monitoring,
            "violation_count": len(self._violations),
            "uptime_seconds": time.time() - self._start_time if self._start_time else 0,
        }
