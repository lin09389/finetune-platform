"""
Gateway 服务器 - WebSocket 控制平面

借鉴 OpenClaw 架构设计
- WebSocket 服务器作为统一入口
- 消息路由和分发
- 设备配对与认证
- 事件广播机制
"""
import asyncio
import json
import logging
import uuid
from collections.abc import Callable
from datetime import datetime
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from .models import (
    DeviceInfo,
    DevicePairingRequest,
    DevicePairingResponse,
    DeviceStatus,
    DeviceType,
    GatewayEvent,
    GatewayMessage,
    GatewayResponse,
)
from .router import MessageRouter
from .session import GatewaySessionManager

logger = logging.getLogger(__name__)


class GatewayServer:
    """
    Gateway 服务器

    功能:
    - WebSocket 连接管理
    - 设备配对与认证
    - 消息路由
    - 事件广播
    - 心跳检测
    """

    def __init__(self, config: dict[str, Any] | None = None):
        self.config = config or {}
        self.host = self.config.get("host", "127.0.0.1")
        self.port = self.config.get("port", 18789)

        self._connections: dict[str, WebSocket] = {}
        self._devices: dict[str, DeviceInfo] = {}
        self._pending_pairings: dict[str, asyncio.Future] = {}

        self._router = MessageRouter()
        self._session_manager = GatewaySessionManager()

        self._heartbeat_interval = self.config.get("heartbeat_interval", 30)
        self._connection_timeout = self.config.get("connection_timeout", 300)

        self._is_running = False
        self._background_tasks: set[asyncio.Task] = set()

        self._event_handlers: dict[str, Callable] = {}
        self._message_handlers: dict[str, Callable] = {}

        self._register_default_handlers()

    def _register_default_handlers(self):
        """注册默认处理器"""
        self._message_handlers["ping"] = self._handle_ping
        self._message_handlers["pair"] = self._handle_pair
        self._message_handlers["auth"] = self._handle_auth
        self._message_handlers["subscribe"] = self._handle_subscribe
        self._message_handlers["unsubscribe"] = self._handle_unsubscribe

    async def start(self):
        """启动 Gateway 服务器"""
        if self._is_running:
            logger.warning("Gateway 服务器已在运行")
            return

        self._is_running = True

        heartbeat_task = asyncio.create_task(self._heartbeat_loop())
        self._background_tasks.add(heartbeat_task)
        heartbeat_task.add_done_callback(self._background_tasks.discard)

        cleanup_task = asyncio.create_task(self._cleanup_loop())
        self._background_tasks.add(cleanup_task)
        cleanup_task.add_done_callback(self._background_tasks.discard)

        logger.info(f"Gateway 服务器已启动: ws://{self.host}:{self.port}")

    async def stop(self):
        """停止 Gateway 服务器"""
        self._is_running = False

        for task in self._background_tasks:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        for device_id, ws in self._connections.items():
            try:
                await ws.close(code=1001, reason="Server shutting down")
            except Exception:
                pass

        self._connections.clear()
        self._devices.clear()

        logger.info("Gateway 服务器已停止")

    async def handle_websocket(self, websocket: WebSocket, device_id: str | None = None):
        """处理 WebSocket 连接"""
        await websocket.accept()

        if not device_id:
            device_id = f"device_{uuid.uuid4().hex[:8]}"

        self._connections[device_id] = websocket

        device_info = DeviceInfo(
            id=device_id,
            type=DeviceType.HEADLESS,
            name=f"Device {device_id[:8]}",
            status=DeviceStatus.PAIRING,
            last_seen=datetime.now(),
        )
        self._devices[device_id] = device_info

        logger.info(f"设备连接: {device_id}")

        try:
            await self._send_pairing_request(websocket, device_id)

            async for message in websocket.iter_text():
                try:
                    await self._handle_message(device_id, message)
                except Exception as e:
                    logger.error(f"处理消息失败: {e}", exc_info=True)
                    await self._send_error(websocket, str(e))

        except WebSocketDisconnect:
            logger.info(f"设备断开连接: {device_id}")
        except Exception as e:
            logger.error(f"WebSocket 错误: {e}", exc_info=True)
        finally:
            await self._cleanup_device(device_id)

    async def _handle_message(self, device_id: str, message: str):
        """处理接收到的消息"""
        try:
            data = json.loads(message)
            msg = GatewayMessage(**data)
        except (json.JSONDecodeError, ValidationError) as e:
            logger.warning(f"无效消息格式: {e}")
            return

        if device_id in self._devices:
            self._devices[device_id].last_seen = datetime.now()

        handler = self._message_handlers.get(msg.action)
        if handler:
            response = await handler(device_id, msg)
            if response:
                await self._send_response(device_id, msg, response)
        else:
            response = await self._router.route(msg)
            await self._send_response(device_id, msg, response)

    async def _handle_ping(self, device_id: str, msg: GatewayMessage) -> dict[str, Any]:
        """处理心跳"""
        return {"pong": True, "timestamp": datetime.now().isoformat()}

    async def _handle_pair(self, device_id: str, msg: GatewayMessage) -> dict[str, Any]:
        """处理设备配对"""
        try:
            request = DevicePairingRequest(**msg.payload)

            if device_id in self._devices:
                self._devices[device_id].type = request.device_type
                self._devices[device_id].name = request.device_name
                self._devices[device_id].status = DeviceStatus.PAIRED

            token = self._generate_device_token(device_id)

            return DevicePairingResponse(
                success=True,
                device_id=device_id,
                token=token,
                expires_at=None,
                message="配对成功"
            ).model_dump()

        except Exception as e:
            logger.error(f"配对失败: {e}")
            return DevicePairingResponse(
                success=False,
                device_id=device_id,
                message=str(e)
            ).model_dump()

    async def _handle_auth(self, device_id: str, msg: GatewayMessage) -> dict[str, Any]:
        """处理认证"""
        token = msg.payload.get("token")

        if self._verify_device_token(device_id, token):
            if device_id in self._devices:
                self._devices[device_id].status = DeviceStatus.PAIRED
            return {"authenticated": True, "device_id": device_id}

        return {"authenticated": False, "error": "Invalid token"}

    async def _handle_subscribe(self, device_id: str, msg: GatewayMessage) -> dict[str, Any]:
        """处理事件订阅"""
        events = msg.payload.get("events", [])
        self._session_manager.subscribe_events(device_id, events)
        return {"subscribed": events}

    async def _handle_unsubscribe(self, device_id: str, msg: GatewayMessage) -> dict[str, Any]:
        """处理取消订阅"""
        events = msg.payload.get("events", [])
        self._session_manager.unsubscribe_events(device_id, events)
        return {"unsubscribed": events}

    async def _send_pairing_request(self, websocket: WebSocket, device_id: str):
        """发送配对请求"""
        event = GatewayEvent(
            id=str(uuid.uuid4()),
            event_type="pairing_request",
            data={
                "device_id": device_id,
                "challenge": str(uuid.uuid4()),
                "timestamp": datetime.now().isoformat(),
            }
        )
        await websocket.send_text(event.model_dump_json())

    async def _send_response(self, device_id: str, msg: GatewayMessage, data: dict[str, Any]):
        """发送响应"""
        if device_id not in self._connections:
            return

        response = GatewayResponse(
            id=str(uuid.uuid4()),
            correlation_id=msg.id,
            success=data.get("success", True),
            data=data,
            error=data.get("error"),
        )

        try:
            await self._connections[device_id].send_text(response.model_dump_json())
        except Exception as e:
            logger.error(f"发送响应失败: {e}")

    async def _send_error(self, websocket: WebSocket, error: str):
        """发送错误消息"""
        response = GatewayResponse(
            id=str(uuid.uuid4()),
            correlation_id="",
            success=False,
            error=error,
        )
        await websocket.send_text(response.model_dump_json())

    async def broadcast_event(self, event: GatewayEvent):
        """广播事件到所有连接的设备"""
        message = event.model_dump_json()
        disconnected = []

        for device_id, ws in self._connections.items():
            try:
                await ws.send_text(message)
            except Exception:
                disconnected.append(device_id)

        for device_id in disconnected:
            await self._cleanup_device(device_id)

    async def send_to_device(self, device_id: str, event: GatewayEvent) -> bool:
        """发送事件到指定设备"""
        if device_id not in self._connections:
            return False

        try:
            await self._connections[device_id].send_text(event.model_dump_json())
            return True
        except Exception as e:
            logger.error(f"发送到设备失败: {e}")
            return False

    async def _cleanup_device(self, device_id: str):
        """清理断开连接的设备"""
        if device_id in self._connections:
            del self._connections[device_id]

        if device_id in self._devices:
            self._devices[device_id].status = DeviceStatus.OFFLINE

        self._session_manager.cleanup_device(device_id)

        logger.info(f"设备已清理: {device_id}")

    async def _heartbeat_loop(self):
        """心跳检测循环"""
        while self._is_running:
            try:
                await asyncio.sleep(self._heartbeat_interval)

                now = datetime.now()
                timeout_devices = []

                for device_id, device in self._devices.items():
                    elapsed = (now - device.last_seen).total_seconds()
                    if elapsed > self._connection_timeout:
                        timeout_devices.append(device_id)

                for device_id in timeout_devices:
                    logger.warning(f"设备超时断开: {device_id}")
                    await self._cleanup_device(device_id)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"心跳检测错误: {e}")

    async def _cleanup_loop(self):
        """定期清理循环"""
        while self._is_running:
            try:
                await asyncio.sleep(60)
                self._session_manager.cleanup_expired()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"清理循环错误: {e}")

    def _generate_device_token(self, device_id: str) -> str:
        """生成设备 Token"""
        import hashlib
        import secrets

        random_bytes = secrets.token_bytes(32)
        token = hashlib.sha256(random_bytes + device_id.encode()).hexdigest()
        return token

    def _verify_device_token(self, device_id: str, token: str) -> bool:
        """验证设备 Token"""
        return token is not None and len(token) == 64

    def register_message_handler(self, action: str, handler: Callable):
        """注册消息处理器"""
        self._message_handlers[action] = handler

    def register_event_handler(self, event_type: str, handler: Callable):
        """注册事件处理器"""
        self._event_handlers[event_type] = handler

    def get_device_info(self, device_id: str) -> DeviceInfo | None:
        """获取设备信息"""
        return self._devices.get(device_id)

    def get_all_devices(self) -> dict[str, DeviceInfo]:
        """获取所有设备"""
        return self._devices.copy()

    def get_stats(self) -> dict[str, Any]:
        """获取统计信息"""
        online = sum(1 for d in self._devices.values() if d.status == DeviceStatus.PAIRED)
        return {
            "total_connections": len(self._connections),
            "online_devices": online,
            "total_devices": len(self._devices),
            "is_running": self._is_running,
        }


_gateway_server: GatewayServer | None = None


def get_gateway_server() -> GatewayServer:
    """获取 Gateway 服务器单例"""
    global _gateway_server
    if _gateway_server is None:
        _gateway_server = GatewayServer()
    return _gateway_server
