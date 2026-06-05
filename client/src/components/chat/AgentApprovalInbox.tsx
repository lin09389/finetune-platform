import { Button, Empty, Tag, Typography } from 'antd';
import { useMemo, useState } from 'react';
import type { AgentHitlDecision, AgentSessionUiPendingPermission, AgentWorkspace } from '../../services/api';
import { AgentChildSessionDetail } from './AgentChildSessionDrawer';
import HitlApprovalPanel from './HitlApprovalPanel';
import styles from './AgentWorkspacePanels.module.css';

interface AgentApprovalInboxProps {
  workspace: AgentWorkspace | null;
  onSubmitPermission: (permissionId: string, decisions: AgentHitlDecision[]) => void | Promise<void>;
  onRefresh: () => void | Promise<void>;
  onSelectAsyncTask?: (taskId: string, childSessionId?: string) => void;
}

interface ApprovalInboxItem {
  id: string;
  scope: 'parent' | 'child';
  title: string;
  subtitle: string;
  status?: string | null;
  taskId?: string;
  childSessionId?: string | null;
  pendingPermission?: AgentSessionUiPendingPermission | null;
  permissionPartId: string;
  actionsCount: number;
}

export default function AgentApprovalInbox({
  workspace,
  onSubmitPermission,
  onRefresh,
  onSelectAsyncTask,
}: AgentApprovalInboxProps) {
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const items = useMemo(() => buildApprovalItems(workspace), [workspace]);

  if (!workspace || !items.length) {
    return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无待确认动作" />;
  }

  return (
    <div className={styles.panel}>
      <div className={styles.panelHeader}>
        <div>
          <Typography.Text strong>Approval Inbox</Typography.Text>
          <Typography.Text type="secondary">集中处理父任务与子任务的暂停点</Typography.Text>
        </div>
        <Tag color="warning">{items.length}</Tag>
      </div>

      <div className={styles.approvalList}>
        {items.map((item) => {
          const expanded = expandedId === item.id || item.scope === 'parent';
          return (
            <div key={item.id} className={styles.approvalItem}>
              <div className={styles.approvalSummary}>
                <div>
                  <Typography.Text strong>{item.title}</Typography.Text>
                  <Typography.Text type="secondary">{item.subtitle}</Typography.Text>
                  <div className={styles.metaRow}>
                    <span>{item.scope === 'parent' ? 'parent session' : 'child session'}</span>
                    <span>part {item.permissionPartId}</span>
                    <span>{item.actionsCount} actions</span>
                  </div>
                </div>
                <div className={styles.tagRow}>
                  <Tag color="warning">{item.status || 'waiting'}</Tag>
                  {item.taskId ? (
                    <Button size="small" onClick={() => onSelectAsyncTask?.(item.taskId!, item.childSessionId || undefined)}>
                      任务
                    </Button>
                  ) : null}
                  {item.scope === 'child' ? (
                    <Button size="small" onClick={() => setExpandedId(expanded ? null : item.id)}>
                      {expanded ? '收起' : '处理'}
                    </Button>
                  ) : null}
                </div>
              </div>

              {expanded && item.scope === 'parent' && (
                <HitlApprovalPanel
                  pendingPermission={item.pendingPermission}
                  presentation="panel"
                  onSubmit={async (permissionId, decisions) => {
                    await onSubmitPermission(permissionId, decisions);
                    await onRefresh();
                  }}
                />
              )}

              {expanded && item.scope === 'child' && (
                <AgentChildSessionDetail
                  childSessionId={item.childSessionId}
                  onDecisionSubmitted={async () => {
                    await onRefresh();
                  }}
                />
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

function buildApprovalItems(workspace: AgentWorkspace | null): ApprovalInboxItem[] {
  if (!workspace) return [];
  const items: ApprovalInboxItem[] = [];
  if (workspace.pending_permission?.part_id) {
    items.push({
      id: `parent:${workspace.pending_permission.part_id}`,
      scope: 'parent',
      title: '父会话等待确认',
      subtitle: workspace.session.title || workspace.session.agent_id,
      status: workspace.session.status,
      pendingPermission: workspace.pending_permission,
      permissionPartId: workspace.pending_permission.part_id,
      actionsCount: workspace.pending_permission.actions?.length || 1,
    });
  }
  for (const task of workspace.async_tasks.tasks) {
    if (!task.has_pending_permission || !task.pending_permission_part_id) continue;
    items.push({
      id: `child:${task.task_id}:${task.pending_permission_part_id}`,
      scope: 'child',
      title: `${task.agent_name} 子任务等待确认`,
      subtitle: String(task.input?.description || task.child_session_id || task.task_id),
      status: task.child_status || task.status,
      taskId: task.task_id,
      childSessionId: task.child_session_id,
      permissionPartId: task.pending_permission_part_id,
      actionsCount: 1,
    });
  }
  return items;
}
