# -*- coding: utf-8 -*-
"""
Gateways API 路由

提供 Gateway 模块的 REST API 端点
"""
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime
from fastapi import APIRouter, HTTPException, Query, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from gateway import (
    GatewayServer,
    MessageRouter,
    GatewaySessionManager,
    BindingManager,
    get_gateway_server,
    get_message_router,
    get_gateway_session_manager,
    get_binding_manager,
)
from gateway.agent_isolation import AgentIsolationManager, get_isolation_manager
from gateway.device_auth import (
    DeviceAuthManager,
    DeviceType,
    DeviceStatus,
    PermissionLevel,
    get_device_auth_manager,
)
from gateway.cross_agent import (
    CrossAgentCommunicator,
    MessageType,
    MessagePriority,
    get_cross_agent_communicator,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/gateway", tags=["Gateway"])


class DeviceRegisterRequest(BaseModel):
    """设备注册请求"""
    device_id: Optional[str] = None
    device_type: str = "web"
    device_name: str
    metadata: Dict[str, Any] = Field(default_factory=dict)


class DeviceAuthRequest(BaseModel):
    """设备认证请求"""
    device_id: str
    token: str


class ChallengeVerifyRequest(BaseModel):
    """挑战验证请求"""
    device_id: str
    challenge_id: str
    signed_response: str


class MessageSendRequest(BaseModel):
    """消息发送请求"""
    target_agent: str
    message_type: str = "request"
    priority: str = "normal"
    payload: Dict[str, Any] = Field(default_factory=dict)
    correlation_id: Optional[str] = None
    timeout: Optional[int] = None


class BindingRuleRequest(BaseModel):
    """绑定规则请求"""
    agent_id: str
    priority: int = 0
    peer_id: Optional[str] = None
    guild_id: Optional[str] = None
    channel_id: Optional[str] = None
    team_id: Optional[str] = None
    account_id: Optional[str] = None
    roles: Optional[List[str]] = None
    enabled: bool = True


class SpawnAgentRequest(BaseModel):
    """生成子 Agent 请求"""
    parent_agent: str
    task_type: str
    config: Optional[Dict[str, Any]] = None


@router.get("/status")
async def get_gateway_status():
    """获取 Gateway 状态"""
    gateway = get_gateway_server()
    router_instance = get_message_router()
    session_manager = get_gateway_session_manager()
    binding_manager = get_binding_manager()
    isolation_manager = get_isolation_manager()
    auth_manager = get_device_auth_manager()
    communicator = get_cross_agent_communicator()
    
    return {
        "gateway": gateway.get_stats(),
        "router": router_instance.get_routing_stats(),
        "sessions": session_manager.get_stats(),
        "bindings": binding_manager.get_stats(),
        "isolation": {
            "total_workspaces": len(isolation_manager.get_all_workspaces()),
        },
        "auth": auth_manager.get_stats(),
        "communication": communicator.get_channel_stats(),
    }


@router.post("/devices/register")
async def register_device(request: DeviceRegisterRequest):
    """注册新设备"""
    auth_manager = get_device_auth_manager()
    
    import uuid
    device_id = request.device_id or f"device_{uuid.uuid4().hex[:8]}"
    
    result = await auth_manager.register_device(
        device_id=device_id,
        device_type=DeviceType(request.device_type),
        device_name=request.device_name,
        metadata=request.metadata,
    )
    
    return {"success": True, **result}


@router.post("/devices/authenticate")
async def authenticate_device(request: DeviceAuthRequest):
    """认证设备"""
    auth_manager = get_device_auth_manager()
    
    success = auth_manager.authenticate_device(
        device_id=request.device_id,
        token=request.token,
    )
    
    return {
        "success": success,
        "device_id": request.device_id,
        "authenticated": success,
    }


@router.post("/devices/challenge")
async def create_challenge(device_id: str):
    """创建签名挑战"""
    auth_manager = get_device_auth_manager()
    
    result = auth_manager.create_challenge(device_id)
    
    if not result:
        raise HTTPException(status_code=404, detail="Device not found")
    
    return result


@router.post("/devices/challenge/verify")
async def verify_challenge(request: ChallengeVerifyRequest):
    """验证签名挑战"""
    auth_manager = get_device_auth_manager()
    
    success = auth_manager.verify_challenge(
        device_id=request.device_id,
        challenge_id=request.challenge_id,
        signed_response=request.signed_response,
    )
    
    return {
        "success": success,
        "device_id": request.device_id,
    }


@router.get("/devices")
async def list_devices(
    device_type: Optional[str] = None,
    status: Optional[str] = None,
):
    """列出所有设备"""
    auth_manager = get_device_auth_manager()
    
    if device_type:
        devices = auth_manager.get_devices_by_type(DeviceType(device_type))
    elif status:
        devices = auth_manager.get_devices_by_status(DeviceStatus(status))
    else:
        devices = auth_manager.get_all_devices()
    
    return {"devices": devices, "total": len(devices)}


@router.get("/devices/{device_id}")
async def get_device(device_id: str):
    """获取设备信息"""
    auth_manager = get_device_auth_manager()
    
    info = auth_manager.get_device_info(device_id)
    
    if not info:
        raise HTTPException(status_code=404, detail="Device not found")
    
    return info


@router.delete("/devices/{device_id}")
async def unregister_device(device_id: str):
    """注销设备"""
    auth_manager = get_device_auth_manager()
    
    success = auth_manager.unregister_device(device_id)
    
    return {"success": success, "device_id": device_id}


@router.post("/devices/{device_id}/permissions")
async def set_device_permissions(
    device_id: str,
    level: str,
    allowed_actions: Optional[List[str]] = None,
    denied_actions: Optional[List[str]] = None,
    rate_limit: Optional[int] = None,
):
    """设置设备权限"""
    auth_manager = get_device_auth_manager()
    
    success = auth_manager.set_permissions(
        device_id=device_id,
        level=PermissionLevel(level),
        allowed_actions=allowed_actions,
        denied_actions=denied_actions,
        rate_limit=rate_limit,
    )
    
    return {"success": success, "device_id": device_id}


@router.post("/messages/send")
async def send_message(request: MessageSendRequest):
    """发送消息"""
    communicator = get_cross_agent_communicator()
    
    message = await communicator.send_message(
        source_agent="api",
        target_agent=request.target_agent,
        payload=request.payload,
        message_type=MessageType(request.message_type),
        priority=MessagePriority(request.priority),
        correlation_id=request.correlation_id,
        timeout=request.timeout,
    )
    
    if not message:
        raise HTTPException(status_code=500, detail="Failed to send message")
    
    return {
        "success": True,
        "message_id": message.id,
        "correlation_id": message.correlation_id,
    }


@router.post("/messages/send-and-wait")
async def send_and_wait(request: MessageSendRequest, timeout: int = 60):
    """发送消息并等待响应"""
    communicator = get_cross_agent_communicator()
    
    result = await communicator.send_and_wait(
        source_agent="api",
        target_agent=request.target_agent,
        payload=request.payload,
        timeout=timeout,
    )
    
    return {"success": True, "result": result}


@router.post("/messages/broadcast")
async def broadcast_message(
    payload: Dict[str, Any],
    exclude: Optional[List[str]] = None,
):
    """广播消息"""
    communicator = get_cross_agent_communicator()
    
    sent_to = await communicator.broadcast(
        source_agent="api",
        payload=payload,
        exclude=exclude,
    )
    
    return {"success": True, "sent_to": sent_to, "count": len(sent_to)}


@router.post("/bindings")
async def create_binding(request: BindingRuleRequest):
    """创建绑定规则"""
    from gateway.models import BindingRule
    import uuid
    
    binding_manager = get_binding_manager()
    
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
    
    success = binding_manager.add_binding(rule)
    
    return {"success": success, "rule_id": rule.id}


@router.get("/bindings")
async def list_bindings(agent_id: Optional[str] = None):
    """列出绑定规则"""
    binding_manager = get_binding_manager()
    
    if agent_id:
        rules = binding_manager.get_agent_bindings(agent_id)
    else:
        rules = binding_manager.get_all_bindings()
    
    return {"bindings": [r.model_dump() for r in rules], "total": len(rules)}


@router.delete("/bindings/{rule_id}")
async def delete_binding(rule_id: str):
    """删除绑定规则"""
    binding_manager = get_binding_manager()
    
    success = binding_manager.remove_binding(rule_id)
    
    return {"success": success, "rule_id": rule_id}


@router.post("/agents/spawn")
async def spawn_agent(request: SpawnAgentRequest):
    """生成子 Agent"""
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
async def list_spawned_agents(parent_agent: Optional[str] = None):
    """列出生成的子 Agent"""
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
            }
            for a in agents
        ],
        "total": len(agents),
    }


@router.delete("/agents/spawned/{spawned_id}")
async def terminate_spawned_agent(spawned_id: str):
    """终止子 Agent"""
    communicator = get_cross_agent_communicator()
    
    success = await communicator.terminate_agent(spawned_id)
    
    return {"success": success, "spawned_id": spawned_id}


@router.post("/agents/results/collect")
async def collect_results(
    agent_ids: List[str],
    timeout: int = 60,
    merge_strategy: str = "combine",
):
    """收集多个 Agent 的结果"""
    communicator = get_cross_agent_communicator()
    
    results = await communicator.collect_results(agent_ids, timeout)
    merged = communicator.merge_results(results, merge_strategy)
    
    return {"results": results, "merged": merged}


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket 端点"""
    gateway = get_gateway_server()
    await gateway.handle_websocket(websocket)
