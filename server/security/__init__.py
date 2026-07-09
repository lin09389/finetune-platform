"""
安全模块 - 加密、沙箱、审计日志、数据脱敏、速率限制、JWT 认证

安全增强功能：
- 数据脱敏（API Key、密码、邮箱、手机号等）
- 响应过滤（自动脱敏敏感字段）
- 审计日志脱敏
- 密钥访问追踪
- API 速率限制（防止暴力破解和 DDoS）
- JWT 认证（Access/Refresh Token 机制）
- 角色权限系统
"""
from .audit_log import AuditLogger, audit_logger
from .auth_middleware import (
    JWTAuthMiddleware,
    RateLimitMiddleware,
    get_current_user,
    get_current_user_optional,
    require_cua_admin,
    require_roles,
)
from .auth_middleware import SecurityMiddleware as AuthSecurityMiddleware
from .data_masking import DataMasker, data_masker, mask, mask_api_key, mask_password, mask_text
from .encryption import SecureStorage, secure_storage
from .file_sandbox import FileSandbox, file_sandbox
from .jwt_auth import JWTAuth, Role, TokenPair, TokenPayload, get_jwt_auth, init_jwt_auth
from .middleware import ResponseMaskingMiddleware, SecurityMiddleware
from .rate_limiter import RateLimiter, get_rate_limiter, init_rate_limiter

__all__ = [
    "secure_storage",
    "SecureStorage",
    "file_sandbox",
    "FileSandbox",
    "audit_logger",
    "AuditLogger",
    "data_masker",
    "DataMasker",
    "mask",
    "mask_text",
    "mask_api_key",
    "mask_password",
    "SecurityMiddleware",
    "ResponseMaskingMiddleware",
    "RateLimiter",
    "get_rate_limiter",
    "init_rate_limiter",
    "RateLimitMiddleware",
    "JWTAuth",
    "get_jwt_auth",
    "init_jwt_auth",
    "TokenPayload",
    "Role",
    "TokenPair",
    "JWTAuthMiddleware",
    "AuthSecurityMiddleware",
    "get_current_user",
    "get_current_user_optional",
    "require_roles",
    "require_cua_admin",
]
