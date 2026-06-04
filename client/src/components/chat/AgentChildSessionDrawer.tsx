import { Drawer, Empty, Spin, Tag, Typography } from 'antd';
import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  decideAgentPermission,
  getAgentSession,
  type AgentHitlDecision,
  type AgentSession,
} from '../../services/api';
import { notify } from '../../utils/notify';
import AgentSessionTimeline from './AgentSessionTimeline';
import HitlApprovalPanel from './HitlApprovalPanel';
import styles from './AgentChildSessionDrawer.module.css';

interface AgentChildSessionDrawerProps {
  open: boolean;
  childSessionId?: string | null;
  onClose: () => void;
  onDecisionSubmitted?: (session: AgentSession) => void | Promise<void>;
}

interface AgentChildSessionDetailProps {
  childSessionId?: string | null;
  onDecisionSubmitted?: (session: AgentSession) => void | Promise<void>;
}

export function AgentChildSessionDetail({
  childSessionId,
  onDecisionSubmitted,
}: AgentChildSessionDetailProps) {
  const [childSession, setChildSession] = useState<AgentSession | null>(null);
  const [loading, setLoading] = useState(false);
  const pendingPermission = useMemo(
    () => childSession?.metadata?.ui_state?.pending_permission || null,
    [childSession?.metadata?.ui_state?.pending_permission],
  );

  const loadChildSession = useCallback(async (sessionId: string) => {
    setChildSession(null);
    setLoading(true);
    try {
      setChildSession(await getAgentSession(sessionId));
    } catch (error) {
      notify.error('子会话加载失败');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!childSessionId) {
      setChildSession(null);
      setLoading(false);
      return;
    }
    void loadChildSession(childSessionId);
  }, [childSessionId, loadChildSession]);

  const handleHitlDecisions = async (permissionId: string, decisions: AgentHitlDecision[]) => {
    try {
      const response = await decideAgentPermission(permissionId, decisions);
      setChildSession(response.session);
      await onDecisionSubmitted?.(response.session);
      notify.success('子代理确认已提交，任务正在继续执行');
    } catch (error) {
      notify.error('子代理确认提交失败');
      throw error;
    }
  };

  return (
    <div className={styles.drawerBody}>
      {loading ? (
        <div className={styles.loadingState}>
          <Spin size="small" />
          <Typography.Text type="secondary">正在加载子会话...</Typography.Text>
        </div>
      ) : childSession ? (
        <>
          <div className={styles.sessionHeader}>
            <div className={styles.sessionHeaderMain}>
              <Typography.Text strong>{childSession.title || childSession.agent_id}</Typography.Text>
              <Typography.Text type="secondary" className={styles.sessionId}>{childSession.id}</Typography.Text>
            </div>
            <Tag color={pendingPermission ? 'warning' : childSession.status === 'completed' ? 'success' : childSession.status === 'failed' ? 'error' : 'processing'}>
              {pendingPermission ? '等待确认' : childSession.status}
            </Tag>
          </div>
          <HitlApprovalPanel
            pendingPermission={pendingPermission}
            onSubmit={handleHitlDecisions}
          />
          <AgentSessionTimeline
            session={childSession}
            onRefreshRun={async (runId) => setChildSession(await getAgentSession(runId))}
          />
        </>
      ) : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} />}
    </div>
  );
}

export default function AgentChildSessionDrawer({
  open,
  childSessionId,
  onClose,
  onDecisionSubmitted,
}: AgentChildSessionDrawerProps) {
  return (
    <Drawer
      title="子会话详情"
      width={560}
      open={open}
      onClose={onClose}
      destroyOnHidden
    >
      <AgentChildSessionDetail childSessionId={open ? childSessionId : null} onDecisionSubmitted={onDecisionSubmitted} />
    </Drawer>
  );
}
