"""
安全验证模块 - 防止命令注入和路径遍历
"""
import re
import os
from pathlib import Path
from typing import Optional, Tuple
from dataclasses import dataclass

from .config import (
    ALLOWED_APPS,
    FORBIDDEN_PATTERNS,
    ALLOWED_FILE_EXTENSIONS,
    READABLE_FILE_EXTENSIONS,
    DANGEROUS_ACTIONS,
    ActionType,
)


@dataclass
class ValidationResult:
    """验证结果"""
    is_valid: bool
    error: Optional[str] = None
    sanitized_value: Optional[str] = None


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
                    f"禁止访问工作目录外的文件"
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
        
        # 转换为小写匹配
        app_key = app_name.lower().strip()
        
        # 检查白名单
        if app_key not in ALLOWED_APPS:
            allowed_list = ", ".join(sorted(set(ALLOWED_APPS.keys())))
            return ValidationResult(
                False, 
                f"不允许打开此应用。允许的应用：{allowed_list}"
            )
        
        # 返回安全的可执行文件名
        return ValidationResult(
            True, 
            sanitized_value=ALLOWED_APPS[app_key]
        )
    
    def validate_url(self, url: str) -> ValidationResult:
        """
        验证 URL 安全性
        """
        if not url:
            return ValidationResult(False, "URL 不能为空")
        
        # 只允许 http/https 协议
        if not url.startswith(("http://", "https://")):
            return ValidationResult(False, "只允许 http/https 协议")
        
        # 禁止本地地址和内网地址（可选）
        forbidden_hosts = [
            "localhost",
            "127.0.0.1",
            "0.0.0.0",
            "192.168.",
            "10.",
            "172.16.",
        ]
        
        for host in forbidden_hosts:
            if host in url:
                return ValidationResult(
                    False, 
                    "禁止访问本地或内网地址"
                )
        
        return ValidationResult(True, sanitized_value=url)
    
    def is_dangerous_action(self, action: ActionType) -> bool:
        """检查是否为危险操作"""
        return action in DANGEROUS_ACTIONS
    
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
    
    def validate_delete(self, file_path: str) -> Tuple[bool, str]:
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