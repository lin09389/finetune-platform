# IronClaw 融合计划 Spec

## Why

当前 finetune-platform 项目已具备基础的 Agent 执行、RAG 知识库、记忆系统等功能，但缺乏 IronClaw 项目中的高级特性：
- **WASM 沙箱安全执行** - 当前 Agent 执行器缺乏隔离机制
- **MCP 协议支持** - 无法连接外部工具服务器
- **Routines 引擎** - 缺少定时任务和事件触发能力
- **多渠道支持** - 仅支持 Web 界面，无 Telegram/Slack 集成
- **Prompt 注入防御** - 安全层较薄弱

融合 IronClaw 的核心架构将显著提升平台的安全性、扩展性和自动化能力。

## What Changes

### 1. 安全沙箱系统
- 新增 `server/sandbox/` 模块，实现 WASM 风格的隔离执行
- 实现能力权限模型（Capability-based permissions）
- 添加凭证保护和泄露检测

### 2. MCP 协议集成
- 新增 `server/mcp/` 模块，实现 Model Context Protocol
- 支持连接外部 MCP 服务器
- 实现工具注册和动态发现

### 3. Routines 引擎
- 新增 `server/routines/` 模块，实现定时任务引擎
- 支持 Cron 调度、事件触发、Webhook 处理
- 集成训练任务自动化

### 4. 多渠道支持
- 新增 `server/channels/` 模块
- 实现 Telegram Bot 集成
- 实现 Slack Bot 集成
- 统一消息路由层

### 5. Safety Layer 增强
- 增强 `server/security/` 模块
- 实现 Prompt 注入检测
- 添加内容清理和策略执行

### 6. 前端界面扩展
- 新增 Routines 管理页面
- 新增渠道配置页面
- 新增安全审计仪表板

## Impact

- **Affected specs**: Agent 执行、安全模块、API 端点
- **Affected code**: 
  - `server/agent/` - 执行器重构
  - `server/security/` - 安全层增强
  - `server/api/` - 新增端点
  - `client/src/pages/` - 新增页面
  - `client/src/services/api.ts` - API 扩展

## ADDED Requirements

### Requirement: WASM 沙箱执行环境

系统 SHALL 提供隔离的工具执行环境，支持：
- 能力权限声明和验证
- 资源限制（内存、CPU、执行时间）
- 网络访问白名单
- 凭证安全注入

#### Scenario: 工具执行隔离
- **WHEN** Agent 需要执行外部工具
- **THEN** 工具在隔离环境中运行，无法直接访问系统资源

#### Scenario: 凭证保护
- **WHEN** 工具需要访问受保护资源
- **THEN** 凭证在主机边界注入，不暴露给工具代码

### Requirement: MCP 协议支持

系统 SHALL 支持 Model Context Protocol：
- 连接外部 MCP 服务器
- 动态发现和注册工具
- 工具调用路由

#### Scenario: MCP 工具发现
- **WHEN** 用户配置 MCP 服务器
- **THEN** 系统自动发现并注册可用工具

#### Scenario: MCP 工具调用
- **WHEN** Agent 需要使用 MCP 工具
- **THEN** 通过协议路由调用并返回结果

### Requirement: Routines 引擎

系统 SHALL 提供自动化任务调度：
- Cron 表达式调度
- 事件触发器
- Webhook 处理器
- 任务执行历史

#### Scenario: 定时训练任务
- **WHEN** 用户创建定时训练任务
- **THEN** 系统按计划自动启动训练

#### Scenario: 事件触发推理
- **WHEN** 特定事件发生（如模型更新）
- **THEN** 自动触发推理测试

### Requirement: 多渠道消息接入

系统 SHALL 支持多渠道消息接入：
- Telegram Bot
- Slack Bot
- 统一消息路由

#### Scenario: Telegram 消息处理
- **WHEN** 用户通过 Telegram 发送消息
- **THEN** 消息路由到 Agent 处理并返回结果

#### Scenario: Slack 命令处理
- **WHEN** 用户在 Slack 中使用斜杠命令
- **THEN** 执行对应操作并返回响应

### Requirement: Prompt 注入防御

系统 SHALL 提供 Prompt 注入防御：
- 模式检测
- 内容清理
- 策略执行（Block/Warn/Review/Sanitize）

#### Scenario: 注入攻击检测
- **WHEN** 用户输入包含潜在注入模式
- **THEN** 系统检测并按策略处理

#### Scenario: 内容清理
- **WHEN** 外部内容包含危险指令
- **THEN** 系统清理后安全注入上下文

## MODIFIED Requirements

### Requirement: Agent 执行器增强

原有 Agent 执行器 SHALL 集成沙箱执行：
- 所有工具调用通过沙箱路由
- 支持权限声明和验证
- 审计日志增强

### Requirement: 安全模块扩展

原有安全模块 SHALL 增加：
- Prompt 注入检测器
- 凭证泄露扫描器
- 端点白名单验证器

### Requirement: API 端点扩展

原有 API SHALL 新增端点：
- `POST /routines/create` - 创建定时任务
- `GET /routines/list` - 列出任务
- `POST /channels/telegram/setup` - 配置 Telegram
- `POST /channels/slack/setup` - 配置 Slack
- `GET /mcp/tools` - 列出 MCP 工具
- `POST /mcp/call` - 调用 MCP 工具

## REMOVED Requirements

无移除的功能，所有改动为增量添加。
