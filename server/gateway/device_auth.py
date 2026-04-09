"""
Gateway device auth manager.
"""
import hashlib
import logging
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class DeviceType(str, Enum):
    WEB = "web"
    DESKTOP = "desktop"
    MOBILE = "mobile"
    CLI = "cli"
    API = "api"


class DeviceStatus(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    SUSPENDED = "suspended"
    REVOKED = "revoked"


class PermissionLevel(str, Enum):
    ADMIN = "admin"
    USER = "user"
    GUEST = "guest"
    READONLY = "readonly"


@dataclass
class DeviceCredentials:
    device_id: str
    token: str
    secret: str
    device_type: DeviceType = DeviceType.WEB
    device_name: str = ""
    status: DeviceStatus = DeviceStatus.ACTIVE
    created_at: datetime = field(default_factory=datetime.now)
    last_active: datetime = field(default_factory=datetime.now)
    expires_at: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class DevicePermissions:
    device_id: str
    level: PermissionLevel = PermissionLevel.USER
    allowed_actions: list[str] = field(default_factory=list)
    denied_actions: list[str] = field(default_factory=list)
    rate_limit: int = 100
    rate_window: int = 60


@dataclass
class Challenge:
    challenge_id: str
    device_id: str
    challenge_data: str
    created_at: datetime = field(default_factory=datetime.now)
    expires_at: datetime = field(default_factory=lambda: datetime.now() + timedelta(minutes=5))
    used: bool = False


class DeviceAuthManager:
    def __init__(self, secret_key: str | None = None):
        self._secret_key = secret_key or secrets.token_hex(32)
        self._devices: dict[str, DeviceCredentials] = {}
        self._permissions: dict[str, DevicePermissions] = {}
        self._challenges: dict[str, Challenge] = {}
        self._token_index: dict[str, str] = {}

    async def register_device(
        self,
        device_id: str,
        device_type: DeviceType,
        device_name: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        token = secrets.token_urlsafe(32)
        secret = secrets.token_hex(16)

        credentials = DeviceCredentials(
            device_id=device_id,
            token=token,
            secret=secret,
            device_type=device_type,
            device_name=device_name,
            metadata=metadata or {},
        )

        self._devices[device_id] = credentials
        self._token_index[token] = device_id
        self._permissions[device_id] = DevicePermissions(
            device_id=device_id,
            level=PermissionLevel.USER,
            allowed_actions=["chat", "inference", "read_models", "read_datasets"],
        )

        return {
            "device_id": device_id,
            "token": token,
            "secret": secret,
            "expires_at": credentials.expires_at.isoformat() if credentials.expires_at else None,
        }

    def unregister_device(self, device_id: str) -> bool:
        credentials = self._devices.get(device_id)
        if not credentials:
            return False

        self._token_index.pop(credentials.token, None)
        del self._devices[device_id]
        self._permissions.pop(device_id, None)
        return True

    def authenticate_device(self, device_id: str, token: str) -> bool:
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

    def authenticate_by_token(self, token: str) -> str | None:
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

    def create_challenge(self, device_id: str) -> dict[str, Any] | None:
        if device_id not in self._devices:
            return None

        challenge = Challenge(
            challenge_id=secrets.token_urlsafe(16),
            device_id=device_id,
            challenge_data=secrets.token_hex(32),
        )
        self._challenges[challenge.challenge_id] = challenge

        return {
            "challenge_id": challenge.challenge_id,
            "challenge_data": challenge.challenge_data,
            "expires_at": challenge.expires_at.isoformat(),
        }

    def verify_challenge(self, device_id: str, challenge_id: str, signed_response: str) -> bool:
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

        expected_response = hashlib.sha256(f"{challenge.challenge_data}{credentials.secret}".encode()).hexdigest()
        if signed_response != expected_response:
            return False

        challenge.used = True
        return True

    def check_permission(self, device_id: str, action: str) -> bool:
        permissions = self._permissions.get(device_id)
        if not permissions:
            return False

        if action in permissions.denied_actions:
            return False
        if permissions.level == PermissionLevel.ADMIN:
            return True
        if "*" in permissions.allowed_actions:
            return True
        return action in permissions.allowed_actions

    def set_permissions(
        self,
        device_id: str,
        level: PermissionLevel | None = None,
        allowed_actions: list[str] | None = None,
        denied_actions: list[str] | None = None,
        rate_limit: int | None = None,
        rate_window: int | None = None,
    ) -> bool:
        permissions = self._permissions.get(device_id)
        if not permissions:
            return False

        if level is not None:
            permissions.level = level
        if allowed_actions is not None:
            permissions.allowed_actions = list(allowed_actions)
        if denied_actions is not None:
            permissions.denied_actions = list(denied_actions)
        if rate_limit is not None:
            permissions.rate_limit = rate_limit
        if rate_window is not None:
            permissions.rate_window = rate_window
        return True

    def grant_permission(self, device_id: str, action: str) -> bool:
        permissions = self._permissions.get(device_id)
        if not permissions:
            return False
        if action not in permissions.allowed_actions:
            permissions.allowed_actions.append(action)
        if action in permissions.denied_actions:
            permissions.denied_actions.remove(action)
        return True

    def revoke_permission(self, device_id: str, action: str) -> bool:
        permissions = self._permissions.get(device_id)
        if not permissions:
            return False
        if action in permissions.allowed_actions:
            permissions.allowed_actions.remove(action)
        if action not in permissions.denied_actions:
            permissions.denied_actions.append(action)
        return True

    def set_permission_level(self, device_id: str, level: PermissionLevel) -> bool:
        return self.set_permissions(device_id=device_id, level=level)

    def get_device_info(self, device_id: str) -> dict[str, Any] | None:
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
            "metadata": credentials.metadata,
        }

    def get_device_permissions(self, device_id: str) -> dict[str, Any] | None:
        permissions = self._permissions.get(device_id)
        if not permissions:
            return None
        return {
            "device_id": permissions.device_id,
            "level": permissions.level.value,
            "allowed_actions": permissions.allowed_actions,
            "denied_actions": permissions.denied_actions,
            "rate_limit": permissions.rate_limit,
            "rate_window": permissions.rate_window,
        }

    def list_devices(self, status: DeviceStatus | None = None) -> list[dict[str, Any]]:
        devices: list[dict[str, Any]] = []
        for device_id, credentials in self._devices.items():
            if status and credentials.status != status:
                continue
            info = self.get_device_info(device_id)
            if info:
                devices.append(info)
        return devices

    def get_all_devices(self) -> list[dict[str, Any]]:
        return self.list_devices()

    def get_devices_by_type(self, device_type: DeviceType) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for device_id, credentials in self._devices.items():
            if credentials.device_type == device_type:
                info = self.get_device_info(device_id)
                if info:
                    result.append(info)
        return result

    def get_devices_by_status(self, status: DeviceStatus) -> list[dict[str, Any]]:
        return self.list_devices(status=status)

    def suspend_device(self, device_id: str) -> bool:
        credentials = self._devices.get(device_id)
        if not credentials:
            return False
        credentials.status = DeviceStatus.SUSPENDED
        return True

    def activate_device(self, device_id: str) -> bool:
        credentials = self._devices.get(device_id)
        if not credentials:
            return False
        credentials.status = DeviceStatus.ACTIVE
        return True

    def revoke_device(self, device_id: str) -> bool:
        credentials = self._devices.get(device_id)
        if not credentials:
            return False
        credentials.status = DeviceStatus.REVOKED
        return True

    def cleanup_expired_challenges(self) -> int:
        now = datetime.now()
        expired = [cid for cid, challenge in self._challenges.items() if challenge.expires_at < now or challenge.used]
        for cid in expired:
            del self._challenges[cid]
        return len(expired)

    def get_stats(self) -> dict[str, Any]:
        total = len(self._devices)
        active = sum(1 for d in self._devices.values() if d.status == DeviceStatus.ACTIVE)
        suspended = sum(1 for d in self._devices.values() if d.status == DeviceStatus.SUSPENDED)
        revoked = sum(1 for d in self._devices.values() if d.status == DeviceStatus.REVOKED)
        return {
            "total_devices": total,
            "online_devices": active,
            "active_devices": active,
            "suspended_devices": suspended,
            "revoked_devices": revoked,
            "challenge_count": len(self._challenges),
        }


_auth_manager: DeviceAuthManager | None = None


def get_auth_manager() -> DeviceAuthManager:
    global _auth_manager
    if _auth_manager is None:
        _auth_manager = DeviceAuthManager()
    return _auth_manager


get_device_auth_manager = get_auth_manager
