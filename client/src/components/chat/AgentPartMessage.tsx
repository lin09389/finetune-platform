import {
  CheckCircleOutlined,
  CodeOutlined,
  EditOutlined,
  ExclamationCircleOutlined,
  EyeOutlined,
  FileTextOutlined,
  LinkOutlined,
  PlayCircleOutlined,
  ReloadOutlined,
  SearchOutlined,
} from '@ant-design/icons';
import { Button, Collapse, Progress, Space, Tag, Typography } from 'antd';
import React, { type ReactNode } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import rehypeSanitize from 'rehype-sanitize';
import type { AgentPart } from '../../services/api';
import type { ChatAgentMetadata } from '../../types';
import AgentTerminal from './AgentTerminal';
import styles from './AgentPartMessage.module.css';

interface AgentPartMessageProps {
  content: string;
  metadata: ChatAgentMetadata;
  onRefreshRun?: (runId: string) => void | Promise<void>;
  onOpenAsyncTask?: (taskId: string, childSessionId?: string, options?: { expandDetail?: boolean }) => void;
}

const SILENT_TOOLS = new Set([
  'read', 'read_file', 'search', 'search_code', 'glob', 'list_files',
  'collect_context', 'inspect_project', 'detect_project_commands',
  'read_execution', 'read_execution_result', 'summarize_test_results',
  'collect_test_failures', 'http_probe', 'get_server_status',
]);

const statusLabel: Record<string, string> = {
  pending: '等待确认',
  running: '进行中',
  completed: '完成',
  failed: '失败',
  blocked: '已阻断',
  approved: '已批准',
  executed: '已执行',
};

const statusColor: Record<string, string> = {
  pending: 'gold',
  running: 'processing',
  completed: 'success',
  failed: 'error',
  blocked: 'warning',
  approved: 'blue',
  executed: 'success',
};

function stringify(value: unknown) {
  if (value === undefined || value === null || value === '') return '';
  if (typeof value === 'string') return value;
  return JSON.stringify(value, null, 2);
}

function agentLabel(value?: unknown) {
  const raw = typeof value === 'string' ? value.trim() : '';
  if (!raw) return '';
  return raw
    .split(/[-_\s]+/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ');
}

function commandText(payload?: Record<string, any>) {
  const command = payload?.command || payload?.payload?.command;
  return Array.isArray(command) ? command.join(' ') : stringify(command);
}

function contextStats(payload?: Record<string, any>) {
  const source = payload?.payload && typeof payload.payload === 'object' ? { ...payload, ...payload.payload } : payload || {};
  return {
    files: Array.isArray(source.files) ? source.files.length : 0,
    matches: Array.isArray(source.matches) ? source.matches.length : 0,
    symbols: Array.isArray(source.symbols) ? source.symbols.length : 0,
    commands: Array.isArray(source.commands) ? source.commands.length : 0,
  };
}

function changedFiles(payload?: Record<string, any>) {
  const files = payload?.changed_files || payload?.payload?.changed_files || payload?.files || payload?.payload?.files || [];
  if (!Array.isArray(files)) return [];
  return files.map((item: any) => (typeof item === 'string' ? item : item?.path || item?.file_path)).filter(Boolean);
}

function normalizeFileStatus(value?: string) {
  const status = (value || '').toLowerCase();
  if (['add', 'added', 'create', 'created', 'new'].includes(status)) return '新增';
  if (['modify', 'modified', 'update', 'updated', 'change', 'changed'].includes(status)) return '修改';
  if (['delete', 'deleted', 'remove', 'removed'].includes(status)) return '删除';
  if (['rename', 'renamed', 'move', 'moved'].includes(status)) return '重命名';
  if (status) return status;
  return '变更';
}

function extractFileDiffs(payload?: Record<string, any>) {
  const source =
    payload?.changed_files_detail ||
    payload?.payload?.changed_files_detail ||
    payload?.file_changes ||
    payload?.payload?.file_changes ||
    payload?.diff_entries ||
    payload?.payload?.diff_entries ||
    payload?.diff ||
    payload?.payload?.diff;

  if (Array.isArray(source)) {
    return source
      .map((item: any) => ({
        path: item?.path || item?.file_path || item?.filename || item?.name || item?.old_path || item?.new_path || '',
        status: item?.status || item?.change_type || item?.action || item?.type || '',
        summary: item?.summary || item?.description || item?.message || '',
        diff: item?.diff || item?.patch || item?.content || item?.after || item?.before || '',
      }))
      .filter((item) => item.path || item.summary || item.diff);
  }

  if (typeof source === 'string') {
    return [{ path: '', status: '', summary: '', diff: source }];
  }

  return [];
}

function diffPreview(payload?: Record<string, any>) {
  if (!payload) return '';
  if (payload.diff) return stringify(payload.diff);
  if (payload.payload?.diff) return stringify(payload.payload.diff);
  const files = payload.payload?.files || payload.files;
  if (Array.isArray(files)) {
    return files.map((file: any) => `${file.path || file.file_path || 'unknown'}\n${file.content || ''}`).join('\n\n');
  }
  return stringify(payload.payload || payload);
}

function partTitle(part: AgentPart, fallback: string) {
  if (part.type === 'tool_call') return part.content || part.title || '执行工具';
  if (part.type === 'tool_result') return part.content || part.title || '工具结果';
  if (part.type === 'diff') return part.title || '文件修改';
  if (part.type === 'command') return commandText(part.payload) || part.title || '验证命令';
  if (part.type === 'summary') return part.content || fallback;
  return part.content || part.title || fallback;
}

function toolEventText(part: AgentPart, payload?: Record<string, any>) {
  const stats = contextStats(payload);
  const command = commandText(payload);
  const toolName = stringify(payload?.tool || payload?.name || payload?.payload?.tool);
  const chips: string[] = [];
  if (stats.files) chips.push(`读取 ${stats.files} 个文件`);
  if (stats.matches) chips.push(`找到 ${stats.matches} 条匹配`);
  if (stats.symbols) chips.push(`命中 ${stats.symbols} 个符号`);
  if (stats.commands) chips.push(`识别 ${stats.commands} 个验证命令`);
  if (command) chips.push(command);
  if (!chips.length && part.content) chips.push(part.content);
  if (chips.length) return chips.slice(0, 2).join('，');
  return partTitle(part, toolName || '工具');
}

function toolEventIcon(toolName?: string) {
  const name = (toolName || '').toLowerCase();
  if (name.includes('search') || name === 'glob' || name === 'list_files') return <SearchOutlined />;
  if (name.includes('read') || name.includes('context') || name.includes('inspect')) return <FileTextOutlined />;
  if (name.includes('test') || name.includes('execution')) return <PlayCircleOutlined />;
  return <CodeOutlined />;
}

function fileEditLabel(part: AgentPart, payload?: Record<string, any>) {
  const files = changedFiles(payload);
  const fileLabel = files.length === 1
    ? files[0]
    : files.length > 1
      ? `${files.length} 个文件`
      : part.title || '文件';
  const additions = Number(payload?.additions ?? payload?.payload?.additions ?? payload?.added_lines ?? 0);
  const deletions = Number(payload?.deletions ?? payload?.payload?.deletions ?? payload?.removed_lines ?? 0);
  return { fileLabel, additions, deletions };
}

function commandStatusText(part: AgentPart, payload?: Record<string, any>) {
  const command = commandText(payload);
  if (command) return command;
  const count = Number(payload?.commands_count ?? payload?.payload?.commands_count ?? 0);
  if (count > 0) return `${count} 条命令`;
  return part.title || part.content || '命令';
}

function TranscriptStatusLine({
  icon,
  children,
}: {
  icon: ReactNode;
  children: ReactNode;
}) {
  return (
    <div className={styles.transcriptStatusLine}>
      <span className={styles.transcriptStatusIcon}>{icon}</span>
      <span className={styles.transcriptStatusText}>{children}</span>
    </div>
  );
}

function looksLikeProtocolText(value?: string) {
  const text = (value || '').trim();
  if (!text) return false;
  if (text.startsWith('{') && /"tool"\s*:/.test(text)) return true;
  if (text.startsWith('```') && /"tool"\s*:/.test(text)) return true;
  if (text.startsWith('[') && /"tool"\s*:/.test(text)) return true;
  return false;
}

function stripProtocolBlocks(value?: string) {
  const text = value || '';
  return text
    .replace(/```(?:json)?\s*[\s\S]*?"tool"\s*:[\s\S]*?```/gi, '')
    .replace(/(^|\n)\s*\{[\s\S]*?"tool"\s*:[\s\S]*?\}\s*$/gi, '$1')
    .trim();
}

const markdownComponents = {
  a: ({ children, href }: any) => (
    <a href={href} className={styles.fileLink} target={href?.startsWith('http') ? '_blank' : undefined} rel="noreferrer">
      {children}
    </a>
  ),
  code: ({ inline, children }: any) => {
    if (inline) {
      return <code className={styles.inlineCode}>{children}</code>;
    }
    return (
      <pre className={styles.codeBlock}>
        <code>{String(children).replace(/\n$/, '')}</code>
      </pre>
    );
  },
  p: ({ children }: any) => <p className={styles.paragraph}>{children}</p>,
  ul: ({ children }: any) => <ul className={styles.list}>{children}</ul>,
  ol: ({ children }: any) => <ol className={styles.list}>{children}</ol>,
  li: ({ children }: any) => <li className={styles.listItem}>{children}</li>,
  strong: ({ children }: any) => <strong className={styles.strong}>{children}</strong>,
};

function MarkdownBody({ children }: { children: string }) {
  return (
    <div className={styles.readableMarkdown}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        rehypePlugins={[rehypeSanitize]}
        components={markdownComponents}
      >
        {children}
      </ReactMarkdown>
    </div>
  );
}

const AgentPartMessage = React.memo(({
  content,
  metadata,
  onRefreshRun,
  onOpenAsyncTask,
}: AgentPartMessageProps) => {
  const part = metadata.agent_part as AgentPart | undefined;
  if (!part) {
    return <Typography.Paragraph style={{ margin: 0 }}>{content}</Typography.Paragraph>;
  }

  const payload = part.payload || {};
  const diagnostics = metadata.agent_session_diagnostics;
  const status = part.status || metadata.status || 'completed';
  const subagentLabel = agentLabel(payload.agent_name);
  const subagentBadge = subagentLabel ? <Tag className={styles.subagentTag}>{subagentLabel}</Tag> : null;
  const isAsyncSubagentSummary = payload.agent_role === 'async_subagent';
  const asyncTaskId = typeof payload.task_id === 'string' ? payload.task_id : '';
  const asyncChildSessionId = typeof payload.child_session_id === 'string' ? payload.child_session_id : undefined;
  const childStatus = typeof payload.child_status === 'string' ? payload.child_status : '';
  const hasPendingPermission = payload.has_pending_permission === true;
  const asyncNeedsAttention = hasPendingPermission || childStatus === 'waiting_permission' || childStatus === 'waiting_approval';
  const files = changedFiles(payload);
  const diffItems = extractFileDiffs(payload);
  const canApprove = false;
  const canExecute = false;
  const isProblem = ['failed', 'blocked'].includes(status);
  const icon =
    part.type === 'tool_call' || part.type === 'tool_result' ? (
      <SearchOutlined />
    ) : part.type === 'diff' ? (
      <CodeOutlined />
    ) : part.type === 'command' ? (
      <PlayCircleOutlined />
    ) : part.type === 'summary' ? (
      <CheckCircleOutlined />
    ) : isProblem ? (
      <ExclamationCircleOutlined />
    ) : (
      <FileTextOutlined />
    );

  const shouldShowDiagnostics =
    Boolean(diagnostics?.stop_reason) &&
    (part.type === 'summary' || isProblem || canApprove || canExecute || status === 'pending' || status === 'blocked' || status === 'failed');
  const diagnosticBlock = shouldShowDiagnostics ? (
    <Space direction="vertical" size={2} style={{ width: '100%' }}>
      <Typography.Text type={isProblem || status === 'blocked' ? 'danger' : 'secondary'}>
        {diagnostics?.stop_reason}
      </Typography.Text>
      {diagnostics?.next_action && (
        <Typography.Text type="secondary">下一步：{diagnostics.next_action}</Typography.Text>
      )}
    </Space>
  ) : null;

  const shell = (body: ReactNode) => (
    <div
      style={{
        borderLeft: `3px solid ${isProblem ? 'var(--accent-warning, #faad14)' : 'var(--border-color, rgba(255,255,255,0.16))'}`,
        padding: '6px 0 6px 12px',
        margin: '2px 0',
      }}
    >
      {body}
    </div>
  );

  const renderDiffPanel = (title: string, preview: string, entry?: { path: string; status: string; diff: string; summary: string }) => {
    const changeRatio = preview ? Math.min(100, Math.max(20, preview.length / 18)) : 0;
    return (
      <div className={styles.diffPanel}>
        <div className={styles.diffPanelHeader}>
          <Space wrap size={6}>
            <CodeOutlined />
            <Typography.Text strong>{title}</Typography.Text>
            {entry?.path ? <Tag color="blue">{entry.path}</Tag> : null}
            {entry?.status ? <Tag>{normalizeFileStatus(entry.status)}</Tag> : null}
          </Space>
          {changeRatio > 0 ? <Progress percent={Math.min(100, Math.round(changeRatio))} showInfo={false} size="small" className={styles.diffProgress} /> : null}
        </div>
        {entry?.summary ? <Typography.Text type="secondary" className={styles.diffSummary}>{entry.summary}</Typography.Text> : null}
        {preview && <pre className={styles.diffPreview}>{preview}</pre>}
      </div>
    );
  };

  if (part.type === 'text') {
    const isStreaming = status === 'running' || (part.payload as Record<string, unknown>)?.streaming === true;
    const protocolOnly = Boolean((part.payload as Record<string, unknown>)?.protocol_only);
    const displayText = stripProtocolBlocks(part.content || content);
    if (protocolOnly || looksLikeProtocolText(displayText)) {
      if (!isStreaming) return null;
      return (
        <Space size={6} style={{ color: 'var(--text-secondary)' }}>
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 2 }}>
            <span className="typing-dot" />
            <span className="typing-dot" style={{ animationDelay: '0.2s' }} />
            <span className="typing-dot" style={{ animationDelay: '0.4s' }} />
          </span>
          <Typography.Text type="secondary">正在准备下一阶段</Typography.Text>
        </Space>
      );
    }

    return (
      <div className={styles.transcriptBlock}>
        <MarkdownBody>{displayText}</MarkdownBody>
        {isStreaming && <span className={styles.streamingCursor} />}
      </div>
    );
  }

  if (part.type === 'summary') {
    return (
      <div className={styles.transcriptBlock}>
        {isAsyncSubagentSummary ? (
          <TranscriptStatusLine icon={<CheckCircleOutlined />}>
            已完成 {subagentLabel || '子任务'}
          </TranscriptStatusLine>
        ) : null}
        {isAsyncSubagentSummary && (
          <div className={styles.asyncTaskMetaRow}>
            {asyncTaskId ? <span>任务 {asyncTaskId}</span> : null}
            {asyncChildSessionId ? <span>子会话 {asyncChildSessionId}</span> : null}
            {subagentLabel ? <span>{subagentLabel}</span> : null}
            <div className={styles.asyncTaskActions}>
              {onOpenAsyncTask && asyncTaskId ? (
                <Button
                  size="small"
                  type={asyncNeedsAttention ? 'primary' : 'default'}
                  icon={<EyeOutlined />}
                  onClick={() => onOpenAsyncTask(asyncTaskId, asyncChildSessionId, { expandDetail: true })}
                >
                  {asyncNeedsAttention ? '处理确认' : '查看任务'}
                </Button>
              ) : null}
            </div>
          </div>
        )}
        <MarkdownBody>{part.content || content}</MarkdownBody>
        {onRefreshRun && (
          <Button size="small" type="text" icon={<ReloadOutlined />} onClick={() => onRefreshRun(metadata.agent_run_id)}>
            刷新状态
          </Button>
        )}
      </div>
    );
  }

  if (part.type === 'diff') {
    const preview = diffPreview(payload);
    const entries = diffItems.length > 0 ? diffItems : files.map((file) => ({ path: file, status: '', diff: preview, summary: '' }));
    const stats = {
      total: entries.length || files.length,
      modified: entries.filter((item) => /修改|modify|change|update/i.test(item.status)).length,
      added: entries.filter((item) => /新增|add|create|new/i.test(item.status)).length,
      removed: entries.filter((item) => /删除|remove|delete/i.test(item.status)).length,
    };
    const { fileLabel, additions, deletions } = fileEditLabel(part, payload);
    return (
      <div className={styles.transcriptEventBlock}>
        <TranscriptStatusLine icon={<EditOutlined />}>
          {status === 'running' ? '正在编辑' : '已编辑'}{' '}
          <span className={styles.transcriptFileName}>{fileLabel}</span>
          {additions > 0 ? <span className={styles.transcriptAdd}> +{additions}</span> : null}
          {deletions > 0 ? <span className={styles.transcriptDel}> -{deletions}</span> : null}
        </TranscriptStatusLine>
        {payload.policy_reason && <Typography.Text type="secondary">{payload.policy_reason}</Typography.Text>}
        {diagnosticBlock}
        {(stats.total > 0 || files.length > 0) && (
          <div className={styles.transcriptDiffDetails}>
            <div className={styles.diffOverviewHeader}>
              <Typography.Text strong>变更文件</Typography.Text>
              <Typography.Text type="secondary" className={styles.diffOverviewMeta}>
                {stats.total} 个文件
                {stats.added ? ` · ${stats.added} 新增` : ''}
                {stats.modified ? ` · ${stats.modified} 修改` : ''}
                {stats.removed ? ` · ${stats.removed} 删除` : ''}
              </Typography.Text>
            </div>
            <div className={styles.diffFileGrid}>
              {entries.map((entry, index) => (
                <div key={`${entry.path || 'diff'}-${index}`} className={styles.diffFileCard}>
                  <div className={styles.diffFileCardTop}>
                    <Typography.Text className={styles.diffFilePath}>{entry.path || `变更 ${index + 1}`}</Typography.Text>
                    {entry.status ? <Tag className={styles.diffFileTag}>{normalizeFileStatus(entry.status)}</Tag> : <Tag className={styles.diffFileTag}>修改</Tag>}
                  </div>
                  {entry.summary ? <Typography.Text className={styles.diffFileSummary}>{entry.summary}</Typography.Text> : null}
                  <Collapse
                    ghost
                    size="small"
                    items={[{
                      key: `${entry.path || 'diff'}-${index}-preview`,
                      label: '代码预览',
                      children: renderDiffPanel(entry.path || `变更 ${index + 1}`, entry.diff || preview, entry),
                    }]}
                  />
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    );
  }

  if (part.type === 'command') {
    return (
      <div className={styles.transcriptEventBlock}>
        <TranscriptStatusLine icon={<PlayCircleOutlined />}>
          {status === 'running' ? '正在运行' : '已运行'} {commandStatusText(part, payload)}
          {payload.duration_ms ? `，已持续 ${Math.round(Number(payload.duration_ms) / 1000)}s` : ''}
        </TranscriptStatusLine>
        {payload.server_url && (
          <Space size={6}>
            <LinkOutlined />
            <Typography.Link href={payload.server_url} target="_blank" rel="noreferrer">
              {payload.server_url}
            </Typography.Link>
          </Space>
        )}
        {(part.content || payload.failure_summary || payload.policy_reason) && (
          <Typography.Text type={status === 'failed' ? 'danger' : 'secondary'}>
            {payload.failure_summary || part.content || payload.policy_reason}
          </Typography.Text>
        )}
        {diagnosticBlock}
        {payload.terminal_id && ['running', 'executed', 'failed'].includes(status) ? (
          <AgentTerminal
            terminalId={String(payload.terminal_id)}
            running={status === 'running'}
            stdout={payload.stdout}
            stderr={payload.stderr}
            exitCode={payload.exit_code}
          />
        ) : null}
        {!payload.terminal_id && (payload.stdout || payload.stderr || payload.exit_code !== undefined) && (
          <Collapse
            ghost
            size="small"
            items={[
              {
                key: 'output',
                label: '查看命令输出',
                children: (
                  <pre style={{ whiteSpace: 'pre-wrap', margin: 0 }}>
                    {`exit_code: ${payload.exit_code ?? ''}\n${payload.stdout || ''}${payload.stderr ? `\n${payload.stderr}` : ''}`}
                  </pre>
                ),
              },
            ]}
          />
        )}
      </div>
    );
  }

  if (part.type === 'error' || isProblem) {
    return shell(
      <Space direction="vertical" size={6}>
        <Space>
          {icon}
          <Typography.Text type="danger">{partTitle(part, content)}</Typography.Text>
          <Tag color={statusColor[status] || 'warning'}>{statusLabel[status] || status}</Tag>
        </Space>
        {payload.guidance && <Typography.Text type="secondary">{payload.guidance}</Typography.Text>}
        {diagnosticBlock}
      </Space>,
    );
  }

  if (part.type === 'permission') {
    const actionRequests = Array.isArray(payload.action_requests) ? payload.action_requests : [];
    const request = actionRequests[0] || {};
    const toolName = payload.tool || request.name || 'tool';
    const args = payload.args || request.args || {};
    return (
      <div className={styles.approvalInline} data-status={status}>
        <div className={styles.approvalHeader}>
          <span className={styles.approvalPulse} />
          <div className={styles.approvalCopy}>
            <Typography.Text strong>等待你确认</Typography.Text>
            {subagentBadge}
            <Typography.Text type="secondary">
              准备继续执行 <Typography.Text code>{String(toolName)}</Typography.Text>
            </Typography.Text>
          </div>
          <Tag color={statusColor[status] || 'warning'} className={styles.approvalStatusTag}>
            {statusLabel[status] || status}
          </Tag>
        </div>
        {Object.keys(args || {}).length > 0 ? (
          <Collapse
            ghost
            size="small"
            className={styles.approvalDetails}
            items={[{
              key: 'args',
              label: '参数',
              children: <pre style={{ whiteSpace: 'pre-wrap', margin: 0 }}>{stringify(args)}</pre>,
            }]}
          />
        ) : null}
        {diagnosticBlock}
        {canApprove && (
          <Typography.Text type="secondary">
            请在输入框上方的审批面板中提交本轮 HITL 决策。
          </Typography.Text>
        )}
      </div>
    );
  }

  if (part.type === 'tool_call' || part.type === 'tool_result') {
    const toolName = payload?.tool || '';
    if (SILENT_TOOLS.has(toolName) && !isProblem) {
      return (
        <div className={styles.transcriptEventBlock}>
          <TranscriptStatusLine icon={toolEventIcon(toolName)}>
            {part.type === 'tool_call' && status === 'running' ? '正在' : '已'}
            {toolName.includes('search') || toolName === 'glob' || toolName === 'list_files' ? '搜索网页' : '处理上下文'}
            {subagentLabel ? <span className={styles.transcriptSubagent}> {subagentLabel}</span> : null}
            {toolEventText(part, payload) ? `：${toolEventText(part, payload)}` : ''}
          </TranscriptStatusLine>
          {status === 'running' && (
            <span className={styles.transcriptTyping}>
              <span className="typing-dot" />
              <span className="typing-dot" style={{ animationDelay: '0.2s' }} />
              <span className="typing-dot" style={{ animationDelay: '0.4s' }} />
            </span>
          )}
        </div>
      );
    }

    return (
      <div className={styles.transcriptEventBlock}>
        <TranscriptStatusLine icon={toolEventIcon(toolName)}>
          {part.type === 'tool_call' && status === 'running' ? '正在运行' : '已运行'} {toolEventText(part, payload)}
          {subagentLabel ? <span className={styles.transcriptSubagent}> {subagentLabel}</span> : null}
        </TranscriptStatusLine>
        {diagnosticBlock}
        {payload.failure_summary && <Typography.Text type="danger">{payload.failure_summary}</Typography.Text>}
        {payload.server_url && (
          <Typography.Link href={payload.server_url} target="_blank" rel="noreferrer">
            {payload.server_url}
          </Typography.Link>
        )}
      </div>
    );
  }

  return shell(
    <Space direction="vertical" size={4} style={{ width: '100%' }}>
      <Space wrap>
        {icon}
        {subagentBadge}
        <Typography.Text>{partTitle(part, content)}</Typography.Text>
        {status !== 'completed' && <Tag color={statusColor[status] || 'default'}>{statusLabel[status] || status}</Tag>}
      </Space>
    </Space>,
  );
});

export default AgentPartMessage;
