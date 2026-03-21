# -*- coding: utf-8 -*-
"""
Gateway 数据模型
"""
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
from datetime import datetime
from enum import Enum


class MessageType(str, Enum):
    """消息类型"""
    REQUEST = "request"
    RESPONSE = "response"
    EVENT = "event"
    ERROR = "error"
    HEARTBEAT = "heartbeat"


class DeviceType(str, Enum):
    """设备类型"""
    CLI = "cli"
    WEB = "web"
    DESKTOP = "desktop"
    MOBILE = "mobile"
    HEADLESS = "headless"


class DeviceStatus(str, Enum):
    """设备状态"""
    ONLINE = "online"
    OFFLINE = "offline"
    PAIRING = "pairing"
    PAIRED = "paired"


class GatewayMessage(BaseModel):
    """Gateway 消息"""
    id: str = Field(..., description="消息 ID")
    type: MessageType = Field(..., description="消息类型")
    action: str = Field(..., description="动作名称")
    payload: Dict[str, Any] = Field(default_factory=dict, description="消息载荷")
    timestamp: datetime = Field(default_factory=datetime.now, description="时间戳")
    source: Optional[str] = Field(None, description="来源设备 ID")
    target: Optional[str] = Field(None, description="目标 Agent ID")
    correlation_id: Optional[str] = Field(None, description="关联 ID（用于请求响应匹配）")


class GatewayResponse(BaseModel):
    """Gateway 响应"""
    id: str = Field(..., description="响应 ID")
    correlation_id: str = Field(..., description="关联的请求 ID")
    success: bool = Field(..., description="是否成功")
    data: Optional[Dict[str, Any]] = Field(None, description="响应数据")
    error: Optional[str] = Field(None, description="错误信息")
    timestamp: datetime = Field(default_factory=datetime.now, description="时间戳")


class GatewayEvent(BaseModel):
    """Gateway 事件"""
    id: str = Field(..., description="事件 ID")
    event_type: str = Field(..., description="事件类型")
    data: Dict[str, Any] = Field(default_factory=dict, description="事件数据")
    timestamp: datetime = Field(default_factory=datetime.now, description="时间戳")
    broadcast: bool = Field(True, description="是否广播")


class DeviceInfo(BaseModel):
    """设备信息"""
    id: str = Field(..., description="设备 ID")
    type: DeviceType = Field(..., description="设备类型")
    name: str = Field(..., description="设备名称")
    status: DeviceStatus = Field(DeviceStatus.ONLINE, description="设备状态")
    ip_address: Optional[str] = Field(None, description="IP 地址")
    user_agent: Optional[str] = Field(None, description="用户代理")
    last_seen: datetime = Field(default_factory=datetime.now, description="最后活跃时间")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="元数据")


class DevicePairingRequest(BaseModel):
    """设备配对请求"""
    device_id: str = Field(..., description="设备 ID")
    device_type: DeviceType = Field(..., description="设备类型")
    device_name: str = Field(..., description="设备名称")
    challenge: Optional[str] = Field(None, description="挑战码（用于签名验证）")


class DevicePairingResponse(BaseModel):
    """设备配对响应"""
    success: bool = Field(..., description="是否成功")
    device_id: str = Field(..., description="设备 ID")
    token: Optional[str] = Field(None, description="认证 Token")
    expires_at: Optional[datetime] = Field(None, description="Token 过期时间")
    message: str = Field("", description="消息")


class BindingRule(BaseModel):
    """绑定规则"""
    id: str = Field(..., description="规则 ID")
    agent_id: str = Field(..., description="目标 Agent ID")
    priority: int = Field(0, description="优先级（数值越大优先级越高）")
    
    peer_id: Optional[str] = Field(None, description="精确匹配 peer ID")
    guild_id: Optional[str] = Field(None, description="匹配 guild ID")
    channel_id: Optional[str] = Field(None, description="匹配 channel ID")
    team_id: Optional[str] = Field(None, description="匹配 team ID")
    account_id: Optional[str] = Field(None, description="匹配 account ID")
    roles: Optional[List[str]] = Field(None, description="匹配角色列表")
    
    enabled: bool = Field(True, description="是否启用")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="元数据")


class AgentInfo(BaseModel):
    """Agent 信息"""
    id: str = Field(..., description="Agent ID")
    name: str = Field(..., description="Agent 名称")
    workspace_path: str = Field(..., description="工作空间路径")
    status: str = Field("idle", description="状态")
    created_at: datetime = Field(default_factory=datetime.now, description="创建时间")
    last_active: datetime = Field(default_factory=datetime.now, description="最后活跃时间")
    config: Dict[str, Any] = Field(default_factory=dict, description="配置")


class HeartbeatConfig(BaseModel):
    """Heartbeat 配置"""
    interval_seconds: int = Field(1800, description="心跳间隔（秒）")
    enabled: bool = Field(True, description="是否启用")
    tasks: List[str] = Field(default_factory=list, description="任务列表")
    max_retries: int = Field(3, description="最大重试次数")
