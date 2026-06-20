import { PlusOutlined } from '@ant-design/icons';
import { Button } from 'antd';
import type { RecentAgentSession } from '../runtime/agentRuntime';
import styles from '../workbench/AgentWorkbench.module.css';

const STATUS_LABELS: Record<string, string> = {
  idle: '待命',
  running: '运行中',
  waiting_permission: '等待审批',
  waiting_approval: '等待审批',
  verifying: '验证中',
  repairing: '修复中',
  completed: '已完成',
  failed: '失败',
  interrupted: '已停止',
  needs_manual_review: '需复核',
};

interface AgentSessionRailProps {
  sessions: RecentAgentSession[];
  activeSessionId: string | null;
  onNew: () => void;
  onSelect: (sessionId: string) => void;
  embedded?: boolean;
}

export default function AgentSessionRail({
  sessions,
  activeSessionId,
  onNew,
  onSelect,
  embedded = false,
}: AgentSessionRailProps) {
  return (
    <aside
      className={`${styles.sessionRail} ${embedded ? styles.embeddedRail : ''}`}
      aria-label="Agent 会话"
    >
      <Button className={styles.newTask} icon={<PlusOutlined />} aria-label="新建任务" onClick={onNew}>
        新建任务
      </Button>
      <div className={styles.railSection}>
        <span className={styles.railLabel}>最近运行</span>
        {sessions.length === 0 ? (
          <div className={styles.railEmpty}>暂无运行</div>
        ) : (
          <div className={styles.sessionList}>
            {sessions.map((session) => (
              <button
                key={session.id}
                type="button"
                className={session.id === activeSessionId ? styles.sessionItemActive : styles.sessionItem}
                onClick={() => onSelect(session.id)}
              >
                <span className={styles.sessionTitle}>{session.title}</span>
                <span className={styles.sessionMeta}>
                  <span className={`${styles.statusDot} ${styles[`status_${session.status}`] || ''}`} />
                  {STATUS_LABELS[session.status] || session.status}
                </span>
              </button>
            ))}
          </div>
        )}
      </div>
    </aside>
  );
}
