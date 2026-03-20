# 模块测试验证计划

## 测试范围

本次测试覆盖以下新开发模块：

### Gateway 模块
- `server/gateway/binding.py` - Binding Router
- `server/gateway/agent_isolation.py` - Agent 隔离管理
- `server/gateway/device_auth.py` - 设备认证管理
- `server/gateway/cross_agent.py` - 跨 Agent 通信
- `server/gateway/server.py` - WebSocket 服务器
- `server/gateway/router.py` - 消息路由器
- `server/gateway/session.py` - 会话管理

### Heartbeat 模块
- `server/heartbeat/__init__.py` - Heartbeat 调度器
- `server/heartbeat/task_executor.py` - 主动任务执行器

### Core 模块
- `server/core/quantization.py` - 量化模型支持
- `server/core/batching.py` - 动态批处理
- `server/core/kv_cache.py` - KV Cache 优化
- `server/core/user_experience.py` - 用户体验优化
- `server/core/error_handling.py` - 错误处理

### Security 模块
- `server/security/sandbox.py` - 沙箱隔离
- `server/security/prompt_security.py` - Prompt 安全
- `server/security/audit_log.py` - 审计日志

### Memory 模块
- `server/memory/operation_memory.py` - 操作记忆管理
- `server/memory/preference_learner.py` - 用户偏好学习

### Skills 模块
- `server/skills/memory_aware_skill.py` - 记忆感知技能基类
- `server/skills/skill_learner.py` - 技能学习与优化

## 测试类型

### 1. 单元测试
- 核心功能测试
- 边界条件测试
- 异常处理测试

### 2. 集成测试
- 模块间交互测试
- API 端到端测试

### 3. 性能测试
- 响应时间测试
- 并发处理测试
- 内存使用测试

## 测试用例

### Gateway 模块测试用例

#### BindingManager 测试
| 用例ID | 测试项 | 输入 | 预期输出 | 优先级 |
|--------|--------|------|----------|--------|
| GM-001 | Agent 注册 | AgentInfo 对象 | 成功注册 | P0 |
| GM-002 | Agent 注销 | agent_id | 成功注销 | P0 |
| GM-003 | 添加绑定规则 | BindingRule | 成功添加 | P0 |
| GM-004 | 移除绑定规则 | rule_id | 成功移除 | P0 |
| GM-005 | 精确匹配查找 | peer_id, guild_id | 返回正确 Agent | P0 |
| GM-006 | 最具体匹配优先 | 多个匹配规则 | 返回最高分匹配 | P0 |
| GM-007 | 无匹配查找 | 不存在的 ID | 返回默认 Agent | P1 |
| GM-008 | 空绑定列表 | 空 | 返回空列表 | P1 |

#### AgentIsolationManager 测试
| 用例ID | 测试项 | 输入 | 预期输出 | 优先级 |
|--------|--------|------|----------|--------|
| AI-001 | 创建 Agent 环境 | agent_id, name | 成功创建 | P0 |
| AI-002 | 删除 Agent 环境 | agent_id | 成功删除 | P0 |
| AI-003 | 获取工作空间 | agent_id | 返回路径 | P0 |
| AI-004 | Session 数据操作 | key, value | 正确存取 | P0 |
| AI-005 | 权限检查 | capability | 正确判断 | P0 |
| AI-006 | 路径访问检查 | path | 正确判断 | P1 |

#### DeviceAuthManager 测试
| 用例ID | 测试项 | 输入 | 预期输出 | 优先级 |
|--------|--------|------|----------|--------|
| DA-001 | 设备注册 | device_type, name | 返回凭证 | P0 |
| DA-002 | 设备注销 | device_id | 成功注销 | P0 |
| DA-003 | Token 认证 | device_id, token | 认证成功 | P0 |
| DA-004 | 无效 Token | device_id, wrong_token | 认证失败 | P0 |
| DA-005 | 创建挑战 | device_id | 返回挑战 | P0 |
| DA-006 | 权限检查 | action | 正确判断 | P0 |

#### CrossAgentCommunicator 测试
| 用例ID | 测试项 | 输入 | 预期输出 | 优先级 |
|--------|--------|------|----------|--------|
| CA-001 | Agent 注册 | agent_id | 成功注册 | P0 |
| CA-002 | 发送消息 | source, target, payload | 消息送达 | P0 |
| CA-003 | 广播消息 | source, payload | 多 Agent 收到 | P0 |
| CA-004 | 接收消息 | agent_id | 正确接收 | P0 |
| CA-005 | 结果合并 | results, strategy | 正确合并 | P1 |
| CA-006 | 不存在目标 | nonexistent target | 返回 None | P1 |

### Heartbeat 模块测试用例

#### HeartbeatScheduler 测试
| 用例ID | 测试项 | 输入 | 预期输出 | 优先级 |
|--------|--------|------|----------|--------|
| HB-001 | 添加任务 | HeartbeatTask | 成功添加 | P0 |
| HB-002 | 移除任务 | task_id | 成功移除 | P0 |
| HB-003 | 启动调度器 | 无 | 开始运行 | P0 |
| HB-004 | 停止调度器 | 无 | 停止运行 | P0 |
| HB-005 | 解析 HEARTBEAT.md | 文件内容 | 任务列表 | P1 |
| HB-006 | 获取到期任务 | 无 | 正确列表 | P1 |

#### TaskExecutor 测试
| 用例ID | 测试项 | 输入 | 预期输出 | 优先级 |
|--------|--------|------|----------|--------|
| TE-001 | 执行检查任务 | check task | 完成状态 | P0 |
| TE-002 | 执行汇报任务 | report task | 生成报告 | P0 |
| TE-003 | 执行提醒任务 | reminder task | 发送提醒 | P0 |
| TE-004 | 禁用任务执行 | disabled task | 取消状态 | P1 |
| TE-005 | 不存在任务 | nonexistent | 失败状态 | P1 |
| TE-006 | 清理旧结果 | days | 清理完成 | P2 |

### Security 模块测试用例

#### SandboxManager 测试
| 用例ID | 测试项 | 输入 | 预期输出 | 优先级 |
|--------|--------|------|----------|--------|
| SB-001 | 创建沙箱 | config | 沙箱实例 | P0 |
| SB-002 | 执行安全命令 | command | 执行结果 | P0 |
| SB-003 | 阻止危险命令 | dangerous cmd | 拒绝执行 | P0 |
| SB-004 | 资源限制检查 | resource | 正确限制 | P1 |
| SB-005 | 权限检查 | capability | 正确判断 | P0 |

#### PromptInjectionDetector 测试
| 用例ID | 测试项 | 输入 | 预期输出 | 优先级 |
|--------|--------|------|----------|--------|
| PI-001 | 检测注入攻击 | malicious prompt | 检测到攻击 | P0 |
| PI-002 | 正常提示词 | normal prompt | 无攻击 | P0 |
| PI-003 | 边界情况 | edge case | 正确处理 | P1 |

#### AuditLogger 测试
| 用例ID | 测试项 | 输入 | 预期输出 | 优先级 |
|--------|--------|------|----------|--------|
| AL-001 | 记录操作日志 | event | 成功记录 | P0 |
| AL-002 | 查询日志 | query | 日志列表 | P0 |
| AL-003 | 生成报告 | time range | 审计报告 | P1 |

### Core 模块测试用例

#### QuantizationDetector 测试
| 用例ID | 测试项 | 输入 | 预期输出 | 优先级 |
|--------|--------|------|----------|--------|
| QT-001 | 检测 GPTQ 模型 | model_path | GPTQ 类型 | P0 |
| QT-002 | 检测 AWQ 模型 | model_path | AWQ 类型 | P0 |
| QT-003 | 检测 GGUF 模型 | model_path | GGUF 类型 | P0 |
| QT-004 | 检测普通模型 | model_path | NONE 类型 | P0 |

#### DynamicBatcher 测试
| 用例ID | 测试项 | 输入 | 预期输出 | 优先级 |
|--------|--------|------|----------|--------|
| DB-001 | 添加请求 | request | 加入队列 | P0 |
| DB-002 | 批处理执行 | batch | 执行结果 | P0 |
| DB-003 | 超时处理 | timeout | 返回结果 | P1 |

#### ErrorHandling 测试
| 用例ID | 测试项 | 输入 | 预期输出 | 优先级 |
|--------|--------|------|----------|--------|
| EH-001 | 创建错误响应 | error_code | 正确响应 | P0 |
| EH-002 | 获取错误建议 | error_type | 建议列表 | P0 |
| EH-003 | 异常处理 | exception | 友好响应 | P0 |

## 测试执行计划

### 阶段 1: 单元测试
1. 运行现有单元测试
2. 分析测试覆盖率
3. 补充缺失的测试用例

### 阶段 2: 集成测试
1. 运行 API 集成测试
2. 测试模块间交互
3. 验证端到端流程

### 阶段 3: 性能测试
1. 响应时间测试
2. 并发处理测试
3. 内存使用监控

## 验收标准

1. 所有单元测试通过率 ≥ 95%
2. 集成测试通过率 100%
3. 无 P0 级别缺陷
4. P1 级别缺陷 ≤ 5 个
5. 测试覆盖率 ≥ 80%
