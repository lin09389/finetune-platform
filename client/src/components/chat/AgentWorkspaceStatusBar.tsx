import { ApartmentOutlined, ThunderboltOutlined } from '@ant-design/icons';
import { Button, Tag, Typography } from 'antd';
import type { AgentAsyncTaskMetrics } from '../../services/api';
import styles from './AgentWorkspaceStatusBar.module.css';

const sessionStatusLabel: Record<string, string> = {
  idle: '空闲',
  running: '运行中',
  waiting_permission: '等待确认',
  waiting_approval: '等待确认',
  verifying: '验证中',
  repairing: '修复中',
  needs_manual_review: '需要人工处理',
  interrupted: '已中断',
  completed: '完成',
  failed: '失败',
};

const sessionStatusColor: Record<string, string> = {
  idle: 'default',
  running: 'processing',
  waiting_permission: 'warning',
  waiting_approval: 'warning',
  verifying: 'processing',
  repairing: 'warning',
  needs_manual_review: 'warning',
  interrupted: 'default',
  completed: 'success',
  failed: 'error',
};

interface AgentWorkspaceStatusBarProps {
  agentName?: string;
  sessionStatus?: string;
  asyncMetrics?: AgentAsyncTaskMetrics | null;
  onOpenAsyncTasks: () => void;
}

export default function AgentWorkspaceStatusBar({
  agentName,
  sessionStatus = 'idle',
  asyncMetrics,
  onOpenAsyncTasks,
}: AgentWorkspaceStatusBarProps) {
  const total = asyncMetrics?.total ?? 0;
  const running = asyncMetrics?.running ?? 0;
  const attention = asyncMetrics?.attention ?? 0;
  const needsAttention = attention > 0 || ['waiting_permission', 'waiting_approval', 'needs_manual_review', 'failed'].includes(sessionStatus);

  return (
    <section className={styles.statusBar} aria-label="Agent 运行状态">
      <div className={styles.identity}>
        <span className={styles.identityIcon}><ApartmentOutlined /></span>
        <div className={styles.copy}>
          <Typography.Text className={styles.kicker}>Agent Run</Typography.Text>
          <Typography.Text strong className={styles.title}>
            {agentName || '当前 Agent'}
          </Typography.Text>
        </div>
      </div>

      <div className={styles.metrics} aria-label="异步子任务状态">
        <Tag color={sessionStatusColor[sessionStatus] || 'default'}>
          {sessionStatusLabel[sessionStatus] || sessionStatus}
        </Tag>
        <span><strong>{running}</strong> 活跃</span>
        <span data-tone={attention > 0 ? 'warning' : undefined}><strong>{attention}</strong> 待处理</span>
        {total > 0 ? <span><strong>{total}</strong> 子任务</span> : null}
        {needsAttention ? <Tag color="warning">需要处理</Tag> : null}
      </div>

      <Button size="small" icon={<ThunderboltOutlined />} onClick={onOpenAsyncTasks}>
        打开子任务
      </Button>
    </section>
  );
}
