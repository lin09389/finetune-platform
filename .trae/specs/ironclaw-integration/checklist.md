# IronClaw 融合计划 Checklist

## Phase 1: 安全沙箱系统

- [ ] `server/sandbox/__init__.py` 模块入口已创建
- [ ] 能力权限模型 `capabilities.py` 已实现
- [ ] 隔离执行器 `executor.py` 已实现
- [ ] 资源限制管理 `resource_limits.py` 已实现
- [ ] 凭证管理器 `credentials.py` 已实现
- [ ] 凭证注入机制正常工作
- [ ] 泄露检测扫描器已实现
- [ ] Agent 执行器已集成沙箱模式
- [ ] 沙箱执行审计日志正常记录

## Phase 2: MCP 协议集成

- [ ] `server/mcp/__init__.py` 模块入口已创建
- [ ] MCP 协议定义 `protocol.py` 已实现
- [ ] MCP 客户端 `client.py` 已实现
- [ ] 服务器管理器 `server_manager.py` 已实现
- [ ] 工具注册表 `tool_registry.py` 已实现
- [ ] 动态工具发现机制正常工作
- [ ] 工具调用路由正常工作
- [ ] `GET /mcp/tools` 端点返回正确数据
- [ ] `POST /mcp/call` 端点正确调用工具
- [ ] `POST /mcp/servers` 端点正确管理服务器

## Phase 3: Routines 引擎

- [ ] `server/routines/__init__.py` 模块入口已创建
- [ ] 调度器 `scheduler.py` 已实现
- [ ] Cron 解析器 `cron_parser.py` 已实现
- [ ] 任务执行器 `task_runner.py` 已实现
- [ ] 事件触发器已实现
- [ ] Webhook 触发器已实现
- [ ] 触发器注册和管理正常工作
- [ ] 训练任务定时启动正常工作
- [ ] 模型更新事件触发正常工作
- [ ] 推理测试自动化正常工作
- [ ] `POST /routines/create` 端点正确创建任务
- [ ] `GET /routines/list` 端点返回正确数据
- [ ] `DELETE /routines/{id}` 端点正确删除任务
- [ ] `GET /routines/history` 端点返回正确历史

## Phase 4: 多渠道支持

- [ ] `server/channels/__init__.py` 模块入口已创建
- [ ] 渠道基类 `base.py` 已实现
- [ ] 消息路由器 `router.py` 已实现
- [ ] Telegram Bot 客户端已实现
- [ ] Telegram 消息处理正常工作
- [ ] Telegram Webhook 设置和管理正常工作
- [ ] Slack Bot 客户端已实现
- [ ] Slack 消息处理正常工作
- [ ] Slack 斜杠命令处理正常工作
- [ ] `POST /channels/telegram/setup` 端点正确配置
- [ ] `POST /channels/slack/setup` 端点正确配置
- [ ] `GET /channels/status` 端点返回正确状态

## Phase 5: Safety Layer 增强

- [ ] Prompt 注入检测器 `prompt_injection.py` 已实现
- [ ] 注入模式库已创建
- [ ] 内容清理器已实现
- [ ] 策略执行引擎已实现
- [ ] 安全中间件已集成新检测器
- [ ] 请求内容安全扫描正常工作
- [ ] 响应内容泄露检测正常工作

## Phase 6: 前端界面扩展

- [ ] `client/src/pages/Routines.tsx` 页面已创建
- [ ] 任务列表展示正常
- [ ] 任务创建表单（Cron 编辑器）正常工作
- [ ] 执行历史查看正常
- [ ] `client/src/pages/Channels.tsx` 页面已创建
- [ ] Telegram 配置表单正常工作
- [ ] Slack 配置表单正常工作
- [ ] 渠道状态展示正常
- [ ] `client/src/pages/SecurityDashboard.tsx` 页面已创建
- [ ] 安全事件统计图表正常显示
- [ ] 注入攻击日志查看正常
- [ ] 策略配置界面正常工作
- [ ] Sidebar 已添加新菜单项
- [ ] API 服务已添加新方法
- [ ] 类型定义已添加

## Phase 7: 测试和文档

- [ ] 沙箱测试 `test_sandbox.py` 通过
- [ ] MCP 测试 `test_mcp.py` 通过
- [ ] Routines 测试 `test_routines.py` 通过
- [ ] 渠道测试 `test_channels.py` 通过
- [ ] Routines 页面测试通过
- [ ] Channels 页面测试通过
- [ ] SecurityDashboard 页面测试通过

## 集成验证

- [ ] 后端服务启动无错误
- [ ] 前端服务启动无错误
- [ ] 所有新 API 端点可访问
- [ ] 所有新页面可访问
- [ ] 沙箱隔离执行验证通过
- [ ] MCP 工具调用验证通过
- [ ] 定时任务执行验证通过
- [ ] Telegram 消息收发验证通过
- [ ] Slack 消息收发验证通过
- [ ] Prompt 注入防御验证通过
