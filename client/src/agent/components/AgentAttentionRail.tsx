import {
  BellOutlined,
  CheckOutlined,
  ClearOutlined,
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
const ATTENTION_HISTORY_KEY = 'finetune.agent.attention-history.v1';

interface AttentionHistoryEntry {
  id: string;
  sessionId: string | null;
  title: string;
  action: string;
  resolvedAt: string;
}

function readAttentionHistory(): AttentionHistoryEntry[] {
  if (typeof localStorage === 'undefined') return [];
  try {
    const value = JSON.parse(localStorage.getItem(ATTENTION_HISTORY_KEY) || '[]');
    return Array.isArray(value) ? value.slice(0, 20) : [];
  } catch {
    return [];
  }
}

function actionIcon(action: AgentAttentionAction) {
  if (action.id === 'approve') return <CheckOutlined />;
  if (action.id === 'reject' || action.id === 'dismiss') return <CloseOutlined />;
  if (action.id === 'recover' || action.id === 'restart_subagent') return <UndoOutlined />;
  return <ReloadOutlined />;
}

function formatPercent(value: number | null): string {
  if (value === null) return '暂无';
  return `${Math.round(value * 100)}%`;
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
  const [history, setHistory] = useState<AttentionHistoryEntry[]>(readAttentionHistory);
  const recoveryRate = state.diagnostics.recoveryRequested
    ? state.diagnostics.recoverySucceeded / state.diagnostics.recoveryRequested
    : null;
  const protocolIssueCount = state.diagnostics.unknownEvents
    + state.diagnostics.parseFailures
    + state.diagnostics.recoveryFailed;
  const recentDiagnosticEvents = state.diagnostics.events.slice(-3).reverse();
  const approvable = useMemo(() => items.flatMap((item) => {
    const action = item.actions.find((candidate) => candidate.id === 'approve');
    return action ? [action] : [];
  }), [items]);

  const recordHistory = (title: string, action: AgentAttentionAction) => {
    setHistory((current) => {
      const next = [{
        id: `${Date.now()}:${action.id}:${title}`,
        sessionId: state.activeSessionId,
        title,
        action: action.label,
        resolvedAt: new Date().toISOString(),
      }, ...current].slice(0, 20);
      if (typeof localStorage !== 'undefined') {
        localStorage.setItem(ATTENTION_HISTORY_KEY, JSON.stringify(next));
      }
      return next;
    });
  };

  const runAction = async (action: AgentAttentionAction, title: string) => {
    if (action.id === 'refresh') {
      onRefresh();
      recordHistory(title, action);
      return;
    }
    if (action.id === 'dismiss') {
      onClearError();
      recordHistory(title, action);
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
      await Promise.resolve(onDecidePermission(
        partId,
        Array.from({ length: count }, () => (
          action.id === 'approve'
            ? { type: 'approve' as const }
            : { type: 'reject' as const, message: 'Rejected from Agent Workbench' }
        )),
      ));
      recordHistory(title, action);
      return;
    }
    if (action.id === 'recover') {
      const nodeId = String(action.payload?.nodeId || '');
      const node = workspace?.execution_plan?.nodes.find((candidate) => candidate.id === nodeId);
      if (node) onRecoverNode(node);
      recordHistory(title, action);
      return;
    }
    if (action.id === 'restart_subagent') {
      onRestartSubagent(
        String(action.payload?.agentName || 'explore'),
        String(action.payload?.description || '重试未完成的子任务'),
      );
      recordHistory(title, action);
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
                  const item = items.find((candidate) => candidate.actions.includes(action));
                  await runAction(action, item?.title || '待处理权限');
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
        <section
          className={`${styles.diagnosticsCard} ${protocolIssueCount > 0 ? styles.diagnosticsCardWarning : ''}`}
          aria-label="Agent 运行诊断"
        >
          <header>
            <span>运行诊断</span>
            <Tag color={protocolIssueCount > 0 ? 'orange' : 'green'}>
              {protocolIssueCount > 0 ? '需关注' : '健康'}
            </Tag>
          </header>
          <div className={styles.diagnosticsGrid}>
            <div>
              <strong>{state.diagnostics.unknownEvents}</strong>
              <span>未知事件</span>
            </div>
            <div>
              <strong>{state.diagnostics.parseFailures}</strong>
              <span>解析失败</span>
            </div>
            <div>
              <strong>{state.diagnostics.reconnects}</strong>
              <span>重连</span>
            </div>
            <div>
              <strong>{formatPercent(recoveryRate)}</strong>
              <span>恢复成功率</span>
            </div>
          </div>
          {recentDiagnosticEvents.length > 0 ? (
            <div className={styles.diagnosticsEvents}>
              {recentDiagnosticEvents.map((event) => (
                <div key={event.id}>
                  <span>{event.type}</span>
                  <small>{event.detail || new Date(event.occurredAt).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</small>
                </div>
              ))}
            </div>
          ) : (
            <p>当前会话暂无协议异常、解析失败或恢复事件。</p>
          )}
        </section>
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
                  onClick={() => void runAction(action, item.title)}
                >
                  {action.label}
                </Button>
              ))}
            </div>
          </section>
        ))}
        {items.length === 0 ? <div className={styles.attentionEmpty}>暂无需要处理的事项</div> : null}
        {history.length > 0 ? (
          <section className={styles.attentionHistory} aria-label="最近处理">
            <header>
              <span>最近处理</span>
              <Button
                type="text"
                size="small"
                icon={<ClearOutlined />}
                aria-label="清空处理历史"
                onClick={() => {
                  if (typeof localStorage !== 'undefined') {
                    localStorage.removeItem(ATTENTION_HISTORY_KEY);
                  }
                  setHistory([]);
                }}
              />
            </header>
            {history.slice(0, 5).map((entry) => (
              <div key={entry.id}>
                <span>{entry.title}</span>
                <small>{entry.action} · {new Date(entry.resolvedAt).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</small>
              </div>
            ))}
          </section>
        ) : null}
      </div>
    </aside>
  );
}
