"""
CUA 窗口管理模块
"""
import asyncio
import platform
import subprocess
import time

import pygetwindow as gw

from .config import get_cua_config
from .exceptions import WindowNotFoundError, WindowOperationError
from .models import OperationResult, OperationType, WindowInfo
from .types import Region


class WindowManager:
    def __init__(self):
        self._config = get_cua_config()
        self._platform = platform.system().lower()

    def _get_window_by_id(self, window_id: str) -> gw.Win32Window:
        try:
            if self._platform == "windows":
                handle = int(window_id)
                windows = gw.getAllWindows()
                for win in windows:
                    if win._hWnd == handle:
                        return win
                raise WindowNotFoundError(window_id)
            else:
                windows = gw.getAllTitles()
                for title in windows:
                    if title and window_id in title:
                        return gw.getWindowsWithTitle(title)[0]
                raise WindowNotFoundError(window_id)
        except ValueError:
            windows = gw.getWindowsWithTitle(window_id)
            if windows:
                return windows[0]
            raise WindowNotFoundError(window_id)
        except Exception as e:
            raise WindowNotFoundError(window_id, details=str(e))

    def _window_to_info(self, win: gw.Win32Window) -> WindowInfo:
        try:
            return WindowInfo(
                title=win.title,
                handle=getattr(win, "_hWnd", None),
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
            raise WindowOperationError(
                message="Failed to convert window info",
                operation="window_to_info",
                details=str(e),
            )

    def list_windows(self) -> list[WindowInfo]:
        try:
            windows = gw.getAllWindows()
            result: list[WindowInfo] = []
            for win in windows:
                if win.title:
                    try:
                        info = self._window_to_info(win)
                        result.append(info)
                    except WindowOperationError:
                        continue
            return result
        except Exception as e:
            raise WindowOperationError(
                message="Failed to list windows",
                operation="list_windows",
                details=str(e),
            )

    async def list_windows_async(self) -> list[WindowInfo]:
        return await asyncio.to_thread(self.list_windows)

    def get_active_window(self) -> WindowInfo:
        try:
            win = gw.getActiveWindow()
            if win is None:
                raise WindowOperationError(
                    message="No active window found",
                    operation="get_active_window",
                )
            return self._window_to_info(win)
        except WindowOperationError:
            raise
        except Exception as e:
            raise WindowOperationError(
                message="Failed to get active window",
                operation="get_active_window",
                details=str(e),
            )

    async def get_active_window_async(self) -> WindowInfo:
        return await asyncio.to_thread(self.get_active_window)

    def find_window(self, title: str) -> WindowInfo:
        try:
            windows = gw.getWindowsWithTitle(title)
            if not windows:
                raise WindowNotFoundError(title)
            return self._window_to_info(windows[0])
        except WindowNotFoundError:
            raise
        except Exception as e:
            raise WindowOperationError(
                message=f"Failed to find window with title: {title}",
                operation="find_window",
                details=str(e),
            )

    async def find_window_async(self, title: str) -> WindowInfo:
        return await asyncio.to_thread(self.find_window, title)

    def activate_window(self, window_id: str) -> OperationResult:
        start_time = time.perf_counter()
        try:
            win = self._get_window_by_id(window_id)
            win.activate()
            duration_ms = (time.perf_counter() - start_time) * 1000
            return OperationResult.success_result(
                operation_type=OperationType.WINDOW_FOCUS,
                message=f"Window activated: {win.title}",
                duration_ms=duration_ms,
            )
        except WindowNotFoundError:
            raise
        except Exception as e:
            raise WindowOperationError(
                message="Failed to activate window",
                operation="activate_window",
                details=str(e),
            )

    async def activate_window_async(self, window_id: str) -> OperationResult:
        return await asyncio.to_thread(self.activate_window, window_id)

    def minimize_window(self, window_id: str) -> OperationResult:
        start_time = time.perf_counter()
        try:
            win = self._get_window_by_id(window_id)
            win.minimize()
            duration_ms = (time.perf_counter() - start_time) * 1000
            return OperationResult.success_result(
                operation_type=OperationType.WINDOW_MINIMIZE,
                message=f"Window minimized: {win.title}",
                duration_ms=duration_ms,
            )
        except WindowNotFoundError:
            raise
        except Exception as e:
            raise WindowOperationError(
                message="Failed to minimize window",
                operation="minimize_window",
                details=str(e),
            )

    async def minimize_window_async(self, window_id: str) -> OperationResult:
        return await asyncio.to_thread(self.minimize_window, window_id)

    def maximize_window(self, window_id: str) -> OperationResult:
        start_time = time.perf_counter()
        try:
            win = self._get_window_by_id(window_id)
            win.maximize()
            duration_ms = (time.perf_counter() - start_time) * 1000
            return OperationResult.success_result(
                operation_type=OperationType.WINDOW_MAXIMIZE,
                message=f"Window maximized: {win.title}",
                duration_ms=duration_ms,
            )
        except WindowNotFoundError:
            raise
        except Exception as e:
            raise WindowOperationError(
                message="Failed to maximize window",
                operation="maximize_window",
                details=str(e),
            )

    async def maximize_window_async(self, window_id: str) -> OperationResult:
        return await asyncio.to_thread(self.maximize_window, window_id)

    def restore_window(self, window_id: str) -> OperationResult:
        start_time = time.perf_counter()
        try:
            win = self._get_window_by_id(window_id)
            win.restore()
            duration_ms = (time.perf_counter() - start_time) * 1000
            return OperationResult.success_result(
                operation_type=OperationType.WINDOW_RESTORE,
                message=f"Window restored: {win.title}",
                duration_ms=duration_ms,
            )
        except WindowNotFoundError:
            raise
        except Exception as e:
            raise WindowOperationError(
                message="Failed to restore window",
                operation="restore_window",
                details=str(e),
            )

    async def restore_window_async(self, window_id: str) -> OperationResult:
        return await asyncio.to_thread(self.restore_window, window_id)

    def close_window(self, window_id: str) -> OperationResult:
        start_time = time.perf_counter()
        try:
            win = self._get_window_by_id(window_id)
            win.close()
            duration_ms = (time.perf_counter() - start_time) * 1000
            return OperationResult.success_result(
                operation_type=OperationType.WINDOW_CLOSE,
                message=f"Window closed: {win.title}",
                duration_ms=duration_ms,
            )
        except WindowNotFoundError:
            raise
        except Exception as e:
            raise WindowOperationError(
                message="Failed to close window",
                operation="close_window",
                details=str(e),
            )

    async def close_window_async(self, window_id: str) -> OperationResult:
        return await asyncio.to_thread(self.close_window, window_id)

    def move_window(self, window_id: str, x: int, y: int) -> OperationResult:
        start_time = time.perf_counter()
        try:
            win = self._get_window_by_id(window_id)
            win.moveTo(x, y)
            duration_ms = (time.perf_counter() - start_time) * 1000
            return OperationResult.success_result(
                operation_type=OperationType.WINDOW_MOVE,
                message=f"Window moved to ({x}, {y}): {win.title}",
                duration_ms=duration_ms,
                data={"x": x, "y": y},
            )
        except WindowNotFoundError:
            raise
        except Exception as e:
            raise WindowOperationError(
                message=f"Failed to move window to ({x}, {y})",
                operation="move_window",
                details=str(e),
            )

    async def move_window_async(self, window_id: str, x: int, y: int) -> OperationResult:
        return await asyncio.to_thread(self.move_window, window_id, x, y)

    def resize_window(self, window_id: str, width: int, height: int) -> OperationResult:
        start_time = time.perf_counter()
        try:
            win = self._get_window_by_id(window_id)
            win.resizeTo(width, height)
            duration_ms = (time.perf_counter() - start_time) * 1000
            return OperationResult.success_result(
                operation_type=OperationType.WINDOW_RESIZE,
                message=f"Window resized to {width}x{height}: {win.title}",
                duration_ms=duration_ms,
                data={"width": width, "height": height},
            )
        except WindowNotFoundError:
            raise
        except Exception as e:
            raise WindowOperationError(
                message=f"Failed to resize window to {width}x{height}",
                operation="resize_window",
                details=str(e),
            )

    async def resize_window_async(self, window_id: str, width: int, height: int) -> OperationResult:
        return await asyncio.to_thread(self.resize_window, window_id, width, height)

    def get_window_rect(self, window_id: str) -> Region:
        try:
            win = self._get_window_by_id(window_id)
            return Region(
                x=win.left,
                y=win.top,
                width=win.width,
                height=win.height,
            )
        except WindowNotFoundError:
            raise
        except Exception as e:
            raise WindowOperationError(
                message="Failed to get window rect",
                operation="get_window_rect",
                details=str(e),
            )

    async def get_window_rect_async(self, window_id: str) -> Region:
        return await asyncio.to_thread(self.get_window_rect, window_id)

    def _run_applescript(self, script: str) -> str:
        if self._platform != "darwin":
            raise WindowOperationError(
                message="AppleScript only available on macOS",
                operation="run_applescript",
            )
        try:
            result = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True,
                text=True,
                check=True,
            )
            return result.stdout.strip()
        except subprocess.CalledProcessError as e:
            raise WindowOperationError(
                message="AppleScript execution failed",
                operation="run_applescript",
                details=e.stderr,
            )

    def _run_wmctrl(self, args: list[str]) -> str:
        if self._platform != "linux":
            raise WindowOperationError(
                message="wmctrl only available on Linux",
                operation="run_wmctrl",
            )
        try:
            result = subprocess.run(
                ["wmctrl"] + args,
                capture_output=True,
                text=True,
                check=True,
            )
            return result.stdout.strip()
        except subprocess.CalledProcessError as e:
            raise WindowOperationError(
                message="wmctrl execution failed",
                operation="run_wmctrl",
                details=e.stderr,
            )
        except FileNotFoundError:
            raise WindowOperationError(
                message="wmctrl not found, please install it",
                operation="run_wmctrl",
            )


_window_manager: WindowManager | None = None


def get_window_manager() -> WindowManager:
    global _window_manager
    if _window_manager is None:
        _window_manager = WindowManager()
    return _window_manager
