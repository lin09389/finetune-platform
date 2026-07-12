/**
 * Phase 7.5 Wave 2 cross-page acceptance boundary.
 *
 * This fixture records public outcomes for the application shell and primary
 * pages. It is deliberately not a route registry, a component inventory, or
 * a visual-test substitute: Track D/E may change their internals as long as
 * these outcomes remain true.
 */

export type Phase75CapabilityTier = 'ga' | 'beta' | 'experimental';
export type Phase75WorkbenchLine = 'daily-coding' | 'specialist-training' | 'supporting-entry';
export type Phase75EvidenceLevel = 'semantic-dom' | 'code-contract' | 'manual-visual';

export interface Phase75NavigationScenario {
  id: string;
  path: string;
  label: string;
  tier: Phase75CapabilityTier;
  workbenchLine: Phase75WorkbenchLine;
  sharedWorkbench: boolean;
  expectation: string;
}

export interface Phase75ViewportScenario {
  id: string;
  width: number;
  height: number;
  automated: boolean;
  expectation: string;
}

export interface Phase75InteractionCheck {
  id: string;
  evidence: Phase75EvidenceLevel;
  automated: boolean;
  minimumCssPixels?: number;
  expectation: string;
}

export interface Phase75StateScenario {
  id: string;
  surface: 'agent' | 'training' | 'ga-beta-shell';
  state: 'loading' | 'empty' | 'error-retry' | 'disconnected';
  primaryActionExpectation: string;
  evidence: Phase75EvidenceLevel;
  automated: boolean;
}

export interface Phase75DeferredManualCheck {
  id: string;
  status: 'deferred';
  rationale: string;
  owner: 'main-thread-visual-gate';
}

const navigation = [
  {
    id: 'agent-daily-workbench',
    path: '/agent',
    label: 'Agent 工作台',
    tier: 'ga',
    workbenchLine: 'daily-coding',
    sharedWorkbench: true,
    expectation: 'Coding 是日常主线；进入同一个 Workbench 后从 Build、Train 或 Hybrid 创建任务。',
  },
  {
    id: 'training-specialist-workbench',
    path: '/training',
    label: '模型训练',
    tier: 'ga',
    workbenchLine: 'specialist-training',
    sharedWorkbench: true,
    expectation: 'Training 保留专业页面密度，同时 Train/Hybrid 任务仍在同一个 Agent Workbench 内恢复和跟踪。',
  },
  {
    id: 'workspace-beta-entry',
    path: '/workspace',
    label: '工作空间',
    tier: 'beta',
    workbenchLine: 'supporting-entry',
    sharedWorkbench: false,
    expectation: 'Beta 工作空间是支持性入口，不能取代任务上下文中的工作区确认步骤。',
  },
  {
    id: 'gateway-experimental-entry',
    path: '/gateway',
    label: 'Gateway',
    tier: 'experimental',
    workbenchLine: 'supporting-entry',
    sharedWorkbench: false,
    expectation: '实验入口只在 /api/info 允许时可用，不能成为默认 Agent 任务模式或 GA 主线。',
  },
] as const satisfies readonly Phase75NavigationScenario[];

const viewports = [
  {
    id: 'desktop-1280',
    width: 1280,
    height: 720,
    automated: false,
    expectation: '主标题、主操作与当前任务的继续路径无裁切；辅助区域不得抢占主任务。',
  },
  {
    id: 'mobile-390',
    width: 390,
    height: 844,
    automated: false,
    expectation: '移动抽屉一次只覆盖一个辅助区域，关闭后回到当前主任务与下一步。',
  },
] as const satisfies readonly Phase75ViewportScenario[];

const interactionChecks = [
  {
    id: 'keyboard-reachability',
    evidence: 'code-contract',
    automated: true,
    expectation: '导航、页面标题对应的主内容区域、主要操作和 retry 均须有语义名称并可通过键盘激活。',
  },
  {
    id: 'focus-visible',
    evidence: 'manual-visual',
    automated: false,
    expectation: '键盘焦点环在纸张/编辑器表面上可见，且不被侧栏、抽屉或粘性输入区裁切。',
  },
  {
    id: 'touch-targets',
    evidence: 'manual-visual',
    automated: false,
    minimumCssPixels: 44,
    expectation: '移动端导航、关闭、主要操作与 retry 的实际可点击目标至少为 44×44 CSS px。',
  },
  {
    id: 'reduced-motion',
    evidence: 'code-contract',
    automated: true,
    expectation: '状态转换必须使用既有 motion token，并在 reduced-motion 设置下保留可理解的状态变化。',
  },
] as const satisfies readonly Phase75InteractionCheck[];

const stateMatrix = [
  {
    id: 'agent-loading',
    surface: 'agent',
    state: 'loading',
    primaryActionExpectation: '加载语义说明正在恢复 Workbench；不把辅助面板空状态当作主任务完成。',
    evidence: 'manual-visual',
    automated: false,
  },
  {
    id: 'agent-empty',
    surface: 'agent',
    state: 'empty',
    primaryActionExpectation: '新任务空状态引导确认工作区并输入任务，而非把 Training 拆到另一首页。',
    evidence: 'manual-visual',
    automated: false,
  },
  {
    id: 'agent-error-retry',
    surface: 'agent',
    state: 'error-retry',
    primaryActionExpectation: '失败说明和可访问的重试或恢复操作同时出现，不能只用颜色表达失败。',
    evidence: 'manual-visual',
    automated: false,
  },
  {
    id: 'training-loading',
    surface: 'training',
    state: 'loading',
    primaryActionExpectation: '专业训练页面加载时保留页面标题和明确的加载上下文。',
    evidence: 'manual-visual',
    automated: false,
  },
  {
    id: 'training-empty',
    surface: 'training',
    state: 'empty',
    primaryActionExpectation: '无训练数据时说明下一步专业操作，不以泛化卡片掩盖模型、数据集或资源前置条件。',
    evidence: 'manual-visual',
    automated: false,
  },
  {
    id: 'training-error-retry',
    surface: 'training',
    state: 'error-retry',
    primaryActionExpectation: '训练失败保留诊断上下文，并提供可访问的重试、恢复或下一步操作。',
    evidence: 'manual-visual',
    automated: false,
  },
  {
    id: 'ga-beta-disconnected',
    surface: 'ga-beta-shell',
    state: 'disconnected',
    primaryActionExpectation: '断线状态可读且 GA/Beta 入口仍保持分层；实验入口不得因离线而被误标为 GA。',
    evidence: 'manual-visual',
    automated: false,
  },
] as const satisfies readonly Phase75StateScenario[];

const deferredManualChecks = [
  {
    id: 'contrast-light-dark',
    status: 'deferred',
    rationale: '自动化 DOM 无法计算主题切换后的真实前景/背景对比度；须在浅色和深色主题截图与实机中检查。',
    owner: 'main-thread-visual-gate',
  },
  {
    id: 'zoom-200-percent',
    status: 'deferred',
    rationale: 'JSDOM 不会重排；须在浏览器 200% 缩放下验证标题、主要操作和抽屉关闭控件未裁切。',
    owner: 'main-thread-visual-gate',
  },
  {
    id: 'screen-reader-announcements',
    status: 'deferred',
    rationale: 'aria 属性存在不等于读屏播报顺序正确；须使用真实读屏器验证 loading、error 和训练进度。',
    owner: 'main-thread-visual-gate',
  },
  {
    id: 'drawer-focus-cycle',
    status: 'deferred',
    rationale: '抽屉焦点循环、初始焦点与返回焦点需要真实浏览器交互，不能由静态契约伪造通过。',
    owner: 'main-thread-visual-gate',
  },
  {
    id: 'mobile-touch-measurement',
    status: 'deferred',
    rationale: '样式声明无法证明最终命中区域；须在 390×844 设备仿真或实机测量 44px 目标。',
    owner: 'main-thread-visual-gate',
  },
] as const satisfies readonly Phase75DeferredManualCheck[];

export const PHASE75_CROSS_PAGE_ACCEPTANCE = {
  navigation,
  viewports,
  interactionChecks,
  stateMatrix,
  deferredManualChecks,
} as const;

export function phase75CrossPageScenario(id: string): Phase75NavigationScenario {
  const scenario = PHASE75_CROSS_PAGE_ACCEPTANCE.navigation.find((entry) => entry.id === id);
  if (!scenario) {
    throw new Error(`Unknown Phase 7.5 cross-page scenario: ${id}`);
  }
  return scenario;
}
