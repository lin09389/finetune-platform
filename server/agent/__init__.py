"""
Agent Module - Computer Operation Capabilities
"""
from .config import ALLOWED_APPS, FORBIDDEN_PATTERNS, ActionType, AgentConfig
from .core.container import DIContainer
from .core.engine import QueueManager, UnifiedExecutor
from .core.feedback import ProgressTracker, ResultFormatter
from .core.parser import NLPParser, ParamExtractor
from .core.registry import ModuleRegistry
from .core.types import (
    ErrorCode,
    ErrorResult,
    ExecutionResult,
    ExecutionStatus,
    FormattedResult,
    IntentType,
    ModuleInfo,
    ParseResult,
    PermissionLevel,
    PermissionResult,
    ProgressInfo,
    ValidationResult,
)
from .security import (
    Permission,
    RBACManager,
    RiskAlertManager,
    RiskScorer,
    Role,
    SensitiveOperationClassifier,
    VerificationAPI,
    VerificationSession,
    VerificationSessionManager,
    check_permission,
    get_alert_manager,
    get_rbac_manager,
    get_verification_api,
    require_admin,
    require_permission,
    require_role,
)

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
