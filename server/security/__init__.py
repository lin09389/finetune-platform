"""
安全模块 - 加密、沙箱、审计日志、数据脱敏、速率限制、JWT 认证

安全增强功能�?- 数据脱敏（API Key、密码、邮箱、手机号等）
- 响应过滤（自动脱敏敏感字段）
- 审计日志脱敏
- 密钥访问追踪
- API 速率限制（防止暴力破解和 DDoS�?- JWT 认证（Access/Refresh Token 机制�?- 角色权限系统
"""
from .encryption import secure_storage, SecureStorage
from .file_sandbox import file_sandbox, FileSandbox
from .audit_log import audit_logger, AuditLogger
from .data_masking import data_masker, DataMasker, mask, mask_text, mask_api_key, mask_password
from .middleware import SecurityMiddleware, ResponseMaskingMiddleware
from .rate_limiter import RateLimiter, get_rate_limiter, init_rate_limiter
from .jwt_auth import JWTAuth, get_jwt_auth, init_jwt_auth, TokenPayload, Role, TokenPair
from .auth_middleware import (
    RateLimitMiddleware,
    JWTAuthMiddleware,
    SecurityMiddleware as AuthSecurityMiddleware,
    get_current_user,
    get_current_user_optional,
    require_roles
)

__all__ = [
    # 加密存储
    "secure_storage",
    "SecureStorage",
    # 文件沙箱
    "file_sandbox",
    "FileSandbox",
    # 审计日志
    "audit_logger",
    "AuditLogger",
    # 数据脱敏
    "data_masker",
    "DataMasker",
    "mask",
    "mask_text",
    "mask_api_key",
    "mask_password",
    # 响应过滤
    "SecurityMiddleware",
    "ResponseMaskingMiddleware",
    # 速率限制
    "RateLimiter",
    "get_rate_limiter",
    "init_rate_limiter",
    "RateLimitMiddleware",
    # JWT 认证
    "JWTAuth",
    "get_jwt_auth",
    "init_jwt_auth",
    "TokenPayload",
    "Role",
    "TokenPair",
    # 认证中间�?    "JWTAuthMiddleware",
    "AuthSecurityMiddleware",
    "get_current_user",
    "get_current_user_optional",
    "require_roles",
]
