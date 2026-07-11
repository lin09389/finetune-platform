import {
  BranchesOutlined,
  CheckCircleOutlined,
  ClockCircleOutlined,
  CodeOutlined,
  DownOutlined,
  ExclamationCircleOutlined,
  FileDoneOutlined,
  FileTextOutlined,
  FolderOpenOutlined,
  LoadingOutlined,
  RightOutlined,
  SafetyCertificateOutlined,
  ToolOutlined,
  UpOutlined,
  UserOutlined,
} from '@ant-design/icons';
import { Alert, Button, Empty, Input, Segmented, Switch } from 'antd';
import { motion } from 'framer-motion';
import { useDeferredValue, useEffect, useMemo, useRef, useState } from 'react';
import { Virtuoso, type VirtuosoHandle } from 'react-virtuoso';
import type { AgentSessionUiTimelineItem, AgentSessionUiPendingPermission } from '../../services/api';
import type { AgentHitlDecision } from '../../services/api';
import { isTrainingToolName, selectTrainingActivity } from '../protocol/agentProtocol';
import styles from '../workbench/AgentWorkbench.module.css';
import AgentMarkdown, { CopyResponseButton } from './AgentMarkdown';
import AgentTrainingActivity from './AgentTrainingActivity';

function itemIcon(item: AgentSessionUiTimelineItem) {
  if (isUserMessage(item)) return <UserOutlined />;
  if (item.type === 'task_context') return <FolderOpenOutlined />;
  if (item.status === 'running' || item.status === 'pending') return <LoadingOutlined spin />;
  if (item.status === 'failed' || item.status === 'blocked') return <ExclamationCircleOutlined />;
  if (item.type === 'permission') return <SafetyCertificateOutlined />;
  if (item.type === 'tool_call' || item.type === 'tool_result') return <ToolOutlined />;
  if (item.type === 'command') return <CodeOutlined />;
  if (item.type === 'summary') return <FileTextOutlined />;
  if (item.status === 'completed' || item.status === 'approved' || item.status === 'executed') {
    return <CheckCircleOutlined />;
  }
  return <ClockCircleOutlined />;
}

function isUserMessage(item: AgentSessionUiTimelineItem): boolean {
  return item.type === 'text' && item.payload?.role === 'user';
}

function isModelResponse(item: AgentSessionUiTimelineItem): boolean {
  return !isUserMessage(item) && ['text', 'summary'].includes(item.type);
}

const EXECUTION_ITEM_TYPES = new Set(['tool_call', 'tool_result', 'command']);

interface ExecutionGroupEntry {
  kind: 'execution_group';
  id: string;
  items: AgentSessionUiTimelineItem[];
}

type TimelineDisplayEntry = AgentSessionUiTimelineItem | ExecutionGroupEntry;

function isExecutionItem(item: AgentSessionUiTimelineItem): boolean {
  return EXECUTION_ITEM_TYPES.has(item.type) && !selectTrainingActivity(item);
}

function isExecutionGroup(entry: TimelineDisplayEntry): entry is ExecutionGroupEntry {
  return 'kind' in entry && entry.kind === 'execution_group';
}

function groupExecutionItems(items: AgentSessionUiTimelineItem[]): TimelineDisplayEntry[] {
  const grouped: TimelineDisplayEntry[] = [];
  let active: AgentSessionUiTimelineItem[] = [];

  const flush = () => {
    if (active.length === 0) return;
    grouped.push({
      kind: 'execution_group',
      id: `execution:${active.map((item) => item.id).join(':')}`,
      items: active,
    });
    active = [];
  };

  for (const item of items) {
    if (isExecutionItem(item)) {
      active.push(item);
      continue;
    }
    flush();
    grouped.push(item);
  }
  flush();
  return grouped;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value);
}

function stringifyCommand(command: unknown): string {
  if (Array.isArray(command)) return command.map((item) => String(item)).join(' ');
  if (typeof command === 'string') return command;
  return '';
}

function payloadText(payload: Record<string, unknown> | undefined, key: string): string {
  const value = payload?.[key];
  return typeof value === 'string' ? value : '';
}

function durationLabel(payload: Record<string, unknown> | undefined): string | null {
  const raw = payload?.duration_ms ?? payload?.elapsed_ms;
  if (typeof raw === 'number' && Number.isFinite(raw)) {
    return raw < 1000
      ? `${Math.round(raw)} 毫秒`
      : `${(raw / 1000).toFixed(raw < 10_000 ? 1 : 0)} 秒`;
  }
  const duration = payload?.duration;
  return typeof duration === 'string' && duration.trim() ? duration.trim() : null;
}

function formatElapsedSeconds(seconds: number): string {
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  const remaining = seconds % 60;
  return `${minutes}m ${remaining.toString().padStart(2, '0')}s`;
}

function liveElapsed(item: AgentSessionUiTimelineItem, now: number): string | null {
  const start = item.created_at ? new Date(item.created_at).getTime() : NaN;
  if (!Number.isFinite(start)) return null;
  const elapsed = Math.max(0, Math.floor((now - start) / 1000));
  return formatElapsedSeconds(elapsed);
}

function shouldShowStatus(item: AgentSessionUiTimelineItem): boolean {
  return (
    ['pending', 'running', 'failed', 'blocked'].includes(String(item.status || '')) ||
    item.type === 'permission' ||
    item.type === 'error'
  );
}

function statusLabel(item: AgentSessionUiTimelineItem): string {
  const labels: Record<string, string> = {
    pending: '等待中',
    running: item.type === 'command' ? '正在运行' : '正在处理',
    completed: '完成',
    approved: '已批准',
    executed: '已执行',
    failed: '失败',
    blocked: '已阻塞',
  };
  return labels[String(item.status || '')] || String(item.status || item.type);
}

function itemTitle(item: AgentSessionUiTimelineItem) {
  if (isUserMessage(item)) return item.title || '我的消息';
  const payload = item.payload;
  const command = stringifyCommand(payload?.command);
  if (item.type === 'command' && command) {
    return item.status === 'running' ? `正在运行 ${command}` : `已运行 ${command}`;
  }
  if (item.type === 'diff') {
    const changedFiles = Array.isArray(payload?.changed_files)
      ? payload.changed_files.length
      : undefined;
    return changedFiles ? `已编辑 ${changedFiles} 个文件` : '文件已更新';
  }
  if (item.type === 'tool_call' && item.tool) return item.tool;
  if (item.type === 'tool_result' && item.tool) return `${item.tool} 结果`;
  return (
    item.title ||
    item.tool ||
    {
      text: 'Agent 输出',
      tool_call: '工具调用',
      tool_result: '工具结果',
      command: '命令',
      permission: '等待审批',
      summary: '运行总结',
      error: '执行错误',
      diff: '文件变更',
      task_context: '任务上下文',
    }[item.type] ||
    item.type
  );
}

function commandOutput(item: AgentSessionUiTimelineItem): string {
  const payload = item.payload;
  const stdout = payloadText(payload, 'stdout');
  const stderr = payloadText(payload, 'stderr');
  const failure = payloadText(payload, 'failure_summary');
  return [stdout, stderr, failure].filter(Boolean).join('\n').trim();
}

function changedFiles(item: AgentSessionUiTimelineItem): string[] {
  const files = item.payload?.changed_files;
  if (!Array.isArray(files)) return [];
  return files.map((file) => String(file)).filter(Boolean);
}

function TimelineMeta({ item }: { item: AgentSessionUiTimelineItem }) {
  const files = changedFiles(item);
  if (item.type === 'diff' || files.length > 0) {
    return (
      <div className={styles.timelineMetaRow}>
        <span>
          <FileDoneOutlined /> {files.length || 1} 个文件已更改
        </span>
        {item.payload?.additions || item.payload?.deletions ? (
          <span>
            +{String(item.payload?.additions || 0)} -{String(item.payload?.deletions || 0)}
          </span>
        ) : null}
      </div>
    );
  }
  if (item.type === 'tool_call' || item.type === 'tool_result') {
    return (
      <div className={styles.timelineMetaRow}>
        <span>
          <ToolOutlined /> {item.tool || '工具'}
        </span>
        {item.agent_name ? (
          <span>
            <BranchesOutlined /> {item.agent_name}
          </span>
        ) : null}
      </div>
    );
  }
  return null;
}

export function CommandCard({ item }: { item: AgentSessionUiTimelineItem }) {
  const [expanded, setExpanded] = useState(
    item.status !== 'completed' || Boolean(commandOutput(item)),
  );
  const command = stringifyCommand(item.payload?.command) || item.content || itemTitle(item);
  const output = commandOutput(item);
  const exitCode = item.payload?.exit_code;
  const duration = durationLabel(item.payload);
  const succeeded = exitCode === 0 || item.status === 'completed';
  const detailsId = `command-${item.id}`;
  return (
    <div className={styles.commandCard}>
      <button
        type="button"
        className={styles.executionHeader}
        aria-label={`${expanded ? '收起' : '展开'} Shell 命令 ${command}`}
        aria-expanded={expanded}
        aria-controls={detailsId}
        onClick={() => setExpanded((current) => !current)}
      >
        <span className={styles.executionChevron}>
          {expanded ? <DownOutlined /> : <RightOutlined />}
        </span>
        <CodeOutlined />
        <span className={styles.executionLabel}>Shell</span>
        <code title={command}>{command}</code>
        <span
          className={`${styles.executionStatus} ${succeeded ? styles.executionStatusSuccess : ''}`}
        >
          {item.status === 'running' ? (
            <LoadingOutlined spin />
          ) : succeeded ? (
            <CheckCircleOutlined />
          ) : null}
          {item.status === 'running' ? '运行中' : item.status === 'failed' ? '失败' : '完成'}
        </span>
      </button>
      {expanded ? (
        <motion.div
          className={styles.executionDetails}
          id={detailsId}
          initial={{ height: 0, opacity: 0 }}
          animate={{ height: 'auto', opacity: 1 }}
          exit={{ height: 0, opacity: 0 }}
          transition={{ duration: 0.18, ease: [0.23, 1, 0.32, 1] }}
        >
          {output ? (
            <pre>{output}</pre>
          ) : (
            <div className={styles.executionEmpty}>命令尚未产生输出</div>
          )}
          <div className={styles.executionFooter}>
            {typeof exitCode === 'number' ? (
              <span className={succeeded ? styles.commandSuccess : styles.commandFailure}>
                进程已退出，代码 {exitCode}
              </span>
            ) : (
              <span>{item.status === 'running' ? '进程正在运行' : '执行完成'}</span>
            )}
            {duration ? <span>{duration}</span> : null}
          </div>
        </motion.div>
      ) : null}
    </div>
  );
}

export function DiffCard({
  item,
  onOpenFile,
}: {
  item: AgentSessionUiTimelineItem;
  onOpenFile?: (filePath: string) => void;
}) {
  const files = changedFiles(item);
  const diff = payloadText(item.payload, 'diff') || item.content || '';
  const [expanded, setExpanded] = useState(Boolean(files.length || diff));
  const additions = Number(item.payload?.additions || 0);
  const deletions = Number(item.payload?.deletions || 0);
  const detailsId = `diff-${item.id}`;
  return (
    <div className={styles.diffSummaryCard}>
      <button
        type="button"
        className={styles.executionHeader}
        aria-label={`${expanded ? '收起' : '展开'} ${files.length ? `${files.length} 个文件变更` : '文件变更'}`}
        aria-expanded={expanded}
        aria-controls={detailsId}
        onClick={() => setExpanded((current) => !current)}
      >
        <span className={styles.executionChevron}>
          {expanded ? <DownOutlined /> : <RightOutlined />}
        </span>
        <FileDoneOutlined />
        <span className={styles.executionLabel}>
          {files.length ? `编辑了 ${files.length} 个文件` : '文件已更新'}
        </span>
        <span className={styles.diffStats}>
          {additions > 0 ? <span className={styles.diffAdditions}>+{additions}</span> : null}
          {deletions > 0 ? <span className={styles.diffDeletions}>-{deletions}</span> : null}
        </span>
      </button>
      {expanded ? (
        <motion.div
          className={styles.executionDetails}
          id={detailsId}
          initial={{ height: 0, opacity: 0 }}
          animate={{ height: 'auto', opacity: 1 }}
          exit={{ height: 0, opacity: 0 }}
          transition={{ duration: 0.18, ease: [0.23, 1, 0.32, 1] }}
        >
          {files.length > 0 ? (
            <ul>
              {files.slice(0, 5).map((file) => (
                <li key={file}>
                  <FileTextOutlined />
                  {onOpenFile ? (
                    <button
                      type="button"
                      className={styles.diffFileName}
                      title={`在文件面板打开 ${file}`}
                      onClick={() => onOpenFile(file)}
                    >
                      {file}
                    </button>
                  ) : (
                    <span>{file}</span>
                  )}
                </li>
              ))}
              {files.length > 5 ? (
                <li className={styles.moreFiles}>还有 {files.length - 5} 个文件</li>
              ) : null}
            </ul>
          ) : null}
          {diff ? <pre>{diff}</pre> : null}
        </motion.div>
      ) : null}
    </div>
  );
}

function PayloadPreview({ item }: { item: AgentSessionUiTimelineItem }) {
  if (!item.payload || !isRecord(item.payload)) return null;
  const usefulPayload = { ...item.payload };
  delete usefulPayload.stdout;
  delete usefulPayload.stderr;
  delete usefulPayload.failure_summary;
  delete usefulPayload.diff;
  delete usefulPayload.changed_files;
  delete usefulPayload.command;
  if (Object.keys(usefulPayload).length === 0) return null;
  return <pre className={styles.timelinePayload}>{JSON.stringify(usefulPayload, null, 2)}</pre>;
}

interface AgentRunTimelineProps {
  timeline: AgentSessionUiTimelineItem[];
  pendingLabel?: string;
  errorMessage?: string | null;
  /** 运行时活动摘要，用于空窗态反馈 */
  activity?: { label: string; detail?: string; startedAt: number } | null;
  /** 会话切换中，显示加载态而非空态 */
  loading?: boolean;
  /** 当前待审批权限请求，用于 timeline 内联审批 */
  pendingPermission?: AgentSessionUiPendingPermission | null;
  /** 审批决策回调 */
  onDecidePermission?: (partId: string, decisions: AgentHitlDecision[]) => void;
  /** 审批是否正在提交中（对应 operation key permission:partId） */
  permissionBusy?: boolean;
  /** 点击 diff 文件名时跳转到文件面板 */
  onOpenFile?: (filePath: string) => void;
}

export function TimelineContent({
  content,
  collapsible = true,
  streaming = false,
}: {
  content: string;
  collapsible?: boolean;
  streaming?: boolean;
}) {
  const [expanded, setExpanded] = useState(false);
  const canCollapse = collapsible && !streaming && (content.length > 600 || content.split('\n').length > 10);
  return (
    <>
      <div
        className={`${styles.timelineContent} ${canCollapse && !expanded ? styles.timelineContentCollapsed : ''}`}
      >
        <AgentMarkdown content={content} streaming={streaming} />
      </div>
      {canCollapse ? (
        <Button
          className={styles.timelineExpand}
          type="link"
          size="small"
          icon={expanded ? <UpOutlined /> : <DownOutlined />}
          onClick={() => setExpanded((current) => !current)}
        >
          {expanded ? '收起' : '展开'}
        </Button>
      ) : null}
    </>
  );
}

function compactValue(value: unknown): string {
  if (typeof value === 'string') return value.trim();
  if (Array.isArray(value)) return value.map((entry) => String(entry)).join(' ');
  if (!isRecord(value)) return '';
  for (const key of ['command', 'file_path', 'path', 'query', 'pattern']) {
    const candidate = value[key];
    if (typeof candidate === 'string' && candidate.trim()) return candidate.trim();
    if (Array.isArray(candidate)) return candidate.map((entry) => String(entry)).join(' ');
  }
  const serialized = JSON.stringify(value);
  return serialized.length > 110 ? `${serialized.slice(0, 107)}…` : serialized;
}

function trainingFieldEntries(item: AgentSessionUiTimelineItem): Array<[string, string]> {
  if (!isTrainingToolName(item.tool || item.title)) return [];
  const values: Record<string, unknown> = {};
  const input = isRecord(item.payload?.input) ? item.payload.input : {};
  const config = isRecord(input.training_config) ? input.training_config : {};
  for (const key of ['model_id', 'dataset_id', 'proposal_id', 'task_id', 'status']) {
    if (typeof input[key] === 'string') values[key] = input[key];
    if (typeof config[key] === 'string') values[key] = config[key];
  }
  try {
    const result = item.content ? JSON.parse(item.content) : null;
    if (isRecord(result)) {
      for (const key of ['model_id', 'dataset_id', 'proposal_id', 'task_id', 'status']) {
        if (typeof result[key] === 'string') values[key] = result[key];
      }
    }
  } catch {
    // Training content is already filtered by selectors; there is no fallback raw display.
  }
  return [
    ['模型', String(values.model_id || '')],
    ['数据集', String(values.dataset_id || '')],
    ['提案', String(values.proposal_id || '')],
    ['任务', String(values.task_id || '')],
    ['状态', String(values.status || '')],
  ].filter((entry): entry is [string, string] => Boolean(entry[1]));
}

function executionLabel(item: AgentSessionUiTimelineItem): string {
  const command = stringifyCommand(item.payload?.command);
  if (command) return command;
  const tool = item.tool || item.title || '工具';
  const trainingFields = trainingFieldEntries(item);
  if (trainingFields.length > 0) {
    return `${tool} · ${trainingFields.map(([label, value]) => `${label}=${value}`).join(' · ')}`;
  }
  const input = compactValue(item.payload?.input || item.payload?.args);
  return input ? `${tool} ${input}` : tool;
}

function executionFailed(item: AgentSessionUiTimelineItem): boolean {
  if (item.status === 'failed' || item.status === 'blocked') return true;
  const exitCode = item.payload?.exit_code;
  if (typeof exitCode === 'number' && exitCode !== 0) return true;
  const content = String(item.content || '')
    .trim()
    .toLowerCase();
  return (
    content.startsWith('error:') ||
    content.startsWith('failed:') ||
    content.includes('permission denied')
  );
}

export function ExecutionGroup({ items }: { items: AgentSessionUiTimelineItem[] }) {
  const failureCount = items.filter(executionFailed).length;
  const running = items.some((item) => item.status === 'running' || item.status === 'pending');
  const [expanded, setExpanded] = useState(failureCount > 0);
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    if (!running) return;
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [running]);
  const detailsId = `execution-group-${items.map((item) => item.id).join('-')}`;
  const summary = running
    ? `正在运行 ${items.length} 条命令`
    : failureCount > 0
      ? `已运行 ${items.length} 条命令 · ${failureCount} 条失败`
      : `已运行 ${items.length} 条命令`;

  return (
    <section className={styles.executionGroup} aria-label={summary}>
      <button
        type="button"
        className={styles.executionGroupToggle}
        aria-label={summary}
        aria-expanded={expanded}
        aria-controls={detailsId}
        onClick={() => setExpanded((current) => !current)}
      >
        <CodeOutlined />
        <span>{summary}</span>
        {running ? <LoadingOutlined spin /> : expanded ? <UpOutlined /> : <DownOutlined />}
      </button>
      {expanded ? (
        <motion.div
          className={styles.executionGroupDetails}
          id={detailsId}
          initial={{ height: 0, opacity: 0 }}
          animate={{ height: 'auto', opacity: 1 }}
          exit={{ height: 0, opacity: 0 }}
          transition={{ duration: 0.18, ease: [0.23, 1, 0.32, 1] }}
        >
          {items.map((item) => {
            const failed = executionFailed(item);
            const active = item.status === 'running' || item.status === 'pending';
            return (
              <div
                className={styles.executionGroupItem}
                key={item.id}
                data-status={failed ? 'failed' : active ? 'running' : 'completed'}
              >
                <span className={styles.executionGroupStatus} aria-hidden="true">
                  {active ? (
                    <LoadingOutlined spin />
                  ) : failed ? (
                    <ExclamationCircleOutlined />
                  ) : (
                    <CheckCircleOutlined />
                  )}
                </span>
                <span className={styles.executionGroupVerb}>
                  {active ? '正在运行' : failed ? '运行失败' : '已运行'}
                </span>
                <code title={executionLabel(item)}>{executionLabel(item)}</code>
                {trainingFieldEntries(item).length > 0 ? (
                  <div className={styles.timelineMetaRow}>
                    {trainingFieldEntries(item).map(([label, value]) => <span key={label}>{label}：{value}</span>)}
                  </div>
                ) : null}
                {active ? (
                  liveElapsed(item, now) ? (
                    <span className={styles.executionGroupDuration}>{liveElapsed(item, now)}</span>
                  ) : null
                ) : (
                  durationLabel(item.payload) ? (
                    <span className={styles.executionGroupDuration}>{durationLabel(item.payload)}</span>
                  ) : null
                )}
                {failed ? (
                  <div className={styles.executionGroupFailure}>
                    {item.content ? <span className={styles.executionGroupError}>{item.content}</span> : null}
                    {typeof item.payload?.exit_code === 'number' && item.payload.exit_code !== 0 ? (
                      <span className={styles.executionGroupExitCode}>退出码 {item.payload.exit_code}</span>
                    ) : null}
                    {typeof item.payload?.failure_summary === 'string' && item.payload.failure_summary.trim() ? (
                      <span className={styles.executionGroupFailureSummary}>{item.payload.failure_summary.trim()}</span>
                    ) : null}
                  </div>
                ) : null}
              </div>
            );
          })}
        </motion.div>
      ) : null}
    </section>
  );
}

function PermissionInlineCard({
  item,
  permission,
  onDecide,
  busy,
}: {
  item: AgentSessionUiTimelineItem;
  permission: AgentSessionUiPendingPermission;
  onDecide: (partId: string, decisions: AgentHitlDecision[]) => void;
  busy?: boolean;
}) {
  const partId = permission.part_id || item.part_id || item.id;
  const actions = permission.actions || [];
  const [decided, setDecided] = useState<'approve' | 'reject' | null>(null);
  const handleDecide = (type: 'approve' | 'reject') => {
    if (busy || decided) return;
    setDecided(type);
    onDecide(partId, Array.from({ length: Math.max(1, actions.length) }, () => (
      type === 'approve'
        ? { type: 'approve' as const }
        : { type: 'reject' as const, message: '已在工作台拒绝' }
    )));
  };
  return (
    <div className={styles.permissionInline}>
      <div className={styles.permissionInlineHeader}>
        <SafetyCertificateOutlined />
        <strong>{decided ? (decided === 'approve' ? '已批准' : '已拒绝') : '等待审批'}</strong>
        <span>{permission.title || item.title || '工具执行前需要确认'}</span>
      </div>
      {decided ? (
        <p className={styles.permissionInlineContent}>
          {decided === 'approve' ? '已提交批准，Agent 正在继续执行...' : '已提交拒绝，Agent 将根据策略处理...'}
        </p>
      ) : (
        <>
          {permission.content ? <p className={styles.permissionInlineContent}>{permission.content}</p> : null}
          {actions.length > 0 ? (
            <div className={styles.permissionInlineActions}>
              {actions.map((action) => (
                <div key={action.index} className={styles.permissionInlineAction}>
                  <code>{action.name}</code>
                  {action.description ? <small>{action.description}</small> : null}
                </div>
              ))}
            </div>
          ) : null}
          <div className={styles.permissionInlineButtons}>
            <Button
              size="small"
              type="primary"
              loading={busy && decided === 'approve'}
              disabled={busy}
              onClick={() => handleDecide('approve')}
            >
              批准
            </Button>
            <Button
              size="small"
              danger
              loading={busy && decided === 'reject'}
              disabled={busy}
              onClick={() => handleDecide('reject')}
            >
              拒绝
            </Button>
          </div>
        </>
      )}
    </div>
  );
}

export function TimelineItem({
  item,
  pendingPermission,
  onDecidePermission,
  permissionBusy,
  onOpenFile,
}: {
  item: AgentSessionUiTimelineItem;
  pendingPermission?: AgentSessionUiPendingPermission | null;
  onDecidePermission?: (partId: string, decisions: AgentHitlDecision[]) => void;
  permissionBusy?: boolean;
  onOpenFile?: (filePath: string) => void;
}) {
  const trainingActivity = selectTrainingActivity(item);
  const modelResponse = isModelResponse(item);
  const isStreaming = modelResponse && (item.status === 'running' || item.status === 'pending'
    || Boolean(item.payload?.streaming));
  const classNames = [
    styles.timelineItem,
    styles[`timeline_${item.status || 'default'}`] || '',
    isUserMessage(item) ? styles.timelineUserMessage : '',
    modelResponse ? styles.timelineModelResponse : '',
    ['tool_call', 'tool_result'].includes(item.type) ? styles.timelineToolActivity : '',
    trainingActivity ? styles.timelineTrainingActivity : '',
  ]
    .filter(Boolean)
    .join(' ');

  return (
    <article className={classNames}>
      <div className={styles.timelineIcon}>{itemIcon(item)}</div>
      <div className={styles.timelineBody}>
        {trainingActivity ? (
          <AgentTrainingActivity activity={trainingActivity} />
        ) : item.type === 'permission' && pendingPermission && onDecidePermission ? (
          <PermissionInlineCard
            item={item}
            permission={pendingPermission}
            onDecide={onDecidePermission}
            busy={permissionBusy}
          />
        ) : item.type === 'command' ? (
          <ExecutionGroup items={[item]} />
        ) : item.type === 'diff' ? (
          <DiffCard item={item} onOpenFile={onOpenFile} />
        ) : item.type === 'tool_call' || item.type === 'tool_result' ? (
          <ExecutionGroup items={[item]} />
        ) : (
          <>
            {!modelResponse ? (
              <div className={styles.timelineHeading}>
                <strong>{itemTitle(item)}</strong>
                {shouldShowStatus(item) ? <span>{statusLabel(item)}</span> : null}
              </div>
            ) : null}
            <TimelineMeta item={item} />
            {item.content ? (
              <TimelineContent
                content={item.content}
                collapsible={!modelResponse && !isUserMessage(item)}
                streaming={isStreaming}
              />
            ) : null}
            {!modelResponse && !item.content && item.payload ? (
              <PayloadPreview item={item} />
            ) : null}
            {modelResponse && item.content ? (
              <div className={styles.responseActions} aria-label="回答操作">
                <CopyResponseButton content={item.content} />
              </div>
            ) : null}
          </>
        )}
      </div>
    </article>
  );
}

export default function AgentRunTimeline({
  timeline,
  pendingLabel,
  errorMessage,
  activity,
  loading,
  pendingPermission,
  onDecidePermission,
  permissionBusy,
  onOpenFile,
}: AgentRunTimelineProps) {
  const [query, setQuery] = useState('');
  const [filter, setFilter] = useState<'all' | 'output' | 'tools' | 'issues'>('all');
  const [autoFollow, setAutoFollow] = useState(true);
  const [showJumpToLatest, setShowJumpToLatest] = useState(false);
  const virtuosoRef = useRef<VirtuosoHandle>(null);
  const deferredQuery = useDeferredValue(query.trim().toLowerCase());
  const visibleTimeline = useMemo(
    () =>
      timeline.filter((item) => {
        if (filter === 'output' && !['text', 'summary'].includes(item.type)) return false;
        if (
          filter === 'tools' &&
          !['tool_call', 'tool_result', 'command', 'diff'].includes(item.type)
        )
          return false;
        if (
          filter === 'issues' &&
          !['failed', 'blocked'].includes(item.status || '') &&
          item.type !== 'error' &&
          item.type !== 'permission'
        ) {
          return false;
        }
        if (!deferredQuery) return true;
        const haystack = [
          itemTitle(item),
          item.content,
          item.tool,
          JSON.stringify(item.payload || {}),
        ]
          .join(' ')
          .toLowerCase();
        return haystack.includes(deferredQuery);
      }),
    [deferredQuery, filter, timeline],
  );
  const hasLiveItems = useMemo(
    () => visibleTimeline.some((item) => item.status === 'running' || item.status === 'pending'),
    [visibleTimeline],
  );
  const displayTimeline = useMemo(() => groupExecutionItems(visibleTimeline), [visibleTimeline]);
  const initialTimelineIndex = useMemo(() => {
    if (hasLiveItems) return Math.max(0, displayTimeline.length - 1);
    for (let index = displayTimeline.length - 1; index >= 0; index -= 1) {
      const entry = displayTimeline[index]!;
      if (!isExecutionGroup(entry) && isModelResponse(entry)) return index;
    }
    return Math.max(0, displayTimeline.length - 1);
  }, [displayTimeline, hasLiveItems]);

  if (timeline.length === 0) {
    return (
      <div className={styles.timelineEmpty}>
        {activity ? (
          <div className={styles.timelineEmptyActivity}>
            <LoadingOutlined spin />
            <span>{activity.label}{activity.detail ? ` · ${activity.detail}` : ''}</span>
          </div>
        ) : loading ? (
          <div className={styles.timelineEmptyActivity}>
            <LoadingOutlined spin />
            <span>正在加载会话...</span>
          </div>
        ) : pendingLabel ? (
          <Alert
            type="info"
            showIcon
            message={pendingLabel}
            description="正在把任务交给后端排队。若网络或服务异常，草稿会自动恢复，你可以直接重试。"
          />
        ) : errorMessage ? (
          <Alert
            type="warning"
            showIcon
            message="任务没有成功提交"
            description={`${errorMessage} 下方输入框已恢复你的内容，检查服务状态后可再次发送。`}
          />
        ) : (
          <Empty
            image={Empty.PRESENTED_IMAGE_SIMPLE}
            description="提交任务后，执行过程会显示在这里"
          />
        )}
      </div>
    );
  }

  return (
    <div className={styles.timeline} aria-label="Agent 执行时间线">
      <div className={styles.timelineToolbar}>
        <Input.Search
          allowClear
          size="small"
          value={query}
          placeholder="搜索执行记录"
          aria-label="搜索执行时间线"
          onChange={(event) => setQuery(event.target.value)}
        />
        <Segmented
          size="small"
          value={filter}
          onChange={(value) => setFilter(value as typeof filter)}
          options={[
            { value: 'all', label: '全部' },
            { value: 'output', label: '输出' },
            { value: 'tools', label: '工具' },
            { value: 'issues', label: '异常' },
          ]}
        />
        <label className={styles.followToggle}>
          <Switch size="small" checked={autoFollow} onChange={setAutoFollow} />
          <span>跟随</span>
        </label>
        <span className={styles.timelineCount}>
          {visibleTimeline.length}/{timeline.length}
        </span>
      </div>
      {visibleTimeline.length === 0 ? (
        <div className={styles.timelineEmpty}>
          <Empty description="没有匹配的执行记录" />
        </div>
      ) : (
        <div className={styles.timelineScrollArea}>
          <Virtuoso
            ref={virtuosoRef}
            data={displayTimeline}
            followOutput={autoFollow ? 'smooth' : false}
            initialTopMostItemIndex={initialTimelineIndex}
            atBottomStateChange={(atBottom) => {
              setShowJumpToLatest(!atBottom);
              if (atBottom && !autoFollow) setAutoFollow(true);
            }}
            itemContent={(_, entry) =>
              isExecutionGroup(entry) ? (
                <motion.div
                  className={styles.timelineExecutionGroup}
                  initial={{ opacity: 0, y: 6 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.12 }}
                >
                  <ExecutionGroup items={entry.items} />
                </motion.div>
              ) : (
                <motion.div initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.12 }}>
                  <TimelineItem
                    item={entry}
                    pendingPermission={pendingPermission}
                    onDecidePermission={onDecidePermission}
                    permissionBusy={permissionBusy}
                    onOpenFile={onOpenFile}
                  />
                </motion.div>
              )
            }
          />
          {showJumpToLatest ? (
            <button
              type="button"
              className={styles.jumpToLatest}
              aria-label="回到最新"
              onClick={() => {
                virtuosoRef.current?.scrollToIndex({
                  index: displayTimeline.length - 1,
                  behavior: 'smooth',
                });
                setAutoFollow(true);
                setShowJumpToLatest(false);
              }}
            >
              <DownOutlined /> 回到最新
            </button>
          ) : null}
        </div>
      )}
    </div>
  );
}
