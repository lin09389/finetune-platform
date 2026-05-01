# OpenCode 完整执行链路分析

## 目录
1. [入口点](#1-入口点)
2. [服务器初始化](#2-服务器初始化)
3. [Bootstrap 过程](#3-bootstrap-过程)
4. [会话创建与管理](#4-会话创建与管理)
5. [ACP 协议消息流](#5-acp-协议消息流)
6. [Agent 选择与执行](#6-agent-选择与执行)
7. [会话 Prompt 处理](#7-会话-prompt-处理)
8. [LM 流处理](#8-lm-流处理)
9. [工具调用机制](#9-工具调用机制)
10. [权限检查流程](#10-权限检查流程)
11. [事件处理](#11-事件处理)
12. [响应流回客户端](#12-响应流回客户端)
13. [关键数据转换](#13-关键数据转换)
14. [核心类和服务](#14-核心类和服务)
15. [完整时序图](#15-完整时序图)

---

## 1. 入口点

### 1.1 CLI 入口 (`packages/opencode/src/index.ts`)

```
用户执行 opencode 命令
    ↓
yargs 解析命令行参数
    ↓
初始化日志和堆内存监控
    ↓
执行数据库迁移 (JSON → SQLite)
    ↓
路由到具体命令 (run/serve/acp 等)
```

### 1.2 Desktop 入口 (`packages/desktop/src/cli.ts`)

```
Tauri 桌面应用启动
    ↓
提供 CLI 安装功能
    ↓
调用核心 opencode 功能
```

### 1.3 Web/Console 入口 (`packages/console/app/src/entry-server.tsx`)

```
SolidJS Web 界面
    ↓
服务端渲染 + locale 支持
    ↓
浏览器访问
```

---

## 2. 服务器初始化

### 2.1 Server 创建流程 (`packages/opencode/src/server/server.ts`)

```
create()
    ↓
Hono app 设置
    ↓
中间件链
    ↓
路由注册
```

### 2.2 中间件栈 (按顺序应用)

```
1. ErrorMiddleware       → 全局错误处理
2. AuthMiddleware       → 认证 (远程服务器基础认证)
3. LoggerMiddleware     → 请求日志
4. CompressionMiddleware → 响应压缩
5. CorsMiddleware       → CORS 头
6. FenceMiddleware      → 工作空间隔离 (如启用)
7. InstanceMiddleware   → 实例上下文注入
```

### 2.3 路由结构

```
/global/*           → 全局路由 (跨工作空间)
/                   → 控制平面路由 (工作空间管理)
/                   → 实例路由 (会话、provider、配置等)
/                   → UI 路由 (Web 界面)
```

### 2.4 服务器监听

```
listen(opts)
    ↓
runtime.listen()
    ↓
mDNS 发布 (如启用)
    ↓
返回 Listener
```

---

## 3. Bootstrap 过程

### 3.1 Bootstrap 流程 (`packages/opencode/src/cli/bootstrap.ts`)

```
bootstrap(directory, callback)
    ↓
Instance.provide()
    ↓
InstanceBootstrap
    ↓
callback 执行
    ↓
Instance.dispose()
```

### 3.2 实例初始化

- 设置项目上下文 (worktree, VCS 检测)
- 初始化 Effect 运行时 + 所有服务层
- 创建工作空间 ID (如启用工作空间)
- 建立数据库连接
- 加载配置和插件

---

## 4. 会话创建与管理

### 4.1 Session 创建 (`packages/opencode/src/session/session.ts`)

```
Session.create()
    ↓
createNext()
    ├── 生成 SessionID (降序时间戳)
    ├── 创建 URL slug
    ├── 设置默认标题
    ├── 存储到数据库
    └── 发布 Session.Created 事件
```

### 4.2 Session 状态

- 存储在 SQLite (`SessionTable`)
- 通过 `InstanceState` 在内存中跟踪
- 通过 `SyncEvent` 系统同步

---

## 5. ACP 协议消息流

### 5.1 ACP Server 设置 (`packages/opencode/src/cli/cmd/acp.ts`)

```
AcpCommand
    ↓
bootstrap()
    ↓
Server.listen()
    ↓
createOpencodeClient()
    ↓
AgentSideConnection(stream)
    ↓
ACP.init()
```

### 5.2 ACP Agent 生命周期 (`packages/opencode/src/acp/agent.ts`)

#### 初始化
```
initialize()
    ↓
返回 capabilities + auth methods
```

#### 会话操作
```
newSession()
    ├── 创建 ACP 会话状态
    ├── loadSessionMode()
    └── 返回配置

loadSession()
    ├── 恢复会话
    ├── 重放消息历史
    └── 返回配置

forkSession()
    ├── fork 现有会话
    ├── 重放消息
    └── 返回配置
```

#### Prompt 流程
```
prompt(params)
    ├── 解析 prompt parts (text, images, resources)
    ├── 检查命令 (以 / 开头)
    ├── 调用 sdk.session.prompt() 或 sdk.session.command()
    └── 流式返回事件
```

#### 事件订阅
```
runEventSubscription()
    ↓
sdk.global.event()
    ↓
for each event:
    ├── permission.asked → requestPermission() → reply()
    ├── message.partupdated → sessionUpdate(tool_call_update)
    └── message.part.delta → sessionUpdate(agent_message_chunk)
```

---

## 6. Agent 选择与执行

### 6.1 内置 Agent

| Agent | 模式 | 权限 |
|-------|------|------|
| `build` | primary | 全权限 (默认) |
| `plan` | primary | 只读，禁止编辑 |
| `general` | subagent | 通用任务 |
| `explore` | subagent | 只读，快速探索 |
| `compaction` | hidden | 会话压缩 |
| `title` | hidden | 标题生成 |
| `summary` | hidden | 摘要生成 |

### 6.2 Agent 选择流程 (`packages/opencode/src/agent/agent.ts`)

```
Agent.Service.get(agentName)
    ├── 从配置加载
    ├── 合并默认权限
    ├── 应用用户权限覆盖
    └── 返回 Agent.Info
```

### 6.3 Agent 配置

```typescript
{
  permissions: Ruleset,        // 权限规则集
  model: ModelConfig,         // 模型覆盖 (可选)
  temperature: number,        // 温度参数
  topP: number,              // Top-P 参数
  prompt: string,            // 自定义系统提示词
  options: Record,            // 工具选项
}
```

---

## 7. 会话 Prompt 处理

### 7.1 Prompt 入口 (`packages/opencode/src/server/routes/instancesession.ts`)

```
POST /session/:sessionID/message
    ↓
SessionPrompt.Service.prompt()
    ↓
流式返回响应
```

### 7.2 Prompt 处理 (`packages/opencode/src/session/prompt.ts`)

```
prompt(input)
    ├── 1. 验证会话不繁忙
    ├── 2. 创建用户消息
    ├── 3. 创建助手消息
    ├── 4. 初始化 SessionProcessor
    ├── 5. 构建工具注册表
    ├── 6. 启动 LM 流
    ├── 7. 处理事件
    └── 8. 返回助手消息
```

---

## 8. LM 流处理

### 8.1 流设置 (`packages/opencode/src/session/llm.ts`)

```
LLM.Service.stream(input)
    ├── 1. 从 provider 获取语言模型
    ├── 2. 构建系统提示词 (agent + provider + custom)
    ├── 3. 应用插件转换
    ├── 4. 解析工具 (按权限过滤)
    ├── 5. 配置参数 (temperature, topP, maxTokens)
    └── 6. 调用 streamText() from AI SDK
```

### 8.2 AI SDK 集成

```typescript
streamText({
  model: wrapLanguageModel(language),
  messages: [...system, ...history],
  tools: resolvedTools,
  temperature, topP, topK, maxOutputTokens,
  headers: { x-opencode-session, User-Agent, ... },
  experimental_telemetry: { tracer, metadata }
})
```

### 8.3 系统提示词构建

```
Agent prompt
    ↓
Provider prompt (如适用)
    ↓
Custom prompt
    ↓
Plugin transforms
    ↓
最终系统提示词
```

---

## 9. 工具调用机制

### 9.1 工具注册 (`packages/opencode/src/tool.ts`)

```
Tool.define(id, init)
    ├── 包装验证逻辑
    ├── 添加截断逻辑
    ├── 添加追踪属性
    └── 返回 Tool.Info
```

### 9.2 工具执行流程

```
LM 发出 tool-call 事件
    ↓
SessionProcessor.handleEvent()
    ├── 1. 创建 tool part (status: pending)
    ├── 2. 更新为 running + input
    ├── 3. 检查 doom loop (3+ 相同调用)
    ├── 4. 通过 AI SDK 执行工具
    └── 5. 更新为 completed/error
```

### 9.3 工具上下文 (`packages/opencode/src/tool/tool.ts`)

```typescript
Context<M> = {
  sessionID,           // 会话 ID
  messageID,           // 消息 ID
  agent,               // 当前 Agent
  abort,              // 中止信号
  callID,             // 调用 ID
  messages,           // 消息历史
  metadata(input),    // 更新 tool part 元数据
  ask(input),         // 请求权限
}
```

### 9.4 工具结果

```typescript
ExecuteResult<M> = {
  title: string,           // 标题
  metadata: M,             // 元数据
  output: string,          // 输出内容
  attachments?: FilePart[]  // 附件
}
```

### 9.5 内置工具

| 工具 | 功能 |
|------|------|
| `read` | 读取文件 |
| `write` | 写入文件 |
| `edit` | 编辑文件 |
| `grep` | 文本搜索 |
| `glob` | 文件模式匹配 |
| `bash` | 执行 shell 命令 |
| `webfetch` | 获取网页内容 |
| `websearch` | 网络搜索 |
| `codesearch` | 代码搜索 |

---

## 10. 权限检查流程

### 10.1 权限请求 (`packages/opencode/src/permission/index.ts`)

```
Permission.Service.ask(input)
    ├── 1. 评估规则 against patterns
    ├── 2. 如果 deny → 抛出 DeniedError
    ├── 3. 如果 allow → 立即返回
    └── 4. 如果 ask → 创建 deferred, 发布事件, 等待回复
```

### 10.2 规则评估 (`packages/opencode/src/permission/evaluate.ts`)

```
evaluate(permission, pattern, ...rulesets)
    ├── 1. 扁平化所有规则集
    ├── 2. 查找匹配规则 (通配符匹配)
    ├── 3. 返回最后匹配的规则 (最具体)
    └── 4. 默认 ask 如果无匹配
```

### 10.3 权限回复 (`packages/opencode/src/permission/index.ts`)

```
Permission.Service.reply(input)
    ├── 1. 查找待处理请求
    ├── 2. 发布回复事件
    ├── 3. 如果 reject → 失败 deferred, 级联到其他会话请求
    ├── 4. 如果 once → 成功 deferred
    └── 5. 如果 always → 添加到已批准规则, 自动批准类似请求
```

### 10.4 权限规则示例

```python
rules = [
    {"permission": "read", "pattern": "*", "action": "allow"},
    {"permission": "edit", "pattern": "*.env", "action": "ask"},
    {"permission": "bash", "pattern": "*", "action": "deny"},
]

# 检查权限
result = evaluate("read", "file.py", rules)  # → "allow"
result = evaluate("edit", ".env", rules)     # → "ask"
result = evaluate("bash", "ls", rules)       # → "deny"
```

---

## 11. 事件处理

### 11.1 SessionProcessor 事件 (`packages/opencode/src/session/processor.ts`)

#### 流事件

| 事件 | 处理 |
|------|------|
| `start` | 设置会话状态为繁忙 |
| `reasoning-start/delta/end` | 跟踪推理 parts |
| `tool-inputstart` | 创建 tool part (pending) |
| `tool-call` | 更新 tool part (running), 检查 doom loop |
| `tool-result` | 完成 tool call |
| `tool-error` | 失败 tool call |
| `text-start/delta/end` | 流式文本 parts |
| `start-step/finish-step` | 跟踪 token 使用量、成本、快照 |
| `error` | 停止处理 |

### 11.2 状态管理

```typescript
ProcessorContext = {
  assistantMessage,     // 助手消息
  sessionID,           // 会话 ID
  model,               // 模型
  toolcalls: Map,      // 工具调用 Map
  shouldBreak,         // 是否中断
  snapshot,           // 快照
  blocked,            // 是否阻塞
  needsCompaction,    // 是否需要压缩
  currentText,         // 当前文本
  reasoningMap         // 推理 Map
}
```

---

## 12. 响应流回客户端

### 12.1 HTTP 流 (`packages/opencode/src/server/routes/instance/session.ts`)

```
POST /session/:sessionID/message
    ↓
stream(c, async (stream) => {
  const msg = await SessionPrompt.Service.prompt()
  stream.write(JSON.stringify(msg))
})
```

### 12.2 事件总线广播 (`packages/opencode/src/bus/bus.ts`)

```
Bus.publish(event, properties)
    ├── 1. 序列化事件
    ├── 2. 广播到所有订阅者
    └── 3. 存储到事件日志 (如同步事件)
```

### 12.3 ACP 事件流 (`packages/opencode/src/acp/agent.ts`)

```
handleEvent(event)
    ↓
match event.type:
    ├── message.part.updated → connection.sessionUpdate(tool_call_update)
    ├── message.part.delta → connection.sessionUpdate(agent_message_chunk)
    └── permission.asked → connection.requestPermission()
```

### 12.4 WebSocket/SSE 事件

```
/event
    ↓
Bus.subscribe()
    ↓
for each event:
    send as Server-Sent Event 或 WebSocket message
```

---

## 13. 关键数据转换

### 13.1 用户输入 → MessageV2.User

```
文本输入
图片上传
文件引用
    ↓
解析为结构化 message parts
    ↓
MessageV2.User
```

### 13.2 MessageV2 → ModelMessage[]

```
OpenCode MessageV2 格式
    ↓
转换为 AI SDK 格式
    ↓
包含系统提示词的历史消息
```

### 13.3 Tool.Def → AI SDK Tool

```
OpenCode Tool 定义
    ↓
包装 schema 验证
    ↓
包装执行逻辑
    ↓
AI SDK Tool 格式
```

### 13.4 LM Events → MessageV2.Part

```
LLM 流事件 (tool-call, text-delta, etc.)
    ↓
转换流事件为数据库 parts
    ↓
MessageV2.Part 格式
```

### 13.5 MessageV2 → ACP 格式

```
OpenCode 内部消息格式
    ↓
转换为 ACP 协议格式
    ↓
客户端消费
```

---

## 14. 核心类和服务

### 14.1 服务层

| 服务 | 职责 |
|------|------|
| `Server` | HTTP 服务器和路由 |
| `Session.Service` | 会话 CRUD 操作 |
| `SessionProcessor.Service` | LM 流处理 |
| `LM.Service` | AI SDK 集成 |
| `Agent.Service` | Agent 配置管理 |
| `Permission.Service` | 权限管理 |
| `Tool` | 工具定义和执行 |
| `Bus.Service` | 事件广播 |
| `ACP.Agent` | ACP 协议实现 |
| `InstanceState` | 每工作空间状态管理 |

### 14.2 关键文件位置

```
packages/opencode/src/
├── index.ts                    # CLI 入口
├── server/
│   ├── server.ts              # 服务器初始化
│   └── routes/
│       └── instancesession.ts # Prompt API 端点
├── session/
│   ├── session.ts             # 会话管理
│   ├── prompt.ts              # Prompt 处理
│   ├── llm.ts                # LM 流处理
│   └── processor.ts           # 事件处理
├── agent/
│   └── agent.ts               # Agent 定义
├── tool/
│   └── tool.ts               # 工具定义
├── permission/
│   ├── index.ts              # 权限服务
│   └── evaluate.ts           # 权限评估
├── bus/
│   └── bus.ts                # 事件总线
├── acp/
│   └── agent.ts              # ACP 协议
└── cli/
    ├── bootstrap.ts          # Bootstrap 过程
    └── cmd/
        └── acp.ts            # ACP 命令
```

---

## 15. 完整时序图

### 15.1 完整请求流程

```
Client (CLI/Web/Desktop)
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│ 1. 入口点 (index.ts)                                        │
│    - yargs 解析参数                                          │
│    - 数据库迁移                                              │
│    - 命令路由                                                │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│ 2. Bootstrap (bootstrap.ts)                                 │
│    - Instance.provide()                                      │
│    - 实例上下文初始化                                         │
│    - 服务层配置                                              │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│ 3. Server 初始化 (server.ts)                                │
│    - 中间件链应用                                             │
│    - 路由注册                                                │
│    - 监听连接                                                │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│ 4. Session 创建 (session.ts)                                │
│    - 生成 SessionID                                          │
│    - 存储到数据库                                             │
│    - 发布 Session.Created 事件                                │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│ 5. Prompt 请求 (instancesession.ts)                          │
│    - POST /session/:sessionID/message                       │
│    - SessionPrompt.Service.prompt()                         │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│ 6. Agent 选择 (agent.ts)                                    │
│    - Agent.Service.get(agentName)                           │
│    - 加载配置 + 合并权限                                     │
│    - 返回 Agent.Info                                        │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│ 7. LLM 流处理 (llm.ts)                                      │
│    - 获取语言模型                                            │
│    - 构建系统提示词                                          │
│    - 解析工具 (按权限过滤)                                   │
│    - streamText() 调用                                       │
└─────────────────────────────────────────────────────────────┘
    │
    ▼ (流式事件)
┌─────────────────────────────────────────────────────────────┐
│ 8. 事件处理 (processor.ts)                                  │
│    - 处理 reasoning 事件                                    │
│    - 处理 tool-call 事件                                    │
│    - 处理 text 事件                                         │
│    - 处理 step 事件                                         │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│ 9. 工具执行 (tool.ts)                                       │
│    - 权限检查 (Permission.Service.ask())                    │
│    - 工具执行                                               │
│    - 结果返回                                               │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│ 10. 响应流回                                               │
│     - Bus.publish() 广播事件                                │
│     - HTTP 流式响应                                         │
│     - ACP 协议事件                                          │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
Client
```

### 15.2 工具调用详细流程

```
LLM 发出 tool_call
    │
    ▼
SessionProcessor.handleEvent(tool-call)
    │
    ├── 创建 tool part (status: pending)
    │
    ▼
    权限检查
    │
    ├── Permission.Service.ask({
    │     permission: "read",
    │     patterns: ["file.py"],
    │     ruleset: agent.permission
    │   })
    │       │
    │       ▼
    │   Permission.evaluate()
    │       │
    │       ├── 匹配规则?
    │       ├── deny → DeniedError
    │       ├── allow → 继续
    │       └── ask → 发布事件, 等待用户确认
    │
    ▼
    执行工具
    │
    ├── Tool 执行函数
    │   ├── 读取文件
    │   ├── 执行 bash
    │   ├── 网络请求
    │   └── ...
    │
    ▼
    返回 ExecuteResult
    │
    ▼
    更新 tool part
    │
    ├── status: completed
    ├── output: 结果内容
    └── metadata: {duration, etc.}
    │
    ▼
    添加到消息历史
    │
    ▼
    继续 LLM 处理 (下一个 token)
```

### 15.3 多轮对话流程

```
┌──────────┐      ┌──────────┐      ┌──────────┐      ┌──────────┐
│ Round 1  │      │ Round 2  │      │ Round 3  │      │ Round N  │
└────┬─────┘      └────┬─────┘      └────┬─────┘      └────┬─────┘
     │                 │                 │                 │
     ▼                 ▼                 ▼                 ▼
┌─────────┐       ┌─────────┐       ┌─────────┐       ┌─────────┐
│ Prompt  │       │ Prompt  │       │ Prompt  │       │ Prompt  │
│ Input   │       │ Input   │       │ Input   │       │ Input   │
└────┬────┘       └────┬────┘       └────┬────┘       └────┬────┘
     │                 │                 │                 │
     ▼                 ▼                 ▼                 ▼
┌─────────┐       ┌─────────┐       ┌─────────┐       ┌─────────┐
│ Agent   │       │ Agent   │       │ Agent   │       │ Agent   │
│ Select  │       │ Select  │       │ Select  │       │ Select  │
└────┬────┘       └────┬────┘       └────┬────┘       └────┬────┘
     │                 │                 │                 │
     ▼                 ▼                 ▼                 ▼
┌─────────┐       ┌─────────┐       ┌─────────┐       ┌─────────┐
│ LLM     │       │ LLM     │       │ LLM     │       │ LLM     │
│ Stream  │       │ Stream  │       │ Stream  │       │ Stream  │
└────┬────┘       └────┬────┘       └────┬────┘       └────┬────┘
     │                 │                 │                 │
     ├──► Tool Call   ├──► Tool Call   ├──► Tool Call   ├──► Tool Call
     │       │        │       │        │       │        │       │
     │       ▼        │       ▼        │       ▼        │       ▼
     │  Permission   │  Permission   │  Permission   │  Permission
     │      │        │      │        │      │        │      │
     │      ▼        │      ▼        │      ▼        │      ▼
     │   Execute    │   Execute    │   Execute    │   Execute
     │      │        │      │        │      │        │      │
     │      └────────┼──────┴────────┼──────┴────────┼──────┘
     │              │               │               │
     ▼              ▼               ▼               ▼
┌─────────┐       ┌─────────┐       ┌─────────┐       ┌─────────┐
│ Response│       │ Response│       │ Response│       │ Response│
│ Output  │       │ Output  │       │ Output  │       │ Output  │
└─────────┘       └─────────┘       └─────────┘       └─────────┘
     │                 │                 │                 │
     ▼                 ▼                 ▼                 ▼
┌─────────────────────────────────────────────────────────────┐
│ Message History (累积)                                      │
│ [msg1, tool1_result, msg2, tool2_result, ..., msgN]         │
└─────────────────────────────────────────────────────────────┘
```

### 15.4 ACP 协议交互

```
┌──────────────┐                     ┌──────────────┐
│ Client       │                     │ OpenCode     │
│ (Console/    │                     │ Server       │
│ Desktop/Web) │                     │              │
└──────┬───────┘                     └──────┬───────┘
       │                                   │
       │  1. ACP.init()                    │
       │──────────────────────────────────>│
       │  2. capabilities + auth           │
       │<──────────────────────────────────│
       │                                   │
       │  3. newSession()                  │
       │──────────────────────────────────>│
       │  4. session config                │
       │<──────────────────────────────────│
       │                                   │
       │  5. prompt(text, agent)           │
       │──────────────────────────────────>│
       │                                   │
       │  6. 事件流                        │
       │  - message.part.delta            │
       │  - message.part.updated          │
       │  - permission.asked              │
       │<──────────────────────────────────│
       │                                   │
       │  7. reply(permission, decision)  │
       │──────────────────────────────────>│
       │                                   │
       │  8. 更多事件流                    │
       │<──────────────────────────────────│
       │                                   │
       │  9. final response               │
       │<──────────────────────────────────│
       │                                   │
       ▼                                   ▼
```

---

## 附录: 文件关键路径

### 核心服务入口

| 文件 | 行号 | 作用 |
|------|------|------|
| `src/index.ts` | 入口 | CLI 入口点 |
| `src/server/server.ts` | create() | 服务器初始化 |
| `src/cli/bootstrap.ts` | bootstrap() | 实例引导 |
| `src/session/session.ts` | create() | 会话创建 |
| `src/agent/agent.ts` | get() | Agent 获取 |
| `src/session/prompt.ts` | prompt() | Prompt 处理 |
| `src/session/llm.ts` | stream() | LLM 流 |
| `src/tool.ts` | define() | 工具定义 |
| `src/permission/index.ts` | ask() | 权限请求 |
| `src/session/processor.ts` | handleEvent() | 事件处理 |
| `src/acp/agent.ts` | prompt() | ACP Prompt |
