"""
CUA (Computer Use Agent) 模块
提供计算机操作自动化能力，包括截图、鼠标、键盘控制等
"""
from .types import Coordinate, Region, MouseButton, KeyCode
from .exceptions import (
    CUAError,
    PermissionDeniedError,
    RateLimitExceededError,
    EmergencyStopError,
    FailSafeTriggeredError,
    MouseOperationError,
    KeyboardOperationError,
    ScreenOperationError,
    ScreenshotError,
    WindowOperationError,
    WindowNotFoundError,
    VisionError,
    TemplateNotFoundError,
    ColorNotFoundError,
    OCRError,
    TesseractNotInstalledError,
    OCRProcessingError,
    TextNotFoundError,
)
from .models import (
    PermissionLevel,
    OperationType,
    ScreenshotResult,
    MousePosition,
    KeyboardInput,
    WindowInfo,
    OperationResult,
    OperationRequest,
    AuditLog,
)
from .config import CUAConfig, get_cua_config, reload_cua_config
from .safety import SafetyController, PermissionManager, get_safety_controller, reset_safety_controller
from .window import WindowManager, get_window_manager
from .vision import VisionRecognizer
from .ocr import OCRRecognizer
from .recorder import ActionRecorder, RecordedAction, RecorderError, RecorderAlreadyRunningError, RecorderNotRunningError

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
