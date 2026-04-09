"""
跨平台适配模块

提供 Windows/macOS/Linux 跨平台兼容支持
"""
import os
import platform
from enum import Enum
from pathlib import Path
from typing import Any


class PlatformType(str, Enum):
    """平台类型"""
    WINDOWS = "windows"
    MACOS = "macos"
    LINUX = "linux"
    UNKNOWN = "unknown"


class PlatformDetector:
    """平台检测器"""

    _current_platform: PlatformType | None = None

    @classmethod
    def detect(cls) -> PlatformType:
        """检测当前平台"""
        if cls._current_platform:
            return cls._current_platform

        system = platform.system().lower()

        if system == "windows":
            cls._current_platform = PlatformType.WINDOWS
        elif system == "darwin":
            cls._current_platform = PlatformType.MACOS
        elif system == "linux":
            cls._current_platform = PlatformType.LINUX
        else:
            cls._current_platform = PlatformType.UNKNOWN

        return cls._current_platform

    @classmethod
    def is_windows(cls) -> bool:
        """是否为 Windows"""
        return cls.detect() == PlatformType.WINDOWS

    @classmethod
    def is_macos(cls) -> bool:
        """是否为 macOS"""
        return cls.detect() == PlatformType.MACOS

    @classmethod
    def is_linux(cls) -> bool:
        """是否为 Linux"""
        return cls.detect() == PlatformType.LINUX

    @classmethod
    def get_platform_info(cls) -> dict[str, Any]:
        """获取平台信息"""
        return {
            "platform": cls.detect().value,
            "system": platform.system(),
            "release": platform.release(),
            "version": platform.version(),
            "machine": platform.machine(),
            "processor": platform.processor(),
            "python_version": platform.python_version(),
        }


class PathConverter:
    """路径格式转换器"""

    @staticmethod
    def normalize(path: str) -> str:
        """标准化路径"""
        return str(Path(path))

    @staticmethod
    def to_posix(path: str) -> str:
        """转换为 POSIX 格式"""
        return Path(path).as_posix()

    @staticmethod
    def to_windows(path: str) -> str:
        """转换为 Windows 格式"""
        return str(Path(path)).replace("/", "\\")

    @staticmethod
    def is_absolute(path: str) -> bool:
        """是否为绝对路径"""
        return Path(path).is_absolute()

    @staticmethod
    def join(*parts: str) -> str:
        """连接路径"""
        return str(Path(*parts))

    @staticmethod
    def get_home() -> str:
        """获取用户主目录"""
        return str(Path.home())

    @staticmethod
    def get_temp() -> str:
        """获取临时目录"""
        return str(Path.cwd())


class PlatformAdapter:
    """平台适配器基类"""

    def __init__(self):
        self.platform_type = PlatformDetector.detect()

    def get_terminal_command(self) -> str:
        """获取终端命令"""
        raise NotImplementedError

    def get_file_manager(self) -> str:
        """获取文件管理器命令"""
        raise NotImplementedError

    def get_text_editor(self) -> str:
        """获取文本编辑器命令"""
        raise NotImplementedError

    def get_path_separator(self) -> str:
        """获取路径分隔符"""
        return os.sep

    def get_env_separator(self) -> str:
        """获取环境变量分隔符"""
        return ";" if self.platform_type == PlatformType.WINDOWS else ":"

    def get_null_device(self) -> str:
        """获取空设备"""
        return "NUL" if self.platform_type == PlatformType.WINDOWS else "/dev/null"


class WindowsAdapter(PlatformAdapter):
    """Windows 平台适配器"""

    def __init__(self):
        super().__init__()

    def get_terminal_command(self) -> str:
        """获取终端命令"""
        return "powershell"

    def get_file_manager(self) -> str:
        """获取文件管理器命令"""
        return "explorer"

    def get_text_editor(self) -> str:
        """获取文本编辑器命令"""
        return "notepad"


class MacOSAdapter(PlatformAdapter):
    """macOS 平台适配器"""

    def __init__(self):
        super().__init__()

    def get_terminal_command(self) -> str:
        """获取终端命令"""
        return "open -a Terminal"

    def get_file_manager(self) -> str:
        """获取文件管理器命令"""
        return "open"

    def get_text_editor(self) -> str:
        """获取文本编辑器命令"""
        return "open -a TextEdit"


class LinuxAdapter(PlatformAdapter):
    """Linux 平台适配器"""

    def __init__(self):
        super().__init__()
        self._terminal = self._detect_terminal()
        self._file_manager = self._detect_file_manager()

    def _detect_terminal(self) -> str:
        """检测终端"""
        terminals = ["gnome-terminal", "konsole", "xfce4-terminal", "xterm"]
        for term in terminals:
            if os.system(f"which {term} > /dev/null 2>&1") == 0:
                return term
        return "xterm"

    def _detect_file_manager(self) -> str:
        """检测文件管理器"""
        managers = ["nautilus", "dolphin", "thunar", "pcmanfm"]
        for fm in managers:
            if os.system(f"which {fm} > /dev/null 2>&1") == 0:
                return fm
        return "nautilus"

    def get_terminal_command(self) -> str:
        """获取终端命令"""
        return self._terminal

    def get_file_manager(self) -> str:
        """获取文件管理器命令"""
        return self._file_manager

    def get_text_editor(self) -> str:
        """获取文本编辑器命令"""
        return "gedit"


def get_platform_adapter() -> PlatformAdapter:
    """获取平台适配器"""
    platform_type = PlatformDetector.detect()

    if platform_type == PlatformType.WINDOWS:
        return WindowsAdapter()
    elif platform_type == PlatformType.MACOS:
        return MacOSAdapter()
    elif platform_type == PlatformType.LINUX:
        return LinuxAdapter()
    else:
        return PlatformAdapter()


_adapter: PlatformAdapter | None = None


def get_adapter() -> PlatformAdapter:
    """获取适配器单例"""
    global _adapter
    if _adapter is None:
        _adapter = get_platform_adapter()
    return _adapter
