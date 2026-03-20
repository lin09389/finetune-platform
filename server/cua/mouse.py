"""
鼠标控制器模�?
提供鼠标操作能力，包括移动、点击、拖拽、滚动等�?"""
import asyncio
import time
from typing import Optional

import pyautogui

from .models import OperationResult
from .types import Coordinate, MouseButton
from .exceptions import (
    MouseOperationError,
    FailSafeTriggeredError,
    CoordinateOutOfRangeError,
)
from .config import get_cua_config, CUAConfig


class MouseController:
    """鼠标控制�?""

    def __init__(self, config: Optional[CUAConfig] = None):
        self._config = config or get_cua_config()
        self._setup_pyautogui()

    def _setup_pyautogui(self) -> None:
        pyautogui.FAILSAFE = self._config.failsafe
        pyautogui.PAUSE = self._config.pause

    def _validate_coordinates(self, x: int, y: int) -> None:
        screen_width, screen_height = self._config.screen_size
        margin = self._config.safe_margin

        if x < margin or x > screen_width - margin:
            raise CoordinateOutOfRangeError(x, y, (screen_width, screen_height))
        if y < margin or y > screen_height - margin:
            raise CoordinateOutOfRangeError(x, y, (screen_width, screen_height))

    def _check_failsafe(self) -> bool:
        try:
            current_pos = pyautogui.position()
            screen_width, screen_height = self._config.screen_size
            if current_pos.x == 0 and current_pos.y == screen_height - 1:
                return True
            return False
        except Exception:
            return False

    def move_to(
        self, x: int, y: int, duration: Optional[float] = None
    ) -> OperationResult:
        if duration is None:
            duration = self._config.move_duration

        try:
            self._validate_coordinates(x, y)
            pyautogui.moveTo(x, y, duration=duration)
            return OperationResult.ok(
                message=f"鼠标已移动到坐标 ({x}, {y})",
                data=Coordinate(x, y),
            )
        except pyautogui.FailSafeException as e:
            raise FailSafeTriggeredError(pyautogui.position())
        except CoordinateOutOfRangeError:
            raise
        except Exception as e:
            raise MouseOperationError(
                message="鼠标移动失败",
                operation="move_to",
                details=str(e),
            )

    async def move_to_async(
        self, x: int, y: int, duration: Optional[float] = None
    ) -> OperationResult:
        return await asyncio.to_thread(self.move_to, x, y, duration)

    def move_relative(
        self, dx: int, dy: int, duration: Optional[float] = None
    ) -> OperationResult:
        if duration is None:
            duration = self._config.move_duration

        try:
            current = pyautogui.position()
            new_x = current.x + dx
            new_y = current.y + dy

            self._validate_coordinates(new_x, new_y)
            pyautogui.moveRel(dx, dy, duration=duration)

            return OperationResult.ok(
                message=f"鼠标已相对移�?({dx}, {dy})",
                data=Coordinate(new_x, new_y),
            )
        except pyautogui.FailSafeException as e:
            raise FailSafeTriggeredError(pyautogui.position())
        except CoordinateOutOfRangeError:
            raise
        except Exception as e:
            raise MouseOperationError(
                message="鼠标相对移动失败",
                operation="move_relative",
                details=str(e),
            )

    async def move_relative_async(
        self, dx: int, dy: int, duration: Optional[float] = None
    ) -> OperationResult:
        return await asyncio.to_thread(self.move_relative, dx, dy, duration)

    def click(
        self,
        x: Optional[int] = None,
        y: Optional[int] = None,
        button: MouseButton = MouseButton.LEFT,
        clicks: int = 1,
    ) -> OperationResult:
        try:
            if x is not None and y is not None:
                self._validate_coordinates(x, y)
                pyautogui.click(x, y, clicks=clicks, button=button.value)
                position = Coordinate(x, y)
            else:
                pyautogui.click(clicks=clicks, button=button.value)
                current = pyautogui.position()
                position = Coordinate(current.x, current.y)

            return OperationResult.ok(
                message=f"已执�?{clicks} �?{button.value} 点击",
                data=position,
            )
        except pyautogui.FailSafeException as e:
            raise FailSafeTriggeredError(pyautogui.position())
        except CoordinateOutOfRangeError:
            raise
        except Exception as e:
            raise MouseOperationError(
                message="鼠标点击失败",
                operation="click",
                details=str(e),
            )

    async def click_async(
        self,
        x: Optional[int] = None,
        y: Optional[int] = None,
        button: MouseButton = MouseButton.LEFT,
        clicks: int = 1,
    ) -> OperationResult:
        return await asyncio.to_thread(self.click, x, y, button, clicks)

    def double_click(
        self, x: Optional[int] = None, y: Optional[int] = None
    ) -> OperationResult:
        return self.click(x, y, button=MouseButton.LEFT, clicks=2)

    async def double_click_async(
        self, x: Optional[int] = None, y: Optional[int] = None
    ) -> OperationResult:
        return await asyncio.to_thread(self.double_click, x, y)

    def right_click(
        self, x: Optional[int] = None, y: Optional[int] = None
    ) -> OperationResult:
        return self.click(x, y, button=MouseButton.RIGHT, clicks=1)

    async def right_click_async(
        self, x: Optional[int] = None, y: Optional[int] = None
    ) -> OperationResult:
        return await asyncio.to_thread(self.right_click, x, y)

    def drag(
        self,
        start_x: int,
        start_y: int,
        end_x: int,
        end_y: int,
        duration: Optional[float] = None,
        button: MouseButton = MouseButton.LEFT,
    ) -> OperationResult:
        if duration is None:
            duration = self._config.drag_duration

        try:
            self._validate_coordinates(start_x, start_y)
            self._validate_coordinates(end_x, end_y)

            pyautogui.moveTo(start_x, start_y, duration=0.1)
            pyautogui.drag(
                end_x - start_x,
                end_y - start_y,
                duration=duration,
                button=button.value,
            )

            return OperationResult.ok(
                message=f"已执行拖拽操�? ({start_x}, {start_y}) -> ({end_x}, {end_y})",
                data={
                    "start": Coordinate(start_x, start_y),
                    "end": Coordinate(end_x, end_y),
                },
            )
        except pyautogui.FailSafeException as e:
            raise FailSafeTriggeredError(pyautogui.position())
        except CoordinateOutOfRangeError:
            raise
        except Exception as e:
            raise MouseOperationError(
                message="鼠标拖拽失败",
                operation="drag",
                details=str(e),
            )

    async def drag_async(
        self,
        start_x: int,
        start_y: int,
        end_x: int,
        end_y: int,
        duration: Optional[float] = None,
        button: MouseButton = MouseButton.LEFT,
    ) -> OperationResult:
        return await asyncio.to_thread(
            self.drag, start_x, start_y, end_x, end_y, duration, button
        )

    def scroll(
        self, clicks: int, x: Optional[int] = None, y: Optional[int] = None
    ) -> OperationResult:
        try:
            if x is not None and y is not None:
                self._validate_coordinates(x, y)
                pyautogui.scroll(clicks, x, y)
                position = Coordinate(x, y)
            else:
                pyautogui.scroll(clicks)
                current = pyautogui.position()
                position = Coordinate(current.x, current.y)

            direction = "向上" if clicks > 0 else "向下"
            return OperationResult.ok(
                message=f"已执行滚�?{direction} 滚动 {abs(clicks)} �?,
                data=position,
            )
        except pyautogui.FailSafeException as e:
            raise FailSafeTriggeredError(pyautogui.position())
        except CoordinateOutOfRangeError:
            raise
        except Exception as e:
            raise MouseOperationError(
                message="鼠标滚动失败",
                operation="scroll",
                details=str(e),
            )

    async def scroll_async(
        self, clicks: int, x: Optional[int] = None, y: Optional[int] = None
    ) -> OperationResult:
        return await asyncio.to_thread(self.scroll, clicks, x, y)

    def get_position(self) -> Coordinate:
        try:
            pos = pyautogui.position()
            return Coordinate(x=pos.x, y=pos.y)
        except Exception as e:
            raise MouseOperationError(
                message="获取鼠标位置失败",
                operation="get_position",
                details=str(e),
            )

    def is_failsafe_triggered(self) -> bool:
        return self._check_failsafe()

    def get_screen_size(self) -> tuple[int, int]:
        return self._config.screen_size

    def reset_position(self) -> OperationResult:
        try:
            screen_width, screen_height = self._config.screen_size
            center_x = screen_width // 2
            center_y = screen_height // 2
            return self.move_to(center_x, center_y, duration=0.1)
        except Exception as e:
            raise MouseOperationError(
                message="重置鼠标位置失败",
                operation="reset_position",
                details=str(e),
            )


_mouse_controller: Optional[MouseController] = None


def get_mouse_controller() -> MouseController:
    global _mouse_controller
    if _mouse_controller is None:
        _mouse_controller = MouseController()
    return _mouse_controller
