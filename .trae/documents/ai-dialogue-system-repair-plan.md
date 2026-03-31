# AI 对话系统深度检查修复计划

## 1. 摘要 (Summary)
本项目旨在修复对 AI 对话页面深度检查中发现的所有 P0 和 P1 级缺陷。重点在于完善意图检测的指标评估与热更新、增强执行引擎的审计与可靠性，以及规范网关层的分流、安全与错误码。通过本次修复，系统将满足准确率 ≥95%、API 超时 ≤800ms、日志保留 30 天等核心性能与合规指标。

## 2. 当前状态分析 (Current State Analysis)
根据深度检查报告，系统目前存在以下核心问题：
- **意图检测**：缺乏真实的准确率/召回率评估；无多轮对话漂移检测；正则规则无法在线更新。
- **执行引擎**：审计日志仅存于内存且周期极短；缺乏全局追踪标识 `traceId`；超时控制过于宽松；无断路器机制。
- **网关治理**：无灰度分流与金丝雀路由；安全策略（WAF/黑名单）缺失；错误码格式不规范，不含追踪标识。

## 3. 拟议变更 (Proposed Changes)

### 3.1 意图检测模块 (Intent Module)
- **指标评估系统实现**：
    - 修改 [metrics.py](file:///c:/Users/JHJ\Desktop/finetune-platform/server/agent/intent/handlers/metrics.py)，引入基于 Ground Truth 的评估逻辑，计算 Accuracy, Recall, F1-score。
- **意图漂移检测**：
    - 在 [context.py](file:///c:/Users/JHJ\Desktop/finetune-platform/server/agent/intent/core/context.py) 中增加 `drift_detector`，计算当前意图与历史意图序列的余弦相似度。
- **规则热更新机制**：
    - 在 [patterns.py](file:///c:/Users/JHJ\Desktop/finetune-platform/server/agent/intent/core/patterns.py) 中引入文件监听器（或定时检查文件 MD5），实现 `RULE_PATTERNS` 的在线重载。
- **低置信度降级策略**：
    - 在 [detector.py](file:///c:/Users/JHJ\Desktop/finetune-platform/server/agent/intent/detector.py) 中，当置信度 < 0.6 时，触发多模型投票或转由高级 LLM (如 GPT-4) 进行二次确认。

### 3.2 执行引擎模块 (Execution Module)
- **持久化审计日志**：
    - 在 [db_manager.py](file:///c:/Users/JHJ\Desktop/finetune-platform/server/core/db_manager.py) 中创建 `audit_logs` 表，包含 `traceId`, `userId`, `intent`, `action`, `latency`, `status` 等字段。
    - 修改 [executor.py](file:///c:/Users/JHJ\Desktop/finetune-platform/server/agent/core/engine/executor.py)，将执行记录写入数据库而非仅存内存。
- **全链路追踪标识 (Tracing)**：
    - 修改 [main.py](file:///c:/Users/JHJ\Desktop/finetune-platform/server/main.py) 的中间件，在请求头中生成 `X-Trace-Id` 并透传至 Context 对象。
- **断路器与超时优化**：
    - 在 [executor.py](file:///c:/Users/JHJ\Desktop/finetune-platform/server/agent/core/engine/executor.py) 中集成 `pycircuitbreaker` 或手动实现基于错误率的断路逻辑。
    - 调整默认超时至 800ms，针对耗时操作使用异步回调机制。

### 3.3 网关模块 (Gateway Module)
- **灰度路由规则**：
    - 修改 [gateway.py](file:///c:/Users/JHJ\Desktop/finetune-platform/server/ai/gateway.py)，根据 Header 中的 `X-App-Version` 动态匹配后端服务版本标签。
- **安全加固**：
    - 在 [main.py](file:///c:/Users/JHJ\Desktop/finetune-platform/server/main.py) 引入 WAF 中间件（正则过滤恶意载荷）与 IP 黑名单检查逻辑。
- **规范错误响应**：
    - 修改 [errors.py](file:///c:/Users/JHJ\Desktop/finetune-platform/server/api/errors.py) 的 `APIError.to_dict` 方法，强制要求返回 `traceId`。

## 4. 假设与决策 (Assumptions & Decisions)
- **日志存储**：由于目前已有 [db_manager.py](file:///c:/Users/JHJ\Desktop/finetune-platform/server/core/db_manager.py) 支持 SQLite/PostgreSQL，审计日志将优先存储在主数据库中。
- **热更新**：为减少外部依赖，将采用定时扫描 `patterns.py` 文件 MD5 的方式实现规则热更新，避免引入复杂的 Watchdog 进程。
- **追踪标识**：`traceId` 将使用 UUIDv4 生成，并通过 `contextvars` 在协程间安全传递。

## 5. 验证步骤 (Verification Steps)
- **自动化测试**：
    - 编写 `test_metrics_calculation` 验证准确率统计。
    - 编写 `test_circuit_breaker_trip` 验证在连续 5 次失败后服务自动熔断。
- **手动检查**：
    - 检查数据库中 `audit_logs` 表是否正常记录超过 30 条的测试数据。
    - 验证 API 响应头中是否包含 `X-Trace-Id`。
- **CI 流水线验证**：
    - 运行 `pytest` 确保所有单元测试通过。
    - 运行 `security_scan` 确保 WAF 规则有效拦截恶意 SQL 注入等请求。
