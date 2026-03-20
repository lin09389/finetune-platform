"""
Sensitive Operation Verification Module
"""
from .classifier import (
    SensitiveOperationClassifier,
    SensitivityLevel,
    SensitiveOperation,
)
from .session import (
    VerificationSession,
    VerificationSessionManager,
    VerificationType,
    VerificationStatus,
)
from .api import (
    VerificationAPI,
    VerificationRequest,
    VerificationResponse,
    get_verification_api,
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
