import type { TaskMode, SelectedWorkspace } from '../runtime/agentRuntime';
import { BUILD_AGENT_TASK_MODE, isMigratingAgentTaskMode } from '../taskModes';
import styles from './AgentTaskContextBar.module.css';

const MODE_OPTIONS: Array<{ value: TaskMode; label: string; disabled?: boolean }> = [
  { value: 'build', label: 'Build' },
  { value: 'train', label: 'Train（迁移中）', disabled: true },
  { value: 'hybrid', label: 'Hybrid（迁移中）', disabled: true },
];

export interface AgentTaskContextBarProps {
  workspace: SelectedWorkspace | null;
  mode: TaskMode;
  onWorkspaceChange: () => void;
  onModeChange: (mode: TaskMode) => void;
}

/** Context that will be bound once when the next Agent session is created. */
export default function AgentTaskContextBar({
  workspace,
  mode,
  onWorkspaceChange,
  onModeChange,
}: AgentTaskContextBarProps) {
  const workspaceLabel = workspace?.label || '先确认工作区';
  const workspaceAction = workspace ? '更换' : '选择';

  return (
    <section className={styles.contextBar} aria-label="任务上下文">
      <div className={styles.workspaceControl}>
        <span className={styles.caption}>{workspace ? '工作区' : '第 1 步 · 工作区'}</span>
        <button
          type="button"
          className={workspace ? styles.workspaceButton : styles.workspaceButtonWarning}
          onClick={onWorkspaceChange}
          aria-label={workspace ? `选择工作区：${workspaceLabel}` : '第 1 步：选择并确认工作区'}
          title={workspace?.projectPath || '选择并确认一个可用工作区'}
        >
          <span className={styles.workspaceDot} aria-hidden="true" />
          <span>{workspaceLabel}</span>
          <span className={styles.workspaceAction}>{workspaceAction}</span>
        </button>
      </div>
      <label className={styles.modeControl}>
        <span className={styles.caption}>任务模式</span>
        <select
          aria-label="任务模式"
          value={isMigratingAgentTaskMode(mode) ? BUILD_AGENT_TASK_MODE : mode}
          onChange={(event) => {
            const nextMode = event.target.value as TaskMode;
            if (!isMigratingAgentTaskMode(nextMode)) onModeChange(nextMode);
          }}
        >
          {MODE_OPTIONS.map((option) => (
            <option key={option.value} value={option.value} disabled={option.disabled}>{option.label}</option>
          ))}
        </select>
        <p className={styles.migrationNotice} role="status">
          Train 和 Hybrid Agent 正在迁移到 Native Agent Loop；当前仅 Build 可用。普通训练 API 与任务不受影响。
        </p>
      </label>
    </section>
  );
}
