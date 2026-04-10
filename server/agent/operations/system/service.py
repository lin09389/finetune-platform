import asyncio
import platform
import subprocess
from contextlib import suppress
from dataclasses import dataclass
from enum import Enum
from typing import Any


class ServiceStatus(str, Enum):
    RUNNING = "running"
    STOPPED = "stopped"
    PAUSED = "paused"
    START_PENDING = "start_pending"
    STOP_PENDING = "stop_pending"
    UNKNOWN = "unknown"


class ServiceAction(str, Enum):
    LIST = "list"
    STATUS = "status"
    START = "start"
    STOP = "stop"
    RESTART = "restart"
    CONFIG = "config"


@dataclass
class ServiceInfo:
    name: str
    display_name: str
    status: ServiceStatus = ServiceStatus.UNKNOWN
    start_type: str = "unknown"
    can_stop: bool = False
    can_pause: bool = False
    description: str = ""
    pid: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "display_name": self.display_name,
            "status": self.status.value,
            "start_type": self.start_type,
            "can_stop": self.can_stop,
            "can_pause": self.can_pause,
            "description": self.description,
            "pid": self.pid,
        }


class ServiceOperations:
    def __init__(self):
        self._is_windows = platform.system() == "Windows"
        self._confirmation_required: dict[str, bool] = {}

    async def list_services(
        self,
        filter_status: str | None = None,
        filter_name: str | None = None,
    ) -> list[dict[str, Any]]:
        if not self._is_windows:
            return await self._list_services_linux(filter_status, filter_name)

        return await self._list_services_windows(filter_status, filter_name)

    async def _list_services_windows(
        self,
        filter_status: str | None,
        filter_name: str | None,
    ) -> list[dict[str, Any]]:
        services = []

        try:
            result = subprocess.run(
                ["sc", "query", "type=", "service", "state=", "all"],
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode != 0:
                return [{"error": result.stderr}]

            current_service = {}

            for line in result.stdout.split("\n"):
                line = line.strip()

                if line.startswith("SERVICE_NAME:"):
                    if current_service and "name" in current_service:
                        if filter_name and filter_name.lower() not in current_service.get("name", "").lower():
                            current_service = {}
                            continue
                        if filter_status and filter_status.lower() != current_service.get("status", "").lower():
                            current_service = {}
                            continue
                        services.append(current_service)
                    current_service = {"name": line.split(":", 1)[1].strip()}

                elif line.startswith("DISPLAY_NAME:"):
                    current_service["display_name"] = line.split(":", 1)[1].strip()

                elif line.startswith("STATE:"):
                    state = line.split(":", 1)[1].strip()
                    if "RUNNING" in state:
                        current_service["status"] = "running"
                    elif "STOPPED" in state:
                        current_service["status"] = "stopped"
                    elif "PAUSED" in state:
                        current_service["status"] = "paused"
                    elif "START_PENDING" in state:
                        current_service["status"] = "start_pending"
                    elif "STOP_PENDING" in state:
                        current_service["status"] = "stop_pending"
                    else:
                        current_service["status"] = "unknown"

            if (
                current_service
                and "name" in current_service
                and (not filter_name or filter_name.lower() in current_service.get("name", "").lower())
                and (not filter_status or filter_status.lower() == current_service.get("status", "").lower())
            ):
                services.append(current_service)

            return services

        except subprocess.TimeoutExpired:
            return [{"error": "查询服务超时"}]
        except Exception as e:
            return [{"error": str(e)}]

    async def _list_services_linux(
        self,
        filter_status: str | None,
        filter_name: str | None,
    ) -> list[dict[str, Any]]:
        services = []

        try:
            result = subprocess.run(
                ["systemctl", "list-units", "--type=service", "--all", "--no-pager"],
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode != 0:
                return [{"error": result.stderr}]

            for line in result.stdout.split("\n")[1:]:
                parts = line.split()
                if len(parts) >= 4 and parts[0].endswith(".service"):
                    name = parts[0]
                    status = parts[3].lower()

                    if filter_name and filter_name.lower() not in name.lower():
                        continue
                    if filter_status and filter_status.lower() != status:
                        continue

                    services.append({
                        "name": name,
                        "status": status,
                        "display_name": " ".join(parts[4:]) if len(parts) > 4 else name,
                    })

            return services

        except FileNotFoundError:
            return [{"error": "systemctl 命令不可用"}]
        except subprocess.TimeoutExpired:
            return [{"error": "查询服务超时"}]
        except Exception as e:
            return [{"error": str(e)}]

    async def get_service_status(self, service_name: str) -> dict[str, Any]:
        if not self._is_windows:
            return await self._get_service_status_linux(service_name)

        return await self._get_service_status_windows(service_name)

    async def _get_service_status_windows(self, service_name: str) -> dict[str, Any]:
        try:
            result = subprocess.run(
                ["sc", "query", service_name],
                capture_output=True,
                text=True,
                timeout=10,
            )

            if result.returncode != 0:
                return {"error": f"服务 {service_name} 不存在或无法访问", "name": service_name}

            info = {"name": service_name}

            for line in result.stdout.split("\n"):
                line = line.strip()

                if line.startswith("DISPLAY_NAME:"):
                    info["display_name"] = line.split(":", 1)[1].strip()
                elif line.startswith("STATE:"):
                    state = line.split(":", 1)[1].strip()
                    if "RUNNING" in state:
                        info["status"] = "running"
                    elif "STOPPED" in state:
                        info["status"] = "stopped"
                    elif "PAUSED" in state:
                        info["status"] = "paused"
                    else:
                        info["status"] = "unknown"
                elif line.startswith("PID:"):
                    pid_str = line.split(":", 1)[1].strip()
                    with suppress(ValueError):
                        info["pid"] = int(pid_str)

            return info

        except subprocess.TimeoutExpired:
            return {"error": "查询服务状态超时", "name": service_name}
        except Exception as e:
            return {"error": str(e), "name": service_name}

    async def _get_service_status_linux(self, service_name: str) -> dict[str, Any]:
        try:
            result = subprocess.run(
                ["systemctl", "status", service_name],
                capture_output=True,
                text=True,
                timeout=10,
            )

            info = {"name": service_name}

            for line in result.stdout.split("\n"):
                line = line.strip()

                if line.startswith("Loaded:"):
                    info["loaded"] = line.split(":", 1)[1].strip()
                elif line.startswith("Active:"):
                    active = line.split(":", 1)[1].strip()
                    if "running" in active.lower():
                        info["status"] = "running"
                    elif "inactive" in active.lower():
                        info["status"] = "stopped"
                    else:
                        info["status"] = "unknown"
                    info["active"] = active
                elif line.startswith("Main PID:"):
                    pid_str = line.split(":", 1)[1].strip().split()[0]
                    with suppress(ValueError):
                        info["pid"] = int(pid_str)

            return info

        except subprocess.TimeoutExpired:
            return {"error": "查询服务状态超时", "name": service_name}
        except Exception as e:
            return {"error": str(e), "name": service_name}

    async def start_service(
        self,
        service_name: str,
        require_confirmation: bool = True,
    ) -> dict[str, Any]:
        if require_confirmation and not self._confirmation_required.get(f"start_{service_name}"):
            self._confirmation_required[f"start_{service_name}"] = True
            return {
                "success": False,
                "requires_confirmation": True,
                "message": f"确认启动服务 {service_name}？请再次执行以确认。",
                "service_name": service_name,
            }

        self._confirmation_required.pop(f"start_{service_name}", None)

        if not self._is_windows:
            return await self._start_service_linux(service_name)

        return await self._start_service_windows(service_name)

    async def _start_service_windows(self, service_name: str) -> dict[str, Any]:
        try:
            result = subprocess.run(
                ["sc", "start", service_name],
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode == 0:
                return {
                    "success": True,
                    "message": f"服务 {service_name} 启动成功",
                    "service_name": service_name,
                }
            else:
                return {
                    "success": False,
                    "error": result.stderr.strip() or "启动服务失败",
                    "service_name": service_name,
                }

        except subprocess.TimeoutExpired:
            return {"success": False, "error": "启动服务超时", "service_name": service_name}
        except Exception as e:
            return {"success": False, "error": str(e), "service_name": service_name}

    async def _start_service_linux(self, service_name: str) -> dict[str, Any]:
        try:
            result = subprocess.run(
                ["systemctl", "start", service_name],
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode == 0:
                return {
                    "success": True,
                    "message": f"服务 {service_name} 启动成功",
                    "service_name": service_name,
                }
            else:
                return {
                    "success": False,
                    "error": result.stderr.strip() or "启动服务失败",
                    "service_name": service_name,
                }

        except subprocess.TimeoutExpired:
            return {"success": False, "error": "启动服务超时", "service_name": service_name}
        except Exception as e:
            return {"success": False, "error": str(e), "service_name": service_name}

    async def stop_service(
        self,
        service_name: str,
        require_confirmation: bool = True,
    ) -> dict[str, Any]:
        if require_confirmation and not self._confirmation_required.get(f"stop_{service_name}"):
            self._confirmation_required[f"stop_{service_name}"] = True
            return {
                "success": False,
                "requires_confirmation": True,
                "message": f"确认停止服务 {service_name}？请再次执行以确认。",
                "service_name": service_name,
            }

        self._confirmation_required.pop(f"stop_{service_name}", None)

        if not self._is_windows:
            return await self._stop_service_linux(service_name)

        return await self._stop_service_windows(service_name)

    async def _stop_service_windows(self, service_name: str) -> dict[str, Any]:
        try:
            result = subprocess.run(
                ["sc", "stop", service_name],
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode == 0:
                return {
                    "success": True,
                    "message": f"服务 {service_name} 停止成功",
                    "service_name": service_name,
                }
            else:
                return {
                    "success": False,
                    "error": result.stderr.strip() or "停止服务失败",
                    "service_name": service_name,
                }

        except subprocess.TimeoutExpired:
            return {"success": False, "error": "停止服务超时", "service_name": service_name}
        except Exception as e:
            return {"success": False, "error": str(e), "service_name": service_name}

    async def _stop_service_linux(self, service_name: str) -> dict[str, Any]:
        try:
            result = subprocess.run(
                ["systemctl", "stop", service_name],
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode == 0:
                return {
                    "success": True,
                    "message": f"服务 {service_name} 停止成功",
                    "service_name": service_name,
                }
            else:
                return {
                    "success": False,
                    "error": result.stderr.strip() or "停止服务失败",
                    "service_name": service_name,
                }

        except subprocess.TimeoutExpired:
            return {"success": False, "error": "停止服务超时", "service_name": service_name}
        except Exception as e:
            return {"success": False, "error": str(e), "service_name": service_name}

    async def restart_service(
        self,
        service_name: str,
        require_confirmation: bool = True,
    ) -> dict[str, Any]:
        if require_confirmation and not self._confirmation_required.get(f"restart_{service_name}"):
            self._confirmation_required[f"restart_{service_name}"] = True
            return {
                "success": False,
                "requires_confirmation": True,
                "message": f"确认重启服务 {service_name}？请再次执行以确认。",
                "service_name": service_name,
            }

        self._confirmation_required.pop(f"restart_{service_name}", None)

        if not self._is_windows:
            return await self._restart_service_linux(service_name)

        return await self._restart_service_windows(service_name)

    async def _restart_service_windows(self, service_name: str) -> dict[str, Any]:
        stop_result = await self._stop_service_windows(service_name)
        if not stop_result.get("success"):
            return stop_result

        await asyncio.sleep(1)

        return await self._start_service_windows(service_name)

    async def _restart_service_linux(self, service_name: str) -> dict[str, Any]:
        try:
            result = subprocess.run(
                ["systemctl", "restart", service_name],
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode == 0:
                return {
                    "success": True,
                    "message": f"服务 {service_name} 重启成功",
                    "service_name": service_name,
                }
            else:
                return {
                    "success": False,
                    "error": result.stderr.strip() or "重启服务失败",
                    "service_name": service_name,
                }

        except subprocess.TimeoutExpired:
            return {"success": False, "error": "重启服务超时", "service_name": service_name}
        except Exception as e:
            return {"success": False, "error": str(e), "service_name": service_name}

    async def get_service_config(self, service_name: str) -> dict[str, Any]:
        if not self._is_windows:
            return await self._get_service_config_linux(service_name)

        return await self._get_service_config_windows(service_name)

    async def _get_service_config_windows(self, service_name: str) -> dict[str, Any]:
        try:
            result = subprocess.run(
                ["sc", "qc", service_name],
                capture_output=True,
                text=True,
                timeout=10,
            )

            if result.returncode != 0:
                return {"error": f"无法获取服务 {service_name} 的配置", "name": service_name}

            config = {"name": service_name}

            for line in result.stdout.split("\n"):
                line = line.strip()

                if line.startswith("DISPLAY_NAME:"):
                    config["display_name"] = line.split(":", 1)[1].strip()
                elif line.startswith("START_TYPE:"):
                    start_type = line.split(":", 1)[1].strip()
                    if "AUTO_START" in start_type:
                        config["start_type"] = "automatic"
                    elif "DEMAND_START" in start_type:
                        config["start_type"] = "manual"
                    elif "DISABLED" in start_type:
                        config["start_type"] = "disabled"
                    else:
                        config["start_type"] = "unknown"
                elif line.startswith("BINARY_PATH_NAME:"):
                    config["binary_path"] = line.split(":", 1)[1].strip()
                elif line.startswith("SERVICE_TYPE:"):
                    config["service_type"] = line.split(":", 1)[1].strip()

            return config

        except subprocess.TimeoutExpired:
            return {"error": "获取服务配置超时", "name": service_name}
        except Exception as e:
            return {"error": str(e), "name": service_name}

    async def _get_service_config_linux(self, service_name: str) -> dict[str, Any]:
        try:
            result = subprocess.run(
                ["systemctl", "show", service_name],
                capture_output=True,
                text=True,
                timeout=10,
            )

            if result.returncode != 0:
                return {"error": f"无法获取服务 {service_name} 的配置", "name": service_name}

            config = {"name": service_name}

            for line in result.stdout.split("\n"):
                if "=" in line:
                    key, value = line.split("=", 1)

                    if key == "Description":
                        config["description"] = value
                    elif key == "ExecStart":
                        config["binary_path"] = value
                    elif key == "UnitFileState":
                        config["enabled"] = value == "enabled"

            return config

        except subprocess.TimeoutExpired:
            return {"error": "获取服务配置超时", "name": service_name}
        except Exception as e:
            return {"error": str(e), "name": service_name}
