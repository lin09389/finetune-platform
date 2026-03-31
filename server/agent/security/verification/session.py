"""
验证会话管理
"""
import asyncio
import hashlib
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum


class VerificationType(str, Enum):
    """验证类型"""
    PASSWORD = "password"
    TWO_FACTOR = "two_factor"
    EMAIL_CODE = "email_code"
    SMS_CODE = "sms_code"
    ADMIN_APPROVAL = "admin_approval"
    BIOMETRIC = "biometric"


class VerificationStatus(str, Enum):
    """验证状态"""
    PENDING = "pending"
    VERIFIED = "verified"
    FAILED = "failed"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


@dataclass
class VerificationSession:
    """验证会话"""
    session_id: str
    user_id: str
    operation: str
    operation_params: dict
    verification_type: VerificationType
    status: VerificationStatus = VerificationStatus.PENDING
    created_at: datetime = field(default_factory=datetime.now)
    expires_at: datetime | None = None
    verified_at: datetime | None = None
    attempts: int = 0
    max_attempts: int = 3
    verification_code: str | None = None
    metadata: dict = field(default_factory=dict)

    def is_expired(self) -> bool:
        """检查是否过期"""
        if self.expires_at is None:
            return False
        return datetime.now() > self.expires_at

    def is_valid(self) -> bool:
        """检查是否有效"""
        return (
            self.status == VerificationStatus.PENDING
            and not self.is_expired()
            and self.attempts < self.max_attempts
        )

    def can_retry(self) -> bool:
        """检查是否可以重试"""
        return (
            self.status == VerificationStatus.PENDING
            and not self.is_expired()
            and self.attempts < self.max_attempts
        )


class VerificationSessionManager:
    """验证会话管理器"""

    DEFAULT_TIMEOUT_SECONDS = 300
    DEFAULT_MAX_ATTEMPTS = 3
    CODE_LENGTH = 6

    def __init__(self):
        self._sessions: dict[str, VerificationSession] = {}
        self._user_sessions: dict[str, str] = {}
        self._lock = asyncio.Lock()

    def _generate_session_id(self) -> str:
        """生成会话ID"""
        return secrets.token_urlsafe(32)

    def _generate_verification_code(self) -> str:
        """生成验证码"""
        return secrets.token_hex(self.CODE_LENGTH // 2).upper()

    def _hash_code(self, code: str) -> str:
        """哈希验证码"""
        return hashlib.sha256(code.encode()).hexdigest()

    async def create_session(
        self,
        user_id: str,
        operation: str,
        operation_params: dict,
        verification_type: VerificationType,
        timeout_seconds: int = None,
        max_attempts: int = None,
    ) -> VerificationSession:
        """创建验证会话"""
        async with self._lock:
            session_id = self._generate_session_id()
            verification_code = self._generate_verification_code()

            timeout = timeout_seconds or self.DEFAULT_TIMEOUT_SECONDS
            expires_at = datetime.now() + timedelta(seconds=timeout)

            session = VerificationSession(
                session_id=session_id,
                user_id=user_id,
                operation=operation,
                operation_params=operation_params,
                verification_type=verification_type,
                expires_at=expires_at,
                max_attempts=max_attempts or self.DEFAULT_MAX_ATTEMPTS,
                verification_code=self._hash_code(verification_code),
                metadata={"plain_code": verification_code},
            )

            self._sessions[session_id] = session
            self._user_sessions[user_id] = session_id

            return session

    async def get_session(self, session_id: str) -> VerificationSession | None:
        """获取验证会话"""
        return self._sessions.get(session_id)

    async def get_user_active_session(self, user_id: str) -> VerificationSession | None:
        """获取用户活跃会话"""
        session_id = self._user_sessions.get(user_id)
        if session_id:
            session = self._sessions.get(session_id)
            if session and session.is_valid():
                return session
        return None

    async def verify(
        self,
        session_id: str,
        code: str,
    ) -> bool:
        """验证"""
        async with self._lock:
            session = self._sessions.get(session_id)
            if not session:
                return False

            if not session.is_valid():
                return False

            session.attempts += 1

            if self._hash_code(code) == session.verification_code:
                session.status = VerificationStatus.VERIFIED
                session.verified_at = datetime.now()
                return True

            if session.attempts >= session.max_attempts:
                session.status = VerificationStatus.FAILED

            return False

    async def cancel(self, session_id: str) -> bool:
        """取消验证"""
        async with self._lock:
            session = self._sessions.get(session_id)
            if session and session.status == VerificationStatus.PENDING:
                session.status = VerificationStatus.CANCELLED
                return True
            return False

    async def cleanup_expired(self) -> int:
        """清理过期会话"""
        async with self._lock:
            expired_count = 0
            expired_sessions = [
                session_id for session_id, session in self._sessions.items()
                if session.is_expired() or session.status in [
                    VerificationStatus.VERIFIED,
                    VerificationStatus.FAILED,
                    VerificationStatus.CANCELLED,
                ]
            ]

            for session_id in expired_sessions:
                session = self._sessions.pop(session_id, None)
                if session:
                    self._user_sessions.pop(session.user_id, None)
                    expired_count += 1

            return expired_count

    async def get_pending_count(self, user_id: str | None = None) -> int:
        """获取待验证数量"""
        if user_id:
            session = await self.get_user_active_session(user_id)
            return 1 if session else 0

        return sum(1 for s in self._sessions.values() if s.is_valid())

    def get_verification_code(self, session_id: str) -> str | None:
        """获取验证码（仅用于测试或管理）"""
        session = self._sessions.get(session_id)
        if session:
            return session.metadata.get("plain_code")
        return None
