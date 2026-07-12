/**
 * Phase 7.5 experience contract for the existing `/agent` Workbench.
 *
 * This is intentionally a static fixture, not a second routing or feature-flag
 * implementation.  Its evidence points to the production owner that already
 * renders the capability and to the state source that survives a refresh.
 */

export type Phase75Delivery = 'wave1' | 'wave2' | 'deferred';
export type WorkbenchAvailability = 'ga' | 'experimental';

export interface WorkbenchCapabilityParityEntry {
  id: string;
  label: string;
  availability: WorkbenchAvailability;
  defaultWorkflow: boolean;
  delivery: Phase75Delivery;
  uiOwner: string;
  discover: string;
  action: string;
  feedback: string;
  recovery: {
    source: string;
    evidence: string;
  };
  responsive: string;
  testOwner: string;
  evidence: string[];
}

export const WORKBENCH_CAPABILITY_PARITY: readonly WorkbenchCapabilityParityEntry[] = [
  {
    id: 'workspace',
    label: 'Workspace',
    availability: 'ga',
    defaultWorkflow: true,
    delivery: 'wave1',
    uiOwner: 'AgentTaskContextBar#workspace-control',
    discover: '任务输入区的“工作区”上下文条；桌面环境栏也显示已解析的路径。',
    action: '选择或更换工作区；未确认工作区时阻止创建任务。',
    feedback: '显示当前工作区或“未确认工作区”，并给出创建任务前的阻止原因。',
    recovery: {
      source: '已保存的 workbench settings projectPath/workspaceId 会在页面初始化时重新验证。',
      evidence: 'agent/workbench/AgentWorkbenchPage.tsx#resolveSelectedWorkspace + agent/config/workbenchSettings.ts',
    },
    responsive: '窄屏从同一上下文条进入设置，不另建 Workspace 首页。',
    testOwner: 'src/test/WorkbenchCapabilityParity.test.tsx',
    evidence: [
      'agent/components/AgentTaskContextBar.tsx',
      'agent/workbench/AgentWorkbenchPage.tsx#taskContextBlockedReason',
      'agent/config/workbenchSettings.ts',
    ],
  },
  {
    id: 'build-mode',
    label: 'Build mode',
    availability: 'ga',
    defaultWorkflow: true,
    delivery: 'wave1',
    uiOwner: 'AgentTaskContextBar#build-mode-select',
    discover: '任务上下文条的任务模式选择器。',
    action: '在创建任务前选择 Build。',
    feedback: 'composer 在会话创建后以只读模式标签保留当前模式。',
    recovery: {
      source: 'workbench settings 和 session persistence 保存 taskMode。',
      evidence: 'agent/config/workbenchSettings.ts + agent/runtime/sessionPersistence.ts',
    },
    responsive: '桌面和窄屏共用原生 select 与相同标签。',
    testOwner: 'src/test/WorkbenchCapabilityParity.test.tsx',
    evidence: ['agent/components/AgentTaskContextBar.tsx#MODE_OPTIONS', 'agent/components/AgentTaskComposer.tsx'],
  },
  {
    id: 'train-mode',
    label: 'Train mode',
    availability: 'ga',
    defaultWorkflow: true,
    delivery: 'wave1',
    uiOwner: 'AgentTaskContextBar#train-mode-option',
    discover: '任务上下文条的任务模式选择器。',
    action: '在创建任务前选择 Train。',
    feedback: '会话运行状态和训练活动卡从同一 workspace snapshot 渲染。',
    recovery: {
      source: 'workbench settings 和 session persistence 保存 taskMode。',
      evidence: 'agent/config/workbenchSettings.ts + agent/runtime/sessionPersistence.ts',
    },
    responsive: 'Train 不是独立移动入口，仍在主任务输入区。',
    testOwner: 'src/test/WorkbenchCapabilityParity.test.tsx',
    evidence: ['agent/components/AgentTaskContextBar.tsx#MODE_OPTIONS', 'agent/components/AgentTrainingActivity.tsx'],
  },
  {
    id: 'hybrid-mode',
    label: 'Hybrid mode',
    availability: 'ga',
    defaultWorkflow: true,
    delivery: 'wave1',
    uiOwner: 'AgentTaskContextBar#hybrid-mode-option',
    discover: '任务上下文条的任务模式选择器。',
    action: '在创建任务前选择 Hybrid。',
    feedback: 'composer 显示不可变的当前模式，避免在同一会话内静默切换。',
    recovery: {
      source: 'workbench settings 和 session persistence 保存 taskMode。',
      evidence: 'agent/config/workbenchSettings.ts + agent/runtime/sessionPersistence.ts',
    },
    responsive: '与 Build/Train 使用相同的窄屏输入骨架。',
    testOwner: 'src/test/WorkbenchCapabilityParity.test.tsx',
    evidence: ['agent/components/AgentTaskContextBar.tsx#MODE_OPTIONS', 'agent/components/AgentTaskComposer.tsx'],
  },
  {
    id: 'approval',
    label: 'Approvals',
    availability: 'ga',
    defaultWorkflow: true,
    delivery: 'wave1',
    uiOwner: 'AgentAttentionRail#approval-actions',
    discover: 'Attention rail 与任务时间线中的待介入状态。',
    action: '对等待审批的操作作出一次性决定。',
    feedback: 'pending/busy 状态和最近处理历史在 Attention rail 可见。',
    recovery: {
      source: '权威 workspace snapshot 的 pending permission/action 状态；SSE 重连后刷新。',
      evidence: 'agent/components/AgentAttentionRail.tsx + agent/runtime/useAgentWorkbench.ts',
    },
    responsive: '窄屏以同一 Attention surface 打开；完整焦点陷阱仍需 Wave 1 人工验收。',
    testOwner: 'src/test/WorkbenchCapabilityParity.test.tsx',
    evidence: ['agent/components/AgentAttentionRail.tsx#onDecidePermission', 'agent/workbench/AgentWorkbenchPage.tsx#decidePermission'],
  },
  {
    id: 'permission',
    label: 'Permissions',
    availability: 'ga',
    defaultWorkflow: true,
    delivery: 'wave1',
    uiOwner: 'AgentActivityBar#pending-permission-summary',
    discover: '主任务区的活动条将待权限请求提升为当前状态。',
    action: '打开 Attention rail 并提交允许或拒绝决定。',
    feedback: '活动条计数、操作 busy 状态和会话 waiting_permission 状态同时反馈。',
    recovery: {
      source: 'workspace.pending_permission 是刷新后重新投影的服务器状态。',
      evidence: 'agent/workbench/AgentWorkbenchPage.tsx#pendingPermissionPartId',
    },
    responsive: '移动端必须保持“继续当前任务”可达；视觉/触控验收归 Wave 1。',
    testOwner: 'src/test/WorkbenchCapabilityParity.test.tsx',
    evidence: ['agent/components/AgentActivityBar.tsx', 'agent/workbench/AgentWorkbenchPage.tsx'],
  },
  {
    id: 'terminal',
    label: 'Terminal',
    availability: 'ga',
    defaultWorkflow: true,
    delivery: 'wave1',
    uiOwner: 'AgentTerminalDock#terminal-panel',
    discover: 'Workbench 顶部“终端”操作和运行下一步路由。',
    action: '打开、关闭和调整终端面板。',
    feedback: '终端输出、可见状态和 resize handle 保持挂载状态。',
    recovery: {
      source: 'panel layout 保存 terminalOpen/terminalHeight，terminalMounted 避免关闭时丢失已挂载终端。',
      evidence: 'agent/workbench/AgentWorkbenchPage.tsx#terminalMounted + agent/config/panelLayout.ts',
    },
    responsive: '窄屏作为独立抽屉打开；44px 触控目标仍由 Wave 1 视觉验收覆盖。',
    testOwner: 'src/test/WorkbenchCapabilityParity.test.tsx',
    evidence: ['agent/components/AgentTerminalDock.tsx', 'agent/workbench/AgentWorkbenchPage.tsx#toggleTerminal'],
  },
  {
    id: 'diff',
    label: 'Diff',
    availability: 'ga',
    defaultWorkflow: true,
    delivery: 'wave1',
    uiOwner: 'AgentWorkspaceView#diff-tab',
    discover: '右侧工作区的 Diff tab，以及下一步动作的 open_tab 路由。',
    action: '切换到 Diff 并审阅 file_change artifacts。',
    feedback: '每个文件变更显示 diff 内容；无结果显示明确空状态。',
    recovery: {
      source: 'workspace.artifacts 从权威 workspace snapshot 重新加载。',
      evidence: 'agent/components/AgentWorkspaceView.tsx#tab-diff',
    },
    responsive: '窄屏在工作区抽屉中显示；密集空状态的视觉收敛归 Wave 1。',
    testOwner: 'src/test/WorkbenchCapabilityParity.test.tsx',
    evidence: ['agent/components/AgentWorkspaceView.tsx#diff', 'agent/workbench/AgentWorkbenchPage.tsx#openWorkspaceTab'],
  },
  {
    id: 'plan',
    label: 'Execution plan',
    availability: 'ga',
    defaultWorkflow: true,
    delivery: 'wave1',
    uiOwner: 'AgentWorkspaceView#plan-tab',
    discover: '任务中心的“计划”tab。',
    action: '查看节点、依赖、时长和可恢复节点。',
    feedback: '节点状态、恢复次数和计划总体状态直接来自 workspace snapshot。',
    recovery: {
      source: 'execution_plan nodes 与后端 recovery command 一起在刷新后恢复。',
      evidence: 'agent/components/AgentWorkspaceView.tsx#tab-plan + agent/runtime/useAgentWorkbench.ts',
    },
    responsive: '窄屏从任务中心抽屉进入，保持同一阅读顺序。',
    testOwner: 'src/test/WorkbenchCapabilityParity.test.tsx',
    evidence: ['agent/components/AgentWorkspaceView.tsx#plan', 'agent/workbench/AgentWorkbenchPage.tsx#TASK_CENTER_TABS'],
  },
  {
    id: 'subagents',
    label: 'Subagents',
    availability: 'ga',
    defaultWorkflow: true,
    delivery: 'wave1',
    uiOwner: 'SubagentModal#start-subagent-dialog',
    discover: '顶栏 Team 操作、任务中心“子 Agent”tab 和下一步路由。',
    action: '启动、查看或取消子 Agent。',
    feedback: '任务中心显示 running/waiting/failed/cancelled/completed 状态及 attention 计数。',
    recovery: {
      source: 'workspace.async_tasks.tasks 是刷新后重建的服务器状态。',
      evidence: 'agent/components/AgentWorkspaceView.tsx#tab-subagents',
    },
    responsive: '创建对话框与任务中心在窄屏仍可访问；焦点循环需 Wave 1 人工验收。',
    testOwner: 'src/test/WorkbenchCapabilityParity.test.tsx',
    evidence: ['agent/components/SubagentModal.tsx', 'agent/components/AgentWorkspaceView.tsx#subagents'],
  },
  {
    id: 'training-activity',
    label: 'Training activity',
    availability: 'ga',
    defaultWorkflow: true,
    delivery: 'wave1',
    uiOwner: 'AgentTrainingActivity#training-progress-card',
    discover: '任务时间线中的训练活动记录。',
    action: '在 Train/Hybrid 任务中查看当前训练进度与状态。',
    feedback: '进度条使用 aria-valuenow/aria-valuetext，并对状态使用 polite live region。',
    recovery: {
      source: '训练活动作为 workspace/timeline snapshot 的投影，在会话恢复时重放。',
      evidence: 'agent/components/AgentTrainingActivity.tsx + agent/runtime/useAgentWorkbench.ts',
    },
    responsive: '与主时间线同列，未单独复制到移动侧栏。',
    testOwner: 'src/test/WorkbenchCapabilityParity.test.tsx',
    evidence: ['agent/components/AgentTrainingActivity.tsx', 'agent/components/AgentRunTimeline.tsx'],
  },
  {
    id: 'recovery',
    label: 'Failure recovery',
    availability: 'ga',
    defaultWorkflow: true,
    delivery: 'wave1',
    uiOwner: 'AgentAttentionRail#recovery-action',
    discover: 'Attention rail 的恢复行动和执行计划中的“恢复”按钮。',
    action: '恢复可恢复计划节点，或按任务下一步重新打开正确 surface。',
    feedback: '恢复操作 busy 状态、恢复次数和“已恢复实时同步”提示可见。',
    recovery: {
      source: '恢复命令、SSE reconnect 和 session refresh 共同恢复执行状态。',
      evidence: 'agent/components/AgentAttentionRail.tsx#recover + agent/workbench/AgentWorkbenchPage.tsx#recoveredAt',
    },
    responsive: '移动端仍需用同一 attention/plan 入口完成恢复；不可仅依赖颜色。',
    testOwner: 'src/test/WorkbenchCapabilityParity.test.tsx',
    evidence: ['agent/components/AgentAttentionRail.tsx', 'agent/components/AgentWorkspaceView.tsx#recoverable'],
  },
  {
    id: 'diagnostics',
    label: 'Diagnostics',
    availability: 'ga',
    defaultWorkflow: false,
    delivery: 'deferred',
    uiOwner: 'AgentAttentionRail#runtime-diagnostics',
    discover: 'Attention rail 的“Agent 运行诊断”卡。',
    action: '查看未知事件、解析失败、重连和恢复率；不从此处创建任务。',
    feedback: '显示最近诊断事件和 warning 状态。',
    recovery: {
      source: '版本化 browser storage 保存受限的每会话诊断快照。',
      evidence: 'agent/diagnostics/agentDiagnostics.ts#STORAGE_KEY',
    },
    responsive: '现有 surface 可用，但主题对比、200% zoom 与读屏播报未由本 fixture 证明，故延后视觉验收。',
    testOwner: 'src/test/WorkbenchCapabilityParity.test.tsx',
    evidence: ['agent/components/AgentAttentionRail.tsx#diagnosticsCard', 'agent/diagnostics/agentDiagnostics.ts'],
  },
  {
    id: 'capability-tier-gating',
    label: 'Capability-tier gating',
    availability: 'experimental',
    defaultWorkflow: false,
    delivery: 'wave2',
    uiOwner: 'ExperimentalRouteGuard#api-info-route-guard',
    discover: '应用导航中的 tier badge；不是 Workbench composer 的模式或推荐入口。',
    action: 'Guard experimental routes only; do not advertise them as Workbench task modes.',
    feedback: '后端关闭实验能力时显示明确的 403 guard，GA Workbench 不受影响。',
    recovery: {
      source: '每次连接后读取 /api/info.experimental_enabled；离线时保留乐观默认。',
      evidence: 'capability/ExperimentalRouteGuard.tsx + capability/tiers.ts#isExperimentalEnabled',
    },
    responsive: '应用壳导航的一致性属于 Wave 2，不改变 Workbench 主任务入口。',
    testOwner: 'src/test/WorkbenchCapabilityParity.test.tsx',
    evidence: ['capability/tiers.ts#ROUTE_CAPABILITY', 'capability/ExperimentalRouteGuard.tsx'],
  },
];
