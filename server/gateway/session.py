"""
Gateway 会话管理

管理设备会话、订阅和状态
"""
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class DeviceSession:
    """设备会话"""
    device_id: str
    connected_at: datetime = field(default_factory=datetime.now)
    last_activity: datetime = field(default_factory=datetime.now)
    subscribed_events: set[str] = field(default_factory=set)
    metadata: dict[str, Any] = field(default_factory=dict)

    def is_expired(self, timeout_seconds: int = 300) -> bool:
        """检查会话是否过期"""
        elapsed = (datetime.now() - self.last_activity).total_seconds()
        return elapsed > timeout_seconds

    def touch(self):
        """更新活动时间"""
        self.last_activity = datetime.now()


class GatewaySessionManager:
    """
    Gateway 会话管理器
    
    功能:
    - 设备会话管理
    - 事件订阅管理
    - 会话状态持久化
    - 过期会话清理
    """

    def __init__(self, session_timeout: int = 300):
        self._sessions: dict[str, DeviceSession] = {}
        self._session_timeout = session_timeout

        self._event_subscriptions: dict[str, set[str]] = {}
        self._agent_sessions: dict[str, set[str]] = {}

    def create_session(self, device_id: str, metadata: dict[str, Any] | None = None) -> DeviceSession:
        """创建设备会话"""
        session = DeviceSession(
            device_id=device_id,
            metadata=metadata or {},
        )
        self._sessions[device_id] = session
        logger.debug(f"创建会话: {device_id}")
        return session

    def get_session(self, device_id: str) -> DeviceSession | None:
        """获取设备会话"""
        session = self._sessions.get(device_id)
        if session:
            session.touch()
        return session

    def update_session(self, device_id: str, metadata: dict[str, Any]) -> bool:
        """更新会话元数据"""
        session = self._sessions.get(device_id)
        if session:
            session.metadata.update(metadata)
            session.touch()
            return True
        return False

    def remove_session(self, device_id: str) -> bool:
        """移除会话"""
        if device_id in self._sessions:
            del self._sessions[device_id]

            for event_type in list(self._event_subscriptions.keys()):
                self._event_subscriptions[event_type].discard(device_id)

            for agent_id in list(self._agent_sessions.keys()):
                self._agent_sessions[agent_id].discard(device_id)

            logger.debug(f"移除会话: {device_id}")
            return True
        return False

    def subscribe_events(self, device_id: str, event_types: list[str]):
        """订阅事件"""
        session = self._sessions.get(device_id)
        if not session:
            return

        for event_type in event_types:
            if event_type not in self._event_subscriptions:
                self._event_subscriptions[event_type] = set()
            self._event_subscriptions[event_type].add(device_id)
            session.subscribed_events.add(event_type)

        logger.debug(f"设备 {device_id} 订阅事件: {event_types}")

    def unsubscribe_events(self, device_id: str, event_types: list[str]):
        """取消订阅事件"""
        session = self._sessions.get(device_id)
        if not session:
            return

        for event_type in event_types:
            if event_type in self._event_subscriptions:
                self._event_subscriptions[event_type].discard(device_id)
            session.subscribed_events.discard(event_type)

        logger.debug(f"设备 {device_id} 取消订阅事件: {event_types}")

    def get_subscribers(self, event_type: str) -> set[str]:
        """获取事件订阅者"""
        return self._event_subscriptions.get(event_type, set()).copy()

    def bind_agent(self, device_id: str, agent_id: str):
        """绑定设备到 Agent"""
        if agent_id not in self._agent_sessions:
            self._agent_sessions[agent_id] = set()
        self._agent_sessions[agent_id].add(device_id)

        session = self._sessions.get(device_id)
        if session:
            session.metadata["bound_agent"] = agent_id

        logger.debug(f"设备 {device_id} 绑定到 Agent {agent_id}")

    def unbind_agent(self, device_id: str, agent_id: str):
        """解绑设备与 Agent"""
        if agent_id in self._agent_sessions:
            self._agent_sessions[agent_id].discard(device_id)

        session = self._sessions.get(device_id)
        if session and session.metadata.get("bound_agent") == agent_id:
            del session.metadata["bound_agent"]

    def get_agent_devices(self, agent_id: str) -> set[str]:
        """获取 Agent 的所有绑定设备"""
        return self._agent_sessions.get(agent_id, set()).copy()

    def cleanup_device(self, device_id: str):
        """清理设备相关的所有资源"""
        self.remove_session(device_id)
        logger.info(f"清理设备资源: {device_id}")

    def cleanup_expired(self) -> int:
        """清理过期会话"""
        expired_devices = [
            device_id for device_id, session in self._sessions.items()
            if session.is_expired(self._session_timeout)
        ]

        for device_id in expired_devices:
            self.remove_session(device_id)

        if expired_devices:
            logger.info(f"清理过期会话: {len(expired_devices)} 个")

        return len(expired_devices)

    def get_all_sessions(self) -> dict[str, DeviceSession]:
        """获取所有会话"""
        return self._sessions.copy()

    def get_active_sessions(self) -> list[DeviceSession]:
        """获取活跃会话"""
        return [
            session for session in self._sessions.values()
            if not session.is_expired(self._session_timeout)
        ]

    def get_stats(self) -> dict[str, Any]:
        """获取统计信息"""
        active_count = len(self.get_active_sessions())
        total_subscriptions = sum(
            len(devices) for devices in self._event_subscriptions.values()
        )

        return {
            "total_sessions": len(self._sessions),
            "active_sessions": active_count,
            "expired_sessions": len(self._sessions) - active_count,
            "event_types": len(self._event_subscriptions),
            "total_subscriptions": total_subscriptions,
            "agents_with_bindings": len(self._agent_sessions),
        }

    def export_session_data(self, device_id: str) -> dict[str, Any] | None:
        """导出会话数据"""
        session = self._sessions.get(device_id)
        if not session:
            return None

        return {
            "device_id": session.device_id,
            "connected_at": session.connected_at.isoformat(),
            "last_activity": session.last_activity.isoformat(),
            "subscribed_events": list(session.subscribed_events),
            "metadata": session.metadata,
        }

    def import_session_data(self, data: dict[str, Any]) -> DeviceSession:
        """导入会话数据"""
        session = DeviceSession(
            device_id=data["device_id"],
            connected_at=datetime.fromisoformat(data["connected_at"]),
            last_activity=datetime.fromisoformat(data["last_activity"]),
            subscribed_events=set(data.get("subscribed_events", [])),
            metadata=data.get("metadata", {}),
        )
        self._sessions[session.device_id] = session
        return session


_session_manager: GatewaySessionManager | None = None


def get_gateway_session_manager() -> GatewaySessionManager:
    """获取会话管理器单例"""
    global _session_manager
    if _session_manager is None:
        _session_manager = GatewaySessionManager()
    return _session_manager
