import hashlib
import logging
import secrets
import uuid
from datetime import datetime, timedelta
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from .rbac import get_action_sensitivity

logger = logging.getLogger(__name__)


class VerificationType(str, Enum):
    TWO_FACTOR = "two_factor"
    PASSWORD = "password"
    BIOMETRIC = "biometric"
    EMAIL_CODE = "email_code"
    SMS_CODE = "sms_code"
    ADMIN_APPROVAL = "admin_approval"


class VerificationStatus(str, Enum):
    PENDING = "pending"
    VERIFIED = "verified"
    EXPIRED = "expired"
    FAILED = "failed"
    CANCELLED = "cancelled"


class SensitiveOperationCategory(str, Enum):
    FILE_DESTRUCTION = "file_destruction"
    SYSTEM_MODIFICATION = "system_modification"
    SECURITY_CHANGE = "security_change"
    DATA_EXPORT = "data_export"
    PRIVILEGE_ESCALATION = "privilege_escalation"
    NETWORK_OPERATION = "network_operation"
    PROCESS_CONTROL = "process_control"


OPERATION_CATEGORIES: dict[str, SensitiveOperationCategory] = {
    "file_delete": SensitiveOperationCategory.FILE_DESTRUCTION,
    "process_stop": SensitiveOperationCategory.PROCESS_CONTROL,
    "service_stop": SensitiveOperationCategory.SYSTEM_MODIFICATION,
    "service_restart": SensitiveOperationCategory.SYSTEM_MODIFICATION,
    "env_write": SensitiveOperationCategory.SYSTEM_MODIFICATION,
    "admin_operation": SensitiveOperationCategory.PRIVILEGE_ESCALATION,
    "file_write": SensitiveOperationCategory.FILE_DESTRUCTION,
    "process_start": SensitiveOperationCategory.PROCESS_CONTROL,
}


CATEGORY_VERIFICATION_REQUIREMENTS: dict[SensitiveOperationCategory, list[VerificationType]] = {
    SensitiveOperationCategory.FILE_DESTRUCTION: [VerificationType.PASSWORD, VerificationType.TWO_FACTOR],
    SensitiveOperationCategory.SYSTEM_MODIFICATION: [VerificationType.TWO_FACTOR, VerificationType.ADMIN_APPROVAL],
    SensitiveOperationCategory.SECURITY_CHANGE: [VerificationType.TWO_FACTOR, VerificationType.ADMIN_APPROVAL],
    SensitiveOperationCategory.DATA_EXPORT: [VerificationType.PASSWORD],
    SensitiveOperationCategory.PRIVILEGE_ESCALATION: [VerificationType.TWO_FACTOR, VerificationType.ADMIN_APPROVAL],
    SensitiveOperationCategory.NETWORK_OPERATION: [VerificationType.PASSWORD],
    SensitiveOperationCategory.PROCESS_CONTROL: [VerificationType.PASSWORD, VerificationType.TWO_FACTOR],
}


class VerificationSession(BaseModel):
    session_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    action: str
    params: dict[str, Any] = Field(default_factory=dict)
    verification_type: VerificationType
    status: VerificationStatus = VerificationStatus.PENDING
    created_at: datetime = Field(default_factory=datetime.now)
    expires_at: datetime
    verified_at: datetime | None = None
    attempts: int = 0
    max_attempts: int = 3
    verification_code: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    def is_expired(self) -> bool:
        return datetime.now() > self.expires_at

    def is_valid(self) -> bool:
        return self.status == VerificationStatus.PENDING and not self.is_expired()


class VerificationRequest(BaseModel):
    user_id: str
    action: str
    params: dict[str, Any] = Field(default_factory=dict)
    context: dict[str, Any] = Field(default_factory=dict)


class VerificationResponse(BaseModel):
    session_id: str
    required_type: VerificationType
    message: str
    expires_in_seconds: int
    attempts_remaining: int


class VerificationResult(BaseModel):
    success: bool
    session_id: str
    status: VerificationStatus
    message: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class VerificationManager:
    DEFAULT_TIMEOUT_MINUTES: int = 5
    CODE_LENGTH: int = 6

    def __init__(self, timeout_minutes: int | None = None):
        self.timeout_minutes = timeout_minutes or self.DEFAULT_TIMEOUT_MINUTES
        self._sessions: dict[str, VerificationSession] = {}
        self._user_sessions: dict[str, list[str]] = {}

    def create_verification_session(
        self,
        user_id: str,
        action: str,
        params: dict[str, Any],
        verification_type: VerificationType | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> VerificationSession:
        category = self._get_operation_category(action)
        required_types = CATEGORY_VERIFICATION_REQUIREMENTS.get(
            category, [VerificationType.PASSWORD]
        )

        selected_type = verification_type or required_types[0]

        verification_code = None
        if selected_type in (
            VerificationType.EMAIL_CODE,
            VerificationType.SMS_CODE,
            VerificationType.TWO_FACTOR,
        ):
            verification_code = self._generate_code()

        session = VerificationSession(
            user_id=user_id,
            action=action,
            params=params,
            verification_type=selected_type,
            expires_at=datetime.now() + timedelta(minutes=self.timeout_minutes),
            verification_code=verification_code,
            metadata=metadata or {},
        )

        self._sessions[session.session_id] = session

        if user_id not in self._user_sessions:
            self._user_sessions[user_id] = []
        self._user_sessions[user_id].append(session.session_id)

        logger.info(
            f"Created verification session {session.session_id} for user {user_id}, action: {action}"
        )

        return session

    def verify(
        self,
        session_id: str,
        verification_value: str,
    ) -> VerificationResult:
        session = self._sessions.get(session_id)

        if not session:
            return VerificationResult(
                success=False,
                session_id=session_id,
                status=VerificationStatus.FAILED,
                message="Session not found",
            )

        if session.is_expired():
            session.status = VerificationStatus.EXPIRED
            return VerificationResult(
                success=False,
                session_id=session_id,
                status=VerificationStatus.EXPIRED,
                message="Verification session has expired",
            )

        if session.status != VerificationStatus.PENDING:
            return VerificationResult(
                success=False,
                session_id=session_id,
                status=session.status,
                message=f"Session is already {session.status.value}",
            )

        session.attempts += 1

        if session.attempts > session.max_attempts:
            session.status = VerificationStatus.FAILED
            return VerificationResult(
                success=False,
                session_id=session_id,
                status=VerificationStatus.FAILED,
                message="Maximum verification attempts exceeded",
            )

        is_valid = self._validate_verification(session, verification_value)

        if is_valid:
            session.status = VerificationStatus.VERIFIED
            session.verified_at = datetime.now()
            logger.info(f"Verification successful for session {session_id}")

            return VerificationResult(
                success=True,
                session_id=session_id,
                status=VerificationStatus.VERIFIED,
                message="Verification successful",
            )
        else:
            remaining = session.max_attempts - session.attempts
            return VerificationResult(
                success=False,
                session_id=session_id,
                status=VerificationStatus.PENDING,
                message=f"Verification failed. {remaining} attempts remaining.",
                metadata={"attempts_remaining": remaining},
            )

    def cancel_verification(self, session_id: str) -> bool:
        session = self._sessions.get(session_id)
        if session and session.status == VerificationStatus.PENDING:
            session.status = VerificationStatus.CANCELLED
            logger.info(f"Verification session {session_id} cancelled")
            return True
        return False

    def get_session(self, session_id: str) -> VerificationSession | None:
        return self._sessions.get(session_id)

    def get_user_pending_sessions(self, user_id: str) -> list[VerificationSession]:
        session_ids = self._user_sessions.get(user_id, [])
        sessions = []

        for session_id in session_ids:
            session = self._sessions.get(session_id)
            if session and session.is_valid():
                sessions.append(session)

        return sessions

    def cleanup_expired_sessions(self) -> int:
        expired_count = 0
        expired_session_ids = []

        for session_id, session in self._sessions.items():
            if session.is_expired() or session.status in (
                VerificationStatus.VERIFIED,
                VerificationStatus.FAILED,
                VerificationStatus.CANCELLED,
            ):
                expired_session_ids.append(session_id)
                expired_count += 1

        for session_id in expired_session_ids:
            session = self._sessions.pop(session_id, None)
            if session:
                user_sessions = self._user_sessions.get(session.user_id, [])
                if session_id in user_sessions:
                    user_sessions.remove(session_id)

        if expired_count > 0:
            logger.info(f"Cleaned up {expired_count} expired verification sessions")

        return expired_count

    def get_required_verification_type(self, action: str) -> VerificationType:
        category = self._get_operation_category(action)
        required_types = CATEGORY_VERIFICATION_REQUIREMENTS.get(
            category, [VerificationType.PASSWORD]
        )
        return required_types[0]

    def get_verification_requirements(self, action: str) -> dict[str, Any]:
        category = self._get_operation_category(action)
        sensitivity = get_action_sensitivity(action)
        required_types = CATEGORY_VERIFICATION_REQUIREMENTS.get(
            category, [VerificationType.PASSWORD]
        )

        return {
            "action": action,
            "category": category.value if category else None,
            "sensitivity": sensitivity.value,
            "required_verification_types": [t.value for t in required_types],
            "timeout_minutes": self.timeout_minutes,
        }

    def _get_operation_category(self, action: str) -> SensitiveOperationCategory:
        return OPERATION_CATEGORIES.get(action, SensitiveOperationCategory.SYSTEM_MODIFICATION)

    def _generate_code(self) -> str:
        return "".join(secrets.choice("0123456789") for _ in range(self.CODE_LENGTH))

    def _validate_verification(
        self, session: VerificationSession, value: str
    ) -> bool:
        if session.verification_type in (
            VerificationType.EMAIL_CODE,
            VerificationType.SMS_CODE,
            VerificationType.TWO_FACTOR,
        ):
            return session.verification_code == value

        if session.verification_type == VerificationType.PASSWORD:
            hashed_value = hashlib.sha256(value.encode()).hexdigest()
            stored_hash = session.metadata.get("password_hash")
            if stored_hash:
                return hashed_value == stored_hash
            return bool(value)

        if session.verification_type == VerificationType.BIOMETRIC:
            return bool(value)

        if session.verification_type == VerificationType.ADMIN_APPROVAL:
            return session.metadata.get("admin_approved", False)

        return False

    def prepare_password_verification(
        self, session_id: str, password_hash: str
    ) -> bool:
        session = self._sessions.get(session_id)
        if session:
            session.metadata["password_hash"] = password_hash
            return True
        return False

    def approve_by_admin(
        self, session_id: str, admin_user_id: str
    ) -> bool:
        session = self._sessions.get(session_id)
        if session and session.verification_type == VerificationType.ADMIN_APPROVAL:
            session.metadata["admin_approved"] = True
            session.metadata["approved_by"] = admin_user_id
            session.metadata["approved_at"] = datetime.now().isoformat()
            return True
        return False


_verification_manager: VerificationManager | None = None


def get_verification_manager() -> VerificationManager:
    global _verification_manager
    if _verification_manager is None:
        _verification_manager = VerificationManager()
    return _verification_manager
