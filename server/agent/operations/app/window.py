"""
窗口管理操作模块
"""
import asyncio
import platform
import subprocess
import time
from typing import List, Optional, Dict, Any
from dataclasses import dataclass
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


@dataclass
class WindowInfo:
    title: str
    handle: int
    x: int
    y: int
    width: int
    height: int
    is_visible: bool
    is_focused: bool
    process_name: Optional[str] = None
    process_id: Optional[int] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "title": self.title,
            "handle": self.handle,
            "x": self.x,
            "y": self.y,
            "width": self.width,
            "height": self.height,
            "is_visible": self.is_visible,
            "is_focused": self.is_focused,
            "process_name": self.process_name,
            "process_id": self.process_id,
        }


@dataclass
class WindowOperationResult:
    success: bool
    message: str
    operation: str
    window_title: Optional[str] = None
    error: Optional[str] = None
    duration_ms: Optional[float] = None
    data: Optional[Dict[str, Any]] = None
    timestamp: str = ""
    
    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "message": self.message,
            "operation": self.operation,
            "window_title": self.window_title,
            "error": self.error,
            "duration_ms": self.duration_ms,
            "data": self.data,
            "timestamp": self.timestamp,
        }


class WindowManager:
    def __init__(self):
        self._platform = platform.system()
        self._initialized = False
        self._gw = None
        self._pywinauto = None
    
    def initialize(self) -> bool:
        if self._initialized:
            return True
        
        try:
            import pygetwindow as gw
            self._gw = gw
            self._initialized = True
            return True
        except ImportError:
            logger.warning("pygetwindow not available, some features may not work")
            return False
    
    def _get_window_by_id(self, window_id: str):
        if not self._initialized:
            self.initialize()
        
        if not self._gw:
            raise RuntimeError("Window manager not initialized")
        
        try:
            if self._platform == "Windows":
                handle = int(window_id)
                windows = self._gw.getAllWindows()
                for win in windows:
                    if win._hWnd == handle:
                        return win
                raise ValueError(f"Window not found: {window_id}")
            else:
                windows = self._gw.getWindowsWithTitle(window_id)
                if windows:
                    return windows[0]
                raise ValueError(f"Window not found: {window_id}")
        except ValueError:
            windows = self._gw.getWindowsWithTitle(window_id)
            if windows:
                return windows[0]
            raise ValueError(f"Window not found: {window_id}")
    
    def _window_to_info(self, win) -> WindowInfo:
        try:
            return WindowInfo(
                title=win.title,
                handle=getattr(win, "_hWnd", 0),
                x=win.left,
                y=win.top,
                width=win.width,
                height=win.height,
                is_visible=win.visible,
                is_focused=win.isActive,
                process_name=None,
                process_id=None,
            )
        except Exception as e:
            raise RuntimeError(f"Failed to convert window info: {e}")
    
    def list_windows(self, include_hidden: bool = False) -> List[WindowInfo]:
        if not self._initialized:
            self.initialize()
        
        if not self._gw:
            return []
        
        try:
            windows = self._gw.getAllWindows()
            result: List[WindowInfo] = []
            
            for win in windows:
                if not win.title:
                    continue
                
                if not include_hidden and not win.visible:
                    continue
                
                try:
                    info = self._window_to_info(win)
                    result.append(info)
                except Exception:
                    continue
            
            return result
        except Exception as e:
            logger.error(f"Failed to list windows: {e}")
            return []
    
    async def list_windows_async(self, include_hidden: bool = False) -> List[WindowInfo]:
        return await asyncio.to_thread(self.list_windows, include_hidden)
    
    def get_active_window(self) -> Optional[WindowInfo]:
        if not self._initialized:
            self.initialize()
        
        if not self._gw:
            return None
        
        try:
            win = self._gw.getActiveWindow()
            if win is None:
                return None
            return self._window_to_info(win)
        except Exception as e:
            logger.error(f"Failed to get active window: {e}")
            return None
    
    async def get_active_window_async(self) -> Optional[WindowInfo]:
        return await asyncio.to_thread(self.get_active_window)
    
    def find_window(self, title: str) -> Optional[WindowInfo]:
        if not self._initialized:
            self.initialize()
        
        if not self._gw:
            return None
        
        try:
            windows = self._gw.getWindowsWithTitle(title)
            if not windows:
                return None
            return self._window_to_info(windows[0])
        except Exception as e:
            logger.error(f"Failed to find window: {e}")
            return None
    
    async def find_window_async(self, title: str) -> Optional[WindowInfo]:
        return await asyncio.to_thread(self.find_window, title)
    
    def find_windows(self, title_pattern: str) -> List[WindowInfo]:
        if not self._initialized:
            self.initialize()
        
        if not self._gw:
            return []
        
        try:
            windows = self._gw.getWindowsWithTitle(title_pattern)
            result: List[WindowInfo] = []
            
            for win in windows:
                try:
                    info = self._window_to_info(win)
                    result.append(info)
                except Exception:
                    continue
            
            return result
        except Exception as e:
            logger.error(f"Failed to find windows: {e}")
            return []
    
    def activate_window(self, window_id: str) -> WindowOperationResult:
        start_time = time.perf_counter()
        
        try:
            win = self._get_window_by_id(window_id)
            win.activate()
            
            duration_ms = (time.perf_counter() - start_time) * 1000
            
            return WindowOperationResult(
                success=True,
                message=f"窗口已激活：{win.title}",
                operation="activate",
                window_title=win.title,
                duration_ms=duration_ms,
            )
        except Exception as e:
            return WindowOperationResult(
                success=False,
                message="激活窗口失败",
                operation="activate",
                error=str(e),
            )
    
    async def activate_window_async(self, window_id: str) -> WindowOperationResult:
        return await asyncio.to_thread(self.activate_window, window_id)
    
    def minimize_window(self, window_id: str) -> WindowOperationResult:
        start_time = time.perf_counter()
        
        try:
            win = self._get_window_by_id(window_id)
            win.minimize()
            
            duration_ms = (time.perf_counter() - start_time) * 1000
            
            return WindowOperationResult(
                success=True,
                message=f"窗口已最小化：{win.title}",
                operation="minimize",
                window_title=win.title,
                duration_ms=duration_ms,
            )
        except Exception as e:
            return WindowOperationResult(
                success=False,
                message="最小化窗口失败",
                operation="minimize",
                error=str(e),
            )
    
    async def minimize_window_async(self, window_id: str) -> WindowOperationResult:
        return await asyncio.to_thread(self.minimize_window, window_id)
    
    def maximize_window(self, window_id: str) -> WindowOperationResult:
        start_time = time.perf_counter()
        
        try:
            win = self._get_window_by_id(window_id)
            win.maximize()
            
            duration_ms = (time.perf_counter() - start_time) * 1000
            
            return WindowOperationResult(
                success=True,
                message=f"窗口已最大化：{win.title}",
                operation="maximize",
                window_title=win.title,
                duration_ms=duration_ms,
            )
        except Exception as e:
            return WindowOperationResult(
                success=False,
                message="最大化窗口失败",
                operation="maximize",
                error=str(e),
            )
    
    async def maximize_window_async(self, window_id: str) -> WindowOperationResult:
        return await asyncio.to_thread(self.maximize_window, window_id)
    
    def restore_window(self, window_id: str) -> WindowOperationResult:
        start_time = time.perf_counter()
        
        try:
            win = self._get_window_by_id(window_id)
            win.restore()
            
            duration_ms = (time.perf_counter() - start_time) * 1000
            
            return WindowOperationResult(
                success=True,
                message=f"窗口已还原：{win.title}",
                operation="restore",
                window_title=win.title,
                duration_ms=duration_ms,
            )
        except Exception as e:
            return WindowOperationResult(
                success=False,
                message="还原窗口失败",
                operation="restore",
                error=str(e),
            )
    
    async def restore_window_async(self, window_id: str) -> WindowOperationResult:
        return await asyncio.to_thread(self.restore_window, window_id)
    
    def close_window(self, window_id: str, force: bool = False) -> WindowOperationResult:
        start_time = time.perf_counter()
        
        try:
            win = self._get_window_by_id(window_id)
            title = win.title
            
            if force and self._platform == "Windows":
                try:
                    import win32gui
                    import win32con
                    win32gui.PostMessage(win._hWnd, win32con.WM_CLOSE, 0, 0)
                except ImportError:
                    win.close()
            else:
                win.close()
            
            duration_ms = (time.perf_counter() - start_time) * 1000
            
            return WindowOperationResult(
                success=True,
                message=f"窗口已关闭：{title}",
                operation="close",
                window_title=title,
                duration_ms=duration_ms,
            )
        except Exception as e:
            return WindowOperationResult(
                success=False,
                message="关闭窗口失败",
                operation="close",
                error=str(e),
            )
    
    async def close_window_async(self, window_id: str, force: bool = False) -> WindowOperationResult:
        return await asyncio.to_thread(self.close_window, window_id, force)
    
    def move_window(self, window_id: str, x: int, y: int) -> WindowOperationResult:
        start_time = time.perf_counter()
        
        try:
            win = self._get_window_by_id(window_id)
            win.moveTo(x, y)
            
            duration_ms = (time.perf_counter() - start_time) * 1000
            
            return WindowOperationResult(
                success=True,
                message=f"窗口已移动到 ({x}, {y})：{win.title}",
                operation="move",
                window_title=win.title,
                duration_ms=duration_ms,
                data={"x": x, "y": y},
            )
        except Exception as e:
            return WindowOperationResult(
                success=False,
                message=f"移动窗口到 ({x}, {y}) 失败",
                operation="move",
                error=str(e),
            )
    
    async def move_window_async(self, window_id: str, x: int, y: int) -> WindowOperationResult:
        return await asyncio.to_thread(self.move_window, window_id, x, y)
    
    def resize_window(self, window_id: str, width: int, height: int) -> WindowOperationResult:
        start_time = time.perf_counter()
        
        try:
            win = self._get_window_by_id(window_id)
            win.resizeTo(width, height)
            
            duration_ms = (time.perf_counter() - start_time) * 1000
            
            return WindowOperationResult(
                success=True,
                message=f"窗口大小已调整为 {width}x{height}：{win.title}",
                operation="resize",
                window_title=win.title,
                duration_ms=duration_ms,
                data={"width": width, "height": height},
            )
        except Exception as e:
            return WindowOperationResult(
                success=False,
                message=f"调整窗口大小到 {width}x{height} 失败",
                operation="resize",
                error=str(e),
            )
    
    async def resize_window_async(self, window_id: str, width: int, height: int) -> WindowOperationResult:
        return await asyncio.to_thread(self.resize_window, window_id, width, height)
    
    def move_and_resize(
        self,
        window_id: str,
        x: int,
        y: int,
        width: int,
        height: int,
    ) -> WindowOperationResult:
        start_time = time.perf_counter()
        
        try:
            win = self._get_window_by_id(window_id)
            win.moveTo(x, y)
            win.resizeTo(width, height)
            
            duration_ms = (time.perf_counter() - start_time) * 1000
            
            return WindowOperationResult(
                success=True,
                message=f"窗口已移动到 ({x}, {y}) 并调整大小为 {width}x{height}：{win.title}",
                operation="move_and_resize",
                window_title=win.title,
                duration_ms=duration_ms,
                data={"x": x, "y": y, "width": width, "height": height},
            )
        except Exception as e:
            return WindowOperationResult(
                success=False,
                message="移动并调整窗口大小失败",
                operation="move_and_resize",
                error=str(e),
            )
    
    async def move_and_resize_async(
        self,
        window_id: str,
        x: int,
        y: int,
        width: int,
        height: int,
    ) -> WindowOperationResult:
        return await asyncio.to_thread(
            self.move_and_resize, window_id, x, y, width, height
        )
    
    def get_window_rect(self, window_id: str) -> Optional[Dict[str, int]]:
        try:
            win = self._get_window_by_id(window_id)
            return {
                "x": win.left,
                "y": win.top,
                "width": win.width,
                "height": win.height,
            }
        except Exception:
            return None
    
    def bring_to_front(self, window_id: str) -> WindowOperationResult:
        return self.activate_window(window_id)
    
    def send_to_back(self, window_id: str) -> WindowOperationResult:
        start_time = time.perf_counter()
        
        try:
            win = self._get_window_by_id(window_id)
            win.minimize()
            win.restore()
            
            duration_ms = (time.perf_counter() - start_time) * 1000
            
            return WindowOperationResult(
                success=True,
                message=f"窗口已移到后台：{win.title}",
                operation="send_to_back",
                window_title=win.title,
                duration_ms=duration_ms,
            )
        except Exception as e:
            return WindowOperationResult(
                success=False,
                message="移动窗口到后台失败",
                operation="send_to_back",
                error=str(e),
            )
    
    def center_window(self, window_id: str) -> WindowOperationResult:
        start_time = time.perf_counter()
        
        try:
            win = self._get_window_by_id(window_id)
            
            import pygetwindow as gw
            screen_width, screen_height = gw.size()
            
            x = (screen_width - win.width) // 2
            y = (screen_height - win.height) // 2
            
            win.moveTo(x, y)
            
            duration_ms = (time.perf_counter() - start_time) * 1000
            
            return WindowOperationResult(
                success=True,
                message=f"窗口已居中：{win.title}",
                operation="center",
                window_title=win.title,
                duration_ms=duration_ms,
                data={"x": x, "y": y},
            )
        except Exception as e:
            return WindowOperationResult(
                success=False,
                message="窗口居中失败",
                operation="center",
                error=str(e),
            )
    
    async def center_window_async(self, window_id: str) -> WindowOperationResult:
        return await asyncio.to_thread(self.center_window, window_id)
    
    def _run_applescript(self, script: str) -> str:
        if self._platform != "Darwin":
            raise RuntimeError("AppleScript only available on macOS")
        
        try:
            result = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True,
                text=True,
                check=True,
            )
            return result.stdout.strip()
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"AppleScript execution failed: {e.stderr}")
    
    def _run_wmctrl(self, args: List[str]) -> str:
        if self._platform != "Linux":
            raise RuntimeError("wmctrl only available on Linux")
        
        try:
            result = subprocess.run(
                ["wmctrl"] + args,
                capture_output=True,
                text=True,
                check=True,
            )
            return result.stdout.strip()
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"wmctrl execution failed: {e.stderr}")
        except FileNotFoundError:
            raise RuntimeError("wmctrl not found, please install it")


_window_manager_instance: Optional[WindowManager] = None


def get_window_manager() -> WindowManager:
    global _window_manager_instance
    if _window_manager_instance is None:
        _window_manager_instance = WindowManager()
        _window_manager_instance.initialize()
    return _window_manager_instance
