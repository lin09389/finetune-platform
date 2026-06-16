# OpenCode Agent 整合统一基线（finetune-platform）

> 历史说明：本文是旧 OpenCode 整合基线。当前 Agent 定义系统已经升级为 Agent Manifest v2 YAML，早期 Markdown Agent 定义路径不再作为实现基线。运行时事实源见 `server/agent_session/agent_registry.py` 和 `server/agent_session/agents/*.agent.yaml`。

## 1. 文档目的

本文件是以下三份文档的统一执行版本：

- `docs/agent_system_design.md`
- `docs/opencode_integration_plan.md`
- `docs/opencode_execution_flow.md`

目标是把三份文档收口为一套可直接落地的实现标准，避免目录、术语、工具命名不一致导致的返工。

---

## 2. 统一结论

1. 不推倒现有系统，基于现有 `server/agent_runtime`、`server/chat_agent`、`/workflows` 增量增强。
2. 聊天页 ` /chat ` 保持主入口，`/workflows` 保持观测与审批入口。
3. OpenCode 借鉴重点是三件事：
- 声明式 Agent 定义（Agent Manifest v2 YAML）
- 细粒度权限（allow/deny/ask）
- 工具执行前权限评估 + 可审计事件

---

## 3. 统一术语与命名

### 3.1 目录统一

统一落在 `server/agent_runtime/`，不新增 `server/agent/` 平行体系。

### 3.2 工具命名映射（必须统一）

OpenCode 语义 → 本项目统一工具名：

- `glob` → `list_files`
- `grep` / `codesearch` → `search_code`
- `read` → `read_file`
- `edit` / `write`（直接执行）→ `propose_patch`（审批后执行）
- `bash`（直接执行）→ `propose_command`（审批后执行）
- `webfetch` / `websearch` → 暂不纳入第 1 批（后续扩展）

原则：本项目当前安全边界不允许 Agent 直接写文件/执行命令，只允许 proposal。

### 3.3 Agent 模式

- `primary`: 用户可直接选
- `subagent`: 仅被其他 Agent 调用
- `all`: 两者皆可

第 1 版只要求数据结构与查询能力，不强制实现复杂子 Agent 调度。

---

## 4. 与现有代码的衔接点

当前已存在并继续复用：

- `server/agent_runtime/engine.py`
- `server/agent_runtime/runner.py`
- `server/agent_runtime/tools.py`
- `server/agent_runtime/tool_loop.py`
- `server/agent_runtime/actions.py`
- `server/agent_runtime/repository.py`
- `server/chat_agent/service.py`
- `server/api/workflows.py`
- `server/api/chat_agent.py`

新增能力必须通过上述模块扩展，不做并行重写。

---

## 5. 统一实施路线（按优先级）

## Phase A：权限引擎接入（最高优先级）

目标：让工具调用从“能跑”升级为“可控可审计”。

实施文件：

- 新增 `server/agent_runtime/permission.py`
- 新增 `server/agent_runtime/agent_schema.py`（先放权限规则模型）
- 修改 `server/agent_runtime/tools.py`（执行前权限检查）
- 修改 `server/agent_runtime/tool_loop.py`（记录权限拒绝/请求事件）
- 修改 `server/agent_runtime/repository.py`（必要时增加 permission 事件写入 helper）

行为标准：

1. `allow`：直接执行工具
2. `deny`：返回失败，不执行工具
3. `ask`：写入审批动作（`permission_request`），等待用户处理

验收：

- 单测覆盖 allow/deny/ask
- `deny` 不产生副作用
- `ask` 在 timeline 可见

## Phase B：声明式 Agent 定义

目标：把“硬编码角色”升级为可配置 Agent。

实施文件：

- 使用 `server/agent_session/agent_registry.py`
- 使用 `server/agent_session/execution_context.py` 的 `AgentManifestV2`
- 使用目录 `server/agent_session/agents/`
- 新增示例 `developer.agent.yaml`、`reviewer.agent.yaml`、`planner.agent.yaml`
- 运行时通过 `server/agent_session/runtime_contract.py` 和 `runtime_policy.py` 消费编译后的 AgentDefinition

行为标准：

1. 只允许从 Agent Manifest v2 YAML 加载内置 Agent
2. 支持用户目录热加载可放到后续，但至少支持手动 reload
3. 缺失 agent 时回退到现有模板定义，不中断流程

## Phase C：API 与前端管理面收口

目标：让配置能力可见可用。

实施文件：

- 新增 `server/api/agent.py`
- 修改 `server/main.py`（注册新 router）
- 修改 `client/src/services/api.ts`（新增 Agent API 方法）
- 新增 `client/src/pages/AgentManager.tsx`
- 修改 `client/src/components/Sidebar.tsx`（入口）
- 修改 `client/src/pages/ChatNew.tsx`（primary agent 选择）

行为标准：

1. 可查看 agent 列表/详情
2. 可 reload agent 定义
3. 聊天发起 workflow 时可选择 primary agent

---

## 6. 执行流对齐要求（来自 OpenCode 分析）

本项目对齐的是“执行机制思想”，不是逐文件复刻：

1. Session/Run 生命周期必须有清晰状态机
2. Tool call 必须是事件驱动、可追踪、可回放
3. 权限是工具调用前置门禁，不是后置补救
4. 事件流必须能回到聊天页与 workflow 观测台

最低可观测事件集：

- `tool_call_started`
- `tool_call_completed`
- `tool_call_failed`
- `permission_asked`
- `permission_approved`
- `permission_denied`

---

## 7. 风险与边界

1. 不引入任意 shell 执行；命令仍走白名单。
2. 不允许 workspace 外读写。
3. 不做自动 git commit/push。
4. 第 1 版不做复杂 subagent 编排树，仅保留模式字段与基础调用入口。

---

## 8. 测试基线

后端新增：

- `server/tests/test_agent_permission.py`
- `server/tests/test_agent_loader.py`
- `server/tests/test_agent_manager.py`

后端回归必须保持通过：

- `server/tests/test_agent_tool_runtime.py`
- `server/tests/test_agent_repair_loop.py`
- `server/tests/test_chat_agent.py`
- `server/tests/test_workflow_observability_actions.py`
- `server/tests/test_workflows.py`
- `server/tests/test_workflow_templates.py`
- `server/tests/test_workflow_context_memory.py`

前端基线：

- `cd client && npm run typecheck`

---

## 9. 实施顺序建议（实际执行）

1. 先做 Phase A（权限引擎）并补测试。
2. 再做 Phase B（Markdown Agent 定义）并接入 runner/engine。
3. 最后做 Phase C（API + UI），避免前端先行导致联调空转。

---

## 10. 三份原文档的保留定位

- `agent_system_design.md`：保留为架构参考（概念和示例）
- `opencode_execution_flow.md`：保留为机制对照手册（事件链路）
- `opencode_integration_plan.md`：保留为历史计划记录

执行时以本文件为准。
