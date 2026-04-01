"""
Gateway 模块 - 统一入口和消息路由
借鉴 OpenClaw 架构设计
- WebSocket 服务器作为控制平面
- 消息路由和分发
- 设备配对与认证
- 事件广播机制
- Binding Router 最具体匹配优先
- Agent 隔离管理
"""
from .agent_isolation import AgentIsolationManager
from .models import (
    AgentInfo,
    BindingRule,
    DeviceInfo,
    DevicePairingRequest,
    DevicePairingResponse,
    GatewayEvent,
    GatewayMessage,
    GatewayResponse,
)
from .binding import BindingManager
from .router import MessageRouter
from .server import GatewayServer
from .session import GatewaySessionManager

_gateway_server = None
_message_router = None
_session_manager = None
_binding_manager = None


def get_gateway_server() -> GatewayServer:
    global _gateway_server
    if _gateway_server is None:
        _gateway_server = GatewayServer()
    return _gateway_server


def get_message_router() -> MessageRouter:
    global _message_router
    if _message_router is None:
        _message_router = MessageRouter()
    return _message_router


def get_gateway_session_manager() -> GatewaySessionManager:
    global _session_manager
    if _session_manager is None:
        _session_manager = GatewaySessionManager()
    return _session_manager


def get_binding_manager() -> BindingManager:
    global _binding_manager
    if _binding_manager is None:
        _binding_manager = BindingManager()
    return _binding_manager


__all__ = [
    "GatewayServer",
    "MessageRouter",
    "GatewaySessionManager",
    "BindingManager",
    "AgentIsolationManager",
    "GatewayMessage",
    "GatewayResponse",
    "GatewayEvent",
    "DeviceInfo",
    "DevicePairingRequest",
    "DevicePairingResponse",
    "BindingRule",
    "AgentInfo",
    "get_gateway_server",
    "get_message_router",
    "get_gateway_session_manager",
    "get_binding_manager",
]
