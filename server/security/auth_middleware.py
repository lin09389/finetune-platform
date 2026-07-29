"""
FastAPI 安全中间件 - 速率限制和 JWT 认证

功能：
- 速率限制中间件
- JWT 认证中间件（legacy class form — not registered by apps.factory）
- 组合安全中间件（legacy class form — not registered by apps.factory）

Live authentication path
------------------------
``server.apps.factory.authentication_middleware`` is the **only** middleware
registered on application startup. Prefer that path for production behavior.

The ``JWTAuthMiddleware`` / ``SecurityMiddleware`` classes below are retained
for optional dependency-injection style usage and legacy imports. Do not
register them alongside the factory middleware unless you intentionally want
a second, different error contract (HTTPException vs JSONResponse).
"""
import logging
import warnings

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from .jwt_auth import JWTAuth, Role, TokenPayload, get_jwt_auth
from .rate_limiter import RateLimiter, get_rate_limiter

logger = logging.getLogger(__name__)

security = HTTPBearer(auto_error=False)

_LEGACY_AUTH_MW_WARNED = False


def _warn_legacy_auth_middleware(name: str) -> None:
    global _LEGACY_AUTH_MW_WARNED
    if _LEGACY_AUTH_MW_WARNED:
        return
    _LEGACY_AUTH_MW_WARNED = True
    warnings.warn(
        f"{name} is a legacy auth middleware path. "
        "The live chain is apps.factory.authentication_middleware.",
        DeprecationWarning,
        stacklevel=3,
    )


class RateLimitMiddleware(BaseHTTPMiddleware):
    """速率限制中间件"""

    def __init__(
        self,
        app: ASGIApp,
        limiter: RateLimiter | None = None,
        enabled: bool = True,
        whitelist_ips: set[str] | None = None
    ):
        super().__init__(app)
        self.limiter = limiter or get_rate_limiter()
        self.enabled = enabled
        self.whitelist_ips = whitelist_ips or set()

        logger.info(f"速率限制中间件已{'启用' if enabled else '禁用'}")

    async def dispatch(self, request: Request, call_next):
        if not self.enabled:
            return await call_next(request)

        client_id = self._get_client_identifier(request)

        if client_id in self.whitelist_ips:
            return await call_next(request)

        endpoint = request.url.path

        allowed, info = self.limiter.is_allowed(client_id, endpoint)

        if not allowed:
            headers = {
                'X-RateLimit-Limit': str(info.get('limit', 0)),
                'X-RateLimit-Remaining': '0',
                'X-RateLimit-Reset': str(info.get('reset', 0)),
                'Retry-After': str(info.get('retry_after', 60))
            }

            if info.get('error') == 'rate_limit_banned':
                raise HTTPException(
                    status_code=429,
                    detail={
                        'error': 'banned',
                        'message': info.get('message', '请求过于频繁'),
                        'retry_after': info.get('retry_after')
                    },
                    headers=headers
                )
            else:
                raise HTTPException(
                    status_code=429,
                    detail={
                        'error': 'rate_limit_exceeded',
                        'message': info.get('message', '请求过于频繁'),
                        'retry_after': info.get('retry_after')
                    },
                    headers=headers
                )

        response = await call_next(request)

        response.headers['X-RateLimit-Limit'] = str(info.get('limit', 0))
        response.headers['X-RateLimit-Remaining'] = str(info.get('remaining', 0))
        response.headers['X-RateLimit-Reset'] = str(info.get('reset', 0))

        return response

    def _get_client_identifier(self, request: Request) -> str:
        api_key = request.headers.get('x-api-key')
        if api_key:
            return f"api_key:{api_key}"

        forwarded_for = request.headers.get('x-forwarded-for')
        if forwarded_for:
            ip = forwarded_for.split(',')[0].strip()
            return f"ip:{ip}"

        client_host = request.client.host if request.client else 'unknown'
        return f"ip:{client_host}"


class JWTAuthMiddleware(BaseHTTPMiddleware):
    """Legacy JWT auth middleware (class form).

    Not registered by ``apps.factory`` — live path is
    ``apps.factory.authentication_middleware``. Prefer Depends-based
    ``get_current_user`` / ``require_roles`` for route-level auth.
    """

    def __init__(
        self,
        app: ASGIApp,
        auth: JWTAuth | None = None,
        enabled: bool = True,
        exclude_paths: set[str] | None = None,
        exclude_prefixes: set[str] | None = None,
        required_role: Role | None = None
    ):
        _warn_legacy_auth_middleware("JWTAuthMiddleware")
        super().__init__(app)
        self.auth = auth or get_jwt_auth()
        self.enabled = enabled
        self.exclude_paths = exclude_paths or set()
        self.exclude_prefixes = exclude_prefixes or {'/docs', '/redoc', '/openapi.json', '/static'}
        self.required_role = required_role

        logger.info(f"JWT 认证中间件已{'启用' if enabled else '禁用'} (legacy class path)")

    async def dispatch(self, request: Request, call_next):
        if not self.enabled:
            return await call_next(request)

        path = request.url.path
        if path in self.exclude_paths:
            return await call_next(request)

        for prefix in self.exclude_prefixes:
            if path.startswith(prefix):
                return await call_next(request)

        auth_header = request.headers.get('authorization')

        if not auth_header:
            raise HTTPException(
                status_code=401,
                detail={'error': 'missing_authorization', 'message': '缺少 Authorization 头'},
                headers={'WWW-Authenticate': 'Bearer'}
            )

        parts = auth_header.split()
        if len(parts) != 2 or parts[0].lower() != 'bearer':
            raise HTTPException(
                status_code=401,
                detail={'error': 'invalid_authorization', 'message': '无效的 Authorization 格式'},
                headers={'WWW-Authenticate': 'Bearer'}
            )

        token = parts[1]

        try:
            payload = self.auth.verify_token(token)

            if self.required_role and not self.auth.has_role(payload, self.required_role):
                    raise HTTPException(
                        status_code=403,
                        detail={'error': 'insufficient_role', 'message': '权限不足'}
                    )

            request.state.current_user = payload
            request.state.user_id = payload.user_id
            request.state.username = payload.username

        except Exception as e:
            logger.warning(f"Token 验证失败：{e}")
            raise HTTPException(
                status_code=401,
                detail={'error': 'invalid_token', 'message': 'Token 无效或已过期'},
                headers={'WWW-Authenticate': 'Bearer'}
            )

        return await call_next(request)


class SecurityMiddleware(BaseHTTPMiddleware):
    """Legacy combined security middleware (class form).

    Not registered by ``apps.factory``. Live chain uses function-style
    ``authentication_middleware`` in factory.py.
    """

    def __init__(
        self,
        app: ASGIApp,
        enabled: bool = True,
        rate_limit_enabled: bool = True,
        jwt_enabled: bool = True,
        jwt_exclude_paths: set[str] | None = None,
        jwt_exclude_prefixes: set[str] | None = None,
        rate_limit_whitelist_ips: set[str] | None = None,
        required_role: Role | None = None
    ):
        _warn_legacy_auth_middleware("SecurityMiddleware")
        super().__init__(app)
        self.enabled = enabled
        self.rate_limit_enabled = rate_limit_enabled
        self.jwt_enabled = jwt_enabled

        if rate_limit_enabled:
            self.rate_limiter_middleware: RateLimitMiddleware | None = RateLimitMiddleware(
                app,
                enabled=True,
                whitelist_ips=rate_limit_whitelist_ips
            )
        else:
            self.rate_limiter_middleware = None

        if jwt_enabled:
            self.jwt_middleware: JWTAuthMiddleware | None = JWTAuthMiddleware(
                app,
                enabled=True,
                exclude_paths=jwt_exclude_paths or {'/api/login', '/api/register', '/health'},
                exclude_prefixes=jwt_exclude_prefixes or {'/docs', '/redoc', '/openapi.json'},
                required_role=required_role
            )
        else:
            self.jwt_middleware = None

        logger.info(f"组合安全中间件已初始化，速率限制：{rate_limit_enabled}, JWT: {jwt_enabled}")

    async def dispatch(self, request: Request, call_next):
        if not self.enabled:
            return await call_next(request)

        if self.rate_limiter_middleware:
            try:
                client_id = self.rate_limiter_middleware._get_client_identifier(request)
                if client_id not in (self.rate_limiter_middleware.whitelist_ips or set()):
                    endpoint = request.url.path
                    allowed, info = self.rate_limiter_middleware.limiter.is_allowed(client_id, endpoint)

                    if not allowed:
                        headers = {
                            'X-RateLimit-Limit': str(info.get('limit', 0)),
                            'X-RateLimit-Remaining': '0',
                            'X-RateLimit-Reset': str(info.get('reset', 0)),
                            'Retry-After': str(info.get('retry_after', 60))
                        }

                        if info.get('error') == 'rate_limit_banned':
                            raise HTTPException(429, detail=info, headers=headers)
                        else:
                            raise HTTPException(429, detail=info, headers=headers)
            except HTTPException:
                raise

        if self.jwt_middleware:
            return await self.jwt_middleware.dispatch(request, call_next)

        return await call_next(request)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> TokenPayload:
    auth = get_jwt_auth()
    return auth.verify_token(credentials.credentials)


async def get_current_user_optional(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> TokenPayload | None:
    if not credentials:
        return None

    auth = get_jwt_auth()
    try:
        return auth.verify_token(credentials.credentials)
    except Exception as e:
        logger.debug(f"Token 验证失败：{e}")
        return None


def require_roles(*roles: Role):
    async def role_checker(current_user: TokenPayload = Depends(get_current_user)):
        auth = get_jwt_auth()
        for role in roles:
            if auth.has_role(current_user, role):
                return current_user
        raise HTTPException(403, detail="权限不足")
    return role_checker


async def require_cua_admin(
    current_user: TokenPayload | None = Depends(get_current_user_optional),
) -> TokenPayload | None:
    """CUA host-control gate: ADMIN+ when auth is enabled; no anonymous control.

    When ENABLE_AUTH=false (local/test), dependency allows the request through so
    non-auth test suites remain usable — production always has ENABLE_AUTH=true.
    DEBUG never bypasses role checks while auth is on.
    """
    from core.config import get_settings

    if not get_settings().enable_auth:
        return current_user
    if current_user is None:
        raise HTTPException(
            status_code=401,
            detail={"error": "missing_authorization", "message": "CUA requires authentication"},
            headers={"WWW-Authenticate": "Bearer"},
        )
    auth = get_jwt_auth()
    if not auth.has_role(current_user, Role.ADMIN):
        raise HTTPException(
            status_code=403,
            detail={"error": "insufficient_role", "message": "CUA requires administrator role"},
        )
    return current_user
