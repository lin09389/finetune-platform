"""
程序启动/关闭操作模块
"""
import asyncio
import os
import platform
import subprocess
import signal
import time
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from datetime import datetime
import logging

from .whitelist import AppWhitelist, get_whitelist

logger = logging.getLogger(__name__)


@dataclass
class ProcessInfo:
    pid: int
    name: str
    executable: str
    cmdline: List[str]
    create_time: float
    status: str
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "pid": self.pid,
            "name": self.name,
            "executable": self.executable,
            "cmdline": self.cmdline,
            "create_time": self.create_time,
            "status": self.status,
        }


@dataclass
class LaunchResult:
    success: bool
    message: str
    pid: Optional[int] = None
    error: Optional[str] = None
    timestamp: str = ""
    
    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "message": self.message,
            "pid": self.pid,
            "error": self.error,
            "timestamp": self.timestamp,
        }


class AppLauncher:
    def __init__(self, whitelist: Optional[AppWhitelist] = None):
        self._whitelist = whitelist or get_whitelist()
        self._platform = platform.system()
        self._processes: Dict[int, subprocess.Popen] = {}
    
    def _get_platform_launch_cmd(
        self,
        executable: str,
        args: Optional[List[str]] = None,
        cwd: Optional[str] = None,
    ) -> tuple:
        args = args or []
        
        if self._platform == "Windows":
            if args:
                return ([executable] + args, cwd)
            return ([executable], cwd)
        elif self._platform == "Darwin":
            if args:
                return (["open", "-a", executable, "--args"] + args, cwd)
            return (["open", "-a", executable], cwd)
        else:
            if args:
                return ([executable] + args, cwd)
            return ([executable], cwd)
    
    def launch(
        self,
        app_name: str,
        args: Optional[List[str]] = None,
        cwd: Optional[str] = None,
        env: Optional[Dict[str, str]] = None,
        wait: bool = False,
        check_whitelist: bool = True,
    ) -> LaunchResult:
        if check_whitelist:
            validation = self._whitelist.validate_app(app_name)
            if not validation.is_valid:
                return LaunchResult(
                    success=False,
                    message="应用不在白名单中",
                    error=validation.error,
                )
            executable = validation.sanitized_value
        else:
            executable = app_name
        
        try:
            cmd, work_dir = self._get_platform_launch_cmd(executable, args, cwd)
            
            process_env = os.environ.copy()
            if env:
                process_env.update(env)
            
            if wait:
                process = subprocess.run(
                    cmd,
                    cwd=work_dir,
                    env=process_env,
                    capture_output=True,
                    text=True,
                    timeout=60,
                )
                
                if process.returncode == 0:
                    return LaunchResult(
                        success=True,
                        message=f"应用已执行完成：{app_name}",
                    )
                else:
                    return LaunchResult(
                        success=False,
                        message="应用执行失败",
                        error=process.stderr or f"退出码: {process.returncode}",
                    )
            else:
                process = subprocess.Popen(
                    cmd,
                    cwd=work_dir,
                    env=process_env,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    shell=False,
                )
                
                self._processes[process.pid] = process
                
                logger.info(f"应用已启动：{app_name} (PID: {process.pid})")
                
                return LaunchResult(
                    success=True,
                    message=f"应用已启动：{app_name}",
                    pid=process.pid,
                )
                
        except FileNotFoundError:
            return LaunchResult(
                success=False,
                message="应用未找到",
                error=f"找不到可执行文件：{executable}",
            )
        except subprocess.TimeoutExpired:
            return LaunchResult(
                success=False,
                message="应用执行超时",
                error="执行时间超过 60 秒",
            )
        except Exception as e:
            logger.error(f"启动应用失败：{app_name} - {e}")
            return LaunchResult(
                success=False,
                message="启动应用失败",
                error=str(e),
            )
    
    async def launch_async(
        self,
        app_name: str,
        args: Optional[List[str]] = None,
        cwd: Optional[str] = None,
        env: Optional[Dict[str, str]] = None,
        wait: bool = False,
        check_whitelist: bool = True,
    ) -> LaunchResult:
        return await asyncio.to_thread(
            self.launch,
            app_name=app_name,
            args=args,
            cwd=cwd,
            env=env,
            wait=wait,
            check_whitelist=check_whitelist,
        )
    
    def launch_with_file(
        self,
        app_name: str,
        file_path: str,
        check_whitelist: bool = True,
    ) -> LaunchResult:
        if not os.path.exists(file_path):
            return LaunchResult(
                success=False,
                message="文件不存在",
                error=f"找不到文件：{file_path}",
            )
        
        return self.launch(
            app_name=app_name,
            args=[file_path],
            check_whitelist=check_whitelist,
        )
    
    def launch_with_url(
        self,
        app_name: str,
        url: str,
        check_whitelist: bool = True,
    ) -> LaunchResult:
        if not url.startswith(("http://", "https://")):
            return LaunchResult(
                success=False,
                message="无效的 URL",
                error="URL 必须以 http:// 或 https:// 开头",
            )
        
        return self.launch(
            app_name=app_name,
            args=[url],
            check_whitelist=check_whitelist,
        )
    
    def is_running(self, pid: int) -> bool:
        try:
            if pid in self._processes:
                return self._processes[pid].poll() is None
            
            os.kill(pid, 0)
            return True
        except (OSError, ProcessLookupError):
            return False
    
    def get_process_info(self, pid: int) -> Optional[ProcessInfo]:
        try:
            import psutil
            
            process = psutil.Process(pid)
            
            return ProcessInfo(
                pid=pid,
                name=process.name(),
                executable=process.exe(),
                cmdline=process.cmdline(),
                create_time=process.create_time(),
                status=process.status(),
            )
        except ImportError:
            if pid in self._processes:
                proc = self._processes[pid]
                return ProcessInfo(
                    pid=pid,
                    name="unknown",
                    executable="unknown",
                    cmdline=[],
                    create_time=time.time(),
                    status="running" if proc.poll() is None else "terminated",
                )
            return None
        except Exception:
            return None
    
    def find_processes_by_name(self, name: str) -> List[ProcessInfo]:
        results = []
        
        try:
            import psutil
            
            for proc in psutil.process_iter(['pid', 'name', 'exe', 'cmdline', 'create_time', 'status']):
                try:
                    proc_name = proc.info.get('name', '').lower()
                    proc_exe = proc.info.get('exe', '') or ''
                    
                    if name.lower() in proc_name or name.lower() in proc_exe.lower():
                        results.append(ProcessInfo(
                            pid=proc.info['pid'],
                            name=proc.info['name'],
                            executable=proc_exe,
                            cmdline=proc.info.get('cmdline', []),
                            create_time=proc.info.get('create_time', 0),
                            status=proc.info.get('status', 'unknown'),
                        ))
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
        except ImportError:
            pass
        
        return results
    
    def close(
        self,
        pid: int,
        timeout: int = 10,
        force: bool = False,
    ) -> LaunchResult:
        if not self.is_running(pid):
            return LaunchResult(
                success=True,
                message="进程已结束",
                pid=pid,
            )
        
        try:
            if self._platform == "Windows":
                if force:
                    subprocess.run(
                        ["taskkill", "/F", "/PID", str(pid)],
                        capture_output=True,
                        timeout=timeout,
                    )
                else:
                    subprocess.run(
                        ["taskkill", "/PID", str(pid)],
                        capture_output=True,
                        timeout=timeout,
                    )
            else:
                sig = signal.SIGKILL if force else signal.SIGTERM
                os.kill(pid, sig)
            
            start_wait = time.time()
            while self.is_running(pid) and (time.time() - start_wait) < timeout:
                time.sleep(0.5)
            
            if self.is_running(pid):
                if not force:
                    return self.close(pid, timeout=timeout, force=True)
                
                return LaunchResult(
                    success=False,
                    message="无法终止进程",
                    error="进程无响应",
                    pid=pid,
                )
            
            if pid in self._processes:
                del self._processes[pid]
            
            action = "强制关闭" if force else "关闭"
            logger.info(f"进程已{action}：PID {pid}")
            
            return LaunchResult(
                success=True,
                message=f"进程已{action}：PID {pid}",
                pid=pid,
            )
            
        except ProcessLookupError:
            return LaunchResult(
                success=True,
                message="进程不存在",
                pid=pid,
            )
        except Exception as e:
            logger.error(f"关闭进程失败：PID {pid} - {e}")
            return LaunchResult(
                success=False,
                message="关闭进程失败",
                error=str(e),
                pid=pid,
            )
    
    async def close_async(
        self,
        pid: int,
        timeout: int = 10,
        force: bool = False,
    ) -> LaunchResult:
        return await asyncio.to_thread(
            self.close,
            pid=pid,
            timeout=timeout,
            force=force,
        )
    
    def close_by_name(
        self,
        name: str,
        force: bool = False,
        timeout: int = 10,
    ) -> List[LaunchResult]:
        processes = self.find_processes_by_name(name)
        results = []
        
        for proc in processes:
            result = self.close(proc.pid, timeout=timeout, force=force)
            results.append(result)
        
        return results
    
    def close_all_launched(self, force: bool = False) -> List[LaunchResult]:
        results = []
        pids = list(self._processes.keys())
        
        for pid in pids:
            result = self.close(pid, force=force)
            results.append(result)
        
        return results
    
    def get_launched_processes(self) -> List[ProcessInfo]:
        results = []
        
        for pid in list(self._processes.keys()):
            info = self.get_process_info(pid)
            if info:
                results.append(info)
        
        return results
    
    def cleanup_terminated(self) -> int:
        cleaned = 0
        
        for pid in list(self._processes.keys()):
            if not self.is_running(pid):
                del self._processes[pid]
                cleaned += 1
        
        return cleaned


_launcher_instance: Optional[AppLauncher] = None


def get_launcher(whitelist: Optional[AppWhitelist] = None) -> AppLauncher:
    global _launcher_instance
    if _launcher_instance is None:
        _launcher_instance = AppLauncher(whitelist)
    return _launcher_instance
