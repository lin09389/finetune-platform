# Finetune Platform 全面重构 Spec（排除训练模块）

## Why

当前 finetune-platform 项目经过多轮迭代开发，存在以下问题需要通过全面重构解决：

1. **架构层面**
   - 模块间耦合度高，依赖关系混乱
   - 部分模块职责不清晰，代码重复
   - 缺乏统一的错误处理和响应格式
   - 配置管理分散，缺乏统一规范

2. **代码质量**
   - 部分代码缺乏类型注解
   - 异常处理不完善
   - 日志记录不规范
   - 测试覆盖率不足

3. **性能问题**
   - API 响应速度不稳定
   - 内存管理不完善
   - 资源清理不及时

4. **可维护性**
   - 模块边界不清晰
   - 接口定义不规范
   - 文档不完整

本次重构旨在系统性地解决上述问题，建立清晰、可维护、高性能的代码架构，同时保持训练模块的稳定性不受影响。

## What Changes

### 1. API 层重构（排除 training.py）

- **BREAKING**: 统一所有 API 响应格式
- **BREAKING**: 重构错误处理机制
- 优化 API 路由组织结构
- 统一请求验证和参数处理
- 实现统一的中间件链

### 2. Core 核心模块重构（排除训练相关）

- 重构 `config.py` 配置管理
- 重构 `logging.py` 日志系统
- 重构 `utils.py` 工具函数
- 重构 `state.py` 状态管理
- 优化 `model_cache.py` 模型缓存
- 重构 `streaming.py` 流式处理

### 3. Agent 模块优化

- 整合现有 agent/core 架构
- 优化意图检测器
- 完善操作执行器
- 增强安全机制

### 4. Gateway 模块优化

- 优化 WebSocket 服务器
- 完善消息路由机制
- 增强设备认证
- 优化会话管理

### 5. Memory 模块重构

- 统一记忆服务接口
- 优化三层记忆架构
- 完善记忆持久化
- 增强记忆检索

### 6. RAG 模块重构

- 统一嵌入器接口
- 优化向量存储
- 完善文档解析
- 增强检索能力

### 7. Security 模块重构

- 统一安全中间件
- 完善权限控制
- 增强审计日志
- 优化沙箱隔离

### 8. Skills 模块重构

- 统一技能注册机制
- 优化技能执行器
- 完善技能学习器
- 增强技能沙箱

### 9. Context 模块重构

- 统一上下文管理
- 优化项目扫描
- 完善符号提取
- 增强语义检索

### 10. CUA 模块优化

- 优化桌面操作执行
- 完善安全机制
- 增强错误恢复

### 11. MCP 模块优化

- 优化协议实现
- 完善工具注册
- 增强错误处理

### 12. 前端重构

- 统一组件设计规范
- 优化状态管理
- 完善错误处理
- 增强用户体验

## Impact

- **Affected specs**: comprehensive-platform-upgrade, local-operation-upgrade, ai-dialogue-system
- **Affected code**:
  - `server/api/` - 所有 API（排除 training.py）
  - `server/core/` - 核心模块（排除 training_*.py）
  - `server/agent/` - Agent 模块
  - `server/gateway/` - Gateway 模块
  - `server/memory/` - Memory 模块
  - `server/rag/` - RAG 模块
  - `server/security/` - Security 模块
  - `server/skills/` - Skills 模块
  - `server/context/` - Context 模块
  - `server/cua/` - CUA 模块
  - `server/mcp/` - MCP 模块
  - `client/src/` - 前端代码
- **NOT affected**:
  - `server/api/training.py` - 训练 API
  - `server/core/training_state.py` - 训练状态
  - `server/core/training_queue.py` - 训练队列
  - `server/core/training_context.py` - 训练上下文
  - `server/tests/test_training*.py` - 训练测试

## ADDED Requirements

### Requirement: 统一 API 响应格式

系统 SHALL 提供统一的 API 响应格式：

```python
# 成功响应
{
    "success": true,
    "data": {...},
    "message": "操作成功"
}

# 错误响应
{
    "success": false,
    "error": {
        "code": "ERROR_CODE",
        "message": "错误描述",
        "details": {...}
    }
}
```

#### Scenario: 成功响应格式
- **WHEN** API 调用成功
- **THEN** 返回统一的成功响应格式
- **AND** 包含 success、data、message 字段

#### Scenario: 错误响应格式
- **WHEN** API 调用失败
- **THEN** 返回统一的错误响应格式
- **AND** 包含 success、error 字段
- **AND** error 包含 code、message、details 字段

### Requirement: 统一错误处理机制

系统 SHALL 提供统一的错误处理机制：

- 定义标准错误类型层次结构
- 实现全局异常处理器
- 提供错误码映射
- 支持国际化错误消息

#### Scenario: 异常捕获
- **WHEN** 发生未捕获异常
- **THEN** 全局异常处理器捕获并转换为标准错误响应
- **AND** 记录详细错误日志

#### Scenario: 业务错误
- **WHEN** 发生业务逻辑错误
- **THEN** 抛出对应的业务异常
- **AND** 返回友好的错误消息

### Requirement: 模块化配置管理

系统 SHALL 提供模块化配置管理：

- 统一配置加载机制
- 支持环境变量覆盖
- 支持配置验证
- 支持配置热更新

#### Scenario: 配置加载
- **WHEN** 应用启动
- **THEN** 从配置文件和环境变量加载配置
- **AND** 验证配置有效性

#### Scenario: 配置验证
- **WHEN** 配置值无效
- **THEN** 抛出配置错误
- **AND** 提供详细的错误信息

### Requirement: 结构化日志系统

系统 SHALL 提供结构化日志系统：

- 统一日志格式（JSON/文本）
- 支持日志级别动态调整
- 支持请求追踪 ID
- 支持敏感信息脱敏

#### Scenario: 请求追踪
- **WHEN** 处理请求
- **THEN** 自动生成追踪 ID
- **AND** 所有相关日志包含追踪 ID

#### Scenario: 敏感信息脱敏
- **WHEN** 记录包含敏感信息的日志
- **THEN** 自动脱敏处理
- **AND** 不泄露敏感数据

### Requirement: 统一中间件链

系统 SHALL 提供统一的中间件链：

- 请求日志中间件
- 安全头中间件
- 速率限制中间件
- 认证授权中间件
- 错误处理中间件

#### Scenario: 中间件执行顺序
- **WHEN** 请求进入系统
- **THEN** 按顺序执行中间件链
- **AND** 每个中间件可中断请求或继续

### Requirement: 模块依赖注入

系统 SHALL 支持模块依赖注入：

- 定义清晰的模块接口
- 支持依赖声明
- 支持生命周期管理
- 支持测试替身

#### Scenario: 依赖注入
- **WHEN** 模块需要依赖其他服务
- **THEN** 通过依赖注入获取
- **AND** 不直接实例化依赖

### Requirement: 资源生命周期管理

系统 SHALL 提供资源生命周期管理：

- 统一资源创建接口
- 统一资源销毁接口
- 支持上下文管理器
- 支持异步资源管理

#### Scenario: 资源清理
- **WHEN** 应用关闭
- **THEN** 自动清理所有资源
- **AND** 不泄露资源

### Requirement: 类型安全

系统 SHALL 确保类型安全：

- 所有公共接口添加类型注解
- 使用 Pydantic 模型验证数据
- 使用 mypy 进行静态类型检查
- 禁止使用 Any 类型（除特殊情况）

#### Scenario: 类型检查
- **WHEN** 运行类型检查
- **THEN** 无类型错误
- **AND** 类型覆盖率 > 90%

### Requirement: 测试覆盖

系统 SHALL 确保测试覆盖：

- 单元测试覆盖率 > 80%
- 集成测试覆盖核心流程
- 端到端测试覆盖关键场景
- 性能测试覆盖关键指标

#### Scenario: 测试执行
- **WHEN** 运行测试套件
- **THEN** 所有测试通过
- **AND** 覆盖率达标

### Requirement: API 文档自动生成

系统 SHALL 自动生成 API 文档：

- OpenAPI 规范文档
- 请求/响应示例
- 错误码说明
- 认证说明

#### Scenario: 文档访问
- **WHEN** 访问 /docs 端点
- **THEN** 显示完整的 API 文档
- **AND** 包含所有端点说明

## MODIFIED Requirements

### Requirement: API 路由组织

现有 API 路由 SHALL 重新组织：

- 按功能域分组路由
- 统一路由前缀规范
- 统一版本管理
- 统一标签分类

### Requirement: 状态管理

现有状态管理 SHALL 统一：

- 统一状态存储接口
- 统一状态访问方式
- 支持状态持久化
- 支持状态恢复

### Requirement: 缓存管理

现有缓存管理 SHALL 优化：

- 统一缓存接口
- 支持多种缓存后端
- 支持缓存失效策略
- 支持缓存预热

## REMOVED Requirements

### Requirement: 旧版 API 响应格式

**Reason**: 统一使用新版响应格式
**Migration**: 所有 API 迁移到新格式

### Requirement: 分散的配置文件

**Reason**: 统一到模块化配置管理
**Migration**: 迁移到统一配置系统

### Requirement: 重复的工具函数

**Reason**: 统一到 utils 模块
**Migration**: 删除重复代码，使用统一工具函数

## 重构范围详细说明

### Phase 1: 基础设施重构

**目标**: 建立统一的基础设施

**范围**:
1. 统一配置管理 (`core/config.py`)
2. 统一日志系统 (`core/logging.py`)
3. 统一错误处理 (`core/error_handling.py`)
4. 统一工具函数 (`core/utils.py`)
5. 统一中间件 (`security/middleware.py`)

**排除**:
- `core/training_state.py`
- `core/training_queue.py`
- `core/training_context.py`

### Phase 2: API 层重构

**目标**: 统一 API 设计规范

**范围**:
1. 统一响应格式 (`api/response.py`)
2. 统一错误处理 (`api/errors.py`)
3. 统一请求验证 (`api/validators.py`)
4. 重构所有 API 端点（排除 training.py）

**排除**:
- `api/training.py`

### Phase 3: 核心模块重构

**目标**: 优化核心模块架构

**范围**:
1. 状态管理 (`core/state.py`)
2. 模型缓存 (`core/model_cache.py`)
3. 流式处理 (`core/streaming.py`)
4. 内存监控 (`core/memory_monitor.py`)
5. 性能监控 (`core/performance.py`)

**排除**:
- 所有 training_*.py 文件

### Phase 4: Agent 模块优化

**目标**: 完善 Agent 架构

**范围**:
1. 核心架构 (`agent/core/`)
2. 意图检测 (`agent/intent/`)
3. 操作执行 (`agent/operations/`)
4. 安全机制 (`agent/security/`)

### Phase 5: Gateway 模块优化

**目标**: 增强 Gateway 能力

**范围**:
1. WebSocket 服务器 (`gateway/server.py`)
2. 消息路由 (`gateway/router.py`)
3. 设备认证 (`gateway/device_auth.py`)
4. 会话管理 (`gateway/session.py`)

### Phase 6: Memory 模块重构

**目标**: 完善记忆系统

**范围**:
1. 记忆服务 (`memory/memory_service.py`)
2. 操作记忆 (`memory/operation_memory.py`)
3. 短期记忆 (`memory/short_term_memory.py`)
4. 偏好学习 (`memory/preference_learner.py`)

### Phase 7: RAG 模块重构

**目标**: 优化 RAG 系统

**范围**:
1. 嵌入器 (`rag/embedder.py`)
2. 向量存储 (`rag/vector_store.py`)
3. 文档解析 (`rag/document_parser.py`)
4. 检索器 (`rag/hybrid_retriever.py`)

### Phase 8: Security 模块重构

**目标**: 增强安全能力

**范围**:
1. 安全中间件 (`security/middleware.py`)
2. 权限控制 (`security/auth_middleware.py`)
3. 审计日志 (`security/audit_log.py`)
4. 沙箱隔离 (`security/sandbox.py`)

### Phase 9: Skills 模块重构

**目标**: 完善技能系统

**范围**:
1. 技能注册 (`skills/registry.py`)
2. 技能执行 (`skills/executor.py`)
3. 技能学习 (`skills/learner.py`)
4. 技能沙箱 (`skills/sandbox.py`)

### Phase 10: Context 模块重构

**目标**: 优化上下文系统

**范围**:
1. 上下文管理 (`context/manager.py`)
2. 项目扫描 (`context/project_scanner.py`)
3. 符号提取 (`context/symbol_extractor.py`)
4. 语义检索 (`context/context_retriever.py`)

### Phase 11: CUA 模块优化

**目标**: 完善桌面操作

**范围**:
1. 操作执行 (`cua/player.py`)
2. 安全机制 (`cua/safety.py`)
3. 错误恢复 (`cua/exceptions.py`)

### Phase 12: MCP 模块优化

**目标**: 完善 MCP 协议

**范围**:
1. 协议实现 (`mcp/protocol.py`)
2. 工具注册 (`mcp/tool_registry.py`)
3. 客户端 (`mcp/client.py`)

### Phase 13: 前端重构

**目标**: 优化前端架构

**范围**:
1. 组件设计规范 (`client/src/components/`)
2. 状态管理 (`client/src/store/`)
3. API 客户端 (`client/src/services/`)
4. 错误处理 (`client/src/utils/errorHandler.ts`)

## 风险评估

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|----------|
| 重构影响训练模块 | 低 | 高 | 明确排除训练模块，建立隔离边界 |
| API 兼容性破坏 | 高 | 高 | 版本化 API，提供迁移指南 |
| 性能回归 | 中 | 中 | 建立性能基准测试，持续监控 |
| 测试覆盖不足 | 中 | 中 | 优先编写测试，确保覆盖率 |
| 依赖冲突 | 中 | 中 | 锁定依赖版本，隔离环境 |

## 验收标准

### 必须达成

- [ ] 所有 API 使用统一响应格式
- [ ] 所有异常被正确处理
- [ ] 测试覆盖率 > 80%
- [ ] 类型检查无错误
- [ ] 训练模块功能不受影响
- [ ] 所有现有功能正常工作

### 应该达成

- [ ] API 响应时间 < 200ms（P95）
- [ ] 内存使用优化 20%
- [ ] 代码重复率 < 5%
- [ ] 文档覆盖率 100%

### 可以达成

- [ ] 性能提升 30%
- [ ] 启动时间优化 50%
- [ ] 包体积优化 20%
