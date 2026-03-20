"""
CUA 类型定义模块
"""
from typing import NamedTuple
from enum import Enum


class Coordinate(NamedTuple):
    """坐标类型"""
    x: int
    y: int


class Region(NamedTuple):
    """区域类型"""
    x: int
    y: int
    width: int
    height: int


class MouseButton(Enum):
    """鼠标按钮枚举"""
    LEFT = "left"
    RIGHT = "right"
    MIDDLE = "middle"


class KeyCode:
    """键码类型 - 常用键码映射"""
    
    BACKSPACE = "\b"
    TAB = "\t"
    ENTER = "\n"
    RETURN = "\n"
    SHIFT = "\x01"
    CTRL = "\x02"
    ALT = "\x03"
    ESC = "\x1b"
    ESCAPE = "\x1b"
    SPACE = " "
    DELETE = "\x7f"
    
    F1 = "\x01\x01"
    F2 = "\x01\x02"
    F3 = "\x01\x03"
    F4 = "\x01\x04"
    F5 = "\x01\x05"
    F6 = "\x01\x06"
    F7 = "\x01\x07"
    F8 = "\x01\x08"
    F9 = "\x01\x09"
    F10 = "\x01\x0a"
    F11 = "\x01\x0b"
    F12 = "\x01\x0c"
    
    HOME = "\x01\x20"
    END = "\x01\x21"
    PAGE_UP = "\x01\x22"
    PAGE_DOWN = "\x01\x23"
    INSERT = "\x01\x24"
    
    UP = "\x01\x25"
    DOWN = "\x01\x26"
    LEFT = "\x01\x27"
    RIGHT = "\x01\x28"
    
    CAPS_LOCK = "\x01\x30"
    NUM_LOCK = "\x01\x31"
    SCROLL_LOCK = "\x01\x32"
    
    WIN = "\x01\x40"
    COMMAND = "\x01\x40"
    OPTION = "\x03"
    
    @classmethod
    def is_special_key(cls, key: str) -> bool:
        """判断是否为特殊键"""
        return key.startswith("\x01") or key in ["\b", "\t", "\n", "\x1b", "\x7f"]
    
    @classmethod
    def get_key_name(cls, key: str) -> str:
        """获取键名"""
        key_map = {
            cls.BACKSPACE: "Backspace",
            cls.TAB: "Tab",
            cls.ENTER: "Enter",
            cls.SHIFT: "Shift",
            cls.CTRL: "Ctrl",
            cls.ALT: "Alt",
            cls.ESC: "Esc",
            cls.SPACE: "Space",
            cls.DELETE: "Delete",
            cls.HOME: "Home",
            cls.END: "End",
            cls.PAGE_UP: "PageUp",
            cls.PAGE_DOWN: "PageDown",
            cls.INSERT: "Insert",
            cls.UP: "Up",
            cls.DOWN: "Down",
            cls.LEFT: "Left",
            cls.RIGHT: "Right",
            cls.CAPS_LOCK: "CapsLock",
            cls.NUM_LOCK: "NumLock",
            cls.SCROLL_LOCK: "ScrollLock",
            cls.WIN: "Win",
        }
        return key_map.get(key, key)
