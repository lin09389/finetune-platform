"""
JWT 认证模块 - 用户身份验证和授�?
功能�?- JWT Token 生成和验�?- Access Token + Refresh Token 机制
- Token 黑名单（注销支持�?- 权限角色系统
- 自动续期

配置示例�?    JWT_SECRET_KEY = "your-secret-key"  # 或使用环境变�?    JWT_ALGORITHM = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES = 30
    REFRESH_TOKEN_EXPIRE_DAYS = 7
"""
import jwt
import uuid
import hashlib
import os
import time
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List, Set
from dataclasses import dataclass, field
from enum import Enum
import logging
from functools import wraps

logger = logging.getLogger(__name__)


class Role(str, Enum):
    """用户角色"""
    USER = "user"
    ADMIN = "admin"
    SUPER_ADMIN = "super_admin"


# 角色权限层级
ROLE_HIERARCHY: Dict[Role, int] = {
    Role.USER: 1,
    Role.ADMIN: 10,
    Role.SUPER_ADMIN: 100,
}


@dataclass
class TokenPair:
    """Token �?""
    access_token: str
    refresh_token: str
    token_type: str = "Bearer"
    expires_in: int = 1800  # �?    
    def to_dict(self) -> Dict:
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
    permissions: List[str] = field(default_factory=list)
    exp: Optional[datetime] = None
    iat: Optional[datetime] = None
    jti: Optional[str] = None  # Token ID（用于黑名单�?    
    def to_dict(self) -> Dict[str, Any]:
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
    def from_dict(cls, data: Dict) -> 'TokenPayload':
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
    """Token 黑名单（内存存储�?""
    
    def __init__(self):
        # jti -> expire_time
        self._blacklist: Dict[str, float] = {}
    
    def add(self, jti: str, expire_time: datetime):
        """添加 Token 到黑名单"""
        self._blacklist[jti] = expire_time.timestamp()
        logger.info(f"Token {jti} 已加入黑名单")
    
    def contains(self, jti: str) -> bool:
        """检�?Token 是否在黑名单�?""
        if jti not in self._blacklist:
            return False
        
        # 检查是否已过期
        if time.time() > self._blacklist[jti]:
            del self._blacklist[jti]
            return False
        
        return True
    
    def cleanup(self):
        """清理过期条目"""
        current_time = time.time()
        expired = [
            jti for jti, exp in self._blacklist.items()
            if current_time > exp
        ]
        for jti in expired:
            del self._blacklist[jti]
    
    def get_stats(self) -> Dict:
        return {
            'total_blacklisted': len(self._blacklist),
            'active_blacklist': sum(
                1 for exp in self._blacklist.values()
                if time.time() < exp
            )
        }


class JWTAuth:
    """JWT 认证管理�?""

    def __init__(
        self,
        secret_key: Optional[str] = None,
        algorithm: str = "HS256",
        access_token_expire_minutes: int = 30,
        refresh_token_expire_days: int = 7,
        issuer: str = "finetune-platform"
    ):
        """
        初始�?JWT 认证

        Args:
            secret_key: 密钥（默认从环境变量读取�?            algorithm: 加密算法
            access_token_expire_minutes: Access Token 过期时间（分钟）
            refresh_token_expire_days: Refresh Token 过期时间（天�?            issuer: 签发�?        """
        self.secret_key = secret_key or os.environ.get('JWT_SECRET_KEY')
        
        if not self.secret_key:
            # 生成临时密钥（生产环境应使用环境变量�?            self.secret_key = self._generate_secret()
            logger.warning("使用自动生成�?JWT 密钥，生产环境请设置 JWT_SECRET_KEY 环境变量")
        
        self.algorithm = algorithm
        self.access_token_expire = timedelta(minutes=access_token_expire_minutes)
        self.refresh_token_expire = timedelta(days=refresh_token_expire_days)
        self.issuer = issuer
        
        # Token 黑名�?        self.blacklist = TokenBlacklist()
        
        # 用户数据库（示例，实际应使用数据库）
        self._users: Dict[str, Dict] = {}
        
        logger.info(f"JWT 认证已初始化，算法：{algorithm}")

    def _generate_secret(self) -> str:
        """生成随机密钥"""
        return uuid.uuid4().hex + uuid.uuid4().hex

    def _hash_password(self, password: str) -> str:
        """密码哈希"""
        return hashlib.sha256(password.encode()).hexdigest()

    def register_user(
        self,
        username: str,
        password: str,
        role: Role = Role.USER,
        permissions: Optional[List[str]] = None
    ) -> Optional[str]:
        """
        注册用户

        Args:
            username: 用户�?            password: 密码
            role: 角色
            permissions: 权限列表

        Returns:
            用户 ID，如果用户名已存在则返回 None
        """
        # 检查用户名是否存在
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

    def authenticate(self, username: str, password: str) -> Optional[str]:
        """
        验证用户凭据

        Args:
            username: 用户�?            password: 密码

        Returns:
            用户 ID，验证失败返�?None
        """
        password_hash = self._hash_password(password)
        
        for user_id, user in self._users.items():
            if user['username'] == username and user['password'] == password_hash:
                return user_id
        
        logger.warning(f"用户 {username} 认证失败")
        return None

    def create_token_pair(
        self,
        user_id: str,
        role: Optional[Role] = None,
        permissions: Optional[List[str]] = None
    ) -> TokenPair:
        """
        创建 Token �?
        Args:
            user_id: 用户 ID
            role: 角色
            permissions: 权限列表

        Returns:
            TokenPair
        """
        user = self._users.get(user_id)
        if not user:
            raise ValueError(f"用户不存在：{user_id}")
        
        now = datetime.now()
        
        # Access Token
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
        
        # Refresh Token（更长过期时间，更少权限�?        refresh_payload = TokenPayload(
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
        """
        验证 Token

        Args:
            token: JWT Token
            check_blacklist: 是否检查黑名单

        Returns:
            TokenPayload

        Raises:
            jwt.InvalidTokenError: Token 无效
            ValueError: Token 在黑名单�?        """
        try:
            payload = jwt.decode(
                token,
                self.secret_key,
                algorithms=[self.algorithm],
                options={'verify_exp': True}
            )
            
            token_payload = TokenPayload.from_dict(payload)
            
            # 检查黑名单
            if check_blacklist and token_payload.jti:
                if self.blacklist.contains(token_payload.jti):
                    raise ValueError("Token 已被注销")
            
            return token_payload
            
        except jwt.ExpiredSignatureError:
            logger.warning("Token 已过�?)
            raise
        except jwt.InvalidTokenError as e:
            logger.warning(f"Token 无效：{e}")
            raise

    def refresh_access_token(self, refresh_token: str) -> TokenPair:
        """
        使用 Refresh Token 刷新 Access Token

        Args:
            refresh_token: Refresh Token

        Returns:
            新的 TokenPair

        Raises:
            ValueError: Refresh Token 无效或已过期
        """
        # 验证 Refresh Token
        payload = self.verify_token(refresh_token)
        
        # 检查是否是 Refresh Token（没�?permissions�?        if payload.permissions:
            raise ValueError("无效�?Refresh Token")
        
        # 将旧 Refresh Token 加入黑名�?        if payload.jti:
            self.blacklist.add(payload.jti, payload.exp)
        
        # 创建新的 Token �?        return self.create_token_pair(
            user_id=payload.user_id,
            role=payload.role
        )

    def logout(self, access_token: str, refresh_token: Optional[str] = None):
        """
        注销（将 Token 加入黑名单）

        Args:
            access_token: Access Token
            refresh_token: Refresh Token（可选）
        """
        try:
            payload = self.verify_token(access_token, check_blacklist=False)
            if payload.jti:
                self.blacklist.add(payload.jti, payload.exp)
        except jwt.InvalidTokenError:
            pass  # Token 已无效，忽略
        
        if refresh_token:
            try:
                payload = self.verify_token(refresh_token, check_blacklist=False)
                if payload.jti:
                    self.blacklist.add(payload.jti, payload.exp)
            except jwt.InvalidTokenError:
                pass
        
        logger.info(f"用户已注销")

    def has_permission(self, token_payload: TokenPayload, permission: str) -> bool:
        """检查用户是否有指定权限"""
        # 管理员拥有所有权�?        if token_payload.role in [Role.ADMIN, Role.SUPER_ADMIN]:
            return True
        
        return permission in token_payload.permissions

    def has_role(self, token_payload: TokenPayload, min_role: Role) -> bool:
        """检查用户角色是否达到最低要�?""
        return ROLE_HIERARCHY.get(token_payload.role, 0) >= ROLE_HIERARCHY.get(min_role, 0)

    def get_user_info(self, user_id: str) -> Optional[Dict]:
        """获取用户信息（不包含密码�?""
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

    def get_stats(self) -> Dict:
        """获取统计信息"""
        return {
            'total_users': len(self._users),
            'blacklist_stats': self.blacklist.get_stats(),
            'access_token_expire_minutes': int(self.access_token_expire.total_seconds() / 60),
            'refresh_token_expire_days': self.refresh_token_expire.days
        }


# FastAPI 依赖注入
def get_current_user(token: str) -> TokenPayload:
    """获取当前用户（用�?FastAPI 依赖注入�?""
    auth = get_jwt_auth()
    return auth.verify_token(token)


def require_role(min_role: Role):
    """
    角色要求装饰�?    
    用法:
        @app.get("/admin")
        @require_role(Role.ADMIN)
        async def admin_endpoint(current_user: TokenPayload = Depends(get_current_user)):
            ...
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            current_user = kwargs.get('current_user')
            if not current_user:
                raise ValueError("未提供用户信�?)
            
            auth = get_jwt_auth()
            if not auth.has_role(current_user, min_role):
                from fastapi import HTTPException
                raise HTTPException(403, detail="权限不足")
            
            return await func(*args, **kwargs)
        return wrapper
    return decorator


# 全局单例
_jwt_auth: Optional[JWTAuth] = None


def get_jwt_auth() -> JWTAuth:
    """获取 JWT 认证单例"""
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
    """初始�?JWT 认证"""
    global _jwt_auth
    _jwt_auth = JWTAuth(
        secret_key=secret_key,
        access_token_expire_minutes=access_token_expire_minutes,
        refresh_token_expire_days=refresh_token_expire_days
    )
    return _jwt_auth
