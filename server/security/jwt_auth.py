"""
JWT 认证模块 - 用户身份验证和授权

功能：
- JWT Token 生成和验证
- Access Token + Refresh Token 机制
- Token 黑名单（注销支持）
- 权限角色系统
- 自动续期
"""
import logging
import os
import secrets
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from functools import wraps
from typing import Any

import bcrypt
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
    """Token 黑名单（持久化到 SQLite）"""

    def __init__(self, db_path: str = "data/app.db"):
        self._db_path = db_path
        self._ensure_table()

    def _ensure_table(self):
        from core.db_manager import get_db_pool
        pool = get_db_pool(self._db_path)
        with pool.get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS token_blacklist (
                    token_jti TEXT PRIMARY KEY,
                    expires_at REAL NOT NULL,
                    blacklisted_at TEXT NOT NULL
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_token_blacklist_expires ON token_blacklist(expires_at)")

    def add(self, jti: str, expire_time: datetime):
        from core.db_manager import get_db_pool
        pool = get_db_pool(self._db_path)
        with pool.get_connection() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO token_blacklist (token_jti, expires_at, blacklisted_at) VALUES (?, ?, ?)",
                (jti, expire_time.timestamp(), datetime.now().isoformat()),
            )
        logger.info(f"Token {jti} 已加入黑名单")

    def contains(self, jti: str) -> bool:
        from core.db_manager import get_db_pool
        pool = get_db_pool(self._db_path)
        with pool.get_readonly_connection() as conn:
            row = conn.execute("SELECT expires_at FROM token_blacklist WHERE token_jti = ?", (jti,)).fetchone()
        if not row:
            return False
        if time.time() > row[0]:
            # 过期条目异步清理
            self._remove(jti)
            return False
        return True

    def _remove(self, jti: str):
        from core.db_manager import get_db_pool
        pool = get_db_pool(self._db_path)
        with pool.get_connection() as conn:
            conn.execute("DELETE FROM token_blacklist WHERE token_jti = ?", (jti,))

    def cleanup(self):
        from core.db_manager import get_db_pool
        pool = get_db_pool(self._db_path)
        with pool.get_connection() as conn:
            conn.execute("DELETE FROM token_blacklist WHERE expires_at < ?", (time.time(),))

    def get_stats(self) -> dict:
        from core.db_manager import get_db_pool
        pool = get_db_pool(self._db_path)
        with pool.get_readonly_connection() as conn:
            total = conn.execute("SELECT COUNT(*) FROM token_blacklist").fetchone()[0]
            active = conn.execute("SELECT COUNT(*) FROM token_blacklist WHERE expires_at > ?", (time.time(),)).fetchone()[0]
        return {
            'total_blacklisted': total,
            'active_blacklist': active,
        }


class JWTAuth:
    """JWT 认证管理器"""

    def __init__(
        self,
        secret_key: str | None = None,
        algorithm: str = "HS256",
        access_token_expire_minutes: int = 30,
        refresh_token_expire_days: int = 7,
        issuer: str = "finetune-platform",
        db_path: str = "data/app.db",
    ):
        from security.runtime_policy import require_configured_jwt_secret

        # Fail-closed: never silently mint a random secret (multi-worker inconsistency).
        self.secret_key = require_configured_jwt_secret(secret_key, source="JWTAuth")

        self.algorithm = algorithm
        self.access_token_expire = timedelta(minutes=access_token_expire_minutes)
        self.refresh_token_expire = timedelta(days=refresh_token_expire_days)
        self.issuer = issuer
        self._db_path = db_path

        self._ensure_users_table()
        self.blacklist = TokenBlacklist(db_path)
        # 内存缓存，实际数据来源为数据库
        self._users: dict[str, dict] = self._load_users_from_db()

        logger.info(f"JWT 认证已初始化，算法：{algorithm}")

    def _ensure_users_table(self):
        from core.db_manager import get_db_pool
        pool = get_db_pool(self._db_path)
        with pool.get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY,
                    username TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    role TEXT NOT NULL DEFAULT 'user',
                    permissions TEXT NOT NULL DEFAULT '[]',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)

    def _load_users_from_db(self) -> dict[str, dict]:
        from core.db_manager import get_db_pool
        import json as _json
        pool = get_db_pool(self._db_path)
        users: dict[str, dict] = {}
        with pool.get_readonly_connection() as conn:
            rows = conn.execute("SELECT id, username, password_hash, role, permissions, created_at FROM users").fetchall()
        for row in rows:
            users[row[0]] = {
                'username': row[1],
                'password': row[2],
                'role': Role(row[3]),
                'permissions': _json.loads(row[4]) if row[4] else [],
                'created_at': row[5],
            }
        return users

    def _generate_secret(self) -> str:
        return secrets.token_hex(32)

    def _hash_password(self, password: str) -> str:
        return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt(rounds=12)).decode('utf-8')

    def _verify_password(self, password: str, password_hash: str) -> bool:
        return bcrypt.checkpw(password.encode('utf-8'), password_hash.encode('utf-8'))

    def register_user(
        self,
        username: str,
        password: str,
        role: Role = Role.USER,
        permissions: list[str] | None = None
    ) -> str | None:
        import json as _json
        for user in self._users.values():
            if user['username'] == username:
                return None

        user_id = uuid.uuid4().hex[:16]
        now = datetime.now().isoformat()
        password_hash = self._hash_password(password)
        perms = permissions or []

        from core.db_manager import get_db_pool
        pool = get_db_pool(self._db_path)
        with pool.get_connection() as conn:
            conn.execute(
                "INSERT INTO users (id, username, password_hash, role, permissions, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (user_id, username, password_hash, role.value, _json.dumps(perms), now, now),
            )

        self._users[user_id] = {
            'username': username,
            'password': password_hash,
            'role': role,
            'permissions': perms,
            'created_at': now,
        }

        logger.info(f"用户 {username} 已注册，ID: {user_id}")
        return user_id

    def authenticate(self, username: str, password: str) -> str | None:
        for user_id, user in self._users.items():
            if user['username'] == username and self._verify_password(password, user['password']):
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

            if check_blacklist and token_payload.jti and self.blacklist.contains(token_payload.jti):
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


def reset_jwt_auth() -> None:
    """Clear process-wide JWTAuth singleton (tests / secret rotation)."""
    global _jwt_auth
    _jwt_auth = None


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
