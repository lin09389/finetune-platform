"""
CUA 配置管理模块
"""
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List, Optional

from .models import PermissionLevel


class CUAConfig(BaseSettings):
    """CUA 配置�?""
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="CUA_",
        case_sensitive=False,
        extra="ignore"
    )
    
    enabled: bool = Field(default=True, description="是否启用 CUA 功能")
    permission_level: PermissionLevel = Field(
        default=PermissionLevel.INTERACTIVE,
        description="默认权限级别"
    )
    screenshot_quality: int = Field(
        default=85,
        ge=1,
        le=100,
        description="截图质量 (1-100)"
    )
    mouse_speed: float = Field(
        default=0.5,
        ge=0.1,
        le=1.0,
        description="鼠标移动速度 (0.1-1.0)"
    )
    keyboard_delay: float = Field(
        default=0.05,
        ge=0.0,
        le=1.0,
        description="键盘按键延迟 (�?"
    )
    operation_timeout: int = Field(
        default=30,
        ge=1,
        le=300,
        description="操作超时时间 (�?"
    )
    failsafe_enabled: bool = Field(
        default=True,
        description="是否启用故障安全 (移动鼠标到角落终�?"
    )
    audit_enabled: bool = Field(
        default=True,
        description="是否启用审计日志"
    )
    audit_log_path: Optional[str] = Field(
        default=None,
        description="审计日志路径"
    )
    max_screenshot_width: int = Field(
        default=1920,
        ge=640,
        le=4096,
        description="最大截图宽�?
    )
    max_screenshot_height: int = Field(
        default=1080,
        ge=480,
        le=2160,
        description="最大截图高�?
    )
    allowed_operations: List[str] = Field(
        default_factory=lambda: [
            "screenshot",
            "mouse_click",
            "mouse_move",
            "mouse_scroll",
            "keyboard_type",
            "keyboard_hotkey",
            "window_focus"
        ],
        description="允许的操作类型列�?
    )
    blocked_applications: List[str] = Field(
        default_factory=lambda: [],
        description="禁止操作的应用程序列�?
    )
    safe_mode: bool = Field(
        default=False,
        description="安全模式 (仅允许只读操�?"
    )
    failsafe: bool = Field(
        default=True,
        description="是否启用故障安全 (pyautogui FAILSAFE)"
    )
    pause: float = Field(
        default=0.1,
        ge=0.0,
        le=1.0,
        description="pyautogui PAUSE 参数"
    )
    move_duration: float = Field(
        default=0.3,
        ge=0.0,
        le=2.0,
        description="鼠标移动持续时间"
    )
    screen_size: tuple = Field(
        default=(2560, 1600),
        description="屏幕尺寸"
    )
    safe_margin: int = Field(
        default=10,
        ge=0,
        le=100,
        description="安全边距"
    )
    
    @field_validator('permission_level', mode='before')
    @classmethod
    def parse_permission_level(cls, v):
        if isinstance(v, str):
            return PermissionLevel(v.lower())
        return v
    
    @field_validator('allowed_operations', mode='before')
    @classmethod
    def parse_allowed_operations(cls, v):
        if isinstance(v, str):
            return [x.strip().lower() for x in v.split(',') if x.strip()]
        return v
    
    @field_validator('blocked_applications', mode='before')
    @classmethod
    def parse_blocked_applications(cls, v):
        if isinstance(v, str):
            return [x.strip().lower() for x in v.split(',') if x.strip()]
        return v
    
    def is_operation_allowed(self, operation_type: str) -> bool:
        """检查操作是否被允许"""
        if self.safe_mode:
            return operation_type.lower() == "screenshot"
        return operation_type.lower() in [op.lower() for op in self.allowed_operations]
    
    def is_application_blocked(self, application_name: str) -> bool:
        """检查应用程序是否被阻止"""
        if not application_name:
            return False
        return application_name.lower() in [app.lower() for app in self.blocked_applications]
    
    def get_effective_permission(self) -> PermissionLevel:
        """获取有效权限级别"""
        if self.safe_mode:
            return PermissionLevel.READ_ONLY
        return self.permission_level


_cua_config: Optional[CUAConfig] = None


def get_cua_config() -> CUAConfig:
    """获取 CUA 配置实例"""
    global _cua_config
    if _cua_config is None:
        _cua_config = CUAConfig()
    return _cua_config


def reload_cua_config() -> CUAConfig:
    """重新加载 CUA 配置"""
    global _cua_config
    _cua_config = CUAConfig()
    return _cua_config
