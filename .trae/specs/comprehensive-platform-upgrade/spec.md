# Finetune Platform 2.0 全面改进升级计划 Spec

## Why

当前 finetune-platform 项目已具备基础的微调、推理、Agent、Skills、记忆系统等功能，但存在多个未完成的升级计划、性能优化待完善、测试覆盖不足、以及与 OpenClaw 等领先架构的差距。本计划旨在系统梳理现状、明确优先级、制定可执行的改进方案，确保项目健康可持续发展。

## 项目现状分析

### 一、已完成的核心能力

| 模块                       | 完成度 | 状态       |
| ------------------------ | --- | -------- |
| 微调训练核心                   | 90% | ✅ 稳定运行   |
| 推理服务（HuggingFace/Ollama） | 85% | ✅ 基本可用   |
| RAG 知识库                  | 80% | ✅ 功能完整   |
| 三级记忆系统                   | 75% | ✅ 架构完整   |
| Skills 系统                | 70% | ⚠️ 需增强   |
| CUA 桌面操作                 | 93% | 🔄 测试待完善 |
| MCP 协议                   | 90% | ✅ 基本可用   |
| 前端界面                     | 80% | ⚠️ 需优化   |

### 二、存在的核心问题

#### 1. 性能瓶颈

### 推理速度未达预期（目标 50+ tokens/s，当前约 20-30）

- 首字延迟偏高（目标 <200ms，当前约 500ms）
- 显存占用优化不足
- 批处理功能未实现
- 前端渲染性能待优化

#### 2. 测试覆盖不足

- 后端单元测试覆盖率低
- 前端组件测试缺失
- 集成测试不完整
- 性能基准测试未建立

#### 3. 架构差距（对比 OpenClaw）

- 缺乏 Gateway 统一入口
- 缺乏多 Agent 路由机制
- 缺乏 Heartbeat 主动唤醒
- 记忆-技能联动未完全打通
- 安全沙箱不完善

#### 4. 用户体验问题

- 配置复杂，新手友好度低
- 错误提示不够清晰
- 文档不完善
- 缺乏操作引导

### 三、未完成的升级计划

| 计划                       | 完成度 | 阻塞项                        |
| ------------------------ | --- | -------------------------- |
| openclaw-gap-analysis    | 93% | 前端测试未完成                    |
| ai-dialogue-system       | 85% | 测试未通过                      |
| optimize-inference-speed | 60% | 量化/批处理未实现                  |
| cua-integration          | 0%  | 与 openclaw-gap-analysis 重复 |
| ironclaw-integration     | 0%  | 待启动                        |

## What Changes

### 1. 性能优化升级（高优先级）

- **BREAKING**: 重构推理引擎架构，统一 HuggingFace/vLLM 接口
- 实现动态批处理（Dynamic Batching）
- 完善 Flash Attention 2 集成
- 实现 KV Cache 优化
- 实现量化模型支持（GPTQ/AWQ/GGUF）
- 优化前端渲染性能（虚拟滚动、懒加载）

### 2. 架构优化升级（高优先级）

- 引入 Gateway 统一入口模式
- 实现多 Agent 路由机制
- 实现 Heartbeat 主动唤醒
- 完善记忆-技能联动
- 增强安全沙箱

### 3. 测试体系完善（中优先级）

- 建立完整的单元测试
- 建立集成测试套件
- 建立性能基准测试
- 建立 E2E 测试

### 4. 用户体验优化（中优先级）

- 简化配置流程
- 改进错误提示
- 完善文档体系
- 添加操作引导

### 5. 运维能力增强（低优先级）

- 完善监控指标
- 实现健康检查
- 实现优雅降级
- 完善日志系统

## Impact

- **Affected specs**: 所有现有 specs 需要整合和清理
- **Affected code**:
  - `server/core/inference/` - 推理引擎重构
  - `server/agent/` - Agent 架构优化
  - `server/memory/` - 记忆系统增强
  - `server/skills/` - Skills 系统完善
  - `server/security/` - 安全模块增强
  - `client/src/` - 前端优化
  - `server/tests/` - 测试完善

## ADDED Requirements

### Requirement: 推理性能优化

系统 SHALL 提供高性能推理能力：

- 7B 模型推理速度达到 50+ tokens/s（使用 vLLM）
- 首字延迟降低到 200ms 以下
- 显存占用减少 30% 以上（使用量化）
- 批处理吞吐量提升 2x 以上
- 流式输出延迟降低到 10ms 以下

#### Scenario: vLLM 引擎加速

- **WHEN** 用户启用 vLLM 引擎
- **THEN** 系统自动配置 PagedAttention 和前缀缓存
- **AND** 推理速度达到 50+ tokens/s

#### Scenario: 量化模型推理

- **WHEN** 用户加载 GPTQ/AWQ/GGUF 量化模型
- **THEN** 系统自动检测模型格式并正确加载
- **AND** 显存占用减少 30% 以上

### Requirement: Gateway 统一入口

系统 SHALL 提供 Gateway 统一入口：

- WebSocket 服务器作为控制平面
- 消息路由和分发
- 设备配对与认证
- 事件广播机制
- Canvas 宿主服务

#### Scenario: 消息路由

- **WHEN** 用户通过不同渠道（CLI/Web/API）发送消息
- **THEN** Gateway 统一接收并路由到正确的 Agent
- **AND** 返回结果正确分发给请求方

### Requirement: 多 Agent 路由

系统 SHALL 支持多 Agent 路由：

- 基于 Binding 的消息路由
- 最具体匹配优先算法
- Agent 隔离（独立 workspace、session、skills）
- 跨 Agent 通信机制

#### Scenario: Agent 隔离

- **WHEN** 消息路由到特定 Agent
- **THEN** 该 Agent 使用独立的 workspace 和配置
- **AND** 不同 Agent 之间数据隔离

### Requirement: Heartbeat 主动唤醒

系统 SHALL 提供 Heartbeat 主动唤醒机制：

- 定期唤醒 Agent（可配置间隔）
- 检查任务清单（HEARTBEAT.md）
- 主动汇报和提醒
- 避免无效轮询

#### Scenario: 定期检查

- **WHEN** Heartbeat 定时器触发
- **THEN** Agent 检查 HEARTBEAT.md 中的任务清单
- **AND** 执行必要的检查和汇报

### Requirement: 记忆-技能深度联动

系统 SHALL 实现记忆-技能深度联动：

- 技能执行前自动注入相关记忆
- 技能执行后自动存储操作结果
- 用户偏好学习与技能参数优化
- 操作模式自动学习

#### Scenario: 记忆注入

- **WHEN** 执行记忆感知技能
- **THEN** 系统自动检索相关记忆并注入上下文
- **AND** 技能可根据记忆优化执行

### Requirement: 完整测试体系

系统 SHALL 建立完整测试体系：

- 后端单元测试覆盖率 > 80%
- 前端组件测试覆盖率 > 70%
- 集成测试覆盖核心流程
- 性能基准测试可重复执行

#### Scenario: CI/CD 集成

- **WHEN** 提交代码变更
- **THEN** 自动运行所有测试
- **AND** 测试失败时阻止合并

### Requirement: 用户体验优化

系统 SHALL 优化用户体验：

- 一键安装和配置
- 清晰的错误提示和解决建议
- 完整的中英文文档
- 交互式操作引导

#### Scenario: 新用户引导

- **WHEN** 新用户首次启动系统
- **THEN** 显示交互式引导流程
- **AND** 自动检测环境并给出配置建议

## MODIFIED Requirements

### Requirement: 推理引擎架构

原有推理引擎 SHALL 重构为统一接口：

- 抽象 InferenceEngine 基类
- HuggingFaceEngine、VLLMEngine、OllamaEngine 实现
- 引擎工厂自动选择最优引擎
- 支持运行时引擎切换

### Requirement: Skills 系统

原有 Skills 系统 SHALL 增强：

- 记忆感知技能基类
- 技能学习与优化机制
- 技能权限细粒度控制
- 技能市场支持

### Requirement: 安全模块

原有安全模块 SHALL 增强：

- Prompt 注入检测
- 敏感数据泄露检测
- 沙箱隔离执行
- 操作审计增强

## REMOVED Requirements

### Requirement: cua-integration spec

**Reason**: 与 openclaw-gap-analysis 功能重复，已合并
**Migration**: 相关任务已整合到本计划

### Requirement: ironclaw-integration spec

**Reason**: 相关功能已整合到本计划的架构优化部分
**Migration**: 沙箱、MCP、Routines 等功能已纳入本计划

## 升级目标与优先级

### P0 - 紧急（1-2 周）

1. 完成现有未完成的测试
2. 修复已知 Bug
3. 完善文档

### P1 - 高优先级（2-4 周）

1. 推理性能优化（vLLM、量化、批处理）
2. Gateway 架构引入
3. 记忆-技能深度联动

### P2 - 中优先级（4-8 周）

1. 多 Agent 路由机制
2. Heartbeat 主动唤醒
3. 测试体系完善
4. 用户体验优化

### P3 - 低优先级（8-12 周）

1. 多渠道支持（Telegram/Slack）
2. 技能市场
3. 高级监控告警

## 资源需求评估

### 人力需求

| 角色    | 人数 | 周期   | 职责         |
| ----- | -- | ---- | ---------- |
| 后端开发  | 2  | 12 周 | 推理优化、架构重构  |
| 前端开发  | 1  | 8 周  | UI 优化、性能提升 |
| 测试工程师 | 1  | 12 周 | 测试体系建设     |
| 文档工程师 | 1  | 4 周  | 文档完善       |

### 时间估算

| 阶段       | 周期  | 里程碑                |
| -------- | --- | ------------------ |
| 阶段一：基础完善 | 2 周 | 测试通过、文档完善          |
| 阶段二：性能优化 | 4 周 | 推理性能达标             |
| 阶段三：架构升级 | 4 周 | Gateway、多 Agent 上线 |
| 阶段四：体验优化 | 2 周 | 用户体验显著提升           |

### 预算估算

| 项目            | 成本          |
| ------------- | ----------- |
| GPU 资源（测试验证）  | ¥5,000      |
| 第三方服务（监控、CDN） | ¥2,000      |
| 文档翻译          | ¥3,000      |
| **总计**        | **¥10,000** |

## 风险评估与应对策略

| 风险         | 概率 | 影响 | 缓解措施                |
| ---------- | -- | -- | ------------------- |
| vLLM 兼容性问题 | 中  | 高  | 保留 HuggingFace 降级方案 |
| 性能优化不达预期   | 中  | 中  | 分阶段验证，及时调整          |
| 架构重构引入 Bug | 高  | 高  | 完善测试，灰度发布           |
| 依赖库版本冲突    | 中  | 中  | 锁定版本，虚拟环境隔离         |
| 人力不足       | 低  | 高  | 优先级排序，分阶段实施         |

## 预期成果与验收标准

### 性能指标

| 指标    | 当前值       | 目标值     | 验收方法            |
| ----- | --------- | ------- | --------------- |
| 推理速度  | 20-30 t/s | 50+ t/s | 性能基准测试          |
| 首字延迟  | \~500ms   | <200ms  | 性能基准测试          |
| 显存占用  | 基准        | -30%    | 监控对比            |
| 测试覆盖率 | \~40%     | >80%    | pytest-cov      |
| 前端帧率  | \~30fps   | 60fps   | Chrome DevTools |

### 功能指标

| 功能        | 验收标准                |
| --------- | ------------------- |
| Gateway   | 所有请求通过 Gateway 路由   |
| 多 Agent   | 支持至少 3 个隔离 Agent    |
| Heartbeat | 定时任务准时触发            |
| 记忆联动      | 技能可访问相关记忆           |
| 量化支持      | GPTQ/AWQ/GGUF 模型可加载 |

### 质量指标

| 指标    | 目标             |
| ----- | -------------- |
| 代码质量  | SonarQube 评分 A |
| 文档完整度 | 所有 API 有文档     |
| 错误处理  | 所有异常有友好提示      |
| 安全审计  | 无高危漏洞          |

