import { Button, Empty, Progress, Tag, Typography } from 'antd';
import { useState } from 'react';
import type {
  AgentAsyncTask,
  AgentExecutionPlan,
  AgentExecutionPlanNode,
  AgentResourceProfile,
  AgentRuntimePolicy,
} from '../../services/api';
import styles from './AgentWorkspacePanels.module.css';

type NodeUiStatus = 'pending' | 'running' | 'blocked' | 'completed' | 'failed' | 'interrupted';

const statusLabel: Record<NodeUiStatus, string> = {
  pending: '待执行',
  running: '执行中',
  blocked: '等待',
  completed: '完成',
  failed: '失败',
  interrupted: '中断',
};

const statusColor: Record<NodeUiStatus, string> = {
  pending: 'default',
  running: 'processing',
  blocked: 'warning',
  completed: 'success',
  failed: 'error',
  interrupted: 'default',
};

interface AgentOrchestrationPanelProps {
  executionPlan?: AgentExecutionPlan | null;
  runtimePolicy?: AgentRuntimePolicy | null;
  resourceProfile?: AgentResourceProfile | null;
  asyncTasks?: AgentAsyncTask[];
  onSelectTask?: (taskId: string) => void;
  onRecoverNode?: (node: AgentExecutionPlanNode, action?: string | null) => void | Promise<void>;
}

export default function AgentOrchestrationPanel({
  executionPlan,
  runtimePolicy,
  resourceProfile,
  asyncTasks = [],
  onSelectTask,
  onRecoverNode,
}: AgentOrchestrationPanelProps) {
  const nodes = executionPlan?.nodes ?? [];
  const completed = nodes.filter((node) => normalizeNodeStatus(node.status) === 'completed').length;
  const percent = nodes.length ? Math.round((completed / nodes.length) * 100) : 0;
  const currentNode = nodes.find((node) => node.id === executionPlan?.current_node_id);

  if (!nodes.length) {
    return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无执行编排" />;
  }

  return (
    <div className={styles.panel}>
      <div className={styles.panelHeader}>
        <div>
          <Typography.Text strong>Agent Orchestration</Typography.Text>
          <Typography.Text type="secondary">{executionPlan?.goal || runtimePolicy?.agent_name || 'execution plan'}</Typography.Text>
        </div>
        <Tag color={statusColor[normalizeNodeStatus(executionPlan?.status || 'pending')]}>
          {statusLabel[normalizeNodeStatus(executionPlan?.status || 'pending')]}
        </Tag>
      </div>

      <div className={styles.compactList}>
        <div className={styles.compactItem}>
          <Typography.Text type="secondary">当前节点</Typography.Text>
          <Typography.Text strong>{currentNode?.title || '无'}</Typography.Text>
        </div>
        <div className={styles.compactItem}>
          <Typography.Text type="secondary">执行进度</Typography.Text>
          <Typography.Text strong>{completed}/{nodes.length}</Typography.Text>
        </div>
        <div className={styles.compactItem}>
          <Typography.Text type="secondary">依赖边</Typography.Text>
          <Typography.Text strong>{executionPlan?.edges?.length ?? 0}</Typography.Text>
        </div>
        <div className={styles.compactItem}>
          <Typography.Text type="secondary">子任务</Typography.Text>
          <Typography.Text strong>{asyncTasks.length}</Typography.Text>
        </div>
      </div>

      <Progress percent={percent} size="small" />

      <div className={styles.section}>
        <Typography.Text strong>Runtime Contract</Typography.Text>
        <div className={styles.metaRow}>
          {runtimePolicy?.agent_id ? <Tag>{runtimePolicy.agent_id}</Tag> : null}
          {runtimePolicy?.mode ? <Tag>{runtimePolicy.mode}</Tag> : null}
          {runtimePolicy?.filesystem_profile ? <Tag>{runtimePolicy.filesystem_profile}</Tag> : null}
          {runtimePolicy?.tools?.async_tools_enabled ? <Tag color="processing">async tools</Tag> : null}
          {resourceProfile?.memory?.namespaces?.length ? <Tag>{resourceProfile.memory.namespaces.length} memory mounts</Tag> : null}
        </div>
      </div>

      <div className={styles.timelineList}>
        {nodes.map((node) => (
          <ExecutionNode
            key={node.id}
            node={node}
            isCurrent={executionPlan?.current_node_id === node.id}
            linkedTask={node.source_task_id ? asyncTasks.find((task) => task.task_id === node.source_task_id) : undefined}
            onSelectTask={onSelectTask}
            onRecoverNode={onRecoverNode}
          />
        ))}
      </div>
    </div>
  );
}

function ExecutionNode({
  node,
  isCurrent,
  linkedTask,
  onSelectTask,
  onRecoverNode,
}: {
  node: AgentExecutionPlanNode;
  isCurrent: boolean;
  linkedTask?: AgentAsyncTask;
  onSelectTask?: (taskId: string) => void;
  onRecoverNode?: (node: AgentExecutionPlanNode, action?: string | null) => void | Promise<void>;
}) {
  const status = normalizeNodeStatus(node.status);
  const approvalTools = Array.isArray(node.approval_policy?.tools) ? node.approval_policy.tools : [];
  const retryAttempts = Number(node.retry_policy?.max_attempts || 0);
  const recoveryAction = node.recovery_action || (node.kind === 'subagent' ? 'restart_subagent' : 'retry_node');
  const recoverLabel = recoveryAction === 'restart_subagent' ? '重启子任务' : '恢复执行';
  const canSelectTask = Boolean(node.source_task_id && onSelectTask);
  const [recovering, setRecovering] = useState(false);
  const recoveryHistory = Array.isArray(node.output?.recovery_history) ? node.output.recovery_history : [];
  const latestRecovery = recoveryHistory.length ? recoveryHistory[recoveryHistory.length - 1] : null;

  return (
    <div
      role={canSelectTask ? 'button' : undefined}
      tabIndex={canSelectTask ? 0 : undefined}
      className={styles.timelineItem}
      onClick={() => node.source_task_id && onSelectTask?.(node.source_task_id)}
      onKeyDown={(event) => {
        if (!canSelectTask) return;
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault();
          node.source_task_id && onSelectTask?.(node.source_task_id);
        }
      }}
    >
      <span className={styles.timelineRail} data-type={status === 'failed' ? 'error' : status === 'blocked' ? 'permission' : 'tool_call'} />
      <span className={styles.timelineBody}>
        <span className={styles.timelineTitle}>
          <Typography.Text strong>{node.title}</Typography.Text>
          {isCurrent ? <Tag color="processing">当前</Tag> : null}
          <Tag color={statusColor[status]}>{statusLabel[status]}</Tag>
          {linkedTask ? <Tag>{linkedTask.agent_name}</Tag> : null}
        </span>
        {node.description ? <Typography.Text type="secondary">{node.description}</Typography.Text> : null}
        <span className={styles.metaRow}>
          {node.agent_id ? <span>agent {node.agent_id}</span> : null}
          {node.kind ? <span>{node.kind}</span> : null}
          {node.tool ? <span>tool {node.tool}</span> : null}
          {node.source_part_id ? <span>part {node.source_part_id}</span> : null}
          {node.source_permission_part_id ? <span>permission {node.source_permission_part_id}</span> : null}
          {node.source_task_id ? <span>task {node.source_task_id}</span> : null}
          {node.depends_on?.length ? <span>depends on {node.depends_on.join(', ')}</span> : null}
          {approvalTools.length ? <span>approval {approvalTools.join(', ')}</span> : null}
          {retryAttempts ? <span>retry {retryAttempts}</span> : null}
          {node.started_at ? <span>started {formatTime(node.started_at)}</span> : null}
          {node.completed_at ? <span>done {formatTime(node.completed_at)}</span> : null}
          {node.recovery_attempts ? <span>recovered {node.recovery_attempts}</span> : null}
          {node.last_recovery_at ? <span>last recovery {formatTime(node.last_recovery_at)}</span> : null}
        </span>
        {node.blocked_reason ? <Typography.Text type="warning">{node.blocked_reason}</Typography.Text> : null}
        {node.error ? <Typography.Text type="danger">{node.error}</Typography.Text> : null}
        {node.recovery_reason ? <Typography.Text type="secondary">{node.recovery_reason}</Typography.Text> : null}
        {node.recovery_error ? <Typography.Text type="danger">{node.recovery_error}</Typography.Text> : null}
        {latestRecovery ? (
          <Typography.Text type="secondary">
            recovery {String(latestRecovery.status || 'updated')}
            {latestRecovery.new_task_id ? ` -> ${latestRecovery.new_task_id}` : ''}
          </Typography.Text>
        ) : null}
        {node.recoverable ? (
          <span className={styles.metaRow}>
            <Button
              size="small"
              type="primary"
              loading={recovering}
              disabled={recovering}
              onClick={async (event) => {
                event.stopPropagation();
                if (recovering) return;
                setRecovering(true);
                try {
                  await onRecoverNode?.(node, recoveryAction);
                } finally {
                  setRecovering(false);
                }
              }}
            >
              {recoverLabel}
            </Button>
          </span>
        ) : null}
      </span>
    </div>
  );
}

function normalizeNodeStatus(status: string): NodeUiStatus {
  if (status === 'running') {
    return 'running';
  }
  if (status === 'completed') {
    return 'completed';
  }
  if (status === 'failed') {
    return 'failed';
  }
  if (status === 'interrupted') {
    return 'interrupted';
  }
  if (['blocked', 'waiting_approval', 'waiting_permission'].includes(status)) {
    return 'blocked';
  }
  return 'pending';
}

function formatTime(value: string): string {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }
  return parsed.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}
