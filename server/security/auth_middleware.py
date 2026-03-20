"""
FastAPI 安全中间�?- 速率限制�?JWT 认证

功能�?- 速率限制中间�?- JWT 认证中间�?- 组合安全中间�?"""
from fastapi import Request, Response, HTTPException, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp
from typing import Optional, Dict, List, Set
import logging
import time

from .rate_limiter import get_rate_limiter, RateLimiter
from .jwt_auth import get_jwt_auth, JWTAuth, TokenPayload, Role

logger = logging.getLogger(__name__)


# HTTP Bearer 认证方案
security = HTTPBearer(auto_error=False)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    速率限制中间�?    
    用法:
        app.add_middleware(RateLimitMiddleware)
    """

    def __init__(
        self,
        app: ASGIApp,
        limiter: Optional[RateLimiter] = None,
        enabled: bool = True,
        whitelist_ips: Optional[Set[str]] = None
    ):
        """
        初始化速率限制中间�?
        Args:
            app: FastAPI 应用
            limiter: 速率限制器（默认使用全局单例�?            enabled: 是否启用
            whitelist_ips: IP 白名单（不受限制�?        """
        super().__init__(app)
        self.limiter = limiter or get_rate_limiter()
        self.enabled = enabled
        self.whitelist_ips = whitelist_ips or set()
        
        logger.info(f"速率限制中间件已{'启用' if enabled else '禁用'}")

    async def dispatch(self, request: Request, call_next):
        # 如果禁用，直接跳�?        if not self.enabled:
            return await call_next(request)

        # 获取客户端标识（IP �?API Key�?        client_id = self._get_client_identifier(request)
        
        # 检�?IP 白名�?        if client_id in self.whitelist_ips:
            return await call_next(request)

        # 获取端点路径
        endpoint = request.url.path

        # 检查速率限制
        allowed, info = self.limiter.is_allowed(client_id, endpoint)

        if not allowed:
            # 构建响应�?            headers = {
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

        # 执行请求
        response = await call_next(request)

        # 添加速率限制�?        response.headers['X-RateLimit-Limit'] = str(info.get('limit', 0))
        response.headers['X-RateLimit-Remaining'] = str(info.get('remaining', 0))
        response.headers['X-RateLimit-Reset'] = str(info.get('reset', 0))

        return response

    def _get_client_identifier(self, request: Request) -> str:
        """获取客户端标识符"""
        # 优先使用 API Key
        api_key = request.headers.get('x-api-key')
        if api_key:
            return f"api_key:{api_key}"

        # 使用 IP 地址
        # 检�?X-Forwarded-For（代理场景）
        forwarded_for = request.headers.get('x-forwarded-for')
        if forwarded_for:
            # 取第一�?IP（真实客户端 IP�?            ip = forwarded_for.split(',')[0].strip()
            return f"ip:{ip}"

        # 直接连接 IP
        client_host = request.client.host if request.client else 'unknown'
        return f"ip:{client_host}"


class JWTAuthMiddleware(BaseHTTPMiddleware):
    """
    JWT 认证中间�?    
    用法:
        app.add_middleware(JWTAuthMiddleware, exclude_paths=['/api/login', '/api/register'])
    """

    def __init__(
        self,
        app: ASGIApp,
        auth: Optional[JWTAuth] = None,
        enabled: bool = True,
        exclude_paths: Optional[Set[str]] = None,
        exclude_prefixes: Optional[Set[str]] = None,
        required_role: Optional[Role] = None
    ):
        """
        初始�?JWT 认证中间�?
        Args:
            app: FastAPI 应用
            auth: JWT 认证器（默认使用全局单例�?            enabled: 是否启用
            exclude_paths: 排除的路径（不需要认证）
            exclude_prefixes: 排除的路径前缀
            required_role: 要求的最低角�?        """
        super().__init__(app)
        self.auth = auth or get_jwt_auth()
        self.enabled = enabled
        self.exclude_paths = exclude_paths or set()
        self.exclude_prefixes = exclude_prefixes or {'/docs', '/redoc', '/openapi.json', '/static'}
        self.required_role = required_role
        
        logger.info(f"JWT 认证中间件已{'启用' if enabled else '禁用'}")

    async def dispatch(self, request: Request, call_next):
        # 如果禁用，直接跳�?        if not self.enabled:
            return await call_next(request)

        # 检查是否在排除列表�?        path = request.url.path
        if path in self.exclude_paths:
            return await call_next(request)

        for prefix in self.exclude_prefixes:
            if path.startswith(prefix):
                return await call_next(request)

        # 获取 Authorization Header
        auth_header = request.headers.get('authorization')
        
        if not auth_header:
            raise HTTPException(
                status_code=401,
                detail={'error': 'missing_authorization', 'message': '缺少 Authorization �?},
                headers={'WWW-Authenticate': 'Bearer'}
            )

        # 解析 Token
        parts = auth_header.split()
        if len(parts) != 2 or parts[0].lower() != 'bearer':
            raise HTTPException(
                status_code=401,
                detail={'error': 'invalid_authorization', 'message': '无效�?Authorization 格式'},
                headers={'WWW-Authenticate': 'Bearer'}
            )

        token = parts[1]

        try:
            # 验证 Token
            payload = self.auth.verify_token(token)
            
            # 检查角色要�?            if self.required_role:
                if not self.auth.has_role(payload, self.required_role):
                    raise HTTPException(
                        status_code=403,
                        detail={'error': 'insufficient_role', 'message': '权限不足'}
                    )

            # 将用户信息存入请求状�?            request.state.current_user = payload
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
    """
    组合安全中间件（速率限制 + JWT 认证�?    
    用法:
        app.add_middleware(SecurityMiddleware)
    """

    def __init__(
        self,
        app: ASGIApp,
        enabled: bool = True,
        rate_limit_enabled: bool = True,
        jwt_enabled: bool = True,
        jwt_exclude_paths: Optional[Set[str]] = None,
        jwt_exclude_prefixes: Optional[Set[str]] = None,
        rate_limit_whitelist_ips: Optional[Set[str]] = None,
        required_role: Optional[Role] = None
    ):
        """
        初始化组合安全中间件

        Args:
            app: FastAPI 应用
            enabled: 是否启用
            rate_limit_enabled: 是否启用速率限制
            jwt_enabled: 是否启用 JWT 认证
            jwt_exclude_paths: JWT 排除路径
            jwt_exclude_prefixes: JWT 排除路径前缀
            rate_limit_whitelist_ips: 速率限制 IP 白名�?            required_role: 要求的最低角�?        """
        super().__init__(app)
        self.enabled = enabled
        self.rate_limit_enabled = rate_limit_enabled
        self.jwt_enabled = jwt_enabled
        
        # 初始化子中间�?        if rate_limit_enabled:
            self.rate_limiter_middleware = RateLimitMiddleware(
                app,
                enabled=True,
                whitelist_ips=rate_limit_whitelist_ips
            )
        else:
            self.rate_limiter_middleware = None

        if jwt_enabled:
            self.jwt_middleware = JWTAuthMiddleware(
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

        # 先执行速率限制
        if self.rate_limiter_middleware:
            # 临时覆盖 call_next 以捕获速率限制异常
            async def next_handler(req):
                return await call_next()
            
            try:
                # 手动调用速率限制逻辑
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

        # 再执�?JWT 认证
        if self.jwt_middleware:
            return await self.jwt_middleware.dispatch(request, call_next)

        return await call_next(request)


# 依赖注入函数
async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> TokenPayload:
    """
    获取当前用户（用�?FastAPI 路由依赖注入�?    
    用法:
        @app.get("/protected")
        async def protected_route(current_user: TokenPayload = Depends(get_current_user)):
            return {"user": current_user.username}
    """
    auth = get_jwt_auth()
    return auth.verify_token(credentials.credentials)


async def get_current_user_optional(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> Optional[TokenPayload]:
    """
    获取当前用户（可选，�?Token 返回 None�?    
    用法:
        @app.get("/optional-auth")
        async def optional_auth_route(current_user: Optional[TokenPayload] = Depends(get_current_user_optional)):
            if current_user:
                return {"user": current_user.username}
            return {"user": "anonymous"}
    """
    if not credentials:
        return None
    
    auth = get_jwt_auth()
    try:
        return auth.verify_token(credentials.credentials)
    except Exception as e:
        logger.debug(f"Token 验证失败：{e}")
        return None


def require_roles(*roles: Role):
    """
    角色要求装饰�?    
    用法:
        @app.get("/admin")
        @require_roles(Role.ADMIN, Role.SUPER_ADMIN)
        async def admin_route(current_user: TokenPayload = Depends(get_current_user)):
            ...
    """
    async def role_checker(current_user: TokenPayload = Depends(get_current_user)):
        auth = get_jwt_auth()
        for role in roles:
            if auth.has_role(current_user, role):
                return current_user
        raise HTTPException(403, detail="权限不足")
    return role_checker
