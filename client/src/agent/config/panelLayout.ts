export type AgentWorkspacePanelTab = 'files' | 'diff';
export type AgentTaskCenterTab = 'plan' | 'subagents' | 'artifacts' | 'environment';

export interface AgentPanelLayout {
  workspaceOpen: boolean;
  taskCenterOpen: boolean;
  terminalOpen: boolean;
  workspaceTab: AgentWorkspacePanelTab;
  taskCenterTab: AgentTaskCenterTab;
  sessionWidth: number;
  dockWidth: number;
  terminalHeight: number;
  workspaceSplit: number;
}

const STORAGE_KEY = 'finetune.agent.panel-layout.v1';
export const MIN_SESSION_WIDTH = 200;
export const MAX_SESSION_WIDTH = 360;
export const MIN_DOCK_WIDTH = 360;
export const MAX_DOCK_WIDTH = 720;
export const MIN_TERMINAL_HEIGHT = 160;
export const MAX_TERMINAL_HEIGHT = 420;
export const MIN_WORKSPACE_SPLIT = 30;
export const MAX_WORKSPACE_SPLIT = 70;

export const DEFAULT_AGENT_PANEL_LAYOUT: AgentPanelLayout = {
  workspaceOpen: true,
  taskCenterOpen: true,
  terminalOpen: true,
  workspaceTab: 'files',
  taskCenterTab: 'plan',
  sessionWidth: 232,
  dockWidth: 520,
  terminalHeight: 220,
  workspaceSplit: 58,
};

function clamp(value: unknown, minimum: number, maximum: number, fallback: number): number {
  return typeof value === 'number' && Number.isFinite(value)
    ? Math.min(maximum, Math.max(minimum, Math.round(value)))
    : fallback;
}

export function readAgentPanelLayout(storage: Pick<Storage, 'getItem'> = localStorage): AgentPanelLayout {
  try {
    const value = JSON.parse(storage.getItem(STORAGE_KEY) || '{}') as Partial<AgentPanelLayout>;
    return {
      workspaceOpen: typeof value.workspaceOpen === 'boolean'
        ? value.workspaceOpen
        : DEFAULT_AGENT_PANEL_LAYOUT.workspaceOpen,
      taskCenterOpen: typeof value.taskCenterOpen === 'boolean'
        ? value.taskCenterOpen
        : DEFAULT_AGENT_PANEL_LAYOUT.taskCenterOpen,
      terminalOpen: typeof value.terminalOpen === 'boolean'
        ? value.terminalOpen
        : DEFAULT_AGENT_PANEL_LAYOUT.terminalOpen,
      workspaceTab: value.workspaceTab === 'diff' ? 'diff' : 'files',
      taskCenterTab: ['plan', 'subagents', 'artifacts', 'environment'].includes(String(value.taskCenterTab))
        ? value.taskCenterTab as AgentTaskCenterTab
        : DEFAULT_AGENT_PANEL_LAYOUT.taskCenterTab,
      sessionWidth: clamp(
        value.sessionWidth,
        MIN_SESSION_WIDTH,
        MAX_SESSION_WIDTH,
        DEFAULT_AGENT_PANEL_LAYOUT.sessionWidth,
      ),
      dockWidth: clamp(
        value.dockWidth,
        MIN_DOCK_WIDTH,
        MAX_DOCK_WIDTH,
        DEFAULT_AGENT_PANEL_LAYOUT.dockWidth,
      ),
      terminalHeight: clamp(
        value.terminalHeight,
        MIN_TERMINAL_HEIGHT,
        MAX_TERMINAL_HEIGHT,
        DEFAULT_AGENT_PANEL_LAYOUT.terminalHeight,
      ),
      workspaceSplit: clamp(
        value.workspaceSplit,
        MIN_WORKSPACE_SPLIT,
        MAX_WORKSPACE_SPLIT,
        DEFAULT_AGENT_PANEL_LAYOUT.workspaceSplit,
      ),
    };
  } catch {
    return DEFAULT_AGENT_PANEL_LAYOUT;
  }
}

export function persistAgentPanelLayout(
  layout: AgentPanelLayout,
  storage: Pick<Storage, 'setItem'> = localStorage,
): void {
  try {
    storage.setItem(STORAGE_KEY, JSON.stringify(layout));
  } catch {
    // Panel controls should remain usable when storage is blocked or full.
  }
}
