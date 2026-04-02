"""
Agent 配置模块 - 安全白名单和黑名单
"""
import platform
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict


class ActionType(str, Enum):
    """操作类型枚举"""
    FILE_CREATE = "file_create"
    FILE_READ = "file_read"
    FILE_WRITE = "file_write"
    FILE_DELETE = "file_delete"
    FILE_LIST = "file_list"
    FILE_COPY = "file_copy"
    FILE_MOVE = "file_move"
    FILE_RENAME = "file_rename"
    FILE_SEARCH = "file_search"
    FILE_EXISTS = "file_exists"
    FILE_INFO = "file_info"

    DIR_CREATE = "dir_create"
    DIR_DELETE = "dir_delete"

    APP_OPEN = "app_open"
    APP_CLOSE = "app_close"
    URL_OPEN = "url_open"

    SCREENSHOT = "screenshot"
    SCREEN_INFO = "screen_info"
    MOUSE_CLICK = "mouse_click"
    MOUSE_DOUBLE_CLICK = "mouse_double_click"
    MOUSE_RIGHT_CLICK = "mouse_right_click"
    MOUSE_MOVE = "mouse_move"
    MOUSE_DRAG = "mouse_drag"
    MOUSE_SCROLL = "mouse_scroll"
    MOUSE_POSITION = "mouse_position"
    KEYBOARD_TYPE = "keyboard_type"
    KEYBOARD_PRESS = "keyboard_press"
    KEYBOARD_HOTKEY = "keyboard_hotkey"
    WINDOW_LIST = "window_list"
    WINDOW_ACTIVE = "window_active"
    WINDOW_ACTIVATE = "window_activate"
    WINDOW_CLOSE = "window_close"
    WINDOW_MINIMIZE = "window_minimize"
    WINDOW_MAXIMIZE = "window_maximize"
    OCR_RECOGNIZE = "ocr_recognize"
    OCR_FIND_TEXT = "ocr_find_text"
    RECORD_START = "record_start"
    RECORD_STOP = "record_stop"
    RECORD_PLAY = "record_play"

    PROCESS_LIST = "process_list"
    PROCESS_KILL = "process_kill"
    SERVICE_LIST = "service_list"
    SERVICE_START = "service_start"
    SERVICE_STOP = "service_stop"
    HARDWARE_MONITOR = "hardware_monitor"

    CLIPBOARD_READ = "clipboard_read"
    CLIPBOARD_WRITE = "clipboard_write"

    CONVERSATION = "conversation"


ALLOWED_APPS_WINDOWS: dict[str, str] = {
    "vscode": "code",
    "visual studio code": "code",
    "notepad": "notepad",
    "notepad++": "notepad++",
    "chrome": "chrome",
    "google chrome": "chrome",
    "edge": "msedge",
    "firefox": "firefox",
    "word": "winword",
    "excel": "excel",
    "powerpoint": "powerpnt",
    "cmd": "cmd",
    "powershell": "powershell",
    "explorer": "explorer",
    "calculator": "calc",
    "paint": "mspaint",
    "terminal": "wt",
    "windows terminal": "wt",
    "wechat": "WeChat",
    "微信": "WeChat",
    "qq": "QQ",
    "tim": "TIM",
    "dingtalk": "DingTalk",
    "钉钉": "DingTalk",
    "feishu": "Feishu",
    "飞书": "Feishu",
    "wechat work": "WXWork",
    "企业微信": "WXWork",
}

ALLOWED_APPS_MACOS: dict[str, str] = {
    "vscode": "Visual Studio Code",
    "visual studio code": "Visual Studio Code",
    "safari": "Safari",
    "chrome": "Google Chrome",
    "finder": "Finder",
    "terminal": "Terminal",
    "calculator": "Calculator",
    "wechat": "WeChat",
    "微信": "WeChat",
}

SYSTEM = platform.system()
ALLOWED_APPS = ALLOWED_APPS_WINDOWS if SYSTEM == "Windows" else ALLOWED_APPS_MACOS

USER_ALLOWED_APPS: dict[str, str] = {}

PENDING_APP_CONFIRMATIONS: dict[str, dict[str, Any]] = {}

FORBIDDEN_PATTERNS: list[str] = [
    r"\.\./",
    r"\.\.\\",
    r"/etc/",
    r"/sys/",
    r"/proc/",
    r"C:\\Windows\\System32",
    r"C:\\Windows\\SysWOW64",
    r"\.env$",
    r"\.pem$",
    r"\.key$",
    r"id_rsa",
    r"\.git/",
    r"__pycache__/",
]

ALLOWED_FILE_EXTENSIONS: set[str] = {
    ".py", ".js", ".ts", ".jsx", ".tsx", ".java", ".go", ".rs", ".c", ".cpp", ".h",
    ".json", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".conf",
    ".md", ".txt", ".rst", ".doc", ".docx",
    ".csv", ".xml", ".sql",
    ".html", ".css", ".scss", ".less",
    ".sh", ".bat", ".ps1",
}

READABLE_FILE_EXTENSIONS: set[str] = ALLOWED_FILE_EXTENSIONS | {
    ".log", ".pdf", ".png", ".jpg", ".jpeg", ".gif", ".svg",
}

DANGEROUS_ACTIONS: set[ActionType] = {
    ActionType.FILE_DELETE,
    ActionType.PROCESS_KILL,
    ActionType.SERVICE_STOP,
}


class SecurityConfig(BaseModel):
    """安全配置"""
    allow_localhost: bool = True
    allow_intranet: bool = False
    strict_path_check: bool = False
    allowed_directories: list[str] = []
    forbidden_directories: list[str] = []

    model_config = ConfigDict(extra="allow")


SECURITY_CONFIG = SecurityConfig()


class AgentConfig(BaseModel):
    """Agent 配置"""
    working_dir: Path
    enable_confirm: bool = True
    enable_audit: bool = True
    max_file_size: int = 10 * 1024 * 1024
    operation_timeout: int = 30
    security: SecurityConfig = SecurityConfig()

    model_config = ConfigDict(arbitrary_types_allowed=True)
