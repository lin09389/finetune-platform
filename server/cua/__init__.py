"""
CUA (Computer Use Agent) 模块
提供计算机操作自动化能力，包括截图、鼠标、键盘控制等
"""
from .config import CUAConfig, get_cua_config, reload_cua_config
from .exceptions import (
    ColorNotFoundError,
    CUAError,
    EmergencyStopError,
    FailSafeTriggeredError,
    KeyboardOperationError,
    MouseOperationError,
    OCRError,
    OCRProcessingError,
    PermissionDeniedError,
    RateLimitExceededError,
    ScreenOperationError,
    ScreenshotError,
    TemplateNotFoundError,
    TesseractNotInstalledError,
    TextNotFoundError,
    VisionError,
    WindowNotFoundError,
    WindowOperationError,
)
from .models import (
    AuditLog,
    KeyboardInput,
    MousePosition,
    OperationRequest,
    OperationResult,
    OperationType,
    PermissionLevel,
    ScreenshotResult,
    WindowInfo,
)
from .ocr import OCRRecognizer
from .recorder import (
    ActionRecorder,
    RecordedAction,
    RecorderAlreadyRunningError,
    RecorderError,
    RecorderNotRunningError,
)
from .safety import (
    PermissionManager,
    SafetyController,
    get_safety_controller,
    reset_safety_controller,
)
from .types import Coordinate, KeyCode, MouseButton, Region
from .vision import VisionRecognizer
from .window import WindowManager, get_window_manager

__all__ = [
    "Coordinate",
    "Region",
    "MouseButton",
    "KeyCode",
    "CUAError",
    "PermissionDeniedError",
    "RateLimitExceededError",
    "EmergencyStopError",
    "FailSafeTriggeredError",
    "MouseOperationError",
    "KeyboardOperationError",
    "ScreenOperationError",
    "ScreenshotError",
    "WindowOperationError",
    "WindowNotFoundError",
    "VisionError",
    "TemplateNotFoundError",
    "ColorNotFoundError",
    "PermissionLevel",
    "OperationType",
    "ScreenshotResult",
    "MousePosition",
    "KeyboardInput",
    "WindowInfo",
    "OperationResult",
    "OperationRequest",
    "AuditLog",
    "CUAConfig",
    "get_cua_config",
    "reload_cua_config",
    "SafetyController",
    "PermissionManager",
    "get_safety_controller",
    "reset_safety_controller",
    "WindowManager",
    "get_window_manager",
    "VisionRecognizer",
    "OCRRecognizer",
    "OCRError",
    "TesseractNotInstalledError",
    "OCRProcessingError",
    "TextNotFoundError",
    "ActionRecorder",
    "RecordedAction",
    "RecorderError",
    "RecorderAlreadyRunningError",
    "RecorderNotRunningError",
]
