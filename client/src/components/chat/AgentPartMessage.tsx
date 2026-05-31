import {
  CheckCircleOutlined,
  CodeOutlined,
  ExclamationCircleOutlined,
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

function asAgentParts(value: unknown): AgentPart[] {
  return Array.isArray(value) ? value.filter((item): item is AgentPart => Boolean(item && typeof item === 'object' && 'type' in item)) : [];
}

function processStats(parts: AgentPart[]) {
  const actionable = parts.filter((item) => ['diff', 'command', 'permission'].includes(item.type));
  const approved = actionable.filter((item) => ['approved', 'executed', 'completed'].includes(item.status || '')).length;
  const commands = parts.filter((item) => item.type === 'command' && ['completed', 'executed'].includes(item.status || '')).length;
  const patches = parts.filter((item) => item.type === 'diff' && item.status === 'executed').length;
  const pending = actionable.filter((item) => item.status === 'pending').length;
  const failed = parts.filter((item) => ['failed', 'blocked'].includes(item.status || '')).length;
  return { approved, commands, patches, pending, failed };
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

function ProcessStrip({ parts, currentPart }: { parts?: AgentPart[]; currentPart?: AgentPart }) {
  const stats = processStats(parts?.length ? parts : currentPart ? [currentPart] : []);
  const items: Array<{ label: string; tone?: 'ok' | 'warn' | 'err' }> = [];
  if (stats.approved) items.push({ label: `已批准 ${stats.approved} 项请求`, tone: 'ok' });
  if (stats.patches) items.push({ label: `已执行 ${stats.patches} 个补丁`, tone: 'ok' });
  if (stats.commands) items.push({ label: `已运行 ${stats.commands} 条命令`, tone: 'ok' });
  if (stats.pending) items.push({ label: '自动审核中', tone: 'warn' });
  if (!stats.pending && (stats.approved || stats.patches || stats.commands)) items.push({ label: '自动审核已批准', tone: 'ok' });
  if (stats.failed) items.push({ label: `${stats.failed} 项需要处理`, tone: 'err' });
  if (!items.length) return null;
  return (
    <div className={styles.processStrip}>
      {items.map((item) => (
        <span key={item.label} className={styles.processPill} data-tone={item.tone || 'ok'}>
          {item.label}
        </span>
      ))}
    </div>
  );
}

function ToolResultStrip({ part, payload }: { part: AgentPart; payload: Record<string, any> }) {
  const stats = contextStats(payload);
  const command = commandText(payload);
  const subagentLabel = agentLabel(payload.agent_name);
  const chips: string[] = [];
  if (stats.files) chips.push(`读取 ${stats.files} 个文件`);
  if (stats.matches) chips.push(`找到 ${stats.matches} 条匹配`);
  if (stats.symbols) chips.push(`命中 ${stats.symbols} 个符号`);
  if (stats.commands) chips.push(`识别 ${stats.commands} 个验证命令`);
  if (command) chips.push(command);
  if (!chips.length && part.content) chips.push(part.content);
  return (
    <div className={styles.eventLine}>
      <span className={styles.eventDot} data-status={part.status || 'completed'} />
      {subagentLabel ? <span className={styles.subagentPill}>{subagentLabel}</span> : null}
      <span className={styles.eventTitle}>{partTitle(part, '工具结果')}</span>
      {chips.slice(0, 4).map((chip) => (
        <span key={chip} className={styles.eventChip}>{chip}</span>
      ))}
    </div>
  );
}

function changedFiles(payload?: Record<string, any>) {
  const files = payload?.changed_files || payload?.payload?.changed_files || payload?.files || payload?.payload?.files || [];
  if (!Array.isArray(files)) return [];
  return files.map((item: any) => (typeof item === 'string' ? item : item?.path || item?.file_path)).filter(Boolean);
}

function repairAttempt(payload?: Record<string, any>, metadata?: ChatAgentMetadata) {
  return payload?.repair_attempt ?? payload?.state?.repair_attempts ?? metadata?.repair_attempts;
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
}: AgentPartMessageProps) => {
  const part = metadata.agent_part as AgentPart | undefined;
  if (!part) {
    return <Typography.Paragraph style={{ margin: 0 }}>{content}</Typography.Paragraph>;
  }

  const payload = part.payload || {};
  const sessionParts = asAgentParts(metadata.agent_parts);
  const diagnostics = metadata.agent_session_diagnostics;
  const streamingDiagnostics = metadata.agent_streaming_diagnostics;
  const status = part.status || metadata.status || 'completed';
  const subagentLabel = agentLabel(payload.agent_name);
  const subagentBadge = subagentLabel ? <Tag className={styles.subagentTag}>{subagentLabel}</Tag> : null;
  const asyncStatus = typeof payload.async_status === 'string' ? payload.async_status : '';
  const asyncStatusTag = asyncStatus ? <Tag color={statusColor[asyncStatus] || (asyncStatus === 'running' ? 'processing' : 'default')}>{statusLabel[asyncStatus] || asyncStatus}</Tag> : null;
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
      <Space direction="vertical" size={4} style={{ width: '100%' }} className={styles.naturalPart}>
        {subagentBadge ? <div className={styles.subagentBadgeRow}>{subagentBadge}</div> : null}
        <MarkdownBody>{displayText}</MarkdownBody>
        {isStreaming && <span className={styles.streamingCursor} />}
        {isStreaming && streamingDiagnostics?.mode && (
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            {streamingDiagnostics.mode === 'chat_stream' ? '流式输出中' : '非流式输出'}
          </Typography.Text>
        )}
      </Space>
    );
  }

  if (part.type === 'summary') {
    return (
      <div className={styles.summaryPart}>
        <Space className={styles.summaryHeader} wrap>
          {icon}
          {subagentBadge}
          <Typography.Text strong>{payload.agent_role === 'async_subagent' ? '异步子任务' : '最终结果'}</Typography.Text>
          {asyncStatusTag || <Tag color="success">已完成</Tag>}
          {streamingDiagnostics?.fallback_to_non_stream ? <Tag color="warning">流式回退</Tag> : null}
          {streamingDiagnostics?.mode === 'chat_stream' && !streamingDiagnostics?.fallback_to_non_stream ? <Tag color="processing">流式</Tag> : null}
        </Space>
        {streamingDiagnostics?.fallback_to_non_stream && (
          <Typography.Text type="secondary">
            流式未生效，已回退非流式：{streamingDiagnostics.error || streamingDiagnostics.reason || 'provider 未返回流式增量'}
          </Typography.Text>
        )}
        <MarkdownBody>{part.content || content}</MarkdownBody>
        <ProcessStrip parts={sessionParts} currentPart={part} />
        {diagnosticBlock}
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
    return shell(
      <Space direction="vertical" size={10} style={{ width: '100%' }}>
        <Space wrap>
          {icon}
          {subagentBadge}
          <Typography.Text strong>{partTitle(part, content)}</Typography.Text>
          <Tag color={statusColor[status] || 'default'}>{statusLabel[status] || status}</Tag>
          <Tag>历史记录/只读</Tag>
          {payload.execution_mode === 'auto' || payload.policy_decision === 'auto' ? <Tag color="green">安全自动</Tag> : null}
          {payload.risk_level ? <Tag>{payload.risk_level}</Tag> : null}
        </Space>
        {payload.policy_reason && <Typography.Text type="secondary">{payload.policy_reason}</Typography.Text>}
        {diagnosticBlock}
        {repairAttempt(payload, metadata) ? (
          <Tag color="orange">修复尝试 {repairAttempt(payload, metadata)}/{metadata.max_repair_attempts || payload.max_repair_attempts || 1}</Tag>
        ) : null}
        {(stats.total > 0 || files.length > 0) && (
          <div className={styles.diffOverview}>
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
      </Space>,
    );
  }

  if (part.type === 'command') {
    return shell(
      <Space direction="vertical" size={8} style={{ width: '100%' }}>
        <Space wrap>
          {icon}
          {subagentBadge}
          <Typography.Text code>{commandText(payload) || part.title || '验证命令'}</Typography.Text>
          <Tag color={statusColor[status] || 'default'}>{statusLabel[status] || status}</Tag>
          <Tag>历史记录/只读</Tag>
          {payload.execution_mode === 'auto' || payload.policy_decision === 'auto' ? <Tag color="green">安全自动</Tag> : null}
          {payload.risk_level ? <Tag>{payload.risk_level}</Tag> : null}
          {repairAttempt(payload, metadata) ? <Tag color="orange">修复尝试 {repairAttempt(payload, metadata)}</Tag> : null}
        </Space>
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
      </Space>,
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
    // 只读工具静默折叠
    const toolName = payload?.tool || '';
    if (
      SILENT_TOOLS.has(toolName) &&
      !isProblem
    ) {
      const silentIcon = toolName.includes('search') || toolName === 'glob' || toolName === 'list_files'
        ? '🔍'
        : toolName.includes('read') || toolName === 'collect_context' || toolName === 'inspect_project'
        ? '📄'
        : toolName.includes('test') || toolName.includes('execution')
        ? '🧪'
        : '⚙️';
      const silentLabel = part.type === 'tool_call' && status === 'running'
        ? partTitle(part, content) + '...'
        : partTitle(part, content);
      return (
        <div style={{
          display: 'flex',
          alignItems: 'center',
          gap: 6,
          padding: '3px 0',
          color: 'var(--text-secondary, rgba(255,255,255,0.45))',
          fontSize: 12,
        }}>
          <span>{silentIcon}</span>
          {subagentLabel ? <span className={styles.subagentPill}>{subagentLabel}</span> : null}
          <span style={{ opacity: 0.7 }}>{silentLabel}</span>
          {status === 'running' && (
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: 2 }}>
              <span className="typing-dot" />
              <span className="typing-dot" style={{ animationDelay: '0.2s' }} />
              <span className="typing-dot" style={{ animationDelay: '0.4s' }} />
            </span>
          )}
        </div>
      );
    }

    return shell(
      <Space direction="vertical" size={6} style={{ width: '100%' }}>
        <ToolResultStrip part={part} payload={payload} />
        {diagnosticBlock}
        {payload.failure_summary && <Typography.Text type="danger">{payload.failure_summary}</Typography.Text>}
        {payload.server_url && (
          <Typography.Link href={payload.server_url} target="_blank" rel="noreferrer">
            {payload.server_url}
          </Typography.Link>
        )}
      </Space>,
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
