"""
应用交互操作模块

提供程序启动/关闭、窗口管理和应用白名单管理功能
"""
from .launcher import (
    AppLauncher,
    LaunchResult,
    ProcessInfo,
    get_launcher,
)
from .whitelist import (
    DEFAULT_MACOS_APPS,
    DEFAULT_WINDOWS_APPS,
    AppWhitelist,
    WhitelistConfig,
    WhitelistEntry,
    get_whitelist,
)
from .window import (
    WindowInfo,
    WindowManager,
    WindowOperationResult,
    get_window_manager,
)

__all__ = [
    "AppWhitelist",
    "WhitelistEntry",
    "WhitelistConfig",
    "get_whitelist",
    "DEFAULT_WINDOWS_APPS",
    "DEFAULT_MACOS_APPS",
    "AppLauncher",
    "ProcessInfo",
    "LaunchResult",
    "get_launcher",
    "WindowManager",
    "WindowInfo",
    "WindowOperationResult",
    "get_window_manager",
]
