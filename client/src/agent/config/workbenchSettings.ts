import type { AgentSessionCreate } from '../../services/api';

export interface AgentWorkbenchSettings {
  projectPath: string;
  autonomyMode: NonNullable<AgentSessionCreate['autonomy_mode']>;
}

const STORAGE_KEY = 'finetune.agent-workbench.settings.v1';

export const DEFAULT_WORKBENCH_SETTINGS: AgentWorkbenchSettings = {
  projectPath: '',
  autonomyMode: 'safe_auto',
};

export function readAgentWorkbenchSettings(
  storage: Pick<Storage, 'getItem'> | null = typeof localStorage === 'undefined' ? null : localStorage,
): AgentWorkbenchSettings {
  if (!storage) return DEFAULT_WORKBENCH_SETTINGS;
  try {
    const parsed = JSON.parse(storage.getItem(STORAGE_KEY) || '{}') as Partial<AgentWorkbenchSettings>;
    const autonomyMode = ['safe_auto', 'confirm_all', 'read_only'].includes(String(parsed.autonomyMode))
      ? parsed.autonomyMode as AgentWorkbenchSettings['autonomyMode']
      : DEFAULT_WORKBENCH_SETTINGS.autonomyMode;
    return {
      projectPath: typeof parsed.projectPath === 'string' ? parsed.projectPath : '',
      autonomyMode,
    };
  } catch {
    return DEFAULT_WORKBENCH_SETTINGS;
  }
}

export function persistAgentWorkbenchSettings(
  settings: AgentWorkbenchSettings,
  storage: Pick<Storage, 'setItem'> | null = typeof localStorage === 'undefined' ? null : localStorage,
): void {
  try {
    storage?.setItem(STORAGE_KEY, JSON.stringify(settings));
  } catch {
    // Storage can be unavailable in private browsing or constrained webviews.
  }
}
