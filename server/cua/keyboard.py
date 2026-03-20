"""
CUA 键盘控制模块
"""
import asyncio
import time
from typing import Optional, List

import pyautogui
import pyperclip

from .config import get_cua_config
from .exceptions import KeyboardOperationError
from .models import OperationResult, OperationType


class KeyboardController:
    def __init__(self):
        self.config = get_cua_config()
        pyautogui.FAILSAFE = self.config.failsafe_enabled
        pyautogui.PAUSE = self.config.keyboard_delay

    def _execute_with_timing(
        self, operation: callable, operation_type: OperationType, operation_name: str
    ) -> OperationResult:
        start_time = time.perf_counter()
        try:
            result = operation()
            duration_ms = (time.perf_counter() - start_time) * 1000
            return OperationResult.success_result(
                operation_type=operation_type,
                message=f"{operation_name} completed successfully",
                duration_ms=duration_ms,
                data=result if result is not None else {},
            )
        except pyautogui.FailSafeException as e:
            duration_ms = (time.perf_counter() - start_time) * 1000
            raise KeyboardOperationError(
                message="FailSafe triggered",
                operation=operation_name,
                details=str(e),
            )
        except Exception as e:
            raise KeyboardOperationError(
                message=f"Failed to execute {operation_name}",
                operation=operation_name,
                details=str(e),
            )

    def _is_chinese_text(self, text: str) -> bool:
        for char in text:
            if "\u4e00" <= char <= "\u9fff":
                return True
        return False

    def type_text(self, text: str, interval: Optional[float] = None) -> OperationResult:
        interval = interval if interval is not None else self.config.keyboard_delay

        def _type():
            if self._is_chinese_text(text):
                pyperclip.copy(text)
                pyautogui.hotkey("ctrl", "v")
                if interval > 0:
                    time.sleep(interval)
            else:
                pyautogui.write(text, interval=interval)

        return self._execute_with_timing(
            _type, OperationType.KEYBOARD_TYPE, "type_text"
        )

    async def type_text_async(
        self, text: str, interval: Optional[float] = None
    ) -> OperationResult:
        return await asyncio.to_thread(self.type_text, text, interval)

    def press(self, key: str) -> OperationResult:
        def _press():
            pyautogui.press(key)

        return self._execute_with_timing(
            _press, OperationType.KEYBOARD_TYPE, f"press({key})"
        )

    async def press_async(self, key: str) -> OperationResult:
        return await asyncio.to_thread(self.press, key)

    def hotkey(self, *keys: str) -> OperationResult:
        def _hotkey():
            pyautogui.hotkey(*keys)

        keys_str = "+".join(keys)
        return self._execute_with_timing(
            _hotkey, OperationType.KEYBOARD_HOTKEY, f"hotkey({keys_str})"
        )

    async def hotkey_async(self, *keys: str) -> OperationResult:
        return await asyncio.to_thread(self.hotkey, *keys)

    def key_down(self, key: str) -> OperationResult:
        def _key_down():
            pyautogui.keyDown(key)

        return self._execute_with_timing(
            _key_down, OperationType.KEYBOARD_TYPE, f"key_down({key})"
        )

    async def key_down_async(self, key: str) -> OperationResult:
        return await asyncio.to_thread(self.key_down, key)

    def key_up(self, key: str) -> OperationResult:
        def _key_up():
            pyautogui.keyUp(key)

        return self._execute_with_timing(
            _key_up, OperationType.KEYBOARD_TYPE, f"key_up({key})"
        )

    async def key_up_async(self, key: str) -> OperationResult:
        return await asyncio.to_thread(self.key_up, key)

    def copy_to_clipboard(self, text: str) -> OperationResult:
        def _copy():
            pyperclip.copy(text)

        return self._execute_with_timing(
            _copy, OperationType.KEYBOARD_TYPE, "copy_to_clipboard"
        )

    async def copy_to_clipboard_async(self, text: str) -> OperationResult:
        return await asyncio.to_thread(self.copy_to_clipboard, text)

    def paste(self) -> OperationResult:
        def _paste():
            pyautogui.hotkey("ctrl", "v")

        return self._execute_with_timing(
            _paste, OperationType.KEYBOARD_HOTKEY, "paste"
        )

    async def paste_async(self) -> OperationResult:
        return await asyncio.to_thread(self.paste)

    def copy(self) -> OperationResult:
        def _copy():
            pyautogui.hotkey("ctrl", "c")

        return self._execute_with_timing(
            _copy, OperationType.KEYBOARD_HOTKEY, "copy"
        )

    async def copy_async(self) -> OperationResult:
        return await asyncio.to_thread(self.copy)

    def cut(self) -> OperationResult:
        def _cut():
            pyautogui.hotkey("ctrl", "x")

        return self._execute_with_timing(
            _cut, OperationType.KEYBOARD_HOTKEY, "cut"
        )

    async def cut_async(self) -> OperationResult:
        return await asyncio.to_thread(self.cut)

    def select_all(self) -> OperationResult:
        def _select_all():
            pyautogui.hotkey("ctrl", "a")

        return self._execute_with_timing(
            _select_all, OperationType.KEYBOARD_HOTKEY, "select_all"
        )

    async def select_all_async(self) -> OperationResult:
        return await asyncio.to_thread(self.select_all)

    def undo(self) -> OperationResult:
        def _undo():
            pyautogui.hotkey("ctrl", "z")

        return self._execute_with_timing(
            _undo, OperationType.KEYBOARD_HOTKEY, "undo"
        )

    async def undo_async(self) -> OperationResult:
        return await asyncio.to_thread(self.undo)

    def redo(self) -> OperationResult:
        def _redo():
            pyautogui.hotkey("ctrl", "y")

        return self._execute_with_timing(
            _redo, OperationType.KEYBOARD_HOTKEY, "redo"
        )

    async def redo_async(self) -> OperationResult:
        return await asyncio.to_thread(self.redo)

    def save(self) -> OperationResult:
        def _save():
            pyautogui.hotkey("ctrl", "s")

        return self._execute_with_timing(
            _save, OperationType.KEYBOARD_HOTKEY, "save"
        )

    async def save_async(self) -> OperationResult:
        return await asyncio.to_thread(self.save)

    def enter(self) -> OperationResult:
        return self.press("enter")

    async def enter_async(self) -> OperationResult:
        return await self.press_async("enter")

    def tab(self) -> OperationResult:
        return self.press("tab")

    async def tab_async(self) -> OperationResult:
        return await self.press_async("tab")

    def escape(self) -> OperationResult:
        return self.press("escape")

    async def escape_async(self) -> OperationResult:
        return await self.press_async("escape")

    def backspace(self) -> OperationResult:
        return self.press("backspace")

    async def backspace_async(self) -> OperationResult:
        return await self.press_async("backspace")

    def delete(self) -> OperationResult:
        return self.press("delete")

    async def delete_async(self) -> OperationResult:
        return await self.press_async("delete")

    def space(self) -> OperationResult:
        return self.press("space")

    async def space_async(self) -> OperationResult:
        return await self.press_async("space")

    def arrow_up(self) -> OperationResult:
        return self.press("up")

    async def arrow_up_async(self) -> OperationResult:
        return await self.press_async("up")

    def arrow_down(self) -> OperationResult:
        return self.press("down")

    async def arrow_down_async(self) -> OperationResult:
        return await self.press_async("down")

    def arrow_left(self) -> OperationResult:
        return self.press("left")

    async def arrow_left_async(self) -> OperationResult:
        return await self.press_async("left")

    def arrow_right(self) -> OperationResult:
        return self.press("right")

    async def arrow_right_async(self) -> OperationResult:
        return await self.press_async("right")

    def home(self) -> OperationResult:
        return self.press("home")

    async def home_async(self) -> OperationResult:
        return await self.press_async("home")

    def end(self) -> OperationResult:
        return self.press("end")

    async def end_async(self) -> OperationResult:
        return await self.press_async("end")

    def page_up(self) -> OperationResult:
        return self.press("pageup")

    async def page_up_async(self) -> OperationResult:
        return await self.press_async("pageup")

    def page_down(self) -> OperationResult:
        return self.press("pagedown")

    async def page_down_async(self) -> OperationResult:
        return await self.press_async("pagedown")

    def alt_tab(self) -> OperationResult:
        return self.hotkey("alt", "tab")

    async def alt_tab_async(self) -> OperationResult:
        return await self.hotkey_async("alt", "tab")

    def ctrl_f(self) -> OperationResult:
        return self.hotkey("ctrl", "f")

    async def ctrl_f_async(self) -> OperationResult:
        return await self.hotkey_async("ctrl", "f")

    def ctrl_p(self) -> OperationResult:
        return self.hotkey("ctrl", "p")

    async def ctrl_p_async(self) -> OperationResult:
        return await self.hotkey_async("ctrl", "p")

    def f5(self) -> OperationResult:
        return self.press("f5")

    async def f5_async(self) -> OperationResult:
        return await self.press_async("f5")

    def get_clipboard_content(self) -> OperationResult:
        def _get():
            content = pyperclip.paste()
            return {"content": content}

        return self._execute_with_timing(
            _get, OperationType.KEYBOARD_TYPE, "get_clipboard_content"
        )

    async def get_clipboard_content_async(self) -> OperationResult:
        return await asyncio.to_thread(self.get_clipboard_content)

    def type_keys(self, keys: List[str], interval: Optional[float] = None) -> OperationResult:
        interval = interval if interval is not None else self.config.keyboard_delay

        def _type_keys():
            for key in keys:
                pyautogui.press(key)
                if interval > 0:
                    time.sleep(interval)

        return self._execute_with_timing(
            _type_keys, OperationType.KEYBOARD_TYPE, "type_keys"
        )

    async def type_keys_async(
        self, keys: List[str], interval: Optional[float] = None
    ) -> OperationResult:
        return await asyncio.to_thread(self.type_keys, keys, interval)
