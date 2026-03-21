# -*- coding: utf-8 -*-
"""
CUA 模块异常定义
"""
from typing import Optional


class CUAError(Exception):
    def __init__(self, message: str, details: Optional[str] = None):
        self.message = message
        self.details = details
        super().__init__(self.message)

    def __str__(self) -> str:
        if self.details:
            return f"{self.message}: {self.details}"
        return self.message


class MouseOperationError(CUAError):
    def __init__(self, message: str, operation: Optional[str] = None, details: Optional[str] = None):
        self.operation = operation
        super().__init__(message, details)

    def __str__(self) -> str:
        parts = [self.message]
        if self.operation:
            parts.insert(0, f"[{self.operation}]")
        if self.details:
            parts.append(f"({self.details})")
        return " ".join(parts)


class FailSafeTriggeredError(MouseOperationError):
    def __init__(self, position: tuple[int, int]):
        super().__init__(
            message="FailSafe 已触发，操作被中止",
            operation="failsafe",
            details=f"鼠标位置: {position}"
        )


class CoordinateOutOfRangeError(MouseOperationError):
    def __init__(self, x: int, y: int, screen_size: tuple[int, int]):
        super().__init__(
            message="坐标超出屏幕范围",
            operation="coordinate_check",
            details=f"目标坐标: ({x}, {y}), 屏幕尺寸: {screen_size}"
        )


class KeyboardOperationError(CUAError):
    def __init__(self, message: str, operation: Optional[str] = None, details: Optional[str] = None):
        self.operation = operation
        super().__init__(message, details)

    def __str__(self) -> str:
        parts = [self.message]
        if self.operation:
            parts.insert(0, f"[{self.operation}]")
        if self.details:
            parts.append(f"({self.details})")
        return " ".join(parts)


class ScreenOperationError(CUAError):
    def __init__(self, message: str, operation: Optional[str] = None, details: Optional[str] = None):
        self.operation = operation
        super().__init__(message, details)

    def __str__(self) -> str:
        parts = [self.message]
        if self.operation:
            parts.insert(0, f"[{self.operation}]")
        if self.details:
            parts.append(f"({self.details})")
        return " ".join(parts)


class ScreenshotError(ScreenOperationError):
    def __init__(self, message: str, original_error: Optional[Exception] = None):
        details = str(original_error) if original_error else None
        super().__init__(message, operation="screenshot", details=details)


class MonitorNotFoundError(ScreenOperationError):
    def __init__(self, monitor_index: int, available_count: int):
        super().__init__(
            message=f"Monitor {monitor_index} not found",
            operation="monitor_selection",
            details=f"Available monitors: {available_count}"
        )


class WindowOperationError(CUAError):
    def __init__(self, message: str, operation: Optional[str] = None, details: Optional[str] = None):
        self.operation = operation
        super().__init__(message, details)

    def __str__(self) -> str:
        parts = [self.message]
        if self.operation:
            parts.insert(0, f"[{self.operation}]")
        if self.details:
            parts.append(f"({self.details})")
        return " ".join(parts)


class WindowNotFoundError(WindowOperationError):
    def __init__(self, window_id: str, details: Optional[str] = None):
        super().__init__(
            message=f"Window not found: {window_id}",
            operation="window_lookup",
            details=details
        )


class PermissionDeniedError(CUAError):
    def __init__(self, message: str, operation: Optional[str] = None, required_level: Optional[str] = None):
        self.operation = operation
        self.required_level = required_level
        super().__init__(message, details=required_level)

    def __str__(self) -> str:
        parts = [self.message]
        if self.operation:
            parts.insert(0, f"[{self.operation}]")
        if self.required_level:
            parts.append(f"(需要权限: {self.required_level})")
        return " ".join(parts)


class RateLimitExceededError(CUAError):
    def __init__(self, message: str, operation: Optional[str] = None, retry_after: Optional[int] = None):
        self.operation = operation
        self.retry_after = retry_after
        super().__init__(message, details=f"重试等待: {retry_after}秒" if retry_after else None)

    def __str__(self) -> str:
        parts = [self.message]
        if self.operation:
            parts.insert(0, f"[{self.operation}]")
        if self.retry_after:
            parts.append(f"(在 {self.retry_after} 秒后重试)")
        return " ".join(parts)


class EmergencyStopError(CUAError):
    def __init__(self, message: str = "紧急停止已触发"):
        super().__init__(message, details="所有操作已被中止")


class OCRError(CUAError):
    def __init__(self, message: str, operation: Optional[str] = None, details: Optional[str] = None):
        self.operation = operation
        super().__init__(message, details)

    def __str__(self) -> str:
        parts = [self.message]
        if self.operation:
            parts.insert(0, f"[{self.operation}]")
        if self.details:
            parts.append(f"({self.details})")
        return " ".join(parts)


class TesseractNotInstalledError(OCRError):
    def __init__(self, details: Optional[str] = None):
        super().__init__(
            message="Tesseract OCR 未安装或未配置",
            operation="tesseract_check",
            details=details or "请安装 Tesseract 并确保其已添加到系统 PATH"
        )


class OCRProcessingError(OCRError):
    def __init__(self, message: str, original_error: Optional[Exception] = None):
        details = str(original_error) if original_error else None
        super().__init__(message, operation="ocr_processing", details=details)


class TextNotFoundError(OCRError):
    def __init__(self, text: str, details: Optional[str] = None):
        super().__init__(
            message=f"未找到文本: {text}",
            operation="text_search",
            details=details
        )


class VisionError(CUAError):
    def __init__(self, message: str, operation: Optional[str] = None, details: Optional[str] = None):
        self.operation = operation
        super().__init__(message, details)

    def __str__(self) -> str:
        parts = [self.message]
        if self.operation:
            parts.insert(0, f"[{self.operation}]")
        if self.details:
            parts.append(f"({self.details})")
        return " ".join(parts)


class TemplateNotFoundError(VisionError):
    def __init__(self, threshold: float, max_match: float):
        super().__init__(
            message="Template not found",
            operation="template_match",
            details=f"Threshold: {threshold}, Max match: {max_match:.3f}"
        )


class ColorNotFoundError(VisionError):
    def __init__(self, color: tuple, tolerance: int):
        super().__init__(
            message="Color not found",
            operation="color_detect",
            details=f"Target color: {color}, Tolerance: {tolerance}"
        )
