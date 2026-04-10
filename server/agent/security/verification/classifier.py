"""
敏感操作分类器
"""
from dataclasses import dataclass, field
from enum import Enum


class SensitivityLevel(str, Enum):
    """敏感级别"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class SensitiveOperation:
    """敏感操作定义"""
    operation: str
    category: str
    sensitivity_level: SensitivityLevel
    description: str
    requires_verification: bool = True
    verification_types: list[str] = field(default_factory=lambda: ["password"])
    cooldown_seconds: int = 300
    max_attempts: int = 3


class SensitiveOperationClassifier:
    """敏感操作分类器"""

    SENSITIVE_OPERATIONS: dict[str, SensitiveOperation] = {
        "file_delete": SensitiveOperation(
            operation="file_delete",
            category="file_destruction",
            sensitivity_level=SensitivityLevel.HIGH,
            description="删除文件",
            verification_types=["password", "two_factor"],
            cooldown_seconds=60,
        ),
        "batch_delete": SensitiveOperation(
            operation="batch_delete",
            category="file_destruction",
            sensitivity_level=SensitivityLevel.CRITICAL,
            description="批量删除文件",
            verification_types=["two_factor", "admin_approval"],
            cooldown_seconds=300,
        ),
        "directory_delete": SensitiveOperation(
            operation="directory_delete",
            category="file_destruction",
            sensitivity_level=SensitivityLevel.HIGH,
            description="删除目录",
            verification_types=["password", "two_factor"],
            cooldown_seconds=120,
        ),
        "process_kill": SensitiveOperation(
            operation="process_kill",
            category="process_control",
            sensitivity_level=SensitivityLevel.MEDIUM,
            description="终止进程",
            verification_types=["password"],
            cooldown_seconds=30,
        ),
        "service_stop": SensitiveOperation(
            operation="service_stop",
            category="system_modification",
            sensitivity_level=SensitivityLevel.HIGH,
            description="停止服务",
            verification_types=["two_factor", "admin_approval"],
            cooldown_seconds=120,
        ),
        "service_restart": SensitiveOperation(
            operation="service_restart",
            category="system_modification",
            sensitivity_level=SensitivityLevel.MEDIUM,
            description="重启服务",
            verification_types=["password"],
            cooldown_seconds=60,
        ),
        "environment_write": SensitiveOperation(
            operation="environment_write",
            category="system_modification",
            sensitivity_level=SensitivityLevel.MEDIUM,
            description="修改环境变量",
            verification_types=["password"],
            cooldown_seconds=60,
        ),
        "admin_operation": SensitiveOperation(
            operation="admin_operation",
            category="privilege_escalation",
            sensitivity_level=SensitivityLevel.CRITICAL,
            description="管理员操作",
            verification_types=["two_factor", "admin_approval"],
            cooldown_seconds=600,
        ),
        "role_manage": SensitiveOperation(
            operation="role_manage",
            category="privilege_escalation",
            sensitivity_level=SensitivityLevel.CRITICAL,
            description="角色管理",
            verification_types=["two_factor", "admin_approval"],
            cooldown_seconds=300,
        ),
        "audit_export": SensitiveOperation(
            operation="audit_export",
            category="security_related",
            sensitivity_level=SensitivityLevel.MEDIUM,
            description="导出审计日志",
            verification_types=["password"],
            cooldown_seconds=60,
        ),
        "config_modify": SensitiveOperation(
            operation="config_modify",
            category="security_related",
            sensitivity_level=SensitivityLevel.HIGH,
            description="修改安全配置",
            verification_types=["two_factor"],
            cooldown_seconds=300,
        ),
    }

    SENSITIVE_PATHS: set[str] = {
        "/etc/",
        "/root/",
        "/sys/",
        "/proc/",
        "C:\\Windows\\System32",
        "C:\\Windows\\SysWOW64",
        "~/.ssh/",
        "~/.gnupg/",
    }

    SENSITIVE_EXTENSIONS: set[str] = {
        ".env",
        ".pem",
        ".key",
        ".p12",
        ".pfx",
        "id_rsa",
        ".git/",
    }

    def __init__(self):
        self._custom_operations: dict[str, SensitiveOperation] = {}

    def classify(self, operation: str, params: dict | None = None) -> SensitiveOperation | None:
        """分类操作"""
        all_operations = {**self.SENSITIVE_OPERATIONS, **self._custom_operations}

        if operation in all_operations:
            return all_operations[operation]

        if params:
            path = params.get("path", "") or params.get("file_path", "")
            if self._is_sensitive_path(path):
                return SensitiveOperation(
                    operation=operation,
                    category="sensitive_path",
                    sensitivity_level=SensitivityLevel.HIGH,
                    description=f"访问敏感路径: {path}",
                    verification_types=["password", "two_factor"],
                )

        return None

    def is_sensitive(self, operation: str, params: dict | None = None) -> bool:
        """判断是否为敏感操作"""
        return self.classify(operation, params) is not None

    def requires_verification(self, operation: str, params: dict | None = None) -> bool:
        """判断是否需要验证"""
        sensitive_op = self.classify(operation, params)
        return sensitive_op.requires_verification if sensitive_op else False

    def get_verification_types(self, operation: str, params: dict | None = None) -> list[str]:
        """获取所需验证类型"""
        sensitive_op = self.classify(operation, params)
        return sensitive_op.verification_types if sensitive_op else []

    def get_sensitivity_level(self, operation: str, params: dict | None = None) -> SensitivityLevel:
        """获取敏感级别"""
        sensitive_op = self.classify(operation, params)
        return sensitive_op.sensitivity_level if sensitive_op else SensitivityLevel.LOW

    def _is_sensitive_path(self, path: str) -> bool:
        """判断是否为敏感路径"""
        if not path:
            return False

        path_lower = path.lower()

        for sensitive_path in self.SENSITIVE_PATHS:
            if sensitive_path.lower() in path_lower:
                return True

        return any(path_lower.endswith(ext.lower()) for ext in self.SENSITIVE_EXTENSIONS)

    def register_sensitive_operation(self, operation: SensitiveOperation) -> None:
        """注册自定义敏感操作"""
        self._custom_operations[operation.operation] = operation

    def unregister_sensitive_operation(self, operation: str) -> bool:
        """注销敏感操作"""
        if operation in self._custom_operations:
            del self._custom_operations[operation]
            return True
        return False

    def get_all_sensitive_operations(self) -> dict[str, SensitiveOperation]:
        """获取所有敏感操作"""
        return {**self.SENSITIVE_OPERATIONS, **self._custom_operations}

    def get_operations_by_category(self, category: str) -> list[SensitiveOperation]:
        """按类别获取敏感操作"""
        all_ops = self.get_all_sensitive_operations()
        return [op for op in all_ops.values() if op.category == category]

    def get_operations_by_level(self, level: SensitivityLevel) -> list[SensitiveOperation]:
        """按敏感级别获取操作"""
        all_ops = self.get_all_sensitive_operations()
        return [op for op in all_ops.values() if op.sensitivity_level == level]
