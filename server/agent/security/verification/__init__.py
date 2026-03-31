"""
Sensitive Operation Verification Module
"""
from .api import (
    VerificationAPI,
    VerificationRequest,
    VerificationResponse,
    get_verification_api,
)
from .classifier import (
    SensitiveOperation,
    SensitiveOperationClassifier,
    SensitivityLevel,
)
from .session import (
    VerificationSession,
    VerificationSessionManager,
    VerificationStatus,
    VerificationType,
)

TwoFactorVerifier = VerificationSessionManager
OperationClassifier = SensitiveOperationClassifier

__all__ = [
    "SensitiveOperationClassifier",
    "SensitivityLevel",
    "SensitiveOperation",
    "VerificationSession",
    "VerificationSessionManager",
    "VerificationType",
    "VerificationStatus",
    "VerificationAPI",
    "VerificationRequest",
    "VerificationResponse",
    "get_verification_api",
    "TwoFactorVerifier",
    "OperationClassifier",
]
