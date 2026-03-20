"""
Agent Module - Computer Operation Capabilities
"""
from .config import AgentConfig, ALLOWED_APPS, FORBIDDEN_PATTERNS, ActionType

from .security import (
    Permission,
    Role,
    RBACManager,
    get_rbac_manager,
    require_permission,
    require_role,
    require_admin,
    check_permission,
    SensitiveOperationClassifier,
    VerificationSession,
    VerificationSessionManager,
    VerificationAPI,
    get_verification_api,
    RiskScorer,
    RiskAlertManager,
    get_alert_manager,
)

from .core.types import (
    IntentType,
    PermissionLevel,
    ExecutionStatus,
    ErrorCode,
    ParseResult,
    PermissionResult,
    ValidationResult,
    ExecutionResult,
    FormattedResult,
    ErrorResult,
    ProgressInfo,
    ModuleInfo,
)

from .core.container import DIContainer
from .core.registry import ModuleRegistry

from .core.parser import NLPParser, ParamExtractor
from .core.engine import UnifiedExecutor, QueueManager
from .core.feedback import ResultFormatter, ProgressTracker

__all__ = [
    "AgentConfig",
    "ALLOWED_APPS",
    "FORBIDDEN_PATTERNS",
    "ActionType",
    "Permission",
    "Role",
    "RBACManager",
    "get_rbac_manager",
    "require_permission",
    "require_role",
    "require_admin",
    "check_permission",
    "SensitiveOperationClassifier",
    "VerificationSession",
    "VerificationSessionManager",
    "VerificationAPI",
    "get_verification_api",
    "RiskScorer",
    "RiskAlertManager",
    "get_alert_manager",
    "IntentType",
    "PermissionLevel",
    "ExecutionStatus",
    "ErrorCode",
    "ParseResult",
    "PermissionResult",
    "ValidationResult",
    "ExecutionResult",
    "FormattedResult",
    "ErrorResult",
    "ProgressInfo",
    "ModuleInfo",
    "DIContainer",
    "ModuleRegistry",
    "NLPParser",
    "ParamExtractor",
    "UnifiedExecutor",
    "QueueManager",
    "ResultFormatter",
    "ProgressTracker",
]
