import { BellOutlined, MenuOutlined } from '@ant-design/icons';
import { Badge, Button, Drawer } from 'antd';
import type { CSSProperties, ReactNode } from 'react';
import { useEffect, useState } from 'react';
import type { AgentConnectionState } from '../protocol/agentProtocol';
import styles from './AgentWorkbench.module.css';

interface AgentWorkbenchShellProps {
  title: string;
  subtitle: string;
  connection: AgentConnectionState;
  connectionLabel: string;
  attentionCount: number;
  attentionOpenRequest?: number;
  sessionWidth?: number;
  onMobileSessionNavigate?: () => void;
  desktopSessionRail: ReactNode;
  mobileSessionRail: ReactNode;
  desktopEnvironmentRail?: ReactNode;
  mobileAttentionRail: ReactNode;
  toolbar: ReactNode;
  children: ReactNode;
}

export default function AgentWorkbenchShell({
  title,
  subtitle,
  connection,
  connectionLabel,
  attentionCount,
  attentionOpenRequest = 0,
  sessionWidth = 232,
  onMobileSessionNavigate,
  desktopSessionRail,
  mobileSessionRail,
  mobileAttentionRail,
  toolbar,
  children,
}: AgentWorkbenchShellProps) {
  const [sessionsOpen, setSessionsOpen] = useState(false);
  const [attentionOpen, setAttentionOpen] = useState(false);

  useEffect(() => {
    if (attentionOpenRequest > 0) setAttentionOpen(true);
  }, [attentionOpenRequest]);

  return (
    <div
      className={styles.workbench}
      style={{ '--agent-session-width': `${sessionWidth}px` } as CSSProperties}
    >
      <header className={styles.topbar}>
        <div className={styles.brand}>
          <span className={styles.brandMark}>A</span>
          <span>Agent 工作台</span>
        </div>
        <div className={styles.projectName}>
          <strong>{title}</strong>
          <span>{subtitle}</span>
        </div>
        <div className={styles.topbarActions}>
          <span className={`${styles.connection} ${styles[`connection_${connection}`] || ''}`}>
            <span aria-hidden="true" />
            {connectionLabel}
          </span>
          <Button
            className={styles.mobileShellAction}
            type="text"
            icon={<MenuOutlined />}
            aria-label="打开会话"
            onClick={() => setSessionsOpen(true)}
          />
          <Badge count={attentionCount} size="small" overflowCount={9}>
            <Button
              className={styles.mobileShellAction}
              type="text"
              icon={<BellOutlined />}
              aria-label="打开注意事项"
              onClick={() => setAttentionOpen(true)}
            />
          </Badge>
          {toolbar}
        </div>
      </header>

      {desktopSessionRail}
      {children}

      <Drawer
        title="Agent 会话"
        placement="left"
        width="min(88vw, 340px)"
        open={sessionsOpen}
        onClose={() => setSessionsOpen(false)}
        styles={{ body: { padding: 0 } }}
      >
        <div
          onClick={(event) => {
            const target = event.target;
            if (target instanceof Element && target.closest('[data-agent-session-navigate="true"]')) {
              setSessionsOpen(false);
              onMobileSessionNavigate?.();
            }
          }}
        >
          {mobileSessionRail}
        </div>
      </Drawer>
      <Drawer
        title="注意事项"
        placement="right"
        width="min(92vw, 380px)"
        open={attentionOpen}
        onClose={() => setAttentionOpen(false)}
        styles={{ body: { padding: 0 } }}
      >
        {mobileAttentionRail}
      </Drawer>
    </div>
  );
}
