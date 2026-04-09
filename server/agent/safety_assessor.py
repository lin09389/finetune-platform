"""
安全操作判断服务
统一管理所有操作的安全级别判断
"""
import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any

from agent.config import ActionType

logger = logging.getLogger(__name__)


class SafetyLevel(str, Enum):
    """安全级别"""
    SAFE = "safe"
    CAUTION = "caution"
    DANGEROUS = "dangerous"
    FORBIDDEN = "forbidden"


@dataclass
class SafetyAssessment:
    """安全评估结果"""
    level: SafetyLevel
    is_safe: bool
    requires_confirmation: bool
    reason: str
    suggestions: list = None

    def __post_init__(self):
        if self.suggestions is None:
            self.suggestions = []


SAFE_ACTIONS: set[ActionType] = {
    ActionType.FILE_READ,
    ActionType.FILE_LIST,
    ActionType.SCREENSHOT,
    ActionType.SCREEN_INFO,
    ActionType.MOUSE_POSITION,
    ActionType.WINDOW_LIST,
    ActionType.WINDOW_ACTIVE,
    ActionType.OCR_RECOGNIZE,
    ActionType.OCR_FIND_TEXT,
    ActionType.RECORD_START,
    ActionType.RECORD_STOP,
}

CAUTION_ACTIONS: set[ActionType] = {
    ActionType.FILE_CREATE,
    ActionType.FILE_WRITE,
    ActionType.APP_OPEN,
    ActionType.URL_OPEN,
    ActionType.MOUSE_MOVE,
    ActionType.MOUSE_SCROLL,
    ActionType.KEYBOARD_TYPE,
    ActionType.KEYBOARD_PRESS,
    ActionType.WINDOW_ACTIVATE,
    ActionType.WINDOW_MINIMIZE,
    ActionType.WINDOW_MAXIMIZE,
    ActionType.RECORD_PLAY,
}

DANGEROUS_ACTIONS: set[ActionType] = {
    ActionType.FILE_DELETE,
    ActionType.FILE_COPY,
    ActionType.FILE_MOVE,
    ActionType.MOUSE_CLICK,
    ActionType.MOUSE_DRAG,
    ActionType.KEYBOARD_HOTKEY,
    ActionType.WINDOW_CLOSE,
    ActionType.PROCESS_KILL,
    ActionType.SERVICE_STOP,
}

FORBIDDEN_ACTIONS: set[ActionType] = {
    ActionType.SERVICE_START,
}

DANGEROUS_FILE_EXTENSIONS: set[str] = {
    ".exe", ".dll", ".so", ".dylib",
    ".bat", ".cmd", ".ps1", ".vbs", ".vbe",
    ".msi", ".reg", ".sh",
    ".jar", ".war", ".ear",
    ".deb", ".rpm",
}

SENSITIVE_FILE_PATTERNS: set[str] = {
    ".env", ".pem", ".key", ".p12", ".pfx",
    "id_rsa", "id_dsa", "id_ecdsa", "id_ed25519",
    ".git", ".svn", ".hg",
    "credentials", "secrets", "password",
    "config.local", "settings.local",
}

DANGEROUS_URL_PATTERNS: set[str] = {
    "localhost", "127.0.0.1", "0.0.0.0",
    "192.168.", "10.", "172.16.", "172.17.", "172.18.",
    "172.19.", "172.20.", "172.21.", "172.22.", "172.23.",
    "172.24.", "172.25.", "172.26.", "172.27.", "172.28.",
    "172.29.", "172.30.", "172.31.",
    "file://", "ftp://",
}


class SafetyAssessor:
    """
    安全评估器

    统一评估所有操作的安全级别
    """

    def __init__(self):
        self._confirmation_callback = None

    def set_confirmation_callback(self, callback):
        """设置确认回调"""
        self._confirmation_callback = callback

    def assess(self, action: ActionType, params: dict[str, Any]) -> SafetyAssessment:
        """
        评估操作安全级别

        Args:
            action: 操作类型
            params: 操作参数

        Returns:
            SafetyAssessment: 安全评估结果
        """
        if action in FORBIDDEN_ACTIONS:
            return SafetyAssessment(
                level=SafetyLevel.FORBIDDEN,
                is_safe=False,
                requires_confirmation=False,
                reason=f"操作 {action.value} 被禁止执行",
                suggestions=["该操作类型已被系统禁止，无法执行"]
            )

        if action in DANGEROUS_ACTIONS:
            return self._assess_dangerous_action(action, params)

        if action in CAUTION_ACTIONS:
            return self._assess_caution_action(action, params)

        if action in SAFE_ACTIONS:
            return SafetyAssessment(
                level=SafetyLevel.SAFE,
                is_safe=True,
                requires_confirmation=False,
                reason=f"操作 {action.value} 是安全的只读操作"
            )

        return SafetyAssessment(
            level=SafetyLevel.CAUTION,
            is_safe=True,
            requires_confirmation=True,
            reason=f"操作 {action.value} 安全级别未知，需要确认"
        )

    def _assess_dangerous_action(self, action: ActionType, params: dict[str, Any]) -> SafetyAssessment:
        """评估危险操作"""
        if action == ActionType.FILE_DELETE:
            file_path = params.get("path", params.get("file_path", ""))
            return SafetyAssessment(
                level=SafetyLevel.DANGEROUS,
                is_safe=False,
                requires_confirmation=True,
                reason=f"删除文件操作需要确认: {file_path}",
                suggestions=[
                    "文件将被移动到回收站，可以从 ~/.finetune_recycle_bin 恢复",
                    "请确认您要删除正确的文件"
                ]
            )

        if action == ActionType.MOUSE_CLICK:
            return SafetyAssessment(
                level=SafetyLevel.DANGEROUS,
                is_safe=False,
                requires_confirmation=True,
                reason="鼠标点击操作可能影响当前活动窗口",
                suggestions=[
                    "请确保目标位置正确",
                    "建议先截图确认目标位置"
                ]
            )

        if action == ActionType.KEYBOARD_HOTKEY:
            keys = params.get("keys", [])
            keys_str = "+".join(str(k) for k in keys) if isinstance(keys, list) else str(keys)
            return SafetyAssessment(
                level=SafetyLevel.DANGEROUS,
                is_safe=False,
                requires_confirmation=True,
                reason=f"组合键操作可能触发系统功能: {keys_str}",
                suggestions=[
                    "请确认组合键不会触发危险操作",
                    "避免使用 Alt+F4, Ctrl+Alt+Delete 等系统组合键"
                ]
            )

        if action == ActionType.WINDOW_CLOSE:
            title = params.get("title", "")
            return SafetyAssessment(
                level=SafetyLevel.DANGEROUS,
                is_safe=False,
                requires_confirmation=True,
                reason=f"关闭窗口操作需要确认: {title}",
                suggestions=[
                    "请确认关闭正确的窗口",
                    "未保存的工作可能会丢失"
                ]
            )

        return SafetyAssessment(
            level=SafetyLevel.DANGEROUS,
            is_safe=False,
            requires_confirmation=True,
            reason=f"危险操作需要确认: {action.value}"
        )

    def _assess_caution_action(self, action: ActionType, params: dict[str, Any]) -> SafetyAssessment:
        """评估注意级别操作"""
        if action == ActionType.FILE_CREATE or action == ActionType.FILE_WRITE:
            file_path = params.get("path", params.get("file_path", ""))

            if self._is_sensitive_file(file_path):
                return SafetyAssessment(
                    level=SafetyLevel.DANGEROUS,
                    is_safe=False,
                    requires_confirmation=True,
                    reason=f"文件路径包含敏感信息: {file_path}",
                    suggestions=["请避免覆盖敏感配置文件"]
                )

            return SafetyAssessment(
                level=SafetyLevel.CAUTION,
                is_safe=True,
                requires_confirmation=False,
                reason=f"文件操作: {file_path}"
            )

        if action == ActionType.URL_OPEN:
            url = params.get("url", "")

            if self._is_dangerous_url(url):
                return SafetyAssessment(
                    level=SafetyLevel.DANGEROUS,
                    is_safe=False,
                    requires_confirmation=True,
                    reason=f"URL 可能指向内部网络或敏感地址: {url}",
                    suggestions=["请确认访问的URL是安全的"]
                )

            return SafetyAssessment(
                level=SafetyLevel.CAUTION,
                is_safe=True,
                requires_confirmation=False,
                reason=f"打开URL: {url}"
            )

        if action == ActionType.APP_OPEN:
            app_name = params.get("app_name", "")
            return SafetyAssessment(
                level=SafetyLevel.CAUTION,
                is_safe=True,
                requires_confirmation=False,
                reason=f"打开应用: {app_name}"
            )

        return SafetyAssessment(
            level=SafetyLevel.CAUTION,
            is_safe=True,
            requires_confirmation=False,
            reason=f"注意级别操作: {action.value}"
        )

    def _is_sensitive_file(self, file_path: str) -> bool:
        """检查是否为敏感文件"""
        if not file_path:
            return False

        file_path_lower = file_path.lower()

        for pattern in SENSITIVE_FILE_PATTERNS:
            if pattern.lower() in file_path_lower:
                return True

        for ext in DANGEROUS_FILE_EXTENSIONS:
            if file_path_lower.endswith(ext):
                return True

        return False

    def _is_dangerous_url(self, url: str) -> bool:
        """检查是否为危险URL"""
        if not url:
            return False

        url_lower = url.lower()

        for pattern in DANGEROUS_URL_PATTERNS:
            if pattern.lower() in url_lower:
                return True

        return False

    def is_safe_action(self, action: ActionType) -> bool:
        """
        快速判断操作是否安全（只读操作）

        Args:
            action: 操作类型

        Returns:
            bool: 是否为安全操作
        """
        return action in SAFE_ACTIONS

    def requires_confirmation(self, action: ActionType, params: dict[str, Any] = None) -> bool:
        """
        判断操作是否需要确认

        Args:
            action: 操作类型
            params: 操作参数

        Returns:
            bool: 是否需要确认
        """
        params = params or {}
        assessment = self.assess(action, params)
        return assessment.requires_confirmation


_safety_assessor: SafetyAssessor | None = None


def get_safety_assessor() -> SafetyAssessor:
    """获取安全评估器单例"""
    global _safety_assessor
    if _safety_assessor is None:
        _safety_assessor = SafetyAssessor()
    return _safety_assessor


def is_safe_action(action: ActionType) -> bool:
    """判断操作是否安全（只读操作）"""
    return get_safety_assessor().is_safe_action(action)


def requires_confirmation(action: ActionType, params: dict[str, Any] = None) -> bool:
    """判断操作是否需要确认"""
    return get_safety_assessor().requires_confirmation(action, params)


def assess_safety(action: ActionType, params: dict[str, Any] = None) -> SafetyAssessment:
    """评估操作安全级别"""
    return get_safety_assessor().assess(action, params or {})
