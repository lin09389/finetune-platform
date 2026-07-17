import type { TaskMode } from './runtime/agentRuntime';

export const BUILD_AGENT_TASK_MODE: TaskMode = 'build';

export function isMigratingAgentTaskMode(mode: TaskMode | undefined | null): boolean {
  return mode === 'train' || mode === 'hybrid';
}

export function availableAgentTaskMode(mode: TaskMode | undefined | null): TaskMode {
  return isMigratingAgentTaskMode(mode) ? BUILD_AGENT_TASK_MODE : (mode || BUILD_AGENT_TASK_MODE);
}
