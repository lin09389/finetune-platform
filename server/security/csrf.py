"""
CSRF 防护模块
防止跨站请求伪造攻击
"""
import logging
import secrets
import time

from fastapi import HTTPException, Request
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)


class CSRFProtection:
    """CSRF Token 管理器"""

    def __init__(self, secret_key: str, token_expire: int = 3600):
        self.secret_key = secret_key
        self.token_expire = token_expire
        self._tokens: dict[str, float] = {}
        self._session_tokens: dict[str, str] = {}

    def generate_token(self, session_id: str) -> str:
        token = secrets.token_urlsafe(32)
        self._tokens[token] = time.time() + self.token_expire
        self._session_tokens[session_id] = token
        return token

    def validate_token(self, token: str, session_id: str | None = None) -> bool:
        if token not in self._tokens:
            return False
        if time.time() > self._tokens[token]:
            del self._tokens[token]
            if session_id and session_id in self._session_tokens:
                del self._session_tokens[session_id]
            return False
        if session_id:
            expected_token = self._session_tokens.get(session_id)
            if expected_token and expected_token != token:
                return False
        return True

    def cleanup_expired(self):
        now = time.time()
        expired = [t for t, exp in self._tokens.items() if exp < now]
        for t in expired:
            del self._tokens[t]
        expired_sessions = [s for s, t in self._session_tokens.items() if t not in self._tokens]
        for s in expired_sessions:
            del self._session_tokens[s]
        if expired:
            logger.debug(f"清理了 {len(expired)} 个过期的 CSRF Token")

    def get_token_for_session(self, session_id: str) -> str | None:
        return self._session_tokens.get(session_id)


class CSRFMiddleware(BaseHTTPMiddleware):
    """CSRF 防护中间件"""

    EXEMPT_METHODS = {"GET", "HEAD", "OPTIONS", "TRACE"}
    EXEMPT_PATHS = {
        "/auth/login",
        "/auth/register",
        "/auth/refresh",
        "/health",
        "/docs",
        "/openapi.json",
        "/redoc",
        "/csrf/token",
    }

    def __init__(self, app, csrf_protection: CSRFProtection):
        super().__init__(app)
        self.csrf_protection = csrf_protection

    async def dispatch(self, request: Request, call_next):
        if request.method in self.EXEMPT_METHODS:
            return await call_next(request)

        path = request.url.path
        for exempt_path in self.EXEMPT_PATHS:
            if path.startswith(exempt_path):
                return await call_next(request)

        csrf_token = request.headers.get("X-CSRF-Token")
        if not csrf_token:
            csrf_token = request.headers.get("X-XSRF-Token")

        if not csrf_token:
            logger.warning(f"CSRF Token 缺失: {path}")
            raise HTTPException(
                status_code=403,
                detail={
                    "error": "csrf_token_missing",
                    "message": "CSRF Token 缺失，请刷新页面重试"
                }
            )

        session_id = request.cookies.get("session_id", "")
        if not self.csrf_protection.validate_token(csrf_token, session_id if session_id else None):
            logger.warning(f"CSRF Token 无效: {path}")
            raise HTTPException(
                status_code=403,
                detail={
                    "error": "csrf_token_invalid",
                    "message": "CSRF Token 无效或已过期，请刷新页面重试"
                }
            )

        return await call_next(request)


_csrf_protection: CSRFProtection | None = None


def get_csrf_protection() -> CSRFProtection:
    global _csrf_protection
    if _csrf_protection is None:
        from core.config import get_settings
        settings = get_settings()
        secret_key = settings.jwt_secret_key or "default-csrf-secret-key"
        _csrf_protection = CSRFProtection(secret_key=secret_key)
    return _csrf_protection


def create_csrf_middleware(app) -> CSRFMiddleware:
    return CSRFMiddleware(app, get_csrf_protection())
