from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

import psutil


class ProcessAction(str, Enum):
    LIST = "list"
    DETAIL = "detail"
    TERMINATE = "terminate"
    TREE = "tree"


@dataclass
class ProcessInfo:
    pid: int
    name: str
    cpu_percent: float = 0.0
    memory_percent: float = 0.0
    memory_mb: float = 0.0
    status: str = "unknown"
    create_time: datetime | None = None
    exe: str | None = None
    cmdline: list[str] = field(default_factory=list)
    username: str | None = None
    num_threads: int = 0
    num_handles: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "pid": self.pid,
            "name": self.name,
            "cpu_percent": round(self.cpu_percent, 2),
            "memory_percent": round(self.memory_percent, 2),
            "memory_mb": round(self.memory_mb, 2),
            "status": self.status,
            "create_time": self.create_time.isoformat() if self.create_time else None,
            "exe": self.exe,
            "cmdline": self.cmdline,
            "username": self.username,
            "num_threads": self.num_threads,
            "num_handles": self.num_handles,
        }


@dataclass
class ProcessTreeNode:
    process: ProcessInfo
    children: list["ProcessTreeNode"] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "process": self.process.to_dict(),
            "children": [child.to_dict() for child in self.children],
        }


class ProcessOperations:
    def __init__(self):
        self._confirmation_required: dict[int, bool] = {}

    async def list_processes(
        self,
        sort_by: str = "cpu",
        descending: bool = True,
        filter_name: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        processes = []

        for proc in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent", "status"]):
            try:
                pinfo = proc.info
                if filter_name and filter_name.lower() not in pinfo["name"].lower():
                    continue

                cpu = pinfo.get("cpu_percent") or 0.0
                mem = pinfo.get("memory_percent") or 0.0

                processes.append({
                    "pid": pinfo["pid"],
                    "name": pinfo["name"],
                    "cpu_percent": round(cpu, 2),
                    "memory_percent": round(mem, 2),
                    "status": pinfo.get("status", "unknown"),
                })
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue

        sort_key = {
            "cpu": lambda x: x["cpu_percent"],
            "memory": lambda x: x["memory_percent"],
            "name": lambda x: x["name"].lower(),
            "pid": lambda x: x["pid"],
        }.get(sort_by, lambda x: x["cpu_percent"])

        processes.sort(key=sort_key, reverse=descending)

        return processes[:limit]

    async def get_process_detail(self, pid: int) -> dict[str, Any] | None:
        try:
            proc = psutil.Process(pid)

            with proc.oneshot():
                cpu_percent = proc.cpu_percent(interval=0.1)
                memory_info = proc.memory_info()
                memory_percent = proc.memory_percent()

                try:
                    create_time = datetime.fromtimestamp(proc.create_time())
                except (OSError, ValueError):
                    create_time = None

                try:
                    exe = proc.exe()
                except (psutil.AccessDenied, psutil.NoSuchProcess):
                    exe = None

                try:
                    cmdline = proc.cmdline()
                except (psutil.AccessDenied, psutil.NoSuchProcess):
                    cmdline = []

                try:
                    username = proc.username()
                except (psutil.AccessDenied, psutil.NoSuchProcess):
                    username = None

                try:
                    num_threads = proc.num_threads()
                except (psutil.AccessDenied, psutil.NoSuchProcess):
                    num_threads = 0

                try:
                    num_handles = proc.num_handles() if hasattr(proc, "num_handles") else 0
                except (psutil.AccessDenied, psutil.NoSuchProcess):
                    num_handles = 0

                info = ProcessInfo(
                    pid=pid,
                    name=proc.name(),
                    cpu_percent=cpu_percent,
                    memory_percent=memory_percent,
                    memory_mb=memory_info.rss / (1024 * 1024),
                    status=proc.status(),
                    create_time=create_time,
                    exe=exe,
                    cmdline=cmdline,
                    username=username,
                    num_threads=num_threads,
                    num_handles=num_handles,
                )

                return info.to_dict()

        except psutil.NoSuchProcess:
            return None
        except psutil.AccessDenied:
            return {"pid": pid, "error": "Access denied"}
        except Exception as e:
            return {"pid": pid, "error": str(e)}

    async def terminate_process(
        self,
        pid: int,
        force: bool = False,
        require_confirmation: bool = True,
    ) -> dict[str, Any]:
        if require_confirmation and not self._confirmation_required.get(pid):
            self._confirmation_required[pid] = True
            return {
                "success": False,
                "requires_confirmation": True,
                "message": f"确认终止进程 PID {pid}？请再次执行以确认。",
                "pid": pid,
            }

        self._confirmation_required.pop(pid, None)

        try:
            proc = psutil.Process(pid)
            process_name = proc.name()

            if force:
                proc.kill()
            else:
                proc.terminate()

            try:
                proc.wait(timeout=5)
            except psutil.TimeoutExpired:
                if not force:
                    proc.kill()
                    proc.wait(timeout=3)

            return {
                "success": True,
                "message": f"进程 {process_name} (PID: {pid}) 已终止",
                "pid": pid,
                "process_name": process_name,
            }

        except psutil.NoSuchProcess:
            return {
                "success": False,
                "error": f"进程 PID {pid} 不存在",
                "pid": pid,
            }
        except psutil.AccessDenied:
            return {
                "success": False,
                "error": f"没有权限终止进程 PID {pid}",
                "pid": pid,
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "pid": pid,
            }

    async def get_process_tree(self, pid: int | None = None) -> dict[str, Any]:
        def build_tree(parent_pid: int | None) -> list[ProcessTreeNode]:
            children = []

            for proc in psutil.process_iter(["pid", "name", "ppid"]):
                try:
                    ppid = proc.info.get("ppid")
                    if ppid == parent_pid:
                        child_info = ProcessInfo(
                            pid=proc.info["pid"],
                            name=proc.info["name"],
                        )
                        child_node = ProcessTreeNode(
                            process=child_info,
                            children=build_tree(proc.info["pid"]),
                        )
                        children.append(child_node)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue

            return children

        if pid is not None:
            try:
                proc = psutil.Process(pid)
                root_info = ProcessInfo(
                    pid=pid,
                    name=proc.name(),
                )
                root_node = ProcessTreeNode(
                    process=root_info,
                    children=build_tree(pid),
                )
                return root_node.to_dict()
            except psutil.NoSuchProcess:
                return {"error": f"进程 PID {pid} 不存在"}
        else:
            return {
                "process": {"pid": 0, "name": "root"},
                "children": build_tree(None),
            }

    async def find_process_by_name(self, name: str) -> list[dict[str, Any]]:
        results = []
        name_lower = name.lower()

        for proc in psutil.process_iter(["pid", "name", "status"]):
            try:
                if name_lower in proc.info["name"].lower():
                    results.append({
                        "pid": proc.info["pid"],
                        "name": proc.info["name"],
                        "status": proc.info.get("status", "unknown"),
                    })
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        return results

    async def get_process_connections(self, pid: int) -> list[dict[str, Any]]:
        try:
            proc = psutil.Process(pid)
            connections = proc.connections()

            result = []
            for conn in connections:
                result.append({
                    "fd": conn.fd,
                    "family": str(conn.family),
                    "type": str(conn.type),
                    "local_address": f"{conn.laddr.ip}:{conn.laddr.port}" if conn.laddr else None,
                    "remote_address": f"{conn.raddr.ip}:{conn.raddr.port}" if conn.raddr else None,
                    "status": conn.status,
                })

            return result

        except psutil.NoSuchProcess:
            return [{"error": f"进程 PID {pid} 不存在"}]
        except psutil.AccessDenied:
            return [{"error": "没有权限访问进程连接信息"}]
        except Exception as e:
            return [{"error": str(e)}]
