"""
安全验证模块 - 防止命令注入和路径遍历
"""
import os
import re
from dataclasses import dataclass
from pathlib import Path

from .config import (
    ALLOWED_APPS,
    ALLOWED_FILE_EXTENSIONS,
    DANGEROUS_ACTIONS,
    FORBIDDEN_PATTERNS,
    READABLE_FILE_EXTENSIONS,
    ActionType,
)


@dataclass
class ValidationResult:
    """验证结果"""
    is_valid: bool
    error: str | None = None
    sanitized_value: str | None = None


class SecurityValidator:
    """安全验证器"""

    def __init__(self, working_dir: Path):
        self.working_dir = working_dir.resolve()

    def validate_path(
        self,
        file_path: str,
        action: ActionType = ActionType.FILE_READ
    ) -> ValidationResult:
        """
        验证文件路径安全性

        防止：
        1. 路径遍历攻击（../）
        2. 访问系统敏感目录
        3. 访问工作目录外的文件
        """
        if not file_path:
            return ValidationResult(False, "文件路径不能为空")

        # 1. 检查危险模式
        for pattern in FORBIDDEN_PATTERNS:
            if re.search(pattern, file_path, re.IGNORECASE):
                return ValidationResult(
                    False,
                    f"路径包含禁止的模式：{pattern}"
                )

        # 2. 规范化路径
        try:
            # 统一使用正斜杠
            normalized = file_path.replace("\\", "/")

            # 移除开头的斜杠（防止绝对路径）
            while normalized.startswith("/"):
                normalized = normalized[1:]

            # 构建完整路径
            if os.path.isabs(file_path):
                # 绝对路径：直接使用
                full_path = Path(file_path).resolve()
            else:
                # 相对路径：限制在工作目录内
                full_path = (self.working_dir / normalized).resolve()

        except Exception as e:
            return ValidationResult(False, f"路径格式错误：{str(e)}")

        # 3. 检查是否在工作目录内（对于相对路径）
        if not os.path.isabs(file_path):
            try:
                full_path.relative_to(self.working_dir)
            except ValueError:
                return ValidationResult(
                    False,
                    "禁止访问工作目录外的文件"
                )

        # 4. 检查文件扩展名
        ext = full_path.suffix.lower()
        if action in [ActionType.FILE_CREATE, ActionType.FILE_WRITE]:
            if ext and ext not in ALLOWED_FILE_EXTENSIONS:
                return ValidationResult(
                    False,
                    f"不允许创建/写入此类型文件：{ext}"
                )
        elif action == ActionType.FILE_READ:
            if ext and ext not in READABLE_FILE_EXTENSIONS:
                return ValidationResult(
                    False,
                    f"不允许读取此类型文件：{ext}"
                )

        return ValidationResult(True, sanitized_value=str(full_path))

    def validate_app(self, app_name: str) -> ValidationResult:
        """
        验证应用名称（白名单机制）

        防止命令注入攻击
        """
        if not app_name:
            return ValidationResult(False, "应用名称不能为空")

        app_key = app_name.lower().strip()

        from .config import USER_ALLOWED_APPS

        if app_key in USER_ALLOWED_APPS:
            return ValidationResult(True, sanitized_value=USER_ALLOWED_APPS[app_key])

        if app_key not in ALLOWED_APPS:
            for key, value in ALLOWED_APPS.items():
                if app_key in key or key in app_key:
                    return ValidationResult(True, sanitized_value=value)

            for key, value in USER_ALLOWED_APPS.items():
                if app_key in key or key in app_key:
                    return ValidationResult(True, sanitized_value=value)

            allowed_list = ", ".join(sorted(set(ALLOWED_APPS.keys()) | set(USER_ALLOWED_APPS.keys())))
            return ValidationResult(
                False,
                f"应用 '{app_name}' 不在允许列表中。允许的应用：{allowed_list}\n\n如需添加此应用，请确认应用名称是否正确，或联系管理员添加到白名单。"
            )

        return ValidationResult(
            True,
            sanitized_value=ALLOWED_APPS[app_key]
        )

    def check_app_permission(self, app_name: str) -> tuple[bool, str]:
        """
        检查应用权限，返回是否需要确认
        """
        from .config import ALLOWED_APPS, USER_ALLOWED_APPS

        app_key = app_name.lower().strip()

        if app_key in ALLOWED_APPS:
            return False, ""

        if app_key in USER_ALLOWED_APPS:
            return False, ""

        for key in ALLOWED_APPS.keys():
            if app_key in key or key in app_key:
                return False, ""

        return True, f"应用 '{app_name}' 不在默认白名单中，是否允许打开？"

    def validate_url(self, url: str, allow_localhost: bool = None) -> ValidationResult:
        """
        验证 URL 安全性

        Args:
            url: 要验证的 URL
            allow_localhost: 是否允许 localhost，None 时使用配置
        """
        if not url:
            return ValidationResult(False, "URL 不能为空")

        if not url.startswith(("http://", "https://")):
            return ValidationResult(False, "只允许 http/https 协议")

        from .config import SECURITY_CONFIG

        if allow_localhost is None:
            allow_localhost = SECURITY_CONFIG.allow_localhost

        if not allow_localhost:
            forbidden_hosts = [
                "localhost",
                "127.0.0.1",
                "0.0.0.0",
            ]

            if not SECURITY_CONFIG.allow_intranet:
                forbidden_hosts.extend([
                    "192.168.",
                    "10.",
                    "172.16.",
                ])

            for host in forbidden_hosts:
                if host in url:
                    return ValidationResult(
                        False,
                        f"禁止访问本地或内网地址：{host}。如需访问，请在安全配置中启用 allow_localhost 或 allow_intranet"
                    )

        return ValidationResult(True, sanitized_value=url)

    def is_dangerous_action(self, action: ActionType) -> bool:
        """检查是否为危险操作"""
        if action in DANGEROUS_ACTIONS:
            return True
        return action == ActionType.FILE_WRITE

    def validate_content(self, content: str, max_size: int = 10 * 1024 * 1024) -> ValidationResult:
        """
        验证文件内容
        """
        if len(content) > max_size:
            return ValidationResult(
                False,
                f"内容大小超过限制（{max_size // 1024 // 1024}MB）"
            )

        return ValidationResult(True)

    def validate_delete(self, file_path: str) -> tuple[bool, str]:
        """
        验证删除操作（额外安全检查）
        """
        # 检查路径
        result = self.validate_path(file_path, ActionType.FILE_DELETE)
        if not result.is_valid:
            return False, result.error

        full_path = Path(result.sanitized_value)

        # 检查文件是否存在
        if not full_path.exists():
            return False, f"文件不存在：{file_path}"

        # 检查是否为目录
        if full_path.is_dir():
            return False, "不能删除目录"

        # 检查是否为重要文件
        important_files = [
            "readme", "license", "changelog",
            "package.json", "requirements.txt",
            ".gitignore", "main.py", "app.py",
        ]

        name_lower = full_path.name.lower()
        for important in important_files:
            if important in name_lower:
                return False, f"禁止删除重要文件：{full_path.name}"

        return True, str(full_path)
