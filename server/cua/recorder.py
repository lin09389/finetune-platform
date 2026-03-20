"""
CUA 操作录制器模�?"""
import json
import threading
import time
from dataclasses import dataclass, asdict, field
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any, Callable

from pynput import mouse, keyboard

from .models import OperationResult, OperationType
from .exceptions import CUAError


@dataclass
class RecordedAction:
    action_type: str
    timestamp: float
    data: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RecordedAction":
        return cls(
            action_type=data["action_type"],
            timestamp=data["timestamp"],
            data=data["data"]
        )


class RecorderError(CUAError):
    def __init__(self, message: str, details: Optional[str] = None):
        super().__init__(message, details)


class RecorderAlreadyRunningError(RecorderError):
    def __init__(self):
        super().__init__("录制器已在运行中")


class RecorderNotRunningError(RecorderError):
    def __init__(self):
        super().__init__("录制器未运行")


class ActionRecorder:
    def __init__(self):
        self._actions: List[RecordedAction] = []
        self._lock = threading.Lock()
        self._is_recording = False
        self._is_paused = False
        self._start_time: Optional[float] = None
        self._mouse_listener: Optional[mouse.Listener] = None
        self._keyboard_listener: Optional[keyboard.Listener] = None
        self._filter: Optional[List[str]] = None
        self._min_interval: float = 0.0
        self._last_record_time: float = 0.0
        self._action_callback: Optional[Callable[[RecordedAction], None]] = None

    def start_recording(self) -> None:
        with self._lock:
            if self._is_recording:
                raise RecorderAlreadyRunningError()

            self._actions.clear()
            self._is_recording = True
            self._is_paused = False
            self._start_time = time.time()
            self._last_record_time = 0.0

        self._mouse_listener = mouse.Listener(
            on_move=self._on_mouse_move,
            on_click=self._on_mouse_click,
            on_scroll=self._on_mouse_scroll
        )
        self._keyboard_listener = keyboard.Listener(
            on_press=self._on_key_press,
            on_release=self._on_key_release
        )

        self._mouse_listener.start()
        self._keyboard_listener.start()

    def stop_recording(self) -> List[RecordedAction]:
        with self._lock:
            if not self._is_recording:
                raise RecorderNotRunningError()

            self._is_recording = False
            self._is_paused = False

        if self._mouse_listener:
            self._mouse_listener.stop()
            self._mouse_listener = None

        if self._keyboard_listener:
            self._keyboard_listener.stop()
            self._keyboard_listener = None

        with self._lock:
            return list(self._actions)

    def pause_recording(self) -> None:
        with self._lock:
            if not self._is_recording:
                raise RecorderNotRunningError()
            self._is_paused = True

    def resume_recording(self) -> None:
        with self._lock:
            if not self._is_recording:
                raise RecorderNotRunningError()
            self._is_paused = False

    def is_recording(self) -> bool:
        with self._lock:
            return self._is_recording

    def is_paused(self) -> bool:
        with self._lock:
            return self._is_paused

    def _should_record(self, action_type: str) -> bool:
        current_time = time.time()

        if self._filter is not None and action_type not in self._filter:
            return False

        if self._min_interval > 0:
            if current_time - self._last_record_time < self._min_interval:
                return False

        self._last_record_time = current_time
        return True

    def _record_action(self, action_type: str, data: Dict[str, Any]) -> None:
        with self._lock:
            if not self._is_recording or self._is_paused:
                return

        if not self._should_record(action_type):
            return

        timestamp = time.time() - (self._start_time or 0)
        action = RecordedAction(
            action_type=action_type,
            timestamp=timestamp,
            data=data
        )

        with self._lock:
            self._actions.append(action)

        if self._action_callback:
            self._action_callback(action)

    def _on_mouse_move(self, x: int, y: int) -> None:
        self._record_action("mouse_move", {"x": x, "y": y})

    def _on_mouse_click(self, x: int, y: int, button: mouse.Button, pressed: bool) -> None:
        button_name = str(button).replace("Button.", "")
        self._record_action("mouse_click", {
            "x": x,
            "y": y,
            "button": button_name,
            "pressed": pressed
        })

    def _on_mouse_scroll(self, x: int, y: int, dx: int, dy: int) -> None:
        self._record_action("mouse_scroll", {
            "x": x,
            "y": y,
            "dx": dx,
            "dy": dy
        })

    def _on_key_press(self, key) -> None:
        key_data = self._parse_key(key)
        self._record_action("key_press", key_data)

    def _on_key_release(self, key) -> None:
        key_data = self._parse_key(key)
        self._record_action("key_release", key_data)

    def _parse_key(self, key) -> Dict[str, Any]:
        if isinstance(key, keyboard.KeyCode):
            return {
                "type": "char",
                "char": key.char if key.char else None,
                "vk": key.vk
            }
        elif isinstance(key, keyboard.Key):
            return {
                "type": "special",
                "name": key.name,
                "value": str(key)
            }
        else:
            return {
                "type": "unknown",
                "value": str(key)
            }

    def get_actions(self) -> List[RecordedAction]:
        with self._lock:
            return list(self._actions)

    def clear_actions(self) -> None:
        with self._lock:
            self._actions.clear()

    def get_action_count(self) -> int:
        with self._lock:
            return len(self._actions)

    def save_to_file(self, filepath: str) -> None:
        with self._lock:
            actions_data = [action.to_dict() for action in self._actions]

        save_data = {
            "version": "1.0",
            "recorded_at": datetime.now().isoformat(),
            "action_count": len(actions_data),
            "actions": actions_data
        }

        path = Path(filepath)
        path.parent.mkdir(parents=True, exist_ok=True)

        with open(path, "w", encoding="utf-8") as f:
            json.dump(save_data, f, ensure_ascii=False, indent=2)

    def load_from_file(self, filepath: str) -> List[RecordedAction]:
        path = Path(filepath)

        if not path.exists():
            raise RecorderError(f"文件不存�? {filepath}")

        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        actions = [RecordedAction.from_dict(action_data) for action_data in data.get("actions", [])]

        with self._lock:
            self._actions = actions

        return actions

    def set_filter(self, action_types: Optional[List[str]]) -> None:
        with self._lock:
            self._filter = action_types

    def set_min_interval(self, interval: float) -> None:
        with self._lock:
            self._min_interval = max(0.0, interval)

    def set_action_callback(self, callback: Optional[Callable[[RecordedAction], None]]) -> None:
        with self._lock:
            self._action_callback = callback

    def get_statistics(self) -> Dict[str, Any]:
        with self._lock:
            if not self._actions:
                return {
                    "total_actions": 0,
                    "duration": 0.0,
                    "action_types": {},
                    "average_interval": 0.0
                }

            action_types: Dict[str, int] = {}
            for action in self._actions:
                action_types[action.action_type] = action_types.get(action.action_type, 0) + 1

            duration = self._actions[-1].timestamp - self._actions[0].timestamp if len(self._actions) > 1 else 0.0

            intervals = []
            for i in range(1, len(self._actions)):
                intervals.append(self._actions[i].timestamp - self._actions[i - 1].timestamp)

            average_interval = sum(intervals) / len(intervals) if intervals else 0.0

            return {
                "total_actions": len(self._actions),
                "duration": duration,
                "action_types": action_types,
                "average_interval": average_interval
            }

    def export_for_replay(self) -> List[Dict[str, Any]]:
        with self._lock:
            return [
                {
                    "action": action.action_type,
                    "delay": action.timestamp,
                    "params": action.data
                }
                for action in self._actions
            ]

    def filter_by_time_range(self, start_time: float, end_time: float) -> List[RecordedAction]:
        with self._lock:
            return [
                action for action in self._actions
                if start_time <= action.timestamp <= end_time
            ]

    def filter_by_type(self, action_type: str) -> List[RecordedAction]:
        with self._lock:
            return [action for action in self._actions if action.action_type == action_type]

    def compress_mouse_moves(self, threshold: float = 0.01) -> None:
        with self._lock:
            if len(self._actions) < 2:
                return

            compressed: List[RecordedAction] = []
            last_move: Optional[RecordedAction] = None

            for action in self._actions:
                if action.action_type == "mouse_move":
                    if last_move is None:
                        last_move = action
                    else:
                        time_diff = action.timestamp - last_move.timestamp
                        if time_diff >= threshold:
                            compressed.append(last_move)
                            last_move = action
                else:
                    if last_move is not None:
                        compressed.append(last_move)
                        last_move = None
                    compressed.append(action)

            if last_move is not None:
                compressed.append(last_move)

            self._actions = compressed
