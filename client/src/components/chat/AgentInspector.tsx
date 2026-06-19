import { Button, Empty, Space, Tag, Typography } from 'antd';
import {
  ApartmentOutlined,
  CodeOutlined,
  FileTextOutlined,
  PlayCircleOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons';
import type React from 'react';
import type {
  AgentHitlDecision,
  AgentLoopGuardSnapshot,
  AgentPart,
  AgentWorkspace,
  AgentWorkspaceArtifact,
  AgentWorkspaceNextAction,
} from '../../services/api';
import type { AgentWorkspaceSelection } from '../../hooks/chat/useAgentWorkspaceSelection';
import { AgentChildSessionDetail } from './AgentChildSessionDrawer';
import HitlApprovalPanel from './HitlApprovalPanel';
import styles from './AgentInspector.module.css';

interface AgentInspectorProps {
  workspace: AgentWorkspace | null;
  selection: AgentWorkspaceSelection | null;
  onSubmitPermission?: (permissionId: string, decisions: AgentHitlDecision[]) => void | Promise<void>;
  onRefresh?: () => void | Promise<void>;
  onOpenFile?: (path: string) => void | Promise<void>;
  onRunNextAction?: (action: AgentWorkspaceNextAction) => void | Promise<void>;
}

const statusColor: Record<string, string> = {
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
  pending: 'gold',
  cancelled: 'default',
};

function commandText(part?: AgentPart) {
  const command = part?.payload?.command;
  return Array.isArray(command) ? command.join(' ') : String(command || part?.title || '命令');
}

export default function AgentInspector({
  workspace,
  selection,
  onSubmitPermission,
  onRefresh,
  onOpenFile,
  onRunNextAction,
}: AgentInspectorProps) {
  if (!workspace || !selection) {
    return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无 Agent 工作区" />;
  }

  if (selection.type === 'async_task') {
    const task = workspace.async_tasks.tasks.find((item) => item.task_id === selection.taskId);
    if (!task) {
      return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="未找到子任务" />;
    }
    return (
      <div className={styles.inspector}>
        <Header icon={<ThunderboltOutlined />} title={`${task.agent_name} 子任务`} tag={task.status} />
        <InfoRow label="任务" value={task.task_id} />
        {task.child_session_id ? <InfoRow label="子会话" value={task.child_session_id} /> : null}
        {task.child_status ? <InfoRow label="Child 状态" value={task.child_status} /> : null}
        {task.input?.description ? <Typography.Paragraph className={styles.summary}>{String(task.input.description)}</Typography.Paragraph> : null}
        {task.has_pending_permission ? <Tag color="warning">等待确认</Tag> : null}
        {task.child_session_id ? (
          <AgentChildSessionDetail childSessionId={task.child_session_id} onDecisionSubmitted={onRefresh} />
        ) : null}
      </div>
    );
  }

  if (selection.type === 'permission') {
    if (!workspace.pending_permission || workspace.pending_permission.part_id !== selection.permissionPartId) {
      return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="未找到待确认权限" />;
    }
    return (
      <div className={styles.inspector}>
        <Header icon={<CodeOutlined />} title="权限确认" tag="等待确认" />
        <HitlApprovalPanel pendingPermission={workspace.pending_permission} presentation="panel" onSubmit={async (permissionId, decisions) => {
          await onSubmitPermission?.(permissionId, decisions);
        }} />
      </div>
    );
  }

  if (selection.type === 'artifact') {
    const artifact = workspace.artifacts.find((item) => item.id === selection.artifactId);
    if (!artifact) {
      return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="未找到产物" />;
    }
    return <ArtifactDetail artifact={artifact} onOpenFile={onOpenFile} />;
  }

  if (selection.type === 'file') {
    const changedFile = workspace.changed_files.find((item) => item.path === selection.path);
    return (
      <div className={styles.inspector}>
        <Header icon={<FileTextOutlined />} title="文件" tag={changedFile?.status || 'workspace'} />
        <InfoRow label="路径" value={selection.path} />
        {changedFile?.summary ? <Typography.Paragraph className={styles.summary}>{changedFile.summary}</Typography.Paragraph> : null}
        <Button size="small" onClick={() => void onOpenFile?.(selection.path)}>在工作区打开</Button>
      </div>
    );
  }

  if (selection.type === 'command') {
    const part = workspace.session.parts.find((item) => item.id === selection.partId);
    return (
      <div className={styles.inspector}>
        <Header icon={<PlayCircleOutlined />} title={commandText(part)} tag={part?.status || 'command'} />
        <InfoRow label="part" value={selection.partId} />
        {part?.payload?.exit_code !== undefined ? <InfoRow label="退出码" value={String(part.payload.exit_code)} /> : null}
        {part?.content ? <Typography.Paragraph className={styles.summary}>{part.content}</Typography.Paragraph> : null}
        <pre className={styles.payload}>{JSON.stringify(part?.payload || {}, null, 2)}</pre>
      </div>
    );
  }

  if (selection.type === 'timeline_item') {
    const item = workspace.timeline.find((entry) => entry.id === selection.itemId || entry.part_id === selection.partId);
    const executionItem = workspace.execution_timeline?.find((entry) => entry.id === selection.itemId || entry.source_part_id === selection.partId);
    const part = workspace.session.parts.find((entry) => entry.id === (selection.partId || executionItem?.source_part_id));
    const detail = item || executionItem;
    return (
      <div className={styles.inspector}>
        <Header icon={<ApartmentOutlined />} title={detail?.title || detail?.type || 'Timeline'} tag={detail?.status || 'item'} />
        {(item?.content || executionItem?.summary) ? (
          <Typography.Paragraph className={styles.summary}>{item?.content || executionItem?.summary}</Typography.Paragraph>
        ) : null}
        <pre className={styles.payload}>{JSON.stringify(part?.payload || item?.payload || executionItem?.payload_excerpt || detail || {}, null, 2)}</pre>
      </div>
    );
  }

  return (
    <div className={styles.inspector}>
      <Header icon={<ApartmentOutlined />} title={workspace.session.title || workspace.session.agent_id} tag={workspace.session.status} />
      <Typography.Paragraph className={styles.summary}>
        {workspace.status_text?.stop_reason || workspace.status_text?.current_phase || '当前 Agent 运行状态。'}
      </Typography.Paragraph>
      {workspace.status_text?.next_action ? <InfoRow label="下一步" value={workspace.status_text.next_action} /> : null}
      {workspace.session.metadata?.loop_guard?.blocked ? (
        <LoopGuardInspector guard={workspace.session.metadata.loop_guard} />
      ) : null}
      <div className={styles.statsGrid}>
        <Stat label="子任务" value={workspace.async_tasks.metrics.total} />
        <Stat label="运行" value={workspace.async_tasks.metrics.running} />
        <Stat label="待处理" value={workspace.async_tasks.metrics.attention} />
        <Stat label="产物" value={workspace.artifacts.length} />
      </div>
      {workspace.runtime ? (
        <div className={styles.artifactList}>
          <div className={styles.sectionTitle}>Runtime Context</div>
          <InfoRow label="Workspace" value={workspace.runtime.workspace_root || '未绑定'} />
          <InfoRow label="VFS mounts" value={String(workspace.runtime.vfs_mounts.length)} />
          <InfoRow label="Skills" value={String(workspace.runtime.skill_sources.length)} />
          <InfoRow label="Memory files" value={String(workspace.runtime.memory_files.length)} />
        </div>
      ) : null}
      <NextActions actions={workspace.next_actions || []} onRunNextAction={onRunNextAction} />
      {workspace.recent_events.length > 0 ? (
        <div className={styles.eventList}>
          {workspace.recent_events.slice(-5).map((event, index) => (
            <div key={event.id || index} className={styles.eventItem}>
              <Typography.Text strong>{event.event_type || 'event'}</Typography.Text>
              {event.message ? <Typography.Text type="secondary">{event.message}</Typography.Text> : null}
            </div>
          ))}
        </div>
      ) : null}
    </div>
  );
}

function LoopGuardInspector({ guard }: { guard: AgentLoopGuardSnapshot }) {
  const reasonLabels: Record<string, string> = {
    repeated_identical_failure: '重复相同失败',
    repeated_failure_family: '重复同类失败',
    consecutive_failures: '连续工具失败',
    repeated_no_progress: '重复操作但无进展',
  };
  const reason = reasonLabels[String(guard.blocked_reason_code || '')] || guard.blocked_reason_code || '循环保护';
  return (
    <div className={styles.artifactList}>
      <div className={styles.sectionTitle}>循环阻断诊断</div>
      <InfoRow label="类型" value={String(reason)} />
      {guard.repeat_count ? <InfoRow label="触发次数" value={String(guard.repeat_count)} /> : null}
      {guard.threshold ? <InfoRow label="阈值" value={String(guard.threshold)} /> : null}
      {guard.tool ? <InfoRow label="工具" value={guard.tool} /> : null}
      {guard.input_excerpt ? <Typography.Paragraph className={styles.summary}>输入：{guard.input_excerpt}</Typography.Paragraph> : null}
      {guard.error_excerpt ? <Typography.Paragraph type="danger" className={styles.summary}>错误：{guard.error_excerpt}</Typography.Paragraph> : null}
      {guard.output_excerpt ? <Typography.Paragraph className={styles.summary}>重复输出：{guard.output_excerpt}</Typography.Paragraph> : null}
    </div>
  );
}

function NextActions({
  actions,
  onRunNextAction,
}: {
  actions: AgentWorkspaceNextAction[];
  onRunNextAction?: (action: AgentWorkspaceNextAction) => void | Promise<void>;
}) {
  if (!actions.length) return null;
  return (
    <div className={styles.nextActions}>
      <div className={styles.sectionTitle}>建议下一步</div>
      {actions.map((action) => (
        <div key={action.id} className={styles.nextActionItem}>
          <div className={styles.nextActionBody}>
            <div className={styles.nextActionHeader}>
              <Typography.Text strong>{action.title}</Typography.Text>
              <Tag color={priorityColor(action.priority)}>{priorityLabel(action.priority)}</Tag>
            </div>
            {action.summary ? <Typography.Text type="secondary">{action.summary}</Typography.Text> : null}
          </div>
          <Button size="small" onClick={() => void onRunNextAction?.(action)}>
            {nextActionButtonLabel(action.action_type)}
          </Button>
        </div>
      ))}
    </div>
  );
}

function ArtifactDetail({ artifact, onOpenFile }: { artifact: AgentWorkspaceArtifact; onOpenFile?: (path: string) => void | Promise<void> }) {
  const payload = artifact.payload || {};
  const common = (
    <>
      {artifact.summary ? <Typography.Paragraph className={styles.summary}>{artifact.summary}</Typography.Paragraph> : null}
      {artifact.source_part_id ? <InfoRow label="来源 part" value={artifact.source_part_id} /> : null}
      {artifact.source_task_id ? <InfoRow label="来源任务" value={artifact.source_task_id} /> : null}
    </>
  );

  if (artifact.artifact_type === 'finding' || artifact.artifact_type === 'findings') {
    return (
      <div className={styles.inspector}>
        <Header icon={<FileTextOutlined />} title={artifact.title} tag="findings" />
        {common}
        <ArtifactItems items={Array.isArray(payload.items) ? payload.items : []} tone="finding" />
        {Array.isArray(payload.files_examined) && payload.files_examined.length > 0 ? (
          <FileChips files={payload.files_examined} onOpenFile={onOpenFile} />
        ) : null}
      </div>
    );
  }

  if (artifact.artifact_type === 'risk' || artifact.artifact_type === 'risks') {
    return (
      <div className={styles.inspector}>
        <Header icon={<CodeOutlined />} title={artifact.title} tag={String(payload.verdict || 'risks')} />
        {common}
        <ArtifactItems items={Array.isArray(payload.items) ? payload.items : []} tone="risk" />
      </div>
    );
  }

  if (artifact.artifact_type === 'test_result') {
    const passed = payload.passed === true;
    return (
      <div className={styles.inspector}>
        <Header icon={<PlayCircleOutlined />} title={artifact.title} tag={passed ? '通过' : '失败'} />
        {common}
        <InfoRow label="退出码" value={String(payload.exit_code ?? '')} />
        {payload.command ? <InfoRow label="命令" value={Array.isArray(payload.command) ? payload.command.join(' ') : String(payload.command)} /> : null}
        <OutputBlock title="stdout" value={payload.stdout} />
        <OutputBlock title="stderr" value={payload.stderr} />
      </div>
    );
  }

  if (artifact.artifact_type === 'file_change') {
    const path = String(payload.path || artifact.title || '');
    return (
      <div className={styles.inspector}>
        <Header icon={<FileTextOutlined />} title={path || '文件变更'} tag={String(payload.status || 'modified')} />
        {common}
        {path ? <Button size="small" onClick={() => void onOpenFile?.(path)}>在工作区打开</Button> : null}
        {payload.preview ? <pre className={styles.payload}>{String(payload.preview)}</pre> : null}
      </div>
    );
  }

  if (artifact.artifact_type === 'command_result') {
    return (
      <div className={styles.inspector}>
        <Header icon={<PlayCircleOutlined />} title={artifact.title} tag="command" />
        {common}
        <InfoRow label="退出码" value={String(payload.exit_code ?? '')} />
        <OutputBlock title="stdout" value={payload.stdout} />
        <OutputBlock title="stderr" value={payload.stderr} />
      </div>
    );
  }

  return (
    <div className={styles.inspector}>
      <Header icon={<FileTextOutlined />} title={artifact.title} tag={artifact.artifact_type} />
      {common}
      <pre className={styles.payload}>{JSON.stringify(payload, null, 2)}</pre>
    </div>
  );
}

function ArtifactItems({ items, tone }: { items: any[]; tone: 'finding' | 'risk' }) {
  if (!items.length) return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无结构化条目" />;
  return (
    <div className={styles.artifactList}>
      {items.map((item, index) => (
        <div key={`${item.title || tone}-${index}`} className={styles.artifactItem}>
          <div className={styles.artifactItemHeader}>
            <Typography.Text strong>{String(item.title || (tone === 'risk' ? '风险' : '发现'))}</Typography.Text>
            {item.severity ? <Tag color={severityColor(String(item.severity))}>{String(item.severity)}</Tag> : null}
            {item.confidence ? <Tag>{String(item.confidence)}</Tag> : null}
          </div>
          {item.summary ? <Typography.Text type="secondary">{String(item.summary)}</Typography.Text> : null}
          {item.recommendation ? <Typography.Text type="secondary">建议：{String(item.recommendation)}</Typography.Text> : null}
          {Array.isArray(item.files) && item.files.length > 0 ? <FileChips files={item.files} /> : null}
        </div>
      ))}
    </div>
  );
}

function FileChips({ files, onOpenFile }: { files: any[]; onOpenFile?: (path: string) => void | Promise<void> }) {
  return (
    <div className={styles.fileChips}>
      {files.slice(0, 12).map((file) => {
        const path = String(file);
        return (
          <button key={path} type="button" className={styles.fileChip} onClick={() => void onOpenFile?.(path)}>
            {path}
          </button>
        );
      })}
    </div>
  );
}

function OutputBlock({ title, value }: { title: string; value: unknown }) {
  const text = value === undefined || value === null ? '' : String(value);
  if (!text) return null;
  return (
    <div className={styles.outputBlock}>
      <Typography.Text type="secondary">{title}</Typography.Text>
      <pre className={styles.payload}>{text}</pre>
    </div>
  );
}

function severityColor(value: string) {
  const normalized = value.toLowerCase();
  if (['high', 'critical', '严重'].includes(normalized)) return 'error';
  if (['medium', '中'].includes(normalized)) return 'warning';
  return 'default';
}

function priorityColor(value: string) {
  if (value === 'high') return 'error';
  if (value === 'medium') return 'warning';
  return 'default';
}

function priorityLabel(value: string) {
  if (value === 'high') return '高';
  if (value === 'medium') return '中';
  return '低';
}

function nextActionButtonLabel(actionType: string) {
  if (actionType === 'resolve_permission') return '处理确认';
  if (actionType === 'review_risks') return '查看风险';
  if (actionType === 'start_review') return '启动审查';
  if (actionType === 'start_explore') return '启动探索';
  if (actionType === 'inspect_file') return '查看文件';
  if (actionType === 'restart_failed_task') return '查看失败任务';
  return '查看建议';
}

function Header({ icon, title, tag }: { icon: React.ReactNode; title: string; tag?: string }) {
  return (
    <div className={styles.header}>
      <Space size={8}>
        {icon}
        <Typography.Text strong ellipsis className={styles.title}>{title}</Typography.Text>
      </Space>
      {tag ? <Tag color={statusColor[tag] || 'default'}>{tag}</Tag> : null}
    </div>
  );
}

function InfoRow({ label, value }: { label: string; value: string }) {
  return (
    <div className={styles.infoRow}>
      <span>{label}</span>
      <Typography.Text code ellipsis>{value}</Typography.Text>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <div className={styles.stat}>
      <strong>{value}</strong>
      <span>{label}</span>
    </div>
  );
}
