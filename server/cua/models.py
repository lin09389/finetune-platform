"""
CUA 数据模型定义模块
"""
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from .types import Coordinate, Region


class PermissionLevel(str, Enum):
    """权限级别枚举"""
    READ_ONLY = "read_only"
    INTERACTIVE = "interactive"
    FULL_CONTROL = "full_control"


class OperationType(str, Enum):
    """操作类型枚举"""
    SCREENSHOT = "screenshot"
    MOUSE_CLICK = "mouse_click"
    MOUSE_MOVE = "mouse_move"
    MOUSE_DRAG = "mouse_drag"
    MOUSE_SCROLL = "mouse_scroll"
    KEYBOARD_TYPE = "keyboard_type"
    KEYBOARD_HOTKEY = "keyboard_hotkey"
    WINDOW_FOCUS = "window_focus"
    WINDOW_MINIMIZE = "window_minimize"
    WINDOW_MAXIMIZE = "window_maximize"
    WINDOW_RESTORE = "window_restore"
    WINDOW_CLOSE = "window_close"
    WINDOW_MOVE = "window_move"
    WINDOW_RESIZE = "window_resize"
    WINDOW_LIST = "window_list"
    WINDOW_GET_RECT = "window_get_rect"


class ScreenshotResult(BaseModel):
    """截图结果模型"""
    image_data: bytes = Field(..., description="截图图像数据 (PNG 格式)")
    width: int = Field(..., ge=1, description="图像宽度")
    height: int = Field(..., ge=1, description="图像高度")
    region: Region | None = Field(default=None, description="截图区域")
    timestamp: datetime = Field(default_factory=datetime.now, description="截图时间")
    format: str = Field(default="png", description="图像格式")
    base64: str | None = Field(default=None, description="Base64 编码的图像数据")
    monitor_index: int = Field(default=0, ge=0, description="显示器索引")

    class Config:
        arbitrary_types_allowed = True


class MousePosition(BaseModel):
    """鼠标位置模型"""
    x: int = Field(..., ge=0, description="X 坐标")
    y: int = Field(..., ge=0, description="Y 坐标")
    screen_width: int | None = Field(default=None, ge=1, description="屏幕宽度")
    screen_height: int | None = Field(default=None, ge=1, description="屏幕高度")

    def to_coordinate(self) -> Coordinate:
        """转换为坐标类型"""
        return Coordinate(x=self.x, y=self.y)


class KeyboardInput(BaseModel):
    """键盘输入模型"""
    text: str | None = Field(default=None, description="输入文本")
    keys: list[str] | None = Field(default=None, description="按键列表")
    hotkey: list[str] | None = Field(default=None, description="快捷键组合")
    interval: float = Field(default=0.05, ge=0, description="按键间隔 (秒)")

    def is_text_input(self) -> bool:
        """是否为文本输入"""
        return self.text is not None

    def is_hotkey(self) -> bool:
        """是否为快捷键"""
        return self.hotkey is not None and len(self.hotkey) > 0


class WindowInfo(BaseModel):
    """窗口信息模型"""
    title: str = Field(..., description="窗口标题")
    handle: int | None = Field(default=None, description="窗口句柄")
    x: int = Field(default=0, description="窗口 X 坐标")
    y: int = Field(default=0, description="窗口 Y 坐标")
    width: int = Field(..., ge=1, description="窗口宽度")
    height: int = Field(..., ge=1, description="窗口高度")
    is_visible: bool = Field(default=True, description="是否可见")
    is_focused: bool = Field(default=False, description="是否聚焦")
    process_name: str | None = Field(default=None, description="进程名称")
    process_id: int | None = Field(default=None, description="进程 ID")

    def to_region(self) -> Region:
        """转换为区域类型"""
        return Region(x=self.x, y=self.y, width=self.width, height=self.height)


class OperationResult(BaseModel):
    """操作结果模型"""
    success: bool = Field(..., description="操作是否成功")
    operation_type: OperationType = Field(..., description="操作类型")
    message: str = Field(default="", description="结果消息")
    timestamp: datetime = Field(default_factory=datetime.now, description="操作时间")
    duration_ms: float | None = Field(default=None, description="操作耗时 (毫秒)")
    data: dict[str, Any] | None = Field(default=None, description="附加数据")
    error: str | None = Field(default=None, description="错误信息")

    @classmethod
    def success_result(
        cls,
        operation_type: OperationType,
        message: str = "Operation completed",
        data: dict[str, Any] | None = None,
        duration_ms: float | None = None
    ) -> "OperationResult":
        """创建成功结果"""
        return cls(
            success=True,
            operation_type=operation_type,
            message=message,
            data=data,
            duration_ms=duration_ms
        )

    @classmethod
    def failure_result(
        cls,
        operation_type: OperationType,
        error: str,
        message: str = "Operation failed"
    ) -> "OperationResult":
        """创建失败结果"""
        return cls(
            success=False,
            operation_type=operation_type,
            message=message,
            error=error
        )


class OperationRequest(BaseModel):
    """操作请求模型"""
    operation_type: OperationType = Field(..., description="操作类型")
    permission_level: PermissionLevel = Field(
        default=PermissionLevel.INTERACTIVE,
        description="所需权限级别"
    )
    parameters: dict[str, Any] = Field(default_factory=dict, description="操作参数")
    timeout: float | None = Field(default=30.0, ge=1, le=300, description="超时时间 (秒)")
    retry_count: int = Field(default=0, ge=0, le=3, description="重试次数")


class AuditLog(BaseModel):
    """审计日志模型"""
    operation_type: OperationType = Field(..., description="操作类型")
    permission_level: PermissionLevel = Field(..., description="权限级别")
    parameters: dict[str, Any] = Field(default_factory=dict, description="操作参数")
    result: bool = Field(..., description="操作结果")
    timestamp: datetime = Field(default_factory=datetime.now, description="操作时间")
    duration_ms: float | None = Field(default=None, description="操作耗时")
    error_message: str | None = Field(default=None, description="错误信息")
    session_id: str | None = Field(default=None, description="会话 ID")


class ActionType(str, Enum):
    """操作动作类型枚举"""
    MOUSE_MOVE = "mouse_move"
    MOUSE_CLICK = "mouse_click"
    MOUSE_DOUBLE_CLICK = "mouse_double_click"
    MOUSE_RIGHT_CLICK = "mouse_right_click"
    MOUSE_DRAG = "mouse_drag"
    MOUSE_SCROLL = "mouse_scroll"
    KEYBOARD_TYPE = "keyboard_type"
    KEYBOARD_PRESS = "keyboard_press"
    KEYBOARD_HOTKEY = "keyboard_hotkey"


class RecordedAction(BaseModel):
    """录制的操作动作模型"""
    action_type: ActionType = Field(..., description="操作类型")
    timestamp: float = Field(..., description="操作时间戳（秒）")
    data: dict[str, Any] = Field(default_factory=dict, description="操作数据")
    duration: float = Field(default=0.0, description="操作持续时间（秒）")

    class Config:
        arbitrary_types_allowed = True
