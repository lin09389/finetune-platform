"""
CUA 操作回放器模�?"""
import asyncio
import time
import json
from typing import List, Optional, Callable
from pathlib import Path
from enum import Enum

from .models import RecordedAction, ActionType, OperationResult, OperationType
from .mouse import MouseController, get_mouse_controller
from .keyboard import KeyboardController
from .types import MouseButton
from .recorder import ActionRecorder


class PlaybackMode(str, Enum):
    """回放模式枚举"""
    REALTIME = "realtime"
    FAST = "fast"


class ErrorHandlingMode(str, Enum):
    """错误处理模式枚举"""
    STOP = "stop"
    SKIP = "skip"
    RETRY = "retry"


class ActionPlayer:
    """操作回放�?""

    def __init__(
        self,
        mouse_controller: Optional[MouseController] = None,
        keyboard_controller: Optional[KeyboardController] = None,
    ):
        self._mouse = mouse_controller or get_mouse_controller()
        self._keyboard = keyboard_controller or KeyboardController()
        self._is_playing = False
        self._is_paused = False
        self._stop_requested = False
        self._speed = 1.0
        self._mode = PlaybackMode.REALTIME
        self._error_handling = ErrorHandlingMode.STOP
        self._retry_count = 3
        self._progress_callback: Optional[Callable[[int, int], None]] = None
        self._action_callback: Optional[Callable[[RecordedAction], None]] = None
        self._current_index = 0
        self._total_actions = 0
        self._pause_event = asyncio.Event()
        self._pause_event.set()

    def play(self, actions: List[RecordedAction]) -> OperationResult:
        return asyncio.run(self.play_async(actions))

    async def play_async(self, actions: List[RecordedAction]) -> OperationResult:
        if self._is_playing:
            return OperationResult.failure_result(
                operation_type=OperationType.SCREENSHOT,
                error="回放正在进行�?,
                message="无法开始新的回�?,
            )

        self._is_playing = True
        self._is_paused = False
        self._stop_requested = False
        self._current_index = 0
        self._total_actions = len(actions)
        self._pause_event.set()

        start_time = time.perf_counter()
        executed_count = 0
        failed_count = 0
        last_timestamp = 0.0

        try:
            for i, action in enumerate(actions):
                if self._stop_requested:
                    break

                await self._pause_event.wait()

                if self._stop_requested:
                    break

                self._current_index = i
                if self._progress_callback:
                    self._progress_callback(i, self._total_actions)

                if self._action_callback:
                    self._action_callback(action)

                if self._mode == PlaybackMode.REALTIME and i > 0:
                    time_diff = action.timestamp - last_timestamp
                    if time_diff > 0:
                        adjusted_delay = time_diff / self._speed
                        await asyncio.sleep(adjusted_delay)

                last_timestamp = action.timestamp

                success = await self._execute_action_with_retry(action)
                if success:
                    executed_count += 1
                else:
                    failed_count += 1
                    if self._error_handling == ErrorHandlingMode.STOP:
                        break

            duration_ms = (time.perf_counter() - start_time) * 1000

            return OperationResult.success_result(
                operation_type=OperationType.SCREENSHOT,
                message=f"回放完成: 执行 {executed_count} 个操�? 失败 {failed_count} �?,
                duration_ms=duration_ms,
                data={
                    "executed": executed_count,
                    "failed": failed_count,
                    "total": self._total_actions,
                    "stopped": self._stop_requested,
                },
            )
        except Exception as e:
            return OperationResult.failure_result(
                operation_type=OperationType.SCREENSHOT,
                error=str(e),
                message="回放过程中发生错�?,
            )
        finally:
            self._is_playing = False
            self._is_paused = False

    def stop(self) -> None:
        self._stop_requested = True
        self._is_playing = False
        self._is_paused = False
        self._pause_event.set()

    def pause(self) -> None:
        if self._is_playing and not self._is_paused:
            self._is_paused = True
            self._pause_event.clear()

    def resume(self) -> None:
        if self._is_playing and self._is_paused:
            self._is_paused = False
            self._pause_event.set()

    def is_playing(self) -> bool:
        return self._is_playing

    def is_paused(self) -> bool:
        return self._is_paused

    def set_speed(self, speed: float) -> None:
        if speed <= 0:
            raise ValueError("速度必须大于 0")
        self._speed = speed

    def get_speed(self) -> float:
        return self._speed

    def set_mode(self, mode: str) -> None:
        if mode == "realtime":
            self._mode = PlaybackMode.REALTIME
        elif mode == "fast":
            self._mode = PlaybackMode.FAST
        else:
            raise ValueError(f"未知的回放模�? {mode}")

    def get_mode(self) -> str:
        return self._mode.value

    def set_progress_callback(self, callback: Callable[[int, int], None]) -> None:
        self._progress_callback = callback

    def set_action_callback(self, callback: Callable[[RecordedAction], None]) -> None:
        self._action_callback = callback

    def set_error_handling(self, mode: str, retry_count: int = 3) -> None:
        if mode == "stop":
            self._error_handling = ErrorHandlingMode.STOP
        elif mode == "skip":
            self._error_handling = ErrorHandlingMode.SKIP
        elif mode == "retry":
            self._error_handling = ErrorHandlingMode.RETRY
            self._retry_count = retry_count
        else:
            raise ValueError(f"未知的错误处理模�? {mode}")

    def get_error_handling(self) -> str:
        return self._error_handling.value

    def play_from_file(self, filepath: str) -> OperationResult:
        return asyncio.run(self.play_from_file_async(filepath))

    async def play_from_file_async(self, filepath: str) -> OperationResult:
        try:
            actions = ActionRecorder.load_from_file(filepath)
            return await self.play_async(actions)
        except FileNotFoundError as e:
            return OperationResult.failure_result(
                operation_type=OperationType.SCREENSHOT,
                error=str(e),
                message="录制文件不存�?,
            )
        except json.JSONDecodeError as e:
            return OperationResult.failure_result(
                operation_type=OperationType.SCREENSHOT,
                error=str(e),
                message="录制文件格式错误",
            )
        except Exception as e:
            return OperationResult.failure_result(
                operation_type=OperationType.SCREENSHOT,
                error=str(e),
                message="加载录制文件失败",
            )

    async def _execute_action_with_retry(self, action: RecordedAction) -> bool:
        max_attempts = 1
        if self._error_handling == ErrorHandlingMode.RETRY:
            max_attempts = self._retry_count + 1

        for attempt in range(max_attempts):
            try:
                await self._execute_action(action)
                return True
            except Exception as e:
                if attempt < max_attempts - 1:
                    await asyncio.sleep(0.1 * (attempt + 1))
                else:
                    if self._error_handling == ErrorHandlingMode.SKIP:
                        return False
                    elif self._error_handling == ErrorHandlingMode.STOP:
                        raise
                    return False

        return False

    async def _execute_action(self, action: RecordedAction) -> None:
        action_type = action.action_type

        if action_type in (
            ActionType.MOUSE_MOVE,
            ActionType.MOUSE_CLICK,
            ActionType.MOUSE_DOUBLE_CLICK,
            ActionType.MOUSE_RIGHT_CLICK,
            ActionType.MOUSE_DRAG,
            ActionType.MOUSE_SCROLL,
        ):
            await self._execute_mouse_action(action)
        elif action_type in (
            ActionType.KEYBOARD_TYPE,
            ActionType.KEYBOARD_PRESS,
            ActionType.KEYBOARD_HOTKEY,
        ):
            await self._execute_keyboard_action(action)
        else:
            raise ValueError(f"未知的操作类�? {action_type}")

    async def _execute_mouse_action(self, action: RecordedAction) -> None:
        action_type = action.action_type
        data = action.data

        if action_type == ActionType.MOUSE_MOVE:
            x = data.get("x", 0)
            y = data.get("y", 0)
            await self._mouse.move_to_async(x, y)

        elif action_type == ActionType.MOUSE_CLICK:
            x = data.get("x")
            y = data.get("y")
            button_str = data.get("button", "left")
            button = MouseButton(button_str)
            clicks = data.get("clicks", 1)
            await self._mouse.click_async(x, y, button, clicks)

        elif action_type == ActionType.MOUSE_DOUBLE_CLICK:
            x = data.get("x")
            y = data.get("y")
            await self._mouse.double_click_async(x, y)

        elif action_type == ActionType.MOUSE_RIGHT_CLICK:
            x = data.get("x")
            y = data.get("y")
            await self._mouse.right_click_async(x, y)

        elif action_type == ActionType.MOUSE_DRAG:
            start_x = data.get("start_x", 0)
            start_y = data.get("start_y", 0)
            end_x = data.get("end_x", 0)
            end_y = data.get("end_y", 0)
            button_str = data.get("button", "left")
            button = MouseButton(button_str)
            await self._mouse.drag_async(start_x, start_y, end_x, end_y, button=button)

        elif action_type == ActionType.MOUSE_SCROLL:
            clicks = data.get("clicks", 0)
            x = data.get("x")
            y = data.get("y")
            await self._mouse.scroll_async(clicks, x, y)

    async def _execute_keyboard_action(self, action: RecordedAction) -> None:
        action_type = action.action_type
        data = action.data

        if action_type == ActionType.KEYBOARD_TYPE:
            text = data.get("text", "")
            interval = data.get("interval", 0.05)
            await self._keyboard.type_text_async(text, interval)

        elif action_type == ActionType.KEYBOARD_PRESS:
            key = data.get("key", "")
            if key:
                await self._keyboard.press_async(key)

        elif action_type == ActionType.KEYBOARD_HOTKEY:
            keys = data.get("keys", [])
            if keys:
                await self._keyboard.hotkey_async(*keys)

    def get_current_progress(self) -> tuple[int, int]:
        return self._current_index, self._total_actions


_action_player: Optional[ActionPlayer] = None


def get_action_player() -> ActionPlayer:
    global _action_player
    if _action_player is None:
        _action_player = ActionPlayer()
    return _action_player
