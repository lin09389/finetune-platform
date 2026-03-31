"""
验证流程 API
"""
from datetime import datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .classifier import SensitiveOperationClassifier
from .session import (
    VerificationSessionManager,
    VerificationStatus,
    VerificationType,
)


class VerificationRequest(BaseModel):
    """验证请求"""
    user_id: str
    operation: str
    operation_params: dict = Field(default_factory=dict)
    verification_type: str = "password"
    timeout_seconds: int = 300


class VerificationResponse(BaseModel):
    """验证响应"""
    session_id: str
    status: str
    verification_type: str
    expires_at: datetime | None = None
    message: str = ""
    code_hint: str | None = None


class VerifyCodeRequest(BaseModel):
    """验证码请求"""
    session_id: str
    code: str


class VerificationStatusResponse(BaseModel):
    """验证状态响应"""
    session_id: str
    status: str
    operation: str
    created_at: datetime
    expires_at: datetime | None = None
    attempts: int
    max_attempts: int


class VerificationAPI:
    """验证流程 API"""

    def __init__(self):
        self._classifier = SensitiveOperationClassifier()
        self._session_manager = VerificationSessionManager()
        self._router = APIRouter(prefix="/verification", tags=["verification"])
        self._setup_routes()

    def _setup_routes(self):
        """设置路由"""
        @self._router.post("/request", response_model=VerificationResponse)
        async def request_verification(req: VerificationRequest):
            return await self.create_verification_request(req)

        @self._router.post("/verify", response_model=VerificationResponse)
        async def verify_code(req: VerifyCodeRequest):
            return await self.submit_verification(req)

        @self._router.get("/status/{session_id}", response_model=VerificationStatusResponse)
        async def get_status(session_id: str):
            return await self.get_verification_status(session_id)

        @self._router.post("/cancel/{session_id}")
        async def cancel_verification(session_id: str):
            return await self.cancel_verification_session(session_id)

    async def create_verification_request(self, req: VerificationRequest) -> VerificationResponse:
        """创建验证请求"""
        sensitive_op = self._classifier.classify(req.operation, req.operation_params)

        if not sensitive_op or not sensitive_op.requires_verification:
            return VerificationResponse(
                session_id="",
                status="not_required",
                verification_type="none",
                message="此操作不需要验证",
            )

        existing_session = await self._session_manager.get_user_active_session(req.user_id)
        if existing_session:
            return VerificationResponse(
                session_id=existing_session.session_id,
                status="pending",
                verification_type=existing_session.verification_type.value,
                expires_at=existing_session.expires_at,
                message="已有待验证的会话",
            )

        try:
            verification_type = VerificationType(req.verification_type)
        except ValueError:
            verification_type = VerificationType.PASSWORD

        session = await self._session_manager.create_session(
            user_id=req.user_id,
            operation=req.operation,
            operation_params=req.operation_params,
            verification_type=verification_type,
            timeout_seconds=req.timeout_seconds,
            max_attempts=sensitive_op.max_attempts,
        )

        return VerificationResponse(
            session_id=session.session_id,
            status="pending",
            verification_type=session.verification_type.value,
            expires_at=session.expires_at,
            message=f"请完成{verification_type.value}验证",
            code_hint=self._session_manager.get_verification_code(session.session_id),
        )

    async def submit_verification(self, req: VerifyCodeRequest) -> VerificationResponse:
        """提交验证"""
        session = await self._session_manager.get_session(req.session_id)

        if not session:
            raise HTTPException(404, "验证会话不存在")

        if session.is_expired():
            return VerificationResponse(
                session_id=req.session_id,
                status="expired",
                verification_type=session.verification_type.value,
                message="验证会话已过期",
            )

        success = await self._session_manager.verify(req.session_id, req.code)

        if success:
            return VerificationResponse(
                session_id=req.session_id,
                status="verified",
                verification_type=session.verification_type.value,
                message="验证成功",
            )

        remaining = session.max_attempts - session.attempts
        if remaining <= 0:
            return VerificationResponse(
                session_id=req.session_id,
                status="failed",
                verification_type=session.verification_type.value,
                message="验证失败次数过多",
            )

        return VerificationResponse(
            session_id=req.session_id,
            status="pending",
            verification_type=session.verification_type.value,
            message=f"验证码错误，剩余 {remaining} 次尝试",
        )

    async def get_verification_status(self, session_id: str) -> VerificationStatusResponse:
        """获取验证状态"""
        session = await self._session_manager.get_session(session_id)

        if not session:
            raise HTTPException(404, "验证会话不存在")

        return VerificationStatusResponse(
            session_id=session.session_id,
            status=session.status.value,
            operation=session.operation,
            created_at=session.created_at,
            expires_at=session.expires_at,
            attempts=session.attempts,
            max_attempts=session.max_attempts,
        )

    async def cancel_verification_session(self, session_id: str) -> dict:
        """取消验证"""
        success = await self._session_manager.cancel(session_id)

        if not success:
            raise HTTPException(400, "无法取消验证会话")

        return {"status": "cancelled", "message": "验证已取消"}

    async def check_operation_requires_verification(
        self,
        operation: str,
        params: dict | None = None,
    ) -> dict:
        """检查操作是否需要验证"""
        sensitive_op = self._classifier.classify(operation, params)

        if not sensitive_op:
            return {
                "requires_verification": False,
                "sensitivity_level": "none",
            }

        return {
            "requires_verification": sensitive_op.requires_verification,
            "sensitivity_level": sensitive_op.sensitivity_level.value,
            "verification_types": sensitive_op.verification_types,
            "description": sensitive_op.description,
        }

    async def is_operation_verified(
        self,
        user_id: str,
        operation: str,
        params: dict | None = None,
    ) -> bool:
        """检查操作是否已验证"""
        session = await self._session_manager.get_user_active_session(user_id)

        if not session:
            return False

        if session.status != VerificationStatus.VERIFIED:
            return False

        if session.operation != operation:
            return False

        return True

    def get_router(self) -> APIRouter:
        """获取路由"""
        return self._router


_verification_api: VerificationAPI | None = None


def get_verification_api() -> VerificationAPI:
    """获取验证 API 单例"""
    global _verification_api
    if _verification_api is None:
        _verification_api = VerificationAPI()
    return _verification_api
