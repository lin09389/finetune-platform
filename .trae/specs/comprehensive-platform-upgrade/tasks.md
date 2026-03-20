# Tasks

## Phase 1: 基础完善（P0 - 紧急）

- [x] Task 1: 完成现有未完成的测试
  - [x] SubTask 1.1: 完成 openclaw-gap-analysis 前端测试（Task 27）
  - [x] SubTask 1.2: 完成 ai-dialogue-system 后端单元测试
  - [x] SubTask 1.3: 完成 ai-dialogue-system 前端组件测试
  - [x] SubTask 1.4: 完成 ai-dialogue-system 集成测试
  - [x] SubTask 1.5: 完成 optimize-inference-speed 引擎测试

- [x] Task 2: 修复已知 Bug
  - [x] SubTask 2.1: 收集和整理现有 Issue 和 Bug 报告
  - [x] SubTask 2.2: 修复推理服务稳定性问题
  - [x] SubTask 2.3: 修复记忆系统存储问题
  - [x] SubTask 2.4: 修复前端渲染性能问题
  - [x] SubTask 2.5: 验证所有修复

- [x] Task 3: 完善文档
  - [x] SubTask 3.1: 更新 CLAUDE.md 推理部分
  - [x] SubTask 3.2: 编写推理优化配置说明
  - [x] SubTask 3.3: 更新 API 文档
  - [x] SubTask 3.4: 编写用户快速入门指南
  - [x] SubTask 3.5: 编写常见问题 FAQ

## Phase 2: 推理性能优化（P1 - 高优先级）

- [x] Task 4: 完善 vLLM 引擎集成
  - [x] SubTask 4.1: 完善 VLLMEngine 类实现
  - [x] SubTask 4.2: 实现多 LoRA 适配器支持
  - [x] SubTask 4.3: 优化 vLLM 配置参数转换
  - [x] SubTask 4.4: 实现优雅降级机制
  - [x] SubTask 4.5: 编写 vLLM 集成测试

- [x] Task 5: 实现量化模型支持
  - [x] SubTask 5.1: 实现 GPTQ 模型加载和推理
  - [x] SubTask 5.2: 实现 AWQ 模型加载和推理
  - [x] SubTask 5.3: 实现 GGUF 模型加载和推理（llama-cpp-python）
  - [x] SubTask 5.4: 实现模型格式自动检测
  - [x] SubTask 5.5: 验证量化模型显存占用

- [x] Task 6: 实现动态批处理
  - [x] SubTask 6.1: 创建 DynamicBatcher 类
  - [x] SubTask 6.2: 实现请求队列管理
  - [x] SubTask 6.3: 实现批处理超时机制
  - [x] SubTask 6.4: 实现批处理结果分发
  - [x] SubTask 6.5: 编写批处理测试

- [x] Task 7: KV Cache 优化
  - [x] SubTask 7.1: 完善 KV Cache 量化配置
  - [x] SubTask 7.2: 实现缓存预热功能
  - [x] SubTask 7.3: 优化缓存分配策略
  - [x] SubTask 7.4: 验证缓存效果

- [x] Task 8: 前端渲染优化
  - [x] SubTask 8.1: 添加推理引擎选择 UI
  - [x] SubTask 8.2: 添加性能监控面板
  - [x] SubTask 8.3: 优化消息渲染性能
  - [x] SubTask 8.4: 实现配置优化建议显示

## Phase 3: Gateway 架构引入（P1 - 高优先级）

- [x] Task 9: 创建 Gateway 核心模块
  - [x] SubTask 9.1: 创建 `server/gateway/__init__.py` 模块入口
  - [x] SubTask 9.2: 创建 `server/gateway/server.py` WebSocket 服务器
  - [x] SubTask 9.3: 创建 `server/gateway/router.py` 消息路由器
  - [x] SubTask 9.4: 创建 `server/gateway/session.py` 会话管理
  - [x] SubTask 9.5: 创建 `server/gateway/models.py` 数据模型

- [x] Task 10: 实现消息路由机制
  - [x] SubTask 10.1: 实现消息接收和解析
  - [x] SubTask 10.2: 实现消息分发到 Agent
  - [x] SubTask 10.3: 实现响应收集和返回
  - [x] SubTask 10.4: 实现事件广播机制
  - [x] SubTask 10.5: 实现心跳和健康检查

- [x] Task 11: 实现设备配对与认证
  - [x] SubTask 11.1: 实现设备注册机制
  - [x] SubTask 11.2: 实现 Token 认证
  - [x] SubTask 11.3: 实现签名挑战验证
  - [x] SubTask 11.4: 实现本地/远程设备区分
  - [x] SubTask 11.5: 实现设备权限管理

- [x] Task 12: 集成现有 API
  - [x] SubTask 12.1: 将现有 REST API 迁移到 Gateway
  - [x] SubTask 12.2: 实现 WebSocket API 端点
  - [x] SubTask 12.3: 实现请求/响应/服务器推送事件
  - [x] SubTask 12.4: 更新前端 API 客户端
  - [x] SubTask 12.5: 编写 Gateway 集成测试

## Phase 4: 记忆-技能深度联动（P1 - 高优先级）

- [x] Task 13: 完善记忆感知技能基类
  - [x] SubTask 13.1: 优化记忆上下文注入钩子
  - [x] SubTask 13.2: 实现记忆相关性排序
  - [x] SubTask 13.3: 实现记忆压缩和摘要
  - [x] SubTask 13.4: 实现跨会话记忆检索

- [x] Task 14: 实现操作记忆管理
  - [x] SubTask 14.1: 扩展操作记忆类型定义
  - [x] SubTask 14.2: 实现操作历史持久化
  - [x] SubTask 14.3: 实现操作模式识别
  - [x] SubTask 14.4: 实现操作回滚支持

- [x] Task 15: 实现用户偏好学习
  - [x] SubTask 15.1: 实现偏好提取算法
  - [x] SubTask 15.2: 实现偏好存储和更新
  - [x] SubTask 15.3: 实现偏好应用到技能参数
  - [x] SubTask 15.4: 实现偏好冲突解决

- [x] Task 16: 实现技能学习与优化
  - [x] SubTask 16.1: 完善技能学习器
  - [x] SubTask 16.2: 实现成功率统计
  - [x] SubTask 16.3: 实现参数自动调优
  - [x] SubTask 16.4: 实现操作建议生成

## Phase 5: 多 Agent 路由机制（P2 - 中优先级）

- [x] Task 17: 实现 Binding Router
  - [x] SubTask 17.1: 创建 `server/gateway/binding.py` 绑定管理
  - [x] SubTask 17.2: 实现绑定规则配置
  - [x] SubTask 17.3: 实现最具体匹配优先算法
  - [x] SubTask 17.4: 实现绑定优先级排序
  - [x] SubTask 17.5: 编写路由算法测试

- [x] Task 18: 实现 Agent 隔离
  - [x] SubTask 18.1: 实现独立 workspace 管理
  - [x] SubTask 18.2: 实现独立 session store
  - [x] SubTask 18.3: 实现独立 skills 管理
  - [x] SubTask 18.4: 实现独立配置管理
  - [x] SubTask 18.5: 编写隔离测试

- [x] Task 19: 实现跨 Agent 通信
  - [x] SubTask 19.1: 实现消息传递机制
  - [x] SubTask 19.2: 实现子 Agent spawn
  - [x] SubTask 19.3: 实现结果收集和合并
  - [x] SubTask 19.4: 实现通信权限控制

## Phase 6: Heartbeat 主动唤醒（P2 - 中优先级）

- [x] Task 20: 实现 Heartbeat 调度器
  - [x] SubTask 20.1: 创建 `server/heartbeat/__init__.py` 模块入口
  - [x] SubTask 20.2: 创建 `server/heartbeat/scheduler.py` 调度器
  - [x] SubTask 20.3: 实现定时唤醒机制
  - [x] SubTask 20.4: 实现任务清单解析（HEARTBEAT.md）
  - [x] SubTask 20.5: 实现唤醒事件触发

- [x] Task 21: 实现主动任务执行
  - [x] SubTask 21.1: 实现检查任务执行
  - [x] SubTask 21.2: 实现汇报任务执行
  - [x] SubTask 21.3: 实现提醒任务执行
  - [x] SubTask 21.4: 实现任务结果处理

## Phase 7: 测试体系完善（P2 - 中优先级）

- [x] Task 22: 建立单元测试
  - [x] SubTask 22.1: 编写推理引擎单元测试
  - [x] SubTask 22.2: 编写记忆系统单元测试
  - [x] SubTask 22.3: 编写 Skills 系统单元测试
  - [x] SubTask 22.4: 编写 Gateway 单元测试
  - [x] SubTask 22.5: 配置 pytest-cov 覆盖率报告

- [x] Task 23: 建立集成测试
  - [x] SubTask 23.1: 编写 Gateway API 集成测试
  - [x] SubTask 23.2: 编写配置向导集成测试
  - [x] SubTask 23.3: 编写错误处理集成测试

- [ ] Task 24: 建立性能基准测试
  - [ ] SubTask 24.1: 创建推理性能基准测试
  - [ ] SubTask 24.2: 创建内存占用基准测试
  - [ ] SubTask 24.3: 创建前端渲染性能测试
  - [ ] SubTask 24.4: 配置 CI/CD 性能回归检测

- [ ] Task 25: 建立前端测试
  - [ ] SubTask 25.1: 配置 Vitest 测试环境
  - [ ] SubTask 25.2: 编写核心组件测试
  - [ ] SubTask 25.3: 编写页面集成测试
  - [ ] SubTask 25.4: 配置测试覆盖率报告

## Phase 8: 用户体验优化（P2 - 中优先级）

- [x] Task 26: 简化配置流程
  - [x] SubTask 26.1: 创建配置向导组件
  - [x] SubTask 26.2: 实现环境自动检测
  - [x] SubTask 26.3: 实现配置建议生成
  - [x] SubTask 26.4: 实现一键配置功能

- [x] Task 27: 改进错误提示
  - [x] SubTask 27.1: 设计友好的错误提示组件
  - [x] SubTask 27.2: 实现错误分类和编码
  - [x] SubTask 27.3: 实现解决建议生成
  - [x] SubTask 27.4: 实现错误日志收集

- [x] Task 28: 完善文档体系
  - [x] SubTask 28.1: 编写用户手册
  - [x] SubTask 28.2: 编写开发者文档
  - [x] SubTask 28.3: 编写 API 参考
  - [x] SubTask 28.4: 编写最佳实践指南

- [x] Task 29: 添加操作引导
  - [x] SubTask 29.1: 创建新手引导流程
  - [x] SubTask 29.2: 创建功能演示
  - [x] SubTask 29.3: 创建交互式教程
  - [x] SubTask 29.4: 创建快捷键提示

## Phase 9: 安全沙箱增强（P2 - 中优先级）

- [x] Task 30: 完善沙箱隔离
  - [x] SubTask 30.1: 实现能力权限模型
  - [x] SubTask 30.2: 实现资源限制管理
  - [x] SubTask 30.3: 实现隔离执行器
  - [x] SubTask 30.4: 实现凭证管理器

- [x] Task 31: 增强 Prompt 安全
  - [x] SubTask 31.1: 实现 Prompt 注入检测器
  - [x] SubTask 31.2: 创建注入模式库
  - [x] SubTask 31.3: 实现内容清理器
  - [x] SubTask 31.4: 集成到安全中间件

- [x] Task 32: 完善审计日志
  - [x] SubTask 32.1: 实现操作审计日志
  - [x] SubTask 32.2: 实现敏感数据访问日志
  - [x] SubTask 32.3: 实现审计日志查询
  - [x] SubTask 32.4: 实现审计报告生成

## Phase 10: 清理与整合

- [x] Task 33: 清理重复的 specs
  - [x] SubTask 33.1: 归档 cua-integration spec（功能已在 openclaw-gap-analysis）
  - [x] SubTask 33.2: 归档 ironclaw-integration spec（功能已整合到本计划）
  - [x] SubTask 33.3: 更新相关文档引用

- [x] Task 34: 最终验证
  - [x] SubTask 34.1: 运行所有测试套件
  - [x] SubTask 34.2: 验证性能指标达标
  - [x] SubTask 34.3: 验证功能完整性
  - [x] SubTask 34.4: 生成验收报告

# Task Dependencies

- [Task 2] depends on [Task 1]
- [Task 3] depends on [Task 1, Task 2]
- [Task 4] depends on [Task 1]
- [Task 5] depends on [Task 4]
- [Task 6] depends on [Task 4]
- [Task 7] depends on [Task 4]
- [Task 8] depends on [Task 4, Task 5, Task 6, Task 7]
- [Task 9] depends on [Task 1]
- [Task 10] depends on [Task 9]
- [Task 11] depends on [Task 9]
- [Task 12] depends on [Task 10, Task 11]
- [Task 13] depends on [Task 1]
- [Task 14] depends on [Task 13]
- [Task 15] depends on [Task 14]
- [Task 16] depends on [Task 15]
- [Task 17] depends on [Task 12]
- [Task 18] depends on [Task 17]
- [Task 19] depends on [Task 18]
- [Task 20] depends on [Task 12]
- [Task 21] depends on [Task 20]
- [Task 22] depends on [Task 1]
- [Task 23] depends on [Task 22]
- [Task 24] depends on [Task 4, Task 5, Task 6, Task 7]
- [Task 25] depends on [Task 22]
- [Task 26] depends on [Task 3]
- [Task 27] depends on [Task 26]
- [Task 28] depends on [Task 3]
- [Task 29] depends on [Task 26, Task 28]
- [Task 30] depends on [Task 1]
- [Task 31] depends on [Task 30]
- [Task 32] depends on [Task 30]
- [Task 33] depends on [Task 1]
- [Task 34] depends on [Task 1-33]

# Parallelizable Work

以下任务可以并行执行：

**Phase 2 可并行：**
- Task 4, 5, 6, 7 可并行开发（不同优化方向）

**Phase 3-4 可并行：**
- Task 9-12（Gateway）与 Task 13-16（记忆联动）可并行

**Phase 5-6 可并行：**
- Task 17-19（多 Agent）与 Task 20-21（Heartbeat）可并行

**Phase 7 可并行：**
- Task 22, 23, 24, 25 可并行开发

**Phase 8 可并行：**
- Task 26, 27, 28, 29 可并行开发

**Phase 9 可并行：**
- Task 30, 31, 32 可并行开发

# 实施里程碑

## 里程碑 1：基础稳定（第 2 周末）

- 所有现有测试通过
- 已知 Bug 修复完成
- 文档基础完善

## 里程碑 2：性能达标（第 6 周末）

- 推理速度达到 50+ tokens/s
- 首字延迟 < 200ms
- 量化模型支持完成

## 里程碑 3：架构升级（第 10 周末）

- Gateway 上线运行
- 多 Agent 路由可用
- Heartbeat 正常工作
- 记忆-技能联动完整

## 里程碑 4：体验优化（第 12 周末）

- 测试覆盖率 > 80%
- 用户体验显著提升
- 文档完整
- 验收通过
