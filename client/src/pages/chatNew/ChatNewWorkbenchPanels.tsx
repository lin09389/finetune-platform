import { Tag } from 'antd';

import { WorkbenchEmpty } from '../../components/chat/AgentWorkbenchPanel';
import type { AgentPart, AgentSessionDiagnosticItem } from '../../services/api';
import styles from '../ChatNew.module.css';

const getStatusColor = (status: string) => {
  if (status === 'completed') return 'success';
  if (status === 'failed') return 'error';
  if (status.includes('waiting')) return 'warning';
  return 'processing';
};

interface ChatNewWorkbenchRunPanelProps {
  activeAgentId?: string;
  fallbackAgentId?: string;
  status: string;
  statusMessage?: string;
  parts: AgentPart[];
}

export const ChatNewWorkbenchRunPanel = ({
  activeAgentId,
  fallbackAgentId,
  status,
  statusMessage,
  parts,
}: ChatNewWorkbenchRunPanelProps) => (
  <div style={{ display: 'grid', gap: 12 }}>
    <div className={styles.projectSidePanel}>
      <div className={styles.projectSideHeader}>
        <div>
          <div className={styles.projectSideKicker}>Current Run</div>
          <div className={styles.projectSideTitle}>{activeAgentId || fallbackAgentId || 'build'}</div>
        </div>
        <Tag color={getStatusColor(status)}>
          {status}
        </Tag>
      </div>
      <div className={styles.projectSideStatus}>
        <span>{statusMessage || '等待新的 Agent 任务。'}</span>
      </div>
    </div>
    {parts.length > 0 ? (
      <div className={styles.projectSidePanel}>
        <div className={styles.projectSideTitle}>最近动作</div>
        <div style={{ display: 'grid', gap: 8 }}>
          {parts.slice(-4).reverse().map((part) => (
            <div key={part.id} className={styles.agentFileCardBody} style={{ padding: 0 }}>
              <div className={styles.agentFileCardTop}>
                <span className={styles.agentFilePath} style={{ paddingLeft: 0 }}>{part.title || part.type}</span>
                <Tag className={styles.agentFileStatus}>{part.status || 'pending'}</Tag>
              </div>
              {part.content ? <div className={styles.agentFileSummary} style={{ paddingLeft: 0 }}>{part.content}</div> : null}
            </div>
          ))}
        </div>
      </div>
    ) : (
      <WorkbenchEmpty description="Agent 启动后，这里会显示最近动作与当前阻塞。" />
    )}
  </div>
);

interface ChatNewWorkbenchProgressPanelProps {
  parts: AgentPart[];
  recentEvents?: AgentSessionDiagnosticItem[];
}

export const ChatNewWorkbenchProgressPanel = ({
  parts,
  recentEvents = [],
}: ChatNewWorkbenchProgressPanelProps) => {
  if (parts.length > 0) {
    return (
      <div style={{ display: 'grid', gap: 10 }}>
        {parts.slice(-8).map((part) => (
          <div key={part.id} className={styles.projectSidePanel}>
            <div className={styles.projectSideHeader}>
              <div className={styles.projectSideTitle}>{part.title || part.type}</div>
              <Tag>{part.status || 'pending'}</Tag>
            </div>
            {part.content ? <div className={styles.agentFileSummary} style={{ paddingLeft: 0 }}>{part.content}</div> : null}
          </div>
        ))}
      </div>
    );
  }

  if (recentEvents.length > 0) {
    return (
      <div style={{ display: 'grid', gap: 10 }}>
        {recentEvents.slice(-8).map((event) => (
          <div key={event.id} className={styles.projectSidePanel}>
            <div className={styles.projectSideHeader}>
              <div className={styles.projectSideTitle}>{event.event_type || 'event'}</div>
              <Tag>{event.created_at || 'recent'}</Tag>
            </div>
            {event.message ? <div className={styles.agentFileSummary} style={{ paddingLeft: 0 }}>{event.message}</div> : null}
          </div>
        ))}
      </div>
    );
  }

  return <WorkbenchEmpty description="执行开始后，这里会展示阶段、节点和工具调用。" />;
};
