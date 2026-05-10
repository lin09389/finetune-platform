import {
  LinkOutlined,
  PlayCircleOutlined,
  ReloadOutlined,
} from '@ant-design/icons';
import { Button, Collapse, Space, Tag, Tooltip, Typography } from 'antd';
import React from 'react';
import type { ChatAgentMetadata } from '../../types';
import type { AgentPart, Workflow, WorkflowAction, WorkflowObservability, WorkflowToolCall } from '../../services/api';

interface AgentRunCardProps {
  content: string;
  metadata: ChatAgentMetadata;
  onApproveStep?: (stepId: string) => void | Promise<void>;
  onApproveAction?: (actionId: string) => void | Promise<void>;
  onRejectAction?: (actionId: string) => void | Promise<void>;
  onExecuteAction?: (actionId: string) => void | Promise<void>;
  onRefreshRun?: (runId: string) => void | Promise<void>;
  onOpenDetails?: (url: string) => void;
}

function stringify(value: unknown) {
  if (value === undefined || value === null) return '';
  if (typeof value === 'string') return value;
  return JSON.stringify(value, null, 2);
}

function stepOutput(step: any) {
  const output = step?.output || step?.output_data || {};
  return output && typeof output === 'object' ? output : {};
}

function shortPath(path: string) {
  const normalized = path.replace(/\\/g, '/');
  const parts = normalized.split('/').filter(Boolean);
  if (parts.length <= 4) return normalized;
  return `${parts[0]}/.../${parts.slice(-2).join('/')}`;
}

function splitReportItem(value: string) {
  const separators = [' —— ', ' — ', ' - ', '：', ':'];
  for (const separator of separators) {
    const index = value.indexOf(separator);
    if (index > 0) {
      return { scope: value.slice(0, index).trim(), detail: value.slice(index + separator.length).trim() };
    }
  }
  return { scope: '', detail: value };
}

function reportRows(report: NonNullable<ChatAgentMetadata['acceptance_report']>) {
  const files = report.changed_files || [];
  const items = report.completed_items || [];
  const max = Math.max(files.length, items.length, 1);
  return Array.from({ length: max }, (_, index) => {
    const parsed = splitReportItem(items[index] || items[0] || report.summary);
    const file = files[index] || (parsed.scope.includes('/') || parsed.scope.includes('\\') ? parsed.scope : files[0] || '');
    const item = parsed.detail || parsed.scope || report.summary;
    return { file, item };
  });
}

function resultTone(result: string) {
  if (result === 'passed') return { status: '已处理', issue: '未发现阻断问题。', accent: 'var(--accent-success, #52c41a)' };
  if (result === 'failed') return { status: '验证失败', issue: '执行或验证未通过。', accent: 'var(--accent-danger, #ff4d4f)' };
  if (result === 'blocked') return { status: '等待处理', issue: '当前链路被策略或审批阻断。', accent: 'var(--accent-warning, #faad14)' };
  return { status: '部分完成', issue: '任务已有进展，但还没有完全闭环。', accent: 'var(--accent-primary, #1677ff)' };
}

const AgentRunCardInner = React.memo(function AgentRunCardInner({
  content,
  metadata,
  onApproveAction,
  onRejectAction,
  onExecuteAction,
  onRefreshRun,
  onOpenDetails,
}: AgentRunCardProps) {
  const workflow = metadata.workflow as Workflow | undefined;
  const agentParts = ((metadata as any).agent_parts as AgentPart[] | undefined) || [];
  const observability = metadata.observability as WorkflowObservability | undefined;
  const toolCalls = ((metadata.tool_calls as WorkflowToolCall[] | undefined) || observability?.tool_calls || []);
  const activeAgentId = (metadata as any).active_agent_id || workflow?.active_agent_id || observability?.active_agent_id;
  const executionState = metadata.execution_state || (workflow?.metadata as any)?.execution_state;
  const executionMessage = metadata.execution_state_message || (workflow?.metadata as any)?.execution_state_message;
  const protocolStatus = metadata.model_protocol_status || (workflow?.metadata as any)?.model_protocol_status;
  const parseRepairCount = metadata.parse_repair_count ?? (workflow?.metadata as any)?.parse_repair_count;
  const fallbackSummaryUsed = metadata.fallback_summary_used ?? (workflow?.metadata as any)?.fallback_summary_used;
  const action = metadata.action as WorkflowAction | undefined;
  const status = action?.status || executionState || metadata.status || workflow?.status || 'running';
  const currentNodeLabel = workflow?.current_stage || 'bootstrap';
  const runningTool = [...toolCalls].reverse().find((call) => call.status === 'running');
  const pendingActions = (observability?.actions || []).filter((item) => item.status === 'pending_approval').length;
  const failedActions = (observability?.actions || []).filter((item) => item.status === 'failed').length;
  const autoExecutedActions = (observability?.actions || []).filter((item) => item.execution_mode === 'auto' && item.status === 'executed').length;
  const changedFileCount = new Set((observability?.actions || []).flatMap((item) => item.changed_files || [])).size;
  const stageLabel =
    executionState === 'waiting_permission' ? '等待权限'
      : executionState === 'waiting_approval' || pendingActions > 0 ? '等待确认'
      : executionState === 'repairing' ? '修复中'
      : executionState === 'verifying' ? '验证中'
      : executionState === 'needs_manual_review' ? '需要人工处理'
      : executionState === 'failed' || status === 'failed' ? '失败'
      : status === 'completed' ? '已完成'
      : runningTool ? `执行 ${runningTool.tool_name}`
      : '处理中';
  const phaseAccent =
    status === 'failed' || executionState === 'failed' || executionState === 'needs_manual_review'
      ? 'var(--accent-danger, #ff4d4f)'
      : pendingActions > 0 || executionState === 'waiting_approval' || executionState === 'waiting_permission'
        ? 'var(--accent-warning, #faad14)'
        : status === 'completed' || action?.status === 'executed'
          ? 'var(--accent-success, #52c41a)'
          : 'var(--accent-primary, #1677ff)';

  const steps = workflow?.steps || [];
  const completedSteps = steps.filter((step) => ['approved', 'completed'].includes(step.status)).length;
  const finalStep = [...steps].reverse().find((step) => {
    const output = stepOutput(step);
    return output.summary || output.next_action || (Array.isArray(output.risks) && output.risks.length);
  });
  const finalOutput = stepOutput(finalStep);
  const finalSummary = metadata.final_summary || finalOutput.summary;
  const showFinalOutput = Boolean(finalSummary || finalOutput.next_action);
  const acceptanceReport = metadata.acceptance_report;
  const reportTone = acceptanceReport ? resultTone(acceptanceReport.result) : undefined;

  const partsPreview = agentParts
    .filter((part) => part.type !== 'text' || part.title !== '请求')
    .slice(0, 5)
    .map((part) => {
      const label = part.type === 'tool_call'
        ? '工具'
        : part.type === 'tool_result'
          ? '结果'
          : part.type === 'diff'
            ? '补丁'
            : part.type === 'command'
              ? '命令'
              : part.type === 'permission'
                ? '权限'
                : part.type === 'summary'
                  ? '总结'
                  : part.type === 'error'
                    ? '错误'
                    : '消息';
      return { id: part.id, label, title: part.title || part.content || label, status: part.status, content: part.content, payload: part.payload };
    });

  return (
    <div style={{ display: 'grid', gap: 10, minWidth: 280, borderLeft: `2px solid ${phaseAccent}`, padding: '2px 0 2px 12px', background: 'transparent' }}>
      <div style={{ display: 'grid', gap: 8 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, alignItems: 'flex-start' }}>
          <div style={{ display: 'grid', gap: 4 }}>
            <Space wrap size={6}>
              <Tag color={phaseAccent.includes('danger') ? 'error' : phaseAccent.includes('warning') ? 'warning' : 'processing'}>{stageLabel}</Tag>
              {activeAgentId ? <Tag>{activeAgentId}</Tag> : null}
              <Tag color="geekblue">{currentNodeLabel}</Tag>
            </Space>
            <Typography.Text type="secondary">
              {status}
              {protocolStatus === 'repaired' ? ' · 模型输出已修复' : ''}
              {protocolStatus === 'fallback_summary' ? ' · 使用兜底总结' : ''}
              {protocolStatus === 'needs_manual_review' ? ' · 协议需人工处理' : ''}
            </Typography.Text>
          </div>
          <Space size={4}>
            {metadata.recoverable && (
              <Tooltip title="刷新运行状态">
                <Button aria-label="刷新运行状态" size="small" type="text" icon={<ReloadOutlined />} onClick={() => onRefreshRun?.(metadata.agent_run_id)} />
              </Tooltip>
            )}
            {metadata.details_url && (
              <Tooltip title="查看执行详情">
                <Button aria-label="查看执行详情" size="small" type="text" icon={<LinkOutlined />} onClick={() => onOpenDetails?.(metadata.details_url!)} />
              </Tooltip>
            )}
          </Space>
        </div>

        <Typography.Text strong>请求：{content}</Typography.Text>

        <Space wrap size={6}>
          <Tag>{agentParts.length ? `输出 ${agentParts.length}` : toolCalls.length ? `工具 ${toolCalls.length}` : '等待工具'}</Tag>
          {autoExecutedActions ? <Tag color="green">自动执行 {autoExecutedActions}</Tag> : null}
          {pendingActions ? <Tag color="gold">待确认 {pendingActions}</Tag> : null}
          {failedActions ? <Tag color="red">失败动作 {failedActions}</Tag> : null}
          {changedFileCount ? <Tag color="cyan">变更文件 {changedFileCount}</Tag> : null}
          {parseRepairCount ? <Tag color="orange">协议修复 {parseRepairCount}</Tag> : null}
        </Space>
      </div>

      <Collapse
        size="small"
        ghost
        items={[
          {
            key: 'timeline',
            label: 'Stage / Node 详情',
            children: (
              <div style={{ display: 'grid', gap: 8, borderTop: '1px solid var(--border-color)', paddingTop: 10 }}>
                <Typography.Text type="secondary">
                  {steps.length ? `Stage：${completedSteps}/${steps.length}` : '当前任务尚未生成阶段拆分'}
                  {steps.map((step) => ` · ${step.title}:${step.status}`).join('')}
                </Typography.Text>

                {executionState && (
                  <Typography.Text type={executionState === 'failed' || executionState === 'needs_manual_review' ? 'danger' : 'secondary'}>
                    当前阶段：{executionState}
                    {executionMessage ? ` · ${executionMessage}` : ' · Agent 正在推进开发闭环。'}
                  </Typography.Text>
                )}

                {protocolStatus && protocolStatus !== 'ok' && (
                  <Typography.Text type={protocolStatus === 'needs_manual_review' ? 'danger' : 'secondary'}>
                    {protocolStatus === 'repaired' ? '模型输出已自动修复' : protocolStatus === 'fallback_summary' ? '已使用后端兜底总结' : '模型协议需要人工确认'}
                    {' · '}修复次数：{parseRepairCount || 0}
                    {fallbackSummaryUsed ? ' · 最终结果由系统根据工具和动作记录生成' : ''}
                    {metadata.last_model_output_preview ? ` · 最近模型输出：${metadata.last_model_output_preview}` : ''}
                  </Typography.Text>
                )}

                {partsPreview.length > 0 && (
                  <Collapse
                    size="small"
                    items={[
                      {
                        key: 'parts',
                        label: '消息与动作明细',
                        children: (
                          <div style={{ display: 'grid', gap: 8 }}>
                            {partsPreview.map((part) => (
                              <div key={part.id} style={{ display: 'grid', gap: 4, paddingLeft: 12, borderLeft: '2px solid var(--border-color)' }}>
                                <Space wrap size={6}>
                                  <Tag>{part.label}</Tag>
                                  <Typography.Text strong>{part.title}</Typography.Text>
                                  {part.status && <Typography.Text type="secondary">{part.status}</Typography.Text>}
                                </Space>
                                {part.content && <Typography.Text type="secondary">{part.content}</Typography.Text>}
                                {(part.label === '补丁' || part.label === '命令') && part.payload && (
                                  <Collapse size="small" items={[{ key: 'payload', label: '查看 payload', children: <pre style={{ margin: 0, whiteSpace: 'pre-wrap' }}>{stringify(part.payload)}</pre> }]} />
                                )}
                                {part.status === 'pending' && (part.label === '补丁' || part.label === '权限') && (
                                  <Space wrap>
                                    <Button size="small" type="primary" onClick={() => onApproveAction?.(part.id)}>批准</Button>
                                    <Button size="small" onClick={() => onRejectAction?.(part.id)}>拒绝</Button>
                                  </Space>
                                )}
                                {part.status === 'approved' && (part.label === '补丁' || part.label === '命令') && (
                                  <Button size="small" type="primary" icon={<PlayCircleOutlined />} onClick={() => onExecuteAction?.(part.id)}>
                                    {part.label === '命令' ? '执行命令' : '执行补丁'}
                                  </Button>
                                )}
                              </div>
                            ))}
                          </div>
                        ),
                      },
                    ]}
                  />
                )}

                {showFinalOutput && (
                  <div style={{ display: 'grid', gap: 4, borderTop: '1px solid var(--border-color)', paddingTop: 10 }}>
                    <Typography.Text strong>最终结果</Typography.Text>
                    {finalSummary && <Typography.Text>{finalSummary}</Typography.Text>}
                    {Array.isArray(finalOutput.risks) && finalOutput.risks.length > 0 && (
                      <Typography.Text type="secondary">风险：{finalOutput.risks.join('；')}</Typography.Text>
                    )}
                    {finalOutput.next_action && <Typography.Text type="secondary">下一步：{finalOutput.next_action}</Typography.Text>}
                  </div>
                )}

                {acceptanceReport && (
                  <section style={{ display: 'grid', gap: 10, borderTop: '1px solid var(--border-color)', paddingTop: 12 }} aria-label="Agent 验收报告">
                    <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, alignItems: 'flex-start' }}>
                      <Space wrap size={6}>
                        <Typography.Text strong style={{ fontSize: 16 }}>开发验收报告</Typography.Text>
                        <Tag color={acceptanceReport.result === 'passed' ? 'success' : acceptanceReport.result === 'failed' ? 'error' : acceptanceReport.result === 'blocked' ? 'warning' : 'processing'}>
                          {acceptanceReport.result}
                        </Tag>
                        {metadata.acceptance_report_source === 'fallback' && <Tag>系统根据执行记录生成</Tag>}
                        {metadata.acceptance_report_source === 'model' && <Tag color="blue">模型自评</Tag>}
                      </Space>
                      {acceptanceReport.commands_run?.length ? <Tag icon={<PlayCircleOutlined />} color="cyan">验证 {acceptanceReport.commands_run.length}</Tag> : null}
                    </div>

                    <Typography.Paragraph style={{ margin: 0, lineHeight: 1.75 }}>{acceptanceReport.summary}</Typography.Paragraph>

                    <Typography.Text type="secondary">
                      结果：{acceptanceReport.result}
                      {' · '}变更：{acceptanceReport.changed_files?.length || 0} 个文件
                      {' · '}验证：{acceptanceReport.commands_run?.length ? `${acceptanceReport.commands_run.length} 条命令` : '未运行命令'}
                      {' · '}状态：{reportTone?.status || '已记录'}
                    </Typography.Text>

                    <div style={{ display: 'grid', gap: 8 }}>
                      {reportRows(acceptanceReport).map((row, index) => (
                        <div key={`${row.file || row.item}-${index}`} style={{ display: 'grid', gap: 4, paddingLeft: 12, borderLeft: `2px solid ${reportTone?.accent || 'var(--accent-primary)'}` }}>
                          <Typography.Text strong style={{ lineHeight: 1.6 }}>
                            {index + 1}. {row.file ? <Typography.Text code style={{ color: 'var(--accent-primary)', background: 'color-mix(in srgb, var(--accent-primary) 10%, transparent)', borderRadius: 6, padding: '2px 6px' }}>{shortPath(row.file)}</Typography.Text> : <Typography.Text type="secondary">执行结果</Typography.Text>} <span>— {row.item}</span>
                          </Typography.Text>
                          <div style={{ display: 'grid', gap: 4, paddingLeft: 18 }}>
                            <Typography.Text type="secondary">• 状态：{reportTone?.status || '已记录'}</Typography.Text>
                            <Typography.Text type="secondary">• 处理：{row.item}</Typography.Text>
                            <Typography.Text type={acceptanceReport.blocking_reason ? 'danger' : 'secondary'}>• 说明：{acceptanceReport.blocking_reason || reportTone?.issue || '已根据执行记录整理。'}</Typography.Text>
                          </div>
                        </div>
                      ))}
                    </div>
                  </section>
                )}
              </div>
            ),
          },
        ]}
      />
    </div>
  );
});

export default AgentRunCardInner;
