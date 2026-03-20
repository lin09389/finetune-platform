"""
CUA 模块测试
"""
import pytest
from unittest.mock import Mock, patch
from datetime import datetime

from cua import (
    Coordinate,
    Region,
    MouseButton,
    PermissionLevel,
    OperationType,
)
from cua.models import (
    ScreenshotResult,
    OperationResult,
    WindowInfo,
)
from cua.types import MouseButton
from cua.safety import SafetyController, PermissionManager


class TestCoordinate:
    def test_coordinate_creation(self):
        coord = Coordinate(x=100, y=200)
        assert coord.x == 100
        assert coord.y == 200

    def test_coordinate_to_dict(self):
        coord = Coordinate(x=100, y=200)
        result = coord._asdict()
        assert result["x"] == 100
        assert result["y"] == 200


class TestRegion:
    def test_region_creation(self):
        region = Region(x=0, y=0, width=1920, height=1080)
        assert region.x == 0
        assert region.y == 0
        assert region.width == 1920
        assert region.height == 1080


class TestMouseButton:
    def test_mouse_button_values(self):
        assert MouseButton.LEFT.value == "left"
        assert MouseButton.RIGHT.value == "right"
        assert MouseButton.MIDDLE.value == "middle"


class TestPermissionLevel:
    def test_permission_level_values(self):
        assert PermissionLevel.READ_ONLY.value == "read_only"
        assert PermissionLevel.INTERACTIVE.value == "interactive"
        assert PermissionLevel.FULL_CONTROL.value == "full_control"


class TestOperationType:
    def test_operation_type_values(self):
        assert OperationType.SCREENSHOT.value == "screenshot"
        assert OperationType.MOUSE_CLICK.value == "mouse_click"
        assert OperationType.KEYBOARD_TYPE.value == "keyboard_type"


class TestScreenshotResult:
    def test_screenshot_result_creation(self):
        result = ScreenshotResult(
            image_data=b"test_image_data",
            width=1920,
            height=1080,
        )
        assert result.image_data == b"test_image_data"
        assert result.width == 1920
        assert result.height == 1080

    def test_screenshot_result_to_dict(self):
        result = ScreenshotResult(
            image_data=b"test_image_data",
            width=1920,
            height=1080,
        )
        data = result.model_dump()
        assert "image_data" in data
        assert data["width"] == 1920


class TestOperationResult:
    def test_operation_result_success(self):
        result = OperationResult(
            success=True,
            message="Operation completed",
            operation_type=OperationType.MOUSE_CLICK,
            data={"key": "value"},
        )
        assert result.success is True
        assert result.message == "Operation completed"

    def test_operation_result_failure(self):
        result = OperationResult(
            success=False,
            message="Operation failed",
            operation_type=OperationType.MOUSE_CLICK,
            error="Error message",
        )
        assert result.success is False
        assert result.error == "Error message"


class TestWindowInfo:
    def test_window_info_creation(self):
        info = WindowInfo(
            title="Test Window",
            handle=12345,
            x=0,
            y=0,
            width=800,
            height=600,
        )
        assert info.title == "Test Window"
        assert info.handle == 12345
        assert info.width == 800
        assert info.height == 600


class TestPermissionManager:
    def test_default_permission_level(self):
        manager = PermissionManager()
        assert manager.get_permission_level() == PermissionLevel.INTERACTIVE

    def test_set_permission_level(self):
        manager = PermissionManager()
        manager.set_permission_level(PermissionLevel.FULL_CONTROL)
        assert manager.get_permission_level() == PermissionLevel.FULL_CONTROL

    def test_check_permission_read_only(self):
        manager = PermissionManager()
        manager.set_permission_level(PermissionLevel.READ_ONLY)
        
        assert manager.check_permission(OperationType.SCREENSHOT) is True
        assert manager.check_permission(OperationType.MOUSE_CLICK) is False

    def test_check_permission_interactive(self):
        manager = PermissionManager()
        manager.set_permission_level(PermissionLevel.INTERACTIVE)
        
        assert manager.check_permission(OperationType.SCREENSHOT) is True
        assert manager.check_permission(OperationType.MOUSE_CLICK) is True


class TestSafetyController:
    def test_is_sensitive_operation(self):
        controller = SafetyController()
        
        assert controller.is_sensitive_operation(
            OperationType.KEYBOARD_TYPE,
            {"text": "format c:"}
        ) is True
        
        assert controller.is_sensitive_operation(
            OperationType.MOUSE_CLICK,
            {"x": 100, "y": 200}
        ) is False

    def test_enable_failsafe(self):
        controller = SafetyController()
        controller.enable_failsafe(True)
        assert controller.is_failsafe_enabled() is True
        
        controller.enable_failsafe(False)
        assert controller.is_failsafe_enabled() is False


class TestExceptions:
    def test_cua_error(self):
        from cua.exceptions import CUAError
        error = CUAError("Test error")
        assert str(error) == "Test error"

    def test_permission_denied_error(self):
        from cua.exceptions import PermissionDeniedError
        error = PermissionDeniedError("mouse_click")
        assert "mouse_click" in str(error)
