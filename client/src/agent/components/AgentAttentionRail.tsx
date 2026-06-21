import {
  BellOutlined,
  CheckOutlined,
  CloseOutlined,
  ReloadOutlined,
  UndoOutlined,
} from '@ant-design/icons';
import { Button, Popconfirm, Tag } from 'antd';
import { useMemo, useState } from 'react';
import type {
  AgentExecutionPlanNode,
  AgentHitlDecision,
  AgentWorkspace,
} from '../../services/api';
import { selectAttentionItems } from '../attention/selectAttentionItems';
import type { AgentAttentionAction } from '../attention/attentionTypes';
import type { AgentRuntimeState } from '../runtime/agentRuntime';
import styles from '../workbench/AgentWorkbench.module.css';

interface AgentAttentionRailProps {
  state: AgentRuntimeState;
  workspace: AgentWorkspace | null;
  onClearError: () => void;
  onRefresh: () => void;
  onDecidePermission: (partId: string, decisions: AgentHitlDecision[]) => Promise<unknown> | void;
  onRecoverNode: (node: AgentExecutionPlanNode) => void;
  onRestartSubagent: (agentName: string, description: string) => void;
  embedded?: boolean;
}

const severityLabels = {
  critical: '严重',
  high: '高',
  medium: '中',
  low: '低',
};

function actionIcon(action: AgentAttentionAction) {
  if (action.id === 'approve') return <CheckOutlined />;
  if (action.id === 'reject' || action.id === 'dismiss') return <CloseOutlined />;
  if (action.id === 'recover' || action.id === 'restart_subagent') return <UndoOutlined />;
  return <ReloadOutlined />;
}

export default function AgentAttentionRail({
  state,
  workspace,
  onClearError,
  onRefresh,
  onDecidePermission,
  onRecoverNode,
  onRestartSubagent,
  embedded = false,
}: AgentAttentionRailProps) {
  const items = selectAttentionItems(state);
  const [batchApproving, setBatchApproving] = useState(false);
  const approvable = useMemo(() => items.flatMap((item) => {
    const action = item.actions.find((candidate) => candidate.id === 'approve');
    return action ? [action] : [];
  }), [items]);

  const runAction = (action: AgentAttentionAction) => {
    if (action.id === 'refresh') {
      onRefresh();
      return;
    }
    if (action.id === 'dismiss') {
      onClearError();
      return;
    }
    if (action.id === 'approve' || action.id === 'reject') {
      const partId = String(action.payload?.partId || '');
      const count = Math.max(
        1,
        Number(action.payload?.actionCount)
          || (workspace?.pending_permission?.part_id === partId
            ? workspace.pending_permission.actions.length
            : 1),
      );
      return onDecidePermission(
        partId,
        Array.from({ length: count }, () => (
          action.id === 'approve'
            ? { type: 'approve' as const }
            : { type: 'reject' as const, message: 'Rejected from Agent Workbench' }
        )),
      );
    }
    if (action.id === 'recover') {
      const nodeId = String(action.payload?.nodeId || '');
      const node = workspace?.execution_plan?.nodes.find((candidate) => candidate.id === nodeId);
      if (node) onRecoverNode(node);
      return;
    }
    if (action.id === 'restart_subagent') {
      onRestartSubagent(
        String(action.payload?.agentName || 'explore'),
        String(action.payload?.description || '重试未完成的子任务'),
      );
    }
  };

  return (
    <aside
      className={`${styles.attentionRail} ${embedded ? styles.embeddedRail : ''}`}
      aria-label="注意事项"
    >
      <div className={styles.attentionHeader}>
        <BellOutlined />
        <span>Attention Center</span>
        <span className={styles.attentionCount}>{items.length}</span>
        {approvable.length > 1 ? (
          <Popconfirm
            title={`批准 ${approvable.length} 项待处理权限？`}
            okText="全部批准"
            cancelText="取消"
            onConfirm={async () => {
              setBatchApproving(true);
              try {
                for (const action of approvable) {
                  await Promise.resolve(runAction(action));
                }
              } finally {
                setBatchApproving(false);
              }
            }}
          >
            <Button size="small" type="link" loading={batchApproving}>全部批准</Button>
          </Popconfirm>
        ) : null}
      </div>
      <div className={styles.attentionBody}>
        {items.map((item) => (
          <section
            key={item.id}
            className={`${styles.attentionItem} ${styles[`attention_${item.severity}`] || ''}`}
            data-attention-kind={item.kind}
          >
            <div className={styles.attentionTitle}>
              <Tag color={item.severity === 'critical' ? 'red' : item.severity === 'high' ? 'orange' : undefined}>
                {severityLabels[item.severity]}
              </Tag>
              <span>{item.title}</span>
            </div>
            <dl className={styles.attentionDetails}>
              <div>
                <dt>发生了什么</dt>
                <dd>{item.whatHappened}</dd>
              </div>
              <div>
                <dt>影响范围</dt>
                <dd>{item.impactScope}</dd>
              </div>
              <div>
                <dt>建议动作</dt>
                <dd>{item.recommendedAction}</dd>
              </div>
            </dl>
            <div className={styles.attentionActions}>
              {item.actions.map((action) => (
                <Button
                  key={action.id}
                  size="small"
                  type={action.primary ? 'primary' : 'default'}
                  danger={action.danger}
                  icon={actionIcon(action)}
                  loading={(
                    action.id === 'refresh'
                    && Boolean(state.activeSessionId && state.operations[`refresh:${state.activeSessionId}`])
                  ) || (
                    ['approve', 'reject'].includes(action.id)
                    && Boolean(state.operations[`permission:${String(action.payload?.partId || '')}`])
                  ) || (
                    action.id === 'recover'
                    && Boolean(state.operations[`recover:${state.activeSessionId}:${String(action.payload?.nodeId || '')}`])
                  )}
                  onClick={() => runAction(action)}
                >
                  {action.label}
                </Button>
              ))}
            </div>
          </section>
        ))}
        {items.length === 0 ? <div className={styles.attentionEmpty}>暂无需要处理的事项</div> : null}
      </div>
    </aside>
  );
}
