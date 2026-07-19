# DeepAgents 0.6.10 工具执行边界审计

日期：2026-07-19
范围：Milestone 2 / Task 5
结论：仅建立兼容目录与启动门禁事实，不改变当前运行行为。

## 1. 执行所有权

平台不运行第二套工具循环。`DeepAgentsRuntimeFactory.build` 将
`AgentRuntimeContract` 交给 `create_deep_agent`；之后
`DeepAgentsSessionRunner` 通过 `graph.astream_events` 驱动执行，并负责事件映射、
轨迹收尾和 HITL resume 包装。

平台当前可控制的接缝是：显式 `tools`、额外 `middleware`、`permissions`、
`interrupt_on`、`backend`、`subagents`、`skills` 和 checkpointer。DeepAgents
内置中间件生成的工具不会因为从 `tools=` 中删除而消失。

## 2. 工具来源

| 来源 | 工具 | 当前注入方式 |
|---|---|---|
| `FilesystemMiddleware` | `ls/read_file/write_file/edit_file/glob/grep/execute` | DeepAgents 内置注入 |
| `TodoListMiddleware` | `write_todos` | DeepAgents 内置注入 |
| `SubAgentMiddleware` | `task` | 存在 inline subagent 时注入 |
| `AgentRuntimeContract.tools` | 平台异步任务与训练工具 | 显式传入 `create_deep_agent` |

DeepAgents 文档明确规定 `tools=` 仅做加法。内置工具只能通过 harness profile 的
`excluded_tools`，或平台当前使用的后置 `_ToolExclusionMiddleware` 从模型请求中隐藏。

## 3. 副作用前边界

```text
模型工具表过滤
  → HITL interrupt（配置时）
  → 平台 TrajectoryGuard（Build 启用时）
  → FilesystemPermission（仅文件工具）
  → Backend
  → 副作用
```

- 文件工具同时具备模型可见性过滤和工具层文件权限；写工具还经过 Build 轨迹门控。
- `execute` 由 `FilesystemMiddleware` 生成，但最终调用 `LocalShellBackend.execute`。
- `task` 由 `SubAgentMiddleware` 执行；当前只有模型可见性过滤，没有平台执行层硬拒绝。
- `write_todos` 由基础中间件注入，当前不在平台 `DEEPAGENTS_BUILTIN_TOOLS` 排除集合中。

## 4. 关键安全缺口：execute

DeepAgents 0.6.10 的 `LocalShellBackend` 明确说明：

- `virtual_mode=True` 不构成 shell 安全边界；
- 命令经 `subprocess.run(..., shell=True)` 以宿主用户权限运行；
- 命令可以访问工作区之外路径、联网、启动进程或修改系统状态。

平台的 `PlatformShellBackend` 负责路径改写、超时和输出限制，但没有命令内容策略或
执行层 deny。默认 `safe_auto` 又不会为 `execute` 安装 HITL。因此当前只能将
`execute` 从模型工具表隐藏，不能证明它在执行层被强制禁止。

## 5. Enforcement capability

适配器将能力固定为三档：

- `hidden_and_enforced`：既能从模型请求隐藏，也存在副作用前硬边界；
- `visible_but_enforced`：无法隐藏，但存在副作用前硬边界；
- `unsupported`：无法证明执行层强制。

当前结果：

| 工具 | 结果 | 原因 |
|---|---|---|
| `ls/read_file/glob/grep` | `hidden_and_enforced` | 排除中间件 + 文件权限 |
| `write_file/edit_file` | `hidden_and_enforced` | 排除 + HITL/轨迹 + 文件权限 |
| `execute` | `unsupported` | 只有隐藏；宿主 shell 无硬 deny |
| `task` | `unsupported` | 只有隐藏；无平台执行层 deny |
| `write_todos` | `unsupported` | 当前未进入平台排除集合 |

`require_controlled_mode_support()` 会对未知或 `unsupported` 工具 fail-closed。
本阶段不会把该函数接入生产启动，因此不会改变 legacy Build 行为。

## 6. 审计可见性

当前安全审计日志主要记录 HTTP 审批结果。默认 `safe_auto` 下，未触发 HITL 的
文件操作与 `execute` 没有统一进入安全审计日志。Agent Session 轨迹和事件能够提供
产品级证据，但不能等同于安全审计事实源。

Task 7 的 Tool Gateway 应把 canonical started/completed/failed 事件投影到现有
Agent Session 事件，并增加安全审计适配；不能建立第二套会话事件日志。

## 7. 后续门禁

1. Task 6 可以实现纯 `allow/ask/deny` 决策，但不得声称已经强制执行。
2. Task 7 Gateway 先覆盖平台自定义工具；内置工具仍受 DeepAgents 接缝限制。
3. `execute` 在进入 controlled Build 前必须具备可验证的执行环境或后端 deny。
4. `task` 必须迁移到平台拥有的确定性 work-unit 编排后再解除 blocker。
5. `write_todos` 应被平台 Goal Plan 替代，或显式纳入可靠排除与执行策略。

因此 Milestone 2 可以继续开发，但 controlled Build 切换必须保持关闭。
