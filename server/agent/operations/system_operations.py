"""System operation handler for process/service/system/app/browser actions."""

import logging
import platform
import subprocess
import webbrowser
from typing import Any

import psutil

from .app.whitelist import get_whitelist
from .base import OperationContext, OperationHandler, OperationResult

logger = logging.getLogger(__name__)


class SystemOperationHandler(OperationHandler):
    """Handle system-level operations exposed to the unified executor."""

    def __init__(
        self,
        context: OperationContext | None = None,
        allowed_commands: list[str] | None = None,
    ):
        super().__init__(context)
        self.allowed_commands = allowed_commands or []
        self._whitelist = get_whitelist()

    def get_supported_actions(self) -> list[str]:
        return [
            "process_list",
            "process_kill",
            "process_start",
            "service_status",
            "service_start",
            "service_stop",
            "hardware_info",
            "gpu_info",
            "memory_info",
            "disk_info",
            "network_info",
            "command_execute",
            "app_open",
            "url_open",
        ]

    def get_action_descriptions(self) -> dict[str, str]:
        return {
            "process_list": "列出运行中的进程",
            "process_kill": "终止指定进程",
            "process_start": "启动新进程",
            "service_status": "查询服务状态",
            "service_start": "启动服务",
            "service_stop": "停止服务",
            "hardware_info": "获取硬件信息",
            "gpu_info": "获取 GPU 信息",
            "memory_info": "获取内存信息",
            "disk_info": "获取磁盘信息",
            "network_info": "获取网络信息",
            "command_execute": "执行系统命令",
            "app_open": "打开应用程序",
            "url_open": "打开网址",
        }

    def validate_params(self, action: str, params: dict[str, Any]) -> str | None:
        validators = {
            "process_kill": lambda p: "pid" not in p and "name" not in p and "缺少参数: pid 或 name" or None,
            "process_start": lambda p: "command" not in p and "缺少参数: command" or None,
            "service_status": lambda p: "name" not in p and "缺少参数: name" or None,
            "service_start": lambda p: "name" not in p and "缺少参数: name" or None,
            "service_stop": lambda p: "name" not in p and "缺少参数: name" or None,
            "command_execute": self._validate_command,
            "app_open": lambda p: "app_name" not in p and "缺少参数: app_name" or None,
            "url_open": lambda p: "url" not in p and "缺少参数: url" or None,
        }

        validator = validators.get(action)
        return validator(params) if validator else None

    def _validate_command(self, params: dict[str, Any]) -> str | None:
        if "command" not in params:
            return "缺少参数: command"

        if self.allowed_commands:
            command = str(params["command"]).split()[0]
            if command not in self.allowed_commands:
                return f"命令不在允许列表中: {command}"

        return None

    async def execute(self, action: str, params: dict[str, Any]) -> OperationResult:
        handlers = {
            "process_list": self._process_list,
            "process_kill": self._process_kill,
            "process_start": self._process_start,
            "service_status": self._service_status,
            "service_start": self._service_start,
            "service_stop": self._service_stop,
            "hardware_info": self._hardware_info,
            "gpu_info": self._gpu_info,
            "memory_info": self._memory_info,
            "disk_info": self._disk_info,
            "network_info": self._network_info,
            "command_execute": self._command_execute,
            "app_open": self._app_open,
            "url_open": self._url_open,
        }

        handler = handlers.get(action)
        if not handler:
            return OperationResult.fail(error=f"未实现的操作: {action}", error_code="NOT_IMPLEMENTED")
        return await handler(params)

    async def _process_list(self, params: dict[str, Any]) -> OperationResult:
        filter_name = params.get("filter")
        processes = []

        for proc in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent"]):
            try:
                info = proc.info
                proc_name = info.get("name") or ""
                if filter_name and str(filter_name).lower() not in proc_name.lower():
                    continue
                processes.append(
                    {
                        "pid": info.get("pid"),
                        "name": proc_name,
                        "cpu_percent": info.get("cpu_percent"),
                        "memory_percent": info.get("memory_percent"),
                    }
                )
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        return OperationResult.ok(
            message=f"找到 {len(processes)} 个进程",
            data={"processes": processes, "count": len(processes)},
        )

    async def _process_kill(self, params: dict[str, Any]) -> OperationResult:
        if "pid" in params:
            pid = int(params["pid"])
            try:
                process = psutil.Process(pid)
                process_name = process.name()
                process.terminate()
                return OperationResult.ok(message=f"已终止进程: {process_name} (PID: {pid})")
            except psutil.NoSuchProcess:
                return OperationResult.fail(error=f"进程不存在: {pid}", error_code="PROCESS_NOT_FOUND")

        name = params.get("name")
        if name:
            killed = 0
            for proc in psutil.process_iter(["pid", "name"]):
                try:
                    proc_name = proc.info.get("name") or ""
                    if str(name).lower() in proc_name.lower():
                        proc.terminate()
                        killed += 1
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue

            return OperationResult.ok(message=f"已终止 {killed} 个名称匹配 {name} 的进程")

        return OperationResult.fail(error="缺少参数: pid 或 name", error_code="MISSING_PARAMS")

    async def _process_start(self, params: dict[str, Any]) -> OperationResult:
        command = params["command"]
        args = params.get("args", [])
        cwd = params.get("cwd")

        try:
            if platform.system() == "Windows":
                process = subprocess.Popen([command] + args, cwd=cwd, creationflags=subprocess.CREATE_NEW_CONSOLE)
            else:
                process = subprocess.Popen([command] + args, cwd=cwd)

            return OperationResult.ok(message=f"进程已启动: {command}", data={"pid": process.pid})
        except Exception as e:
            return OperationResult.fail(error=f"启动进程失败: {e}", error_code="PROCESS_START_ERROR")

    async def _service_status(self, params: dict[str, Any]) -> OperationResult:
        name = params["name"]

        try:
            if platform.system() == "Windows":
                result = subprocess.run(["sc", "query", name], capture_output=True, text=True)
                status = "running" if "RUNNING" in result.stdout else "stopped"
            else:
                result = subprocess.run(["systemctl", "is-active", name], capture_output=True, text=True)
                status = result.stdout.strip()

            return OperationResult.ok(message=f"服务状态: {name}", data={"name": name, "status": status})
        except Exception as e:
            return OperationResult.fail(error=f"查询服务状态失败: {e}", error_code="SERVICE_STATUS_ERROR")

    async def _service_start(self, params: dict[str, Any]) -> OperationResult:
        name = params["name"]

        try:
            if platform.system() == "Windows":
                subprocess.run(["net", "start", name], check=True)
            else:
                subprocess.run(["sudo", "systemctl", "start", name], check=True)

            return OperationResult.ok(message=f"服务已启动: {name}")
        except Exception as e:
            return OperationResult.fail(error=f"启动服务失败: {e}", error_code="SERVICE_START_ERROR")

    async def _service_stop(self, params: dict[str, Any]) -> OperationResult:
        name = params["name"]

        try:
            if platform.system() == "Windows":
                subprocess.run(["net", "stop", name], check=True)
            else:
                subprocess.run(["sudo", "systemctl", "stop", name], check=True)

            return OperationResult.ok(message=f"服务已停止: {name}")
        except Exception as e:
            return OperationResult.fail(error=f"停止服务失败: {e}", error_code="SERVICE_STOP_ERROR")

    async def _hardware_info(self, params: dict[str, Any]) -> OperationResult:
        info = {
            "platform": platform.system(),
            "platform_version": platform.version(),
            "architecture": platform.architecture(),
            "processor": platform.processor(),
            "cpu_count": psutil.cpu_count(),
            "cpu_count_logical": psutil.cpu_count(logical=True),
            "cpu_freq": psutil.cpu_freq()._asdict() if psutil.cpu_freq() else None,
        }
        return OperationResult.ok(message="获取硬件信息成功", data=info)

    async def _gpu_info(self, params: dict[str, Any]) -> OperationResult:
        try:
            import pynvml

            pynvml.nvmlInit()
            device_count = pynvml.nvmlDeviceGetCount()
            gpus = []

            for i in range(device_count):
                handle = pynvml.nvmlDeviceGetHandleByIndex(i)
                name = pynvml.nvmlDeviceGetName(handle)
                memory_info = pynvml.nvmlDeviceGetMemoryInfo(handle)
                gpus.append(
                    {
                        "index": i,
                        "name": name.decode() if isinstance(name, bytes) else name,
                        "memory_total": memory_info.total,
                        "memory_used": memory_info.used,
                        "memory_free": memory_info.free,
                    }
                )

            pynvml.nvmlShutdown()
            return OperationResult.ok(message=f"找到 {device_count} 个 GPU", data={"gpus": gpus, "count": device_count})
        except ImportError:
            return OperationResult.fail(error="pynvml 未安装，请运行: pip install pynvml", error_code="NVML_NOT_INSTALLED")
        except Exception as e:
            return OperationResult.fail(error=f"获取 GPU 信息失败: {e}", error_code="GPU_INFO_ERROR")

    async def _memory_info(self, params: dict[str, Any]) -> OperationResult:
        memory = psutil.virtual_memory()
        swap = psutil.swap_memory()

        return OperationResult.ok(
            message="获取内存信息成功",
            data={
                "total": memory.total,
                "available": memory.available,
                "used": memory.used,
                "percent": memory.percent,
                "swap_total": swap.total,
                "swap_used": swap.used,
                "swap_percent": swap.percent,
            },
        )

    async def _disk_info(self, params: dict[str, Any]) -> OperationResult:
        disks = []
        for partition in psutil.disk_partitions():
            try:
                usage = psutil.disk_usage(partition.mountpoint)
                disks.append(
                    {
                        "device": partition.device,
                        "mountpoint": partition.mountpoint,
                        "fstype": partition.fstype,
                        "total": usage.total,
                        "used": usage.used,
                        "free": usage.free,
                        "percent": usage.percent,
                    }
                )
            except PermissionError:
                continue

        return OperationResult.ok(message=f"找到 {len(disks)} 个磁盘分区", data={"disks": disks, "count": len(disks)})

    async def _network_info(self, params: dict[str, Any]) -> OperationResult:
        interfaces = []
        for name, addrs in psutil.net_if_addrs().items():
            interface = {"name": name, "addresses": []}
            for addr in addrs:
                interface["addresses"].append(
                    {
                        "family": str(addr.family),
                        "address": addr.address,
                        "netmask": addr.netmask,
                    }
                )
            interfaces.append(interface)

        io_counters = psutil.net_io_counters()

        return OperationResult.ok(
            message="获取网络信息成功",
            data={
                "interfaces": interfaces,
                "bytes_sent": io_counters.bytes_sent,
                "bytes_recv": io_counters.bytes_recv,
                "packets_sent": io_counters.packets_sent,
                "packets_recv": io_counters.packets_recv,
            },
        )

    async def _command_execute(self, params: dict[str, Any]) -> OperationResult:
        command = params["command"]
        timeout = int(params.get("timeout", 60))
        shell = bool(params.get("shell", False))

        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=timeout, shell=shell)
            return OperationResult.ok(
                message="命令执行完成",
                data={"returncode": result.returncode, "stdout": result.stdout, "stderr": result.stderr},
            )
        except subprocess.TimeoutExpired:
            return OperationResult.fail(error=f"命令执行超时 ({timeout}s)", error_code="COMMAND_TIMEOUT")
        except Exception as e:
            return OperationResult.fail(error=f"命令执行失败: {e}", error_code="COMMAND_ERROR")

    async def _app_open(self, params: dict[str, Any]) -> OperationResult:
        app_name = str(params.get("app_name", "")).strip()
        args = params.get("args", [])
        if not app_name:
            return OperationResult.fail(error="缺少参数: app_name", error_code="MISSING_PARAMS")

        validation = self._whitelist.validate_app(app_name)
        if not validation.is_valid:
            return OperationResult.fail(error=validation.error or "应用不在白名单中", error_code="APP_NOT_ALLOWED")

        executable = validation.sanitized_value or app_name
        try:
            if platform.system() == "Windows":
                process = subprocess.Popen([executable] + list(args), shell=False)
            else:
                process = subprocess.Popen([executable] + list(args))
            return OperationResult.ok(
                message=f"应用已启动: {app_name}",
                data={"app_name": app_name, "executable": executable, "pid": process.pid},
            )
        except Exception as e:
            return OperationResult.fail(error=f"启动应用失败: {e}", error_code="APP_OPEN_ERROR")

    async def _url_open(self, params: dict[str, Any]) -> OperationResult:
        url = str(params.get("url", "")).strip()
        if not url:
            return OperationResult.fail(error="缺少参数: url", error_code="MISSING_PARAMS")
        if not url.startswith(("http://", "https://")):
            return OperationResult.fail(error="URL 必须以 http:// 或 https:// 开头", error_code="INVALID_URL")

        ok = webbrowser.open(url, new=2)
        if not ok:
            return OperationResult.fail(error="无法打开 URL", error_code="URL_OPEN_ERROR", data={"url": url})
        return OperationResult.ok(message="网址已打开", data={"url": url})
