# Workbench 前端能力对齐契约

日期：2026-07-12
范围：Phase 7.5 Wave 1 Track A（只读盘点与回归契约）

## 结论

`/agent` 是 Coding 主日常线和 Training 专业线共享的唯一 Workbench。Build、Train、Hybrid 不是三个产品；它们由同一个任务上下文条创建，并由同一 workspace snapshot、SSE 增量和刷新流程恢复。本文件没有声称任何生产 UI 已完成视觉改造：它冻结当前可证实的入口、动作、反馈和恢复来源，并把未验证项明确保留为 Wave 1、Wave 2 或 deferred。

`/api/info` 只控制应用级能力分层：`/agent` 映射为 GA `chat_sessions`；实验路由由 `experimental_enabled` 守卫。它不能把实验功能提升为 Workbench 默认模式，也不是任务运行时能力的替代来源。证据：`client/src/capability/tiers.ts`、`client/src/capability/ExperimentalRouteGuard.tsx`。

## Wave 分层

| 波次 | 范围 | 不在本轨道中做的事 |
| --- | --- | --- |
| Wave 1 | Workspace、Build/Train/Hybrid、审批/权限、终端、Diff、计划、子 Agent、训练活动与恢复的 Workbench 可发现性、状态和窄屏优先级。 | 不新建功能、不改后端、不将专业线拆成新首页。 |
| Wave 2 | 应用壳的命名与导航分层，包括 `/api/info` 实验能力 guard 的一致呈现。 | 不将实验路由作为 Workbench 任务模式或默认推荐。 |
| Deferred | 诊断卡的主题对比、200% zoom、读屏播报和移动焦点循环的人工验收。 | 不以静态 fixture 或截图伪造这些通过。 |

## 能力矩阵

| 能力 | 当前发现 / 动作 | 当前反馈 | 刷新或恢复来源 | 响应式与测试 owner | 波次 / 证据 |
| --- | --- | --- | --- | --- | --- |
| Workspace | `AgentTaskContextBar`；选择/更换，未确认时阻止提交。 | 当前路径或“未确认工作区”与阻止原因。 | settings 的 `projectPath/workspaceId` 初始化后重新验证。 | 同一上下文条；`WorkbenchCapabilityParity.test.tsx`。 | Wave 1；`AgentWorkbenchPage.tsx#resolveSelectedWorkspace`。 |
| Build / Train / Hybrid | 同一模式 select；创建前选择，不拆独立首页。 | 会话创建后 composer 保留不可变模式；Train/Hybrid 另有活动卡。 | workbench settings 与 `sessionPersistence` 的 `taskMode`。 | 同一原生 select；同一测试 owner。 | Wave 1；`AgentTaskContextBar.tsx#MODE_OPTIONS`。 |
| 审批 | Attention rail 和时间线待介入状态；一次性决定。 | pending/busy 与最近处理历史。 | workspace snapshot 的 pending actions，SSE 重连后刷新。 | 窄屏同一 surface；焦点陷阱待人工验收。 | Wave 1；`AgentAttentionRail.tsx`。 |
| 权限 | 主活动条汇总；打开 Attention 后允许/拒绝。 | 计数、busy、`waiting_permission` 状态。 | `workspace.pending_permission` 重投影。 | 移动端“继续任务”与触控目标待 Wave 1 验收。 | Wave 1；`AgentWorkbenchPage.tsx#pendingPermissionPartId`。 |
| 终端 | 顶部终端操作和 next-action 路由；打开/关闭/resize。 | 输出、可见性和 resize handle。 | persisted panel layout；`terminalMounted` 保留挂载终端。 | 窄屏独立抽屉；44px 仍待人工验收。 | Wave 1；`AgentTerminalDock.tsx`。 |
| Diff | 工作区 Diff tab 或 next action；审阅 `file_change`。 | 变更内容或明确空状态。 | `workspace.artifacts` snapshot。 | 窄屏工作区抽屉；紧凑空状态在 Track C 验收。 | Wave 1；`AgentWorkspaceView.tsx#diff`。 |
| 计划 | 任务中心“计划”；查看节点、依赖、时长和可恢复节点。 | 节点状态/恢复次数/计划总状态。 | `execution_plan` snapshot + 后端 recovery command。 | 窄屏任务中心抽屉。 | Wave 1；`AgentWorkspaceView.tsx#plan`。 |
| 子 Agent | Team 操作、任务中心 tab、next action；启动/取消/查看。 | 运行、等待、失败、取消、完成与 attention 计数。 | `workspace.async_tasks.tasks` snapshot。 | 窄屏仍可打开，modal 焦点循环待人工验收。 | Wave 1；`SubagentModal.tsx`、`AgentWorkspaceView.tsx#subagents`。 |
| 训练活动 | 主时间线；查看 Train/Hybrid 进度。 | 进度 `aria-valuenow`/`aria-valuetext` 和 polite 状态。 | workspace/timeline snapshot 的会话恢复投影。 | 保持主列，不复制到移动侧栏。 | Wave 1；`AgentTrainingActivity.tsx`。 |
| 恢复 | Attention action 与计划“恢复”；恢复节点或路由下一步。 | busy、恢复次数和“已恢复实时同步”。 | recovery command、SSE reconnect、session refresh。 | 移动端使用同一入口，不能只靠颜色。 | Wave 1；`AgentAttentionRail.tsx`、`AgentWorkbenchPage.tsx#recoveredAt`。 |
| 诊断 | Attention 的运行诊断卡；仅查看。 | unknown/parse/reconnect/recovery 指标和最近事件。 | 版本化 browser storage。 | 对比度、zoom、读屏未自动证明。 | Deferred；`agentDiagnostics.ts`。 |
| 能力分层 | 导航 tier badge；实验路由由 `/api/info` guard。 | 关闭时 403 guard，GA `/agent` 不受影响。 | 每次连接读取 `/api/info.experimental_enabled`；离线乐观默认。 | 归应用壳，不是 Workbench mode。 | Wave 2；`tiers.ts`、`ExperimentalRouteGuard.tsx`。 |

## 已锁定的回归规则

`client/src/agent/testing/workbenchCapabilityParity.ts` 是此表的 typed fixture，`client/src/test/WorkbenchCapabilityParity.test.tsx` 断言：

- 14 个范围内能力均有唯一的 UI owner，避免新增重复入口。
- 每一项都有面向用户或状态恢复的来源与代码证据。
- 实验能力分层不是默认 Workbench 工作流，且不会被当成 Build/Train/Hybrid 模式。

该测试不替代视觉验收。截图审计已证实的 P0/P1 是主任务焦点、窄屏辅助抽屉、状态层级和未确认 Workspace 的下一步提示；Track B/C 必须在相同视口上解决并再截图。诊断的主题/zoom/读屏、抽屉焦点约束和 reduced-motion 不因本文件通过而视为已验收。
