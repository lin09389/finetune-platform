import type { TaskMode, SelectedWorkspace } from '../runtime/agentRuntime';
import styles from './AgentTaskContextBar.module.css';

const MODE_OPTIONS: Array<{ value: TaskMode; label: string }> = [
  { value: 'build', label: 'Build' },
  { value: 'train', label: 'Train' },
  { value: 'hybrid', label: 'Hybrid' },
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
  const workspaceLabel = workspace?.label || '未确认工作区';

  return (
    <section className={styles.contextBar} aria-label="任务上下文">
      <div className={styles.workspaceControl}>
        <span className={styles.caption}>工作区</span>
        <button
          type="button"
          className={workspace ? styles.workspaceButton : styles.workspaceButtonWarning}
          onClick={onWorkspaceChange}
          aria-label={`选择工作区：${workspaceLabel}`}
          title={workspace?.projectPath || '选择并确认一个可用工作区'}
        >
          <span className={styles.workspaceDot} aria-hidden="true" />
          <span>{workspaceLabel}</span>
          <span className={styles.workspaceAction}>更换</span>
        </button>
      </div>
      <label className={styles.modeControl}>
        <span className={styles.caption}>任务模式</span>
        <select aria-label="任务模式" value={mode} onChange={(event) => onModeChange(event.target.value as TaskMode)}>
          {MODE_OPTIONS.map((option) => (
            <option key={option.value} value={option.value}>{option.label}</option>
          ))}
        </select>
      </label>
    </section>
  );
}
