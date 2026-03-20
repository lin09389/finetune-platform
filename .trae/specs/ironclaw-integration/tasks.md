# Tasks

## Phase 1: 安全沙箱系统

- [ ] Task 1: 创建沙箱核心模块
  - [ ] SubTask 1.1: 创建 `server/sandbox/__init__.py` 模块入口
  - [ ] SubTask 1.2: 实现 `server/sandbox/capabilities.py` 能力权限模型
  - [ ] SubTask 1.3: 实现 `server/sandbox/executor.py` 隔离执行器
  - [ ] SubTask 1.4: 实现 `server/sandbox/resource_limits.py` 资源限制管理

- [ ] Task 2: 实现凭证保护机制
  - [ ] SubTask 2.1: 创建 `server/sandbox/credentials.py` 凭证管理器
  - [ ] SubTask 2.2: 实现凭证注入机制（主机边界注入）
  - [ ] SubTask 2.3: 实现泄露检测扫描器

- [ ] Task 3: 集成沙箱到 Agent 执行器
  - [ ] SubTask 3.1: 修改 `server/agent/executor.py` 支持沙箱模式
  - [ ] SubTask 3.2: 添加沙箱执行配置选项
  - [ ] SubTask 3.3: 更新审计日志记录沙箱事件

## Phase 2: MCP 协议集成

- [ ] Task 4: 创建 MCP 核心模块
  - [ ] SubTask 4.1: 创建 `server/mcp/__init__.py` 模块入口
  - [ ] SubTask 4.2: 实现 `server/mcp/protocol.py` 协议定义
  - [ ] SubTask 4.3: 实现 `server/mcp/client.py` MCP 客户端
  - [ ] SubTask 4.4: 实现 `server/mcp/server_manager.py` 服务器管理器

- [ ] Task 5: 实现工具注册和发现
  - [ ] SubTask 5.1: 实现 `server/mcp/tool_registry.py` 工具注册表
  - [ ] SubTask 5.2: 实现动态工具发现机制
  - [ ] SubTask 5.3: 实现工具调用路由

- [ ] Task 6: 创建 MCP API 端点
  - [ ] SubTask 6.1: 创建 `server/api/mcp.py` API 路由
  - [ ] SubTask 6.2: 实现 `GET /mcp/tools` 列出工具
  - [ ] SubTask 6.3: 实现 `POST /mcp/call` 调用工具
  - [ ] SubTask 6.4: 实现 `POST /mcp/servers` 管理服务器

## Phase 3: Routines 引擎

- [ ] Task 7: 创建 Routines 核心模块
  - [ ] SubTask 7.1: 创建 `server/routines/__init__.py` 模块入口
  - [ ] SubTask 7.2: 实现 `server/routines/scheduler.py` 调度器
  - [ ] SubTask 7.3: 实现 `server/routines/cron_parser.py` Cron 解析器
  - [ ] SubTask 7.4: 实现 `server/routines/task_runner.py` 任务执行器

- [ ] Task 8: 实现触发器系统
  - [ ] SubTask 8.1: 实现 `server/routines/triggers/event.py` 事件触发器
  - [ ] SubTask 8.2: 实现 `server/routines/triggers/webhook.py` Webhook 触发器
  - [ ] SubTask 8.3: 实现触发器注册和管理

- [ ] Task 9: 集成训练自动化
  - [ ] SubTask 9.1: 实现训练任务定时启动
  - [ ] SubTask 9.2: 实现模型更新事件触发
  - [ ] SubTask 9.3: 实现推理测试自动化

- [ ] Task 10: 创建 Routines API 端点
  - [ ] SubTask 10.1: 创建 `server/api/routines.py` API 路由
  - [ ] SubTask 10.2: 实现 `POST /routines/create` 创建任务
  - [ ] SubTask 10.3: 实现 `GET /routines/list` 列出任务
  - [ ] SubTask 10.4: 实现 `DELETE /routines/{id}` 删除任务
  - [ ] SubTask 10.5: 实现 `GET /routines/history` 执行历史

## Phase 4: 多渠道支持

- [ ] Task 11: 创建渠道核心模块
  - [ ] SubTask 11.1: 创建 `server/channels/__init__.py` 模块入口
  - [ ] SubTask 11.2: 实现 `server/channels/base.py` 渠道基类
  - [ ] SubTask 11.3: 实现 `server/channels/router.py` 消息路由器

- [ ] Task 12: 实现 Telegram Bot 集成
  - [ ] SubTask 12.1: 创建 `server/channels/telegram/__init__.py`
  - [ ] SubTask 12.2: 实现 `server/channels/telegram/bot.py` Bot 客户端
  - [ ] SubTask 12.3: 实现 `server/channels/telegram/handler.py` 消息处理
  - [ ] SubTask 12.4: 实现 Webhook 设置和管理

- [ ] Task 13: 实现 Slack Bot 集成
  - [ ] SubTask 13.1: 创建 `server/channels/slack/__init__.py`
  - [ ] SubTask 13.2: 实现 `server/channels/slack/bot.py` Bot 客户端
  - [ ] SubTask 13.3: 实现 `server/channels/slack/handler.py` 消息处理
  - [ ] SubTask 13.4: 实现斜杠命令处理

- [ ] Task 14: 创建渠道 API 端点
  - [ ] SubTask 14.1: 创建 `server/api/channels.py` API 路由
  - [ ] SubTask 14.2: 实现 `POST /channels/telegram/setup` 配置 Telegram
  - [ ] SubTask 14.3: 实现 `POST /channels/slack/setup` 配置 Slack
  - [ ] SubTask 14.4: 实现 `GET /channels/status` 渠道状态

## Phase 5: Safety Layer 增强

- [ ] Task 15: 实现 Prompt 注入防御
  - [ ] SubTask 15.1: 创建 `server/security/prompt_injection.py` 检测器
  - [ ] SubTask 15.2: 实现注入模式库
  - [ ] SubTask 15.3: 实现内容清理器
  - [ ] SubTask 15.4: 实现策略执行引擎

- [ ] Task 16: 增强安全中间件
  - [ ] SubTask 16.1: 更新 `server/security/middleware.py` 集成新检测器
  - [ ] SubTask 16.2: 添加请求内容安全扫描
  - [ ] SubTask 16.3: 添加响应内容泄露检测

## Phase 6: 前端界面扩展

- [ ] Task 17: 创建 Routines 管理页面
  - [ ] SubTask 17.1: 创建 `client/src/pages/Routines.tsx` 页面组件
  - [ ] SubTask 17.2: 实现任务列表展示
  - [ ] SubTask 17.3: 实现任务创建表单（Cron 编辑器）
  - [ ] SubTask 17.4: 实现执行历史查看

- [ ] Task 18: 创建渠道配置页面
  - [ ] SubTask 18.1: 创建 `client/src/pages/Channels.tsx` 页面组件
  - [ ] SubTask 18.2: 实现 Telegram 配置表单
  - [ ] SubTask 18.3: 实现 Slack 配置表单
  - [ ] SubTask 18.4: 实现渠道状态展示

- [ ] Task 19: 创建安全审计仪表板
  - [ ] SubTask 19.1: 创建 `client/src/pages/SecurityDashboard.tsx` 页面组件
  - [ ] SubTask 19.2: 实现安全事件统计图表
  - [ ] SubTask 19.3: 实现注入攻击日志查看
  - [ ] SubTask 19.4: 实现策略配置界面

- [ ] Task 20: 更新导航和 API 服务
  - [ ] SubTask 20.1: 更新 `client/src/components/Sidebar.tsx` 添加新菜单
  - [ ] SubTask 20.2: 更新 `client/src/services/api.ts` 添加新 API 方法
  - [ ] SubTask 20.3: 更新 `client/src/types/index.ts` 添加类型定义

## Phase 7: 测试和文档

- [ ] Task 21: 编写后端测试
  - [ ] SubTask 21.1: 编写 `server/tests/test_sandbox.py` 沙箱测试
  - [ ] SubTask 21.2: 编写 `server/tests/test_mcp.py` MCP 测试
  - [ ] SubTask 21.3: 编写 `server/tests/test_routines.py` Routines 测试
  - [ ] SubTask 21.4: 编写 `server/tests/test_channels.py` 渠道测试

- [ ] Task 22: 编写前端测试
  - [ ] SubTask 22.1: 编写 Routines 页面测试
  - [ ] SubTask 22.2: 编写 Channels 页面测试
  - [ ] SubTask 22.3: 编写 SecurityDashboard 页面测试

# Task Dependencies

- [Task 2] depends on [Task 1]
- [Task 3] depends on [Task 1, Task 2]
- [Task 5] depends on [Task 4]
- [Task 6] depends on [Task 4, Task 5]
- [Task 8] depends on [Task 7]
- [Task 9] depends on [Task 7, Task 8]
- [Task 10] depends on [Task 7, Task 8, Task 9]
- [Task 12] depends on [Task 11]
- [Task 13] depends on [Task 11]
- [Task 14] depends on [Task 11, Task 12, Task 13]
- [Task 16] depends on [Task 15]
- [Task 17] depends on [Task 10]
- [Task 18] depends on [Task 14]
- [Task 19] depends on [Task 15, Task 16]
- [Task 20] depends on [Task 17, Task 18, Task 19]
- [Task 21] depends on [Task 1-16]
- [Task 22] depends on [Task 17-20]

# Parallelizable Work

以下任务可以并行执行：
- Phase 1 (Task 1-3) 和 Phase 2 (Task 4-6) 可以并行
- Phase 3 (Task 7-10) 和 Phase 4 (Task 11-14) 可以并行
- Phase 5 (Task 15-16) 可以与其他 Phase 并行
- Phase 6 (Task 17-19) 的各页面可以并行开发
