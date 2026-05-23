"""Gateway REST API routes."""

import logging
import os
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, WebSocket
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from gateway import (
    get_binding_manager,
    get_gateway_server,
    get_gateway_session_manager,
    get_message_router,
)
from gateway.agent_isolation import get_isolation_manager
from gateway.cross_agent import MessagePriority, MessageType, get_cross_agent_communicator
from gateway.device_auth import DeviceStatus, DeviceType, PermissionLevel, get_device_auth_manager
from pydantic import BaseModel, Field

security = HTTPBearer(auto_error=False)


async def require_admin_auth(
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    """要求管理员认证"""
    if os.getenv("ENABLE_AUTH", "false").lower() != "true":
        return True

    if not credentials:
        raise HTTPException(status_code=401, detail="需要认证")

    from security.jwt_auth import Role, get_jwt_auth
    auth = get_jwt_auth()
    try:
        payload = auth.verify_token(credentials.credentials)
        if not auth.has_role(payload, Role.ADMIN):
            raise HTTPException(status_code=403, detail="需要管理员权限")
        return True
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=401, detail="Token 无效或已过期")

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/gateway", tags=["Gateway"])


def _serialize_device(auth_manager, device: dict[str, Any]) -> dict[str, Any]:
    permissions = auth_manager.get_device_permissions(device["device_id"]) or {}
    return {
        "id": device["device_id"],
        "device_id": device["device_id"],
        "name": device.get("device_name") or device["device_id"],
        "device_name": device.get("device_name") or device["device_id"],
        "type": device.get("device_type", "unknown"),
        "device_type": device.get("device_type", "unknown"),
        "status": device.get("status", "unknown"),
        "created_at": device.get("created_at"),
        "last_seen": device.get("last_active"),
        "last_active": device.get("last_active"),
        "expires_at": device.get("expires_at"),
        "metadata": device.get("metadata", {}),
        "permissions": permissions.get("allowed_actions", []),
        "permission_level": permissions.get("level"),
        "denied_actions": permissions.get("denied_actions", []),
        "rate_limit": permissions.get("rate_limit"),
        "rate_window": permissions.get("rate_window"),
    }


class DeviceRegisterRequest(BaseModel):
    device_id: str | None = None
    device_type: str = "web"
    device_name: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class DeviceAuthRequest(BaseModel):
    device_id: str
    token: str


class ChallengeVerifyRequest(BaseModel):
    device_id: str
    challenge_id: str
    signed_response: str


class MessageSendRequest(BaseModel):
    target_agent: str
    message_type: str = "request"
    priority: str = "normal"
    payload: dict[str, Any] = Field(default_factory=dict)
    correlation_id: str | None = None
    timeout: int | None = None


class BindingRuleRequest(BaseModel):
    agent_id: str
    priority: int = 0
    peer_id: str | None = None
    guild_id: str | None = None
    channel_id: str | None = None
    team_id: str | None = None
    account_id: str | None = None
    roles: list[str] | None = None
    enabled: bool = True


class SpawnAgentRequest(BaseModel):
    parent_agent: str
    task_type: str
    config: dict[str, Any] | None = None


@router.get("/status")
async def get_gateway_status():
    gateway = get_gateway_server()
    router_instance = get_message_router()
    session_manager = get_gateway_session_manager()
    binding_manager = get_binding_manager()
    isolation_manager = get_isolation_manager()
    auth_manager = get_device_auth_manager()
    communicator = get_cross_agent_communicator()
    gateway_stats = gateway.get_stats()
    runtime_status = "ready" if gateway_stats.get("active_connections", 0) > 0 else "limited"

    return {
        "tier": "experimental",
        "available": True,
        "runtime_status": runtime_status,
        "dependency_status": "paired_devices_or_agents_required",
        "failure_mode": "explicit_status",
        "message": "Gateway 为实验功能；只有完成设备配对或 Agent 连接后，消息路由与会话能力才具备实际价值。",
        "gateway": gateway_stats,
        "router": router_instance.get_routing_stats(),
        "sessions": session_manager.get_stats(),
        "bindings": binding_manager.get_stats(),
        "isolation": {"total_workspaces": len(isolation_manager.get_all_workspaces())},
        "auth": auth_manager.get_stats(),
        "communication": communicator.get_channel_stats(),
    }


@router.post("/devices/register")
async def register_device(
    request: DeviceRegisterRequest,
    _auth: bool = Depends(require_admin_auth),
):
    import uuid

    auth_manager = get_device_auth_manager()
    device_id = request.device_id or f"device_{uuid.uuid4().hex[:8]}"
    result = await auth_manager.register_device(
        device_id=device_id,
        device_type=DeviceType(request.device_type),
        device_name=request.device_name,
        metadata=request.metadata,
    )
    if not result:
        raise HTTPException(status_code=500, detail="Failed to register device")
    return {"success": True, **result}


@router.post("/devices/authenticate")
async def authenticate_device(request: DeviceAuthRequest):
    auth_manager = get_device_auth_manager()
    ok = auth_manager.authenticate_device(device_id=request.device_id, token=request.token)
    return {"success": ok, "device_id": request.device_id, "authenticated": ok}


@router.post("/devices/challenge")
async def create_challenge(device_id: str):
    auth_manager = get_device_auth_manager()
    result = auth_manager.create_challenge(device_id)
    if not result:
        raise HTTPException(status_code=404, detail="Device not found")
    return result


@router.post("/devices/challenge/verify")
async def verify_challenge(request: ChallengeVerifyRequest):
    auth_manager = get_device_auth_manager()
    ok = auth_manager.verify_challenge(request.device_id, request.challenge_id, request.signed_response)
    if not ok:
        raise HTTPException(status_code=401, detail="Challenge verification failed")
    return {"success": ok, "device_id": request.device_id}


@router.get("/devices")
async def list_devices(device_type: str | None = None, status: str | None = None):
    auth_manager = get_device_auth_manager()
    if device_type:
        devices = auth_manager.get_devices_by_type(DeviceType(device_type))
    elif status:
        devices = auth_manager.get_devices_by_status(DeviceStatus(status))
    else:
        devices = auth_manager.get_all_devices()
    serialized_devices = [_serialize_device(auth_manager, device) for device in devices]
    return {"devices": serialized_devices, "total": len(serialized_devices)}


@router.get("/devices/{device_id}")
async def get_device(device_id: str):
    auth_manager = get_device_auth_manager()
    info = auth_manager.get_device_info(device_id)
    if not info:
        raise HTTPException(status_code=404, detail="Device not found")
    return _serialize_device(auth_manager, info)


@router.delete("/devices/{device_id}")
async def unregister_device(device_id: str):
    auth_manager = get_device_auth_manager()
    ok = auth_manager.unregister_device(device_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Device not found")
    return {"success": ok, "device_id": device_id}


@router.post("/devices/{device_id}/permissions")
async def set_device_permissions(
    device_id: str,
    level: str,
    allowed_actions: list[str] | None = None,
    denied_actions: list[str] | None = None,
    rate_limit: int | None = None,
    _auth: bool = Depends(require_admin_auth),
):
    auth_manager = get_device_auth_manager()
    ok = auth_manager.set_permissions(
        device_id=device_id,
        level=PermissionLevel(level),
        allowed_actions=allowed_actions,
        denied_actions=denied_actions,
        rate_limit=rate_limit,
    )
    if not ok:
        raise HTTPException(status_code=404, detail="Device not found")
    return {"success": ok, "device_id": device_id}


@router.post("/messages/send")
async def send_message(request: MessageSendRequest):
    communicator = get_cross_agent_communicator()
    msg = await communicator.send_message(
        source_agent="api",
        target_agent=request.target_agent,
        payload=request.payload,
        message_type=MessageType(request.message_type),
        priority=MessagePriority(request.priority),
        correlation_id=request.correlation_id,
        timeout=request.timeout,
    )
    if not msg:
        raise HTTPException(status_code=500, detail="Failed to send message")
    return {"success": True, "message_id": msg.id, "correlation_id": msg.correlation_id}


@router.post("/messages/send-and-wait")
async def send_and_wait(request: MessageSendRequest, timeout: int = 60):
    communicator = get_cross_agent_communicator()
    result = await communicator.send_and_wait(
        source_agent="api",
        target_agent=request.target_agent,
        payload=request.payload,
        timeout=timeout,
    )
    if result is None:
        raise HTTPException(status_code=504, detail="No response received from target agent")
    return {"success": True, "result": result}


@router.post("/messages/broadcast")
async def broadcast_message(payload: dict[str, Any], exclude: list[str] | None = None):
    communicator = get_cross_agent_communicator()
    sent_to = await communicator.broadcast(source_agent="api", payload=payload, exclude=exclude)
    if not sent_to:
        raise HTTPException(status_code=404, detail="No target agents available for broadcast")
    return {"success": True, "sent_to": sent_to, "count": len(sent_to)}


@router.post("/bindings")
async def create_binding(request: BindingRuleRequest):
    import uuid

    from gateway.models import AgentInfo, BindingRule

    binding_manager = get_binding_manager()

    if request.agent_id not in binding_manager._agents:
        binding_manager.register_agent(
            AgentInfo(id=request.agent_id, name=request.agent_id, workspace_path=f"workspaces/{request.agent_id}")
        )

    rule = BindingRule(
        id=f"binding_{uuid.uuid4().hex[:8]}",
        agent_id=request.agent_id,
        priority=request.priority,
        peer_id=request.peer_id,
        guild_id=request.guild_id,
        channel_id=request.channel_id,
        team_id=request.team_id,
        account_id=request.account_id,
        roles=request.roles,
        enabled=request.enabled,
    )

    ok = binding_manager.add_binding(rule)
    return {"success": ok, "rule_id": rule.id}


@router.get("/bindings")
async def list_bindings(agent_id: str | None = None):
    binding_manager = get_binding_manager()
    rules = binding_manager.get_agent_bindings(agent_id) if agent_id else binding_manager.get_all_bindings()
    return {
        "bindings": [r.model_dump() if hasattr(r, "model_dump") else r.__dict__ for r in rules],
        "total": len(rules),
    }


@router.delete("/bindings/{rule_id}")
async def delete_binding(rule_id: str):
    binding_manager = get_binding_manager()
    ok = binding_manager.remove_binding(rule_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Binding rule not found")
    return {"success": ok, "rule_id": rule_id}


@router.post("/agents/spawn")
async def spawn_agent(request: SpawnAgentRequest):
    communicator = get_cross_agent_communicator()
    spawned_id = await communicator.spawn_agent(
        parent_agent=request.parent_agent,
        task_type=request.task_type,
        config=request.config,
    )
    if not spawned_id:
        raise HTTPException(status_code=500, detail="Failed to spawn agent")
    return {"success": True, "spawned_id": spawned_id}


@router.get("/agents/spawned")
async def list_spawned_agents(parent_agent: str | None = None):
    communicator = get_cross_agent_communicator()
    agents = communicator.get_spawned_agents(parent_agent)
    return {
        "agents": [
            {
                "id": a.id,
                "parent_agent": a.parent_agent,
                "task_type": a.task_type,
                "status": a.status,
                "created_at": a.created_at.isoformat(),
                "completed_at": a.completed_at.isoformat() if a.completed_at else None,
                "error": a.error,
                "session_id": a.session_id,
            }
            for a in agents
        ],
        "total": len(agents),
    }


@router.delete("/agents/spawned/{spawned_id}")
async def terminate_spawned_agent(spawned_id: str):
    communicator = get_cross_agent_communicator()
    ok = await communicator.terminate_agent(spawned_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Spawned agent not found")
    return {"success": ok, "spawned_id": spawned_id}


@router.post("/agents/results/collect")
async def collect_results(agent_ids: list[str], timeout: int = 60, merge_strategy: str = "combine"):
    communicator = get_cross_agent_communicator()
    results = await communicator.collect_results(agent_ids, timeout)
    merged = communicator.merge_results(results, merge_strategy)
    return {"results": results, "merged": merged}


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    gateway = get_gateway_server()
    await gateway.handle_websocket(websocket)
