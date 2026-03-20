"""
设备认证管理模块
"""
import secrets
import hashlib
import logging
from typing import Dict, List, Optional, Any, Set
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
import json

logger = logging.getLogger(__name__)


class DeviceType(str, Enum):
    """设备类型"""
    WEB = "web"
    DESKTOP = "desktop"
    MOBILE = "mobile"
    CLI = "cli"
    API = "api"


class DeviceStatus(str, Enum):
    """设备状态"""
    ACTIVE = "active"
    INACTIVE = "inactive"
    SUSPENDED = "suspended"
    REVOKED = "revoked"


class PermissionLevel(str, Enum):
    """权限级别"""
    ADMIN = "admin"
    USER = "user"
    GUEST = "guest"
    READONLY = "readonly"


@dataclass
class DeviceCredentials:
    """设备凭证"""
    device_id: str
    token: str
    secret: str
    device_type: DeviceType = DeviceType.WEB
    device_name: str = ""
    status: DeviceStatus = DeviceStatus.ACTIVE
    created_at: datetime = field(default_factory=datetime.now)
    last_active: datetime = field(default_factory=datetime.now)
    expires_at: Optional[datetime] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DevicePermissions:
    """设备权限"""
    device_id: str
    level: PermissionLevel = PermissionLevel.USER
    allowed_actions: List[str] = field(default_factory=list)
    denied_actions: List[str] = field(default_factory=list)
    rate_limit: int = 100
    rate_window: int = 60


@dataclass
class Challenge:
    """挑战验证"""
    challenge_id: str
    device_id: str
    challenge_data: str
    created_at: datetime = field(default_factory=datetime.now)
    expires_at: datetime = field(default_factory=lambda: datetime.now() + timedelta(minutes=5))
    used: bool = False


class DeviceAuthManager:
    """
    设备认证管理器
    
    功能：
    - 设备注册与注销
    - Token 认证
    - 挑战-响应验证
    - 权限管理
    """
    
    def __init__(self, secret_key: Optional[str] = None):
        self._secret_key = secret_key or secrets.token_hex(32)
        self._devices: Dict[str, DeviceCredentials] = {}
        self._permissions: Dict[str, DevicePermissions] = {}
        self._challenges: Dict[str, Challenge] = {}
        self._token_index: Dict[str, str] = {}
    
    async def register_device(
        self,
        device_id: str,
        device_type: DeviceType,
        device_name: str = "",
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """注册设备"""
        token = secrets.token_urlsafe(32)
        secret = secrets.token_hex(16)
        
        credentials = DeviceCredentials(
            device_id=device_id,
            token=token,
            secret=secret,
            device_type=device_type,
            device_name=device_name,
            metadata=metadata or {}
        )
        
        self._devices[device_id] = credentials
        self._token_index[token] = device_id
        
        permissions = DevicePermissions(
            device_id=device_id,
            level=PermissionLevel.USER,
            allowed_actions=["chat", "inference", "read_models", "read_datasets"]
        )
        self._permissions[device_id] = permissions
        
        logger.info(f"设备注册成功: {device_id}")
        
        return {
            "device_id": device_id,
            "token": token,
            "secret": secret,
            "expires_at": credentials.expires_at.isoformat() if credentials.expires_at else None
        }
    
    def unregister_device(self, device_id: str) -> bool:
        """注销设备"""
        if device_id not in self._devices:
            return False
        
        credentials = self._devices[device_id]
        self._token_index.pop(credentials.token, None)
        
        del self._devices[device_id]
        self._permissions.pop(device_id, None)
        
        logger.info(f"设备注销成功: {device_id}")
        return True
    
    def authenticate_device(self, device_id: str, token: str) -> bool:
        """Token 认证"""
        credentials = self._devices.get(device_id)
        if not credentials:
            return False
        
        if credentials.token != token:
            return False
        
        if credentials.status != DeviceStatus.ACTIVE:
            return False
        
        if credentials.expires_at and credentials.expires_at < datetime.now():
            return False
        
        credentials.last_active = datetime.now()
        return True
    
    def authenticate_by_token(self, token: str) -> Optional[str]:
        """通过 Token 获取设备 ID"""
        device_id = self._token_index.get(token)
        if not device_id:
            return None
        
        credentials = self._devices.get(device_id)
        if not credentials:
            return None
        
        if credentials.status != DeviceStatus.ACTIVE:
            return None
        
        if credentials.expires_at and credentials.expires_at < datetime.now():
            return None
        
        credentials.last_active = datetime.now()
        return device_id
    
    def create_challenge(self, device_id: str) -> Optional[Dict[str, Any]]:
        """创建挑战"""
        if device_id not in self._devices:
            return None
        
        challenge = self._generate_challenge(device_id)
        self._challenges[challenge.challenge_id] = challenge
        
        return {
            "challenge_id": challenge.challenge_id,
            "challenge_data": challenge.challenge_data,
            "expires_at": challenge.expires_at.isoformat()
        }
    
    def _generate_challenge(self, device_id: str) -> Challenge:
        """生成挑战"""
        challenge_id = secrets.token_urlsafe(16)
        challenge_data = secrets.token_hex(32)
        
        return Challenge(
            challenge_id=challenge_id,
            device_id=device_id,
            challenge_data=challenge_data
        )
    
    def verify_challenge(
        self,
        device_id: str,
        challenge_id: str,
        signed_response: str
    ) -> bool:
        """验证挑战响应"""
        challenge = self._challenges.get(challenge_id)
        if not challenge:
            return False
        
        if challenge.device_id != device_id:
            return False
        
        if challenge.used:
            return False
        
        if challenge.expires_at < datetime.now():
            return False
        
        credentials = self._devices.get(device_id)
        if not credentials:
            return False
        
        expected_response = hashlib.sha256(
            f"{challenge.challenge_data}{credentials.secret}".encode()
        ).hexdigest()
        
        if signed_response != expected_response:
            return False
        
        challenge.used = True
        return True
    
    def check_permission(self, device_id: str, action: str) -> bool:
        """检查权限"""
        permissions = self._permissions.get(device_id)
        if not permissions:
            return False
        
        if action in permissions.denied_actions:
            return False
        
        if "*" in permissions.allowed_actions:
            return True
        
        if action in permissions.allowed_actions:
            return True
        
        if permissions.level == PermissionLevel.ADMIN:
            return True
        
        return False
    
    def grant_permission(self, device_id: str, action: str) -> bool:
        """授予权限"""
        permissions = self._permissions.get(device_id)
        if not permissions:
            return False
        
        if action not in permissions.allowed_actions:
            permissions.allowed_actions.append(action)
        
        if action in permissions.denied_actions:
            permissions.denied_actions.remove(action)
        
        return True
    
    def revoke_permission(self, device_id: str, action: str) -> bool:
        """撤销权限"""
        permissions = self._permissions.get(device_id)
        if not permissions:
            return False
        
        if action in permissions.allowed_actions:
            permissions.allowed_actions.remove(action)
        
        if action not in permissions.denied_actions:
            permissions.denied_actions.append(action)
        
        return True
    
    def set_permission_level(self, device_id: str, level: PermissionLevel) -> bool:
        """设置权限级别"""
        permissions = self._permissions.get(device_id)
        if not permissions:
            return False
        
        permissions.level = level
        return True
    
    def get_device_info(self, device_id: str) -> Optional[Dict[str, Any]]:
        """获取设备信息"""
        credentials = self._devices.get(device_id)
        if not credentials:
            return None
        
        return {
            "device_id": credentials.device_id,
            "device_type": credentials.device_type.value,
            "device_name": credentials.device_name,
            "status": credentials.status.value,
            "created_at": credentials.created_at.isoformat(),
            "last_active": credentials.last_active.isoformat(),
            "expires_at": credentials.expires_at.isoformat() if credentials.expires_at else None,
            "metadata": credentials.metadata
        }
    
    def get_device_permissions(self, device_id: str) -> Optional[Dict[str, Any]]:
        """获取设备权限"""
        permissions = self._permissions.get(device_id)
        if not permissions:
            return None
        
        return {
            "device_id": permissions.device_id,
            "level": permissions.level.value,
            "allowed_actions": permissions.allowed_actions,
            "denied_actions": permissions.denied_actions,
            "rate_limit": permissions.rate_limit,
            "rate_window": permissions.rate_window
        }
    
    def list_devices(self, status: Optional[DeviceStatus] = None) -> List[Dict[str, Any]]:
        """列出设备"""
        devices = []
        
        for device_id, credentials in self._devices.items():
            if status and credentials.status != status:
                continue
            
            devices.append(self.get_device_info(device_id))
        
        return devices
    
    def suspend_device(self, device_id: str) -> bool:
        """暂停设备"""
        credentials = self._devices.get(device_id)
        if not credentials:
            return False
        
        credentials.status = DeviceStatus.SUSPENDED
        return True
    
    def activate_device(self, device_id: str) -> bool:
        """激活设备"""
        credentials = self._devices.get(device_id)
        if not credentials:
            return False
        
        credentials.status = DeviceStatus.ACTIVE
        return True
    
    def revoke_device(self, device_id: str) -> bool:
        """吊销设备"""
        credentials = self._devices.get(device_id)
        if not credentials:
            return False
        
        credentials.status = DeviceStatus.REVOKED
        return True
    
    def cleanup_expired_challenges(self) -> int:
        """清理过期挑战"""
        now = datetime.now()
        expired = [
            cid for cid, challenge in self._challenges.items()
            if challenge.expires_at < now or challenge.used
        ]
        
        for cid in expired:
            del self._challenges[cid]
        
        return len(expired)


_auth_manager: Optional[DeviceAuthManager] = None


def get_auth_manager() -> DeviceAuthManager:
    """获取认证管理器单例"""
    global _auth_manager
    if _auth_manager is None:
        _auth_manager = DeviceAuthManager()
    return _auth_manager
