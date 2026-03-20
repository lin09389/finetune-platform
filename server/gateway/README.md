# Gateway 模块文档

## 概述

Gateway 模块是 Finetune Platform 2.0 的统一入口，借鉴 OpenClaw 架构设计，提供 WebSocket 控制平面、消息路由、设备认证和事件广播功能。

## 架构

```
┌─────────────────────────────────────────────────────────┐
│                     Gateway 架构                         │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐ │
│  │   CLI       │    │    Web      │    │  Desktop    │ │
│  │  Client     │    │   Client    │    │   Client    │ │
│  └──────┬──────┘    └──────┬──────┘    └──────┬──────┘ │
│         │                  │                   │        │
│         └──────────────────┼───────────────────┘        │
│                            │                            │
│                            ▼                            │
│  ┌─────────────────────────────────────────────────┐   │
│  │              GatewayServer                       │   │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────┐  │   │
│  │  │ WebSocket   │  │  Device     │  │  Event  │  │   │
│  │  │ Server      │  │  Auth       │  │  Broadcast│  │   │
│  │  └─────────────┘  └─────────────┘  └─────────┘  │   │
│  └─────────────────────────────────────────────────┘   │
│                            │                            │
│                            ▼                            │
│  ┌─────────────────────────────────────────────────┐   │
│  │              MessageRouter                       │   │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────┐  │   │
│  │  │ Binding     │  │  Priority   │  │  Agent  │  │   │
│  │  │ Rules       │  │  Matching   │  │  Router │  │   │
│  │  └─────────────┘  └─────────────┘  └─────────┘  │   │
│  └─────────────────────────────────────────────────┘   │
│                            │                            │
│         ┌──────────────────┼──────────────────┐        │
│         ▼                  ▼                  ▼        │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐ │
│  │   Agent A   │    │   Agent B   │    │   Agent C   │ │
│  │ (Workspace) │    │ (Workspace) │    │ (Workspace) │ │
│  └─────────────┘    └─────────────┘    └─────────────┘ │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

## 核心组件

### 1. GatewayServer

WebSocket 服务器，作为统一入口。

```python
from server.gateway import GatewayServer, get_gateway_server

# 获取单例
gateway = get_gateway_server()

# 启动服务器
await gateway.start()

# 处理 WebSocket 连接
@app.websocket("/ws/{device_id}")
async def websocket_endpoint(websocket: WebSocket, device_id: str):
    await gateway.handle_websocket(websocket, device_id)

# 停止服务器
await gateway.stop()
```

### 2. MessageRouter

消息路由器，实现最具体匹配优先算法。

```python
from server.gateway import MessageRouter, BindingRule, AgentInfo

router = MessageRouter()

# 注册 Agent
router.register_agent(AgentInfo(
    id="agent_001",
    name="Main Agent",
    workspace_path="/path/to/workspace",
))

# 添加绑定规则
router.add_binding(BindingRule(
    id="rule_001",
    agent_id="agent_001",
    priority=100,
    peer_id="user_123",  # 精确匹配
))

# 路由消息
response = await router.route(message, context)
```

### 3. GatewaySessionManager

会话管理器，管理设备会话和订阅。

```python
from server.gateway import GatewaySessionManager

session_manager = GatewaySessionManager()

# 创建会话
session = session_manager.create_session("device_001")

# 订阅事件
session_manager.subscribe_events("device_001", ["message", "notification"])

# 获取订阅者
subscribers = session_manager.get_subscribers("message")
```

## 消息类型

### GatewayMessage

```python
class GatewayMessage(BaseModel):
    id: str                    # 消息 ID
    type: MessageType          # request/response/event/error/heartbeat
    action: str                # 动作名称
    payload: Dict[str, Any]    # 消息载荷
    timestamp: datetime        # 时间戳
    source: Optional[str]      # 来源设备 ID
    target: Optional[str]      # 目标 Agent ID
    correlation_id: Optional[str]  # 关联 ID
```

### DeviceInfo

```python
class DeviceInfo(BaseModel):
    id: str                    # 设备 ID
    type: DeviceType           # cli/web/desktop/mobile/headless
    name: str                  # 设备名称
    status: DeviceStatus       # online/offline/pairing/paired
    ip_address: Optional[str]  # IP 地址
    user_agent: Optional[str]  # 用户代理
    last_seen: datetime        # 最后活跃时间
```

## 路由算法

### 最具体匹配优先

路由优先级从高到低：

1. **peer 精确匹配** - 特定 DM/群组 ID（score += 1000）
2. **guildId + roles** - Discord 服务器 + 角色（score += 100 + 50 + matched_roles * 10）
3. **teamId** - Slack 团队（score += 80）
4. **accountId** - 账户 ID（score += 70）
5. **channelId** - 频道 ID（score += 60）
6. **fallback** - 默认 Agent

```python
# 示例绑定规则
rules = [
    BindingRule(id="r1", agent_id="agent_a", peer_id="user_123"),      # 最高优先级
    BindingRule(id="r2", agent_id="agent_b", guild_id="guild_001"),    # 次高
    BindingRule(id="r3", agent_id="agent_c", team_id="team_001"),      # 中等
    BindingRule(id="r4", agent_id="agent_d", account_id="acc_001"),    # 较低
]
```

## 设备认证流程

```
┌──────────┐                    ┌──────────┐
│  Device  │                    │ Gateway  │
└────┬─────┘                    └────┬─────┘
     │                               │
     │  1. Connect (WebSocket)       │
     │──────────────────────────────>│
     │                               │
     │  2. Pairing Request           │
     │<──────────────────────────────│
     │                               │
     │  3. Pairing Response          │
     │  (device_id, challenge)       │
     │──────────────────────────────>│
     │                               │
     │  4. Pairing Confirmation      │
     │  (signed challenge)           │
     │<──────────────────────────────│
     │                               │
     │  5. Auth Token                │
     │──────────────────────────────>│
     │                               │
     │  6. Auth Success              │
     │<──────────────────────────────│
     │                               │
     │  7. Normal Communication      │
     │<─────────────────────────────>│
     │                               │
```

## 事件广播

```python
from server.gateway import GatewayEvent

# 创建事件
event = GatewayEvent(
    id="event_001",
    event_type="message",
    data={"content": "Hello"},
    broadcast=True,
)

# 广播到所有设备
await gateway.broadcast_event(event)

# 发送到特定设备
await gateway.send_to_device("device_001", event)
```

## 配置

```python
config = {
    "host": "127.0.0.1",
    "port": 18789,
    "heartbeat_interval": 30,
    "connection_timeout": 300,
}

gateway = GatewayServer(config)
```

## 与现有系统集成

### FastAPI 集成

```python
from fastapi import FastAPI, WebSocket
from server.gateway import get_gateway_server

app = FastAPI()
gateway = get_gateway_server()

@app.on_event("startup")
async def startup():
    await gateway.start()

@app.on_event("shutdown")
async def shutdown():
    await gateway.stop()

@app.websocket("/ws/{device_id}")
async def websocket_endpoint(websocket: WebSocket, device_id: str):
    await gateway.handle_websocket(websocket, device_id)
```

### Agent 集成

```python
from server.gateway import get_message_router, BindingRule, AgentInfo

router = get_message_router()

# 注册 Agent
router.register_agent(AgentInfo(
    id="my_agent",
    name="My Agent",
    workspace_path="/path/to/workspace",
))

# 设置消息处理器
async def handle_message(message, context):
    return {"response": "processed"}

router.register_agent_handler("my_agent", handle_message)
```
