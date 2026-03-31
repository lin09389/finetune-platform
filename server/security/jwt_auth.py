"""
JWT 认证模块 - 用户身份验证和授权

功能：
- JWT Token 生成和验证
- Access Token + Refresh Token 机制
- Token 黑名单（注销支持）
- 权限角色系统
- 自动续期
"""
import hashlib
import logging
import os
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from functools import wraps
from typing import Any

import jwt

logger = logging.getLogger(__name__)


class Role(str, Enum):
    """用户角色"""
    USER = "user"
    ADMIN = "admin"
    SUPER_ADMIN = "super_admin"


ROLE_HIERARCHY: dict[Role, int] = {
    Role.USER: 1,
    Role.ADMIN: 10,
    Role.SUPER_ADMIN: 100,
}


@dataclass
class TokenPair:
    """Token 对"""
    access_token: str
    refresh_token: str
    token_type: str = "Bearer"
    expires_in: int = 1800

    def to_dict(self) -> dict:
        return {
            'access_token': self.access_token,
            'refresh_token': self.refresh_token,
            'token_type': self.token_type,
            'expires_in': self.expires_in
        }


@dataclass
class TokenPayload:
    """Token 载荷"""
    user_id: str
    username: str
    role: Role = Role.USER
    permissions: list[str] = field(default_factory=list)
    exp: datetime | None = None
    iat: datetime | None = None
    jti: str | None = None

    def to_dict(self) -> dict[str, Any]:
        data = {
            'user_id': self.user_id,
            'username': self.username,
            'role': self.role.value,
            'permissions': self.permissions,
        }
        if self.exp:
            data['exp'] = self.exp.timestamp()
        if self.iat:
            data['iat'] = self.iat.timestamp()
        if self.jti:
            data['jti'] = self.jti
        return data

    @classmethod
    def from_dict(cls, data: dict) -> 'TokenPayload':
        return cls(
            user_id=data.get('user_id', ''),
            username=data.get('username', ''),
            role=Role(data.get('role', 'user')),
            permissions=data.get('permissions', []),
            exp=datetime.fromtimestamp(data['exp']) if 'exp' in data else None,
            iat=datetime.fromtimestamp(data['iat']) if 'iat' in data else None,
            jti=data.get('jti')
        )


class TokenBlacklist:
    """Token 黑名单"""

    def __init__(self):
        self._blacklist: dict[str, float] = {}

    def add(self, jti: str, expire_time: datetime):
        self._blacklist[jti] = expire_time.timestamp()
        logger.info(f"Token {jti} 已加入黑名单")

    def contains(self, jti: str) -> bool:
        if jti not in self._blacklist:
            return False

        if time.time() > self._blacklist[jti]:
            del self._blacklist[jti]
            return False

        return True

    def cleanup(self):
        current_time = time.time()
        expired = [
            jti for jti, exp in self._blacklist.items()
            if current_time > exp
        ]
        for jti in expired:
            del self._blacklist[jti]

    def get_stats(self) -> dict:
        return {
            'total_blacklisted': len(self._blacklist),
            'active_blacklist': sum(
                1 for exp in self._blacklist.values()
                if time.time() < exp
            )
        }


class JWTAuth:
    """JWT 认证管理器"""

    def __init__(
        self,
        secret_key: str | None = None,
        algorithm: str = "HS256",
        access_token_expire_minutes: int = 30,
        refresh_token_expire_days: int = 7,
        issuer: str = "finetune-platform"
    ):
        self.secret_key = secret_key or os.environ.get('JWT_SECRET_KEY')

        if not self.secret_key:
            self.secret_key = self._generate_secret()
            logger.warning("使用自动生成的 JWT 密钥，生产环境请设置 JWT_SECRET_KEY 环境变量")

        self.algorithm = algorithm
        self.access_token_expire = timedelta(minutes=access_token_expire_minutes)
        self.refresh_token_expire = timedelta(days=refresh_token_expire_days)
        self.issuer = issuer

        self.blacklist = TokenBlacklist()
        self._users: dict[str, dict] = {}

        logger.info(f"JWT 认证已初始化，算法：{algorithm}")

    def _generate_secret(self) -> str:
        return uuid.uuid4().hex + uuid.uuid4().hex

    def _hash_password(self, password: str) -> str:
        return hashlib.sha256(password.encode()).hexdigest()

    def register_user(
        self,
        username: str,
        password: str,
        role: Role = Role.USER,
        permissions: list[str] | None = None
    ) -> str | None:
        for user in self._users.values():
            if user['username'] == username:
                return None

        user_id = uuid.uuid4().hex[:16]
        self._users[user_id] = {
            'username': username,
            'password': self._hash_password(password),
            'role': role,
            'permissions': permissions or [],
            'created_at': datetime.now().isoformat()
        }

        logger.info(f"用户 {username} 已注册，ID: {user_id}")
        return user_id

    def authenticate(self, username: str, password: str) -> str | None:
        password_hash = self._hash_password(password)

        for user_id, user in self._users.items():
            if user['username'] == username and user['password'] == password_hash:
                return user_id

        logger.warning(f"用户 {username} 认证失败")
        return None

    def create_token_pair(
        self,
        user_id: str,
        role: Role | None = None,
        permissions: list[str] | None = None
    ) -> TokenPair:
        user = self._users.get(user_id)
        if not user:
            raise ValueError(f"用户不存在：{user_id}")

        now = datetime.now()

        access_payload = TokenPayload(
            user_id=user_id,
            username=user['username'],
            role=role or user['role'],
            permissions=permissions or user['permissions'],
            iat=now,
            exp=now + self.access_token_expire,
            jti=uuid.uuid4().hex
        )

        access_token = jwt.encode(
            access_payload.to_dict(),
            self.secret_key,
            algorithm=self.algorithm
        )

        refresh_payload = TokenPayload(
            user_id=user_id,
            username=user['username'],
            role=role or user['role'],
            iat=now,
            exp=now + self.refresh_token_expire,
            jti=uuid.uuid4().hex
        )

        refresh_token = jwt.encode(
            refresh_payload.to_dict(),
            self.secret_key,
            algorithm=self.algorithm
        )

        return TokenPair(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=int(self.access_token_expire.total_seconds())
        )

    def verify_token(self, token: str, check_blacklist: bool = True) -> TokenPayload:
        try:
            payload = jwt.decode(
                token,
                self.secret_key,
                algorithms=[self.algorithm],
                options={'verify_exp': True}
            )

            token_payload = TokenPayload.from_dict(payload)

            if check_blacklist and token_payload.jti:
                if self.blacklist.contains(token_payload.jti):
                    raise ValueError("Token 已被注销")

            return token_payload

        except jwt.ExpiredSignatureError:
            logger.warning("Token 已过期")
            raise
        except jwt.InvalidTokenError as e:
            logger.warning(f"Token 无效：{e}")
            raise

    def refresh_access_token(self, refresh_token: str) -> TokenPair:
        payload = self.verify_token(refresh_token)

        if payload.permissions:
            raise ValueError("无效的 Refresh Token")

        if payload.jti:
            self.blacklist.add(payload.jti, payload.exp)

        return self.create_token_pair(
            user_id=payload.user_id,
            role=payload.role
        )

    def logout(self, access_token: str, refresh_token: str | None = None):
        try:
            payload = self.verify_token(access_token, check_blacklist=False)
            if payload.jti:
                self.blacklist.add(payload.jti, payload.exp)
        except jwt.InvalidTokenError:
            pass

        if refresh_token:
            try:
                payload = self.verify_token(refresh_token, check_blacklist=False)
                if payload.jti:
                    self.blacklist.add(payload.jti, payload.exp)
            except jwt.InvalidTokenError:
                pass

        logger.info("用户已注销")

    def has_permission(self, token_payload: TokenPayload, permission: str) -> bool:
        if token_payload.role in [Role.ADMIN, Role.SUPER_ADMIN]:
            return True

        return permission in token_payload.permissions

    def has_role(self, token_payload: TokenPayload, min_role: Role) -> bool:
        return ROLE_HIERARCHY.get(token_payload.role, 0) >= ROLE_HIERARCHY.get(min_role, 0)

    def get_user_info(self, user_id: str) -> dict | None:
        user = self._users.get(user_id)
        if not user:
            return None

        return {
            'user_id': user_id,
            'username': user['username'],
            'role': user['role'].value,
            'permissions': user['permissions'],
            'created_at': user['created_at']
        }

    def get_stats(self) -> dict:
        return {
            'total_users': len(self._users),
            'blacklist_stats': self.blacklist.get_stats(),
            'access_token_expire_minutes': int(self.access_token_expire.total_seconds() / 60),
            'refresh_token_expire_days': self.refresh_token_expire.days
        }


def get_current_user(token: str) -> TokenPayload:
    auth = get_jwt_auth()
    return auth.verify_token(token)


def require_role(min_role: Role):
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            current_user = kwargs.get('current_user')
            if not current_user:
                raise ValueError("未提供用户信息")

            auth = get_jwt_auth()
            if not auth.has_role(current_user, min_role):
                from fastapi import HTTPException
                raise HTTPException(403, detail="权限不足")

            return await func(*args, **kwargs)
        return wrapper
    return decorator


_jwt_auth: JWTAuth | None = None


def get_jwt_auth() -> JWTAuth:
    global _jwt_auth
    if _jwt_auth is None:
        _jwt_auth = JWTAuth(
            secret_key=os.environ.get('JWT_SECRET_KEY'),
            access_token_expire_minutes=int(
                os.environ.get('JWT_ACCESS_TOKEN_EXPIRE_MINUTES', '30')
            ),
            refresh_token_expire_days=int(
                os.environ.get('JWT_REFRESH_TOKEN_EXPIRE_DAYS', '7')
            )
        )
    return _jwt_auth


def init_jwt_auth(
    secret_key: str,
    access_token_expire_minutes: int = 30,
    refresh_token_expire_days: int = 7
) -> JWTAuth:
    global _jwt_auth
    _jwt_auth = JWTAuth(
        secret_key=secret_key,
        access_token_expire_minutes=access_token_expire_minutes,
        refresh_token_expire_days=refresh_token_expire_days
    )
    return _jwt_auth
