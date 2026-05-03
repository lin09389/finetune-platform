import {
  CheckCircleOutlined,
  CodeOutlined,
  ExclamationCircleOutlined,
  FileTextOutlined,
  LinkOutlined,
  PlayCircleOutlined,
  ReloadOutlined,
  SafetyCertificateOutlined,
  SearchOutlined,
} from '@ant-design/icons';
import { Button, Collapse, Divider, Space, Tag, Tooltip, Typography } from 'antd';
import type { ChatAgentMetadata } from '../../types';
import type { Workflow, WorkflowAction, WorkflowObservability, WorkflowToolCall } from '../../services/api';

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

const statusLabel: Record<string, string> = {
  created: '已创建',
  running: '运行中',
  planning: '规划中',
  inspecting: '理解项目',
  proposing_patch: '生成补丁',
  waiting_permission: '等待权限',
  waiting_approval: '等待审批',
  applying_patch: '应用补丁',
  verifying: '验证中',
  repairing: '修复中',
  awaiting_approval: '等待审批',
  implementing: '实现中',
  reviewing: '审查中',
  completed: '已完成',
  failed: '失败',
  blocked: '已阻断',
  needs_manual_review: '需人工确认',
  pending_approval: '等待审批',
  approved: '已批准',
  executed: '已执行',
  rejected: '已拒绝',
};

const toolLabel: Record<string, string> = {
  list_files: '列出文件',
  search_code: '搜索代码',
  read_file: '读取文件',
  inspect_project: '检查项目',
  detect_project_commands: '识别验证命令',
  get_git_status: '读取变更状态',
  get_git_diff: '读取变更 diff',
  list_changed_files: '列出变更文件',
  propose_patch: '生成补丁',
  propose_command: '生成命令',
  read_execution_result: '读取执行结果',
  read_test_failures: '读取失败摘要',
  finalize: '完成总结',
};

const acceptanceResultLabel: Record<string, string> = {
  passed: '已通过',
  partial: '部分完成',
  blocked: '已阻断',
  failed: '失败',
};

const acceptanceResultColor: Record<string, string> = {
  passed: 'success',
  partial: 'processing',
  blocked: 'warning',
  failed: 'error',
};

function stringify(value: unknown) {
  if (value === undefined || value === null) return '';
  if (typeof value === 'string') return value;
  return JSON.stringify(value, null, 2);
}

function actionPreview(action?: WorkflowAction) {
  if (!action) return '';
  if (action.action_type === 'command') {
    const command = action.payload?.command;
    return Array.isArray(command) ? command.join(' ') : stringify(command);
  }
  const files = action.payload?.files || action.payload?.file_changes;
  if (action.payload?.format === 'unified_diff' || action.payload?.diff) {
    return stringify(action.payload?.diff || action.payload);
  }
  if (Array.isArray(files)) {
    return files.map((file: any) => `${file.path || file.file_path || 'unknown'}\n${file.content || ''}`).join('\n\n');
  }
  return stringify(action.payload);
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
      return {
        scope: value.slice(0, index).trim(),
        detail: value.slice(index + separator.length).trim(),
      };
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
  if (result === 'passed') {
    return {
      status: '已处理',
      issue: '未发现阻断问题。',
      accent: 'var(--accent-success, #52c41a)',
    };
  }
  if (result === 'failed') {
    return {
      status: '验证失败',
      issue: '执行或验证未通过。',
      accent: 'var(--accent-danger, #ff4d4f)',
    };
  }
  if (result === 'blocked') {
    return {
      status: '等待处理',
      issue: '当前链路被策略或审批阻断。',
      accent: 'var(--accent-warning, #faad14)',
    };
  }
  return {
    status: '部分完成',
    issue: '任务已有进展，但还没有完全闭环。',
    accent: 'var(--accent-primary, #1677ff)',
  };
}

function toolTone(call: WorkflowToolCall) {
  if (call.status === 'failed') {
    return {
      color: 'error',
      accent: 'var(--accent-danger, #ff4d4f)',
      label: '失败',
    };
  }
  if (call.status === 'running') {
    return {
      color: 'processing',
      accent: 'var(--accent-primary, #1677ff)',
      label: '进行中',
    };
  }
  if (call.status === 'blocked' || call.permission_decision === 'deny') {
    return {
      color: 'warning',
      accent: 'var(--accent-warning, #faad14)',
      label: '已阻断',
    };
  }
  return {
    color: 'success',
    accent: 'var(--accent-success, #52c41a)',
    label: '完成',
  };
}

function actionTone(action: WorkflowAction) {
  if (action.status === 'failed') {
    return { color: 'error', accent: 'var(--accent-danger, #ff4d4f)', label: '执行失败' };
  }
  if (action.status === 'blocked' || action.execution_mode === 'blocked') {
    return { color: 'warning', accent: 'var(--accent-warning, #faad14)', label: '策略阻断' };
  }
  if (action.status === 'pending_approval') {
    return { color: 'gold', accent: 'var(--accent-warning, #faad14)', label: '等待确认' };
  }
  if (action.status === 'executed') {
    return { color: 'success', accent: 'var(--accent-success, #52c41a)', label: action.execution_mode === 'auto' ? '已自动执行' : '已执行' };
  }
  if (action.status === 'approved') {
    return { color: 'processing', accent: 'var(--accent-primary, #1677ff)', label: '已批准' };
  }
  return { color: 'default', accent: 'var(--border-color)', label: statusLabel[action.status] || action.status };
}

function actionKindLabel(action: WorkflowAction) {
  if (action.action_type === 'patch') return '文件补丁';
  if (action.action_type === 'permission_request') return '权限请求';
  return '验证命令';
}

export default function AgentRunCard({
  content,
  metadata,
  onApproveStep,
  onApproveAction,
  onRejectAction,
  onExecuteAction,
  onRefreshRun,
  onOpenDetails,
}: AgentRunCardProps) {
  const workflow = metadata.workflow as Workflow | undefined;
  const observability = metadata.observability as WorkflowObservability | undefined;
  const toolCalls = ((metadata.tool_calls as WorkflowToolCall[] | undefined) || observability?.tool_calls || []);
  const activeAgentId = (metadata as any).active_agent_id || workflow?.active_agent_id || observability?.active_agent_id;
  const executionState = metadata.execution_state || (workflow?.metadata as any)?.execution_state;
  const executionMessage = metadata.execution_state_message || (workflow?.metadata as any)?.execution_state_message;
  const protocolStatus = metadata.model_protocol_status || (workflow?.metadata as any)?.model_protocol_status;
  const parseRepairCount = metadata.parse_repair_count ?? (workflow?.metadata as any)?.parse_repair_count;
  const fallbackSummaryUsed = metadata.fallback_summary_used ?? (workflow?.metadata as any)?.fallback_summary_used;
  const subagentRuns = ((metadata as any).subagent_runs as Array<Record<string, any>> | undefined) || observability?.subagent_runs || [];
  const recentToolCalls = toolCalls.slice(-3).reverse();
  const runningTool = [...toolCalls].reverse().find((call) => call.status === 'running');
  const latestBlockedTool = [...toolCalls]
    .reverse()
    .find((call) => call.status === 'blocked' || call.permission_decision === 'ask' || call.permission_decision === 'deny');
  const latestTool = toolCalls.length ? toolCalls[toolCalls.length - 1] : undefined;
  const diagnosticLatestTool = ((metadata.latest_tool_call as WorkflowToolCall | undefined) || latestTool);
  const diagnosticLatestAction = ((metadata.latest_action as WorkflowAction | undefined) || (metadata.action as WorkflowAction | undefined));
  const diagnosticLatestEvent = (metadata.latest_event || metadata.event) as Record<string, any> | undefined;
  const action = metadata.action as WorkflowAction | undefined;
  const waitingStep = workflow?.steps?.find((step) => step.status === 'awaiting_approval');
  const lastExecution = action?.executions?.[action.executions.length - 1];
  const preview = actionPreview(action);
  const status = action?.status || executionState || metadata.status || workflow?.status || 'running';
  const completedSteps = workflow?.steps?.filter((step) => ['approved', 'completed'].includes(step.status)).length || 0;
  const totalSteps = workflow?.steps?.length || 0;
  const actionNeedsDecision = action?.status === 'pending_approval';
  const actionCanExecute = action?.status === 'approved' && action?.action_type !== 'permission_request';
  const finalStep = [...(workflow?.steps || [])]
    .reverse()
    .find((step) => {
      const output = stepOutput(step);
      return output.summary || output.next_action || (Array.isArray(output.risks) && output.risks.length);
    });
  const finalOutput = stepOutput(finalStep);
  const finalSummary = metadata.final_summary || finalOutput.summary;
  const showFinalOutput = Boolean(finalSummary || finalOutput.next_action);
  const acceptanceReport = metadata.acceptance_report;
  const actions = observability?.actions?.length ? observability.actions : action ? [action] : [];
  const autoExecutedActions = actions.filter((item) => item.execution_mode === 'auto' && item.status === 'executed').length;
  const pendingActions = actions.filter((item) => item.status === 'pending_approval').length;
  const failedActions = actions.filter((item) => item.status === 'failed').length;
  const changedFileCount = new Set(actions.flatMap((item) => item.changed_files || [])).size;
  const reportTone = acceptanceReport ? resultTone(acceptanceReport.result) : undefined;
  const phaseAccent =
    status === 'failed' || executionState === 'failed' || executionState === 'needs_manual_review'
      ? 'var(--accent-danger, #ff4d4f)'
      : pendingActions || actionNeedsDecision || executionState === 'waiting_approval' || executionState === 'waiting_permission'
        ? 'var(--accent-warning, #faad14)'
        : status === 'completed' || action?.status === 'executed'
          ? 'var(--accent-success, #52c41a)'
          : 'var(--accent-primary, #1677ff)';

  return (
    <div
      style={{
        display: 'grid',
        gap: 10,
        minWidth: 280,
        borderLeft: `2px solid ${phaseAccent}`,
        padding: '2px 0 2px 12px',
        background: 'transparent',
      }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, alignItems: 'flex-start' }}>
        <Typography.Text type="secondary">
          {statusLabel[status] || status}
          {activeAgentId ? ` · ${activeAgentId}` : ''}
          {workflow?.current_stage ? ` · ${workflow.current_stage}` : ''}
          {protocolStatus === 'repaired' ? ' · 模型输出已修复' : ''}
          {protocolStatus === 'fallback_summary' ? ' · 使用兜底总结' : ''}
          {protocolStatus === 'needs_manual_review' ? ' · 协议需人工处理' : ''}
        </Typography.Text>
        <Space size={4}>
          {metadata.recoverable && (
            <Tooltip title="刷新运行状态">
              <Button
                aria-label="刷新运行状态"
                size="small"
                type="text"
                icon={<ReloadOutlined />}
                onClick={() => onRefreshRun?.(metadata.agent_run_id)}
              />
            </Tooltip>
          )}
          {metadata.details_url && (
            <Tooltip title="查看工作流详情">
              <Button
                aria-label="查看工作流详情"
                size="small"
                type="text"
                icon={<LinkOutlined />}
                onClick={() => onOpenDetails?.(metadata.details_url!)}
              />
            </Tooltip>
          )}
        </Space>
      </div>

      <Typography.Text strong>请求：{content}</Typography.Text>

      <Typography.Text type="secondary">
        {toolCalls.length ? `工具 ${toolCalls.length}` : '等待工具'}
        {actions.length ? ` · 动作 ${actions.length}` : ''}
        {autoExecutedActions ? ` · 自动执行 ${autoExecutedActions}` : ''}
        {pendingActions ? ` · 待确认 ${pendingActions}` : ''}
        {failedActions ? ` · 失败动作 ${failedActions}` : ''}
        {changedFileCount ? ` · 变更文件 ${changedFileCount}` : ''}
        {parseRepairCount ? ` · 协议修复 ${parseRepairCount}` : ''}
      </Typography.Text>

      {executionState && (
        <Typography.Text type={executionState === 'failed' || executionState === 'needs_manual_review' ? 'danger' : 'secondary'}>
          当前阶段：{statusLabel[executionState] || executionState}
          {executionMessage ? ` · ${executionMessage}` : ' · Agent 正在推进开发闭环。'}
        </Typography.Text>
      )}

      {executionState === 'needs_manual_review' && (
        <Typography.Text type="danger">
          需要人工确认：{(metadata.blocked_state as any)?.reason || executionMessage || 'Agent 当前无法自动继续，请查看工具调用和动作输出后决定下一步。'}
        </Typography.Text>
      )}

      {protocolStatus && protocolStatus !== 'ok' && (
        <Typography.Text type={protocolStatus === 'needs_manual_review' ? 'danger' : 'secondary'}>
          {protocolStatus === 'repaired'
            ? '模型输出已自动修复'
            : protocolStatus === 'fallback_summary'
              ? '已使用后端兜底总结'
              : '模型协议需要人工确认'}
          {' · '}修复次数：{parseRepairCount || 0}
          {fallbackSummaryUsed ? ' · 最终结果由系统根据工具和动作记录生成' : ''}
          {metadata.last_model_output_preview ? ` · 最近模型输出：${metadata.last_model_output_preview}` : ''}
        </Typography.Text>
      )}

      {showFinalOutput && (
        <div style={{ display: 'grid', gap: 4, borderTop: '1px solid var(--border-color)', paddingTop: 10 }}>
          <Typography.Text strong>最终结果</Typography.Text>
          {finalSummary && <Typography.Text>{finalSummary}</Typography.Text>}
          {Array.isArray(finalOutput.risks) && finalOutput.risks.length > 0 && (
            <Typography.Text type="secondary">风险：{finalOutput.risks.join('；')}</Typography.Text>
          )}
          {finalOutput.next_action && (
            <Typography.Text type="secondary">下一步：{finalOutput.next_action}</Typography.Text>
          )}
        </div>
      )}

      {acceptanceReport && (
        <section
          style={{
            display: 'grid',
            gap: 10,
            borderTop: '1px solid var(--border-color)',
            paddingTop: 12,
          }}
          aria-label="Agent 验收报告"
        >
          <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, alignItems: 'flex-start' }}>
            <Space wrap size={6}>
              <Typography.Text strong style={{ fontSize: 16 }}>开发验收报告</Typography.Text>
              <Tag color={acceptanceResultColor[acceptanceReport.result] || 'default'}>
                {acceptanceResultLabel[acceptanceReport.result] || acceptanceReport.result}
              </Tag>
              {metadata.acceptance_report_source === 'fallback' && <Tag>系统根据执行记录生成</Tag>}
              {metadata.acceptance_report_source === 'model' && <Tag color="blue">模型自评</Tag>}
            </Space>
            {acceptanceReport.commands_run?.length ? (
              <Tag icon={<PlayCircleOutlined />} color="cyan">验证 {acceptanceReport.commands_run.length}</Tag>
            ) : null}
          </div>

          <Typography.Paragraph style={{ margin: 0, lineHeight: 1.75 }}>
            {acceptanceReport.summary}
          </Typography.Paragraph>

          <Typography.Text type="secondary">
            结果：{acceptanceResultLabel[acceptanceReport.result] || acceptanceReport.result}
            {' · '}变更：{acceptanceReport.changed_files?.length || 0} 个文件
            {' · '}验证：{acceptanceReport.commands_run?.length ? `${acceptanceReport.commands_run.length} 条命令` : '未运行命令'}
            {' · '}状态：{reportTone?.status || '已记录'}
          </Typography.Text>

          <div style={{ display: 'grid', gap: 8 }}>
            {reportRows(acceptanceReport).map((row, index) => (
              <div
                key={`${row.file || row.item}-${index}`}
                style={{
                  display: 'grid',
                  gap: 4,
                  paddingLeft: 12,
                  borderLeft: `2px solid ${reportTone?.accent || 'var(--accent-primary)'}`,
                }}
              >
                <Typography.Text strong style={{ lineHeight: 1.6 }}>
                  {index + 1}.{' '}
                  {row.file ? (
                    <Typography.Text
                      code
                      style={{
                        color: 'var(--accent-primary)',
                        background: 'color-mix(in srgb, var(--accent-primary) 10%, transparent)',
                        borderRadius: 6,
                        padding: '2px 6px',
                      }}
                    >
                      {shortPath(row.file)}
                    </Typography.Text>
                  ) : (
                    <Typography.Text type="secondary">执行结果</Typography.Text>
                  )}{' '}
                  <span>— {row.item}</span>
                </Typography.Text>
                <div style={{ display: 'grid', gap: 4, paddingLeft: 18 }}>
                  <Typography.Text type="secondary">
                    • 状态：{reportTone?.status || '已记录'}
                  </Typography.Text>
                  <Typography.Text type="secondary">
                    • 处理：{row.item}
                  </Typography.Text>
                  <Typography.Text type={acceptanceReport.blocking_reason ? 'danger' : 'secondary'}>
                    • 说明：{acceptanceReport.blocking_reason || reportTone?.issue || '已根据执行记录整理。'}
                  </Typography.Text>
                </div>
              </div>
            ))}
          </div>

          <div style={{ display: 'grid', gap: 8 }}>
            {acceptanceReport.changed_files?.length ? (
              <Typography.Text type="secondary">
                变更文件：{acceptanceReport.changed_files.map(shortPath).join('；')}
              </Typography.Text>
            ) : null}
            {acceptanceReport.commands_run?.length ? (
              <Typography.Text type="secondary">
                执行命令：{acceptanceReport.commands_run.join('；')}
              </Typography.Text>
            ) : null}
            {acceptanceReport.verification_result && (
              <Typography.Text type="secondary">
                验证结果：{acceptanceReport.verification_result}
              </Typography.Text>
            )}
            {acceptanceReport.blocking_reason && (
              <Typography.Text type="danger">
                阻断原因：{acceptanceReport.blocking_reason}
              </Typography.Text>
            )}
            {acceptanceReport.next_action && (
              <Typography.Text type="secondary">
                下一步：{acceptanceReport.next_action}
              </Typography.Text>
            )}
          </div>
        </section>
      )}

      {workflow?.steps?.length ? (
        <Typography.Text type="secondary">
          阶段：{completedSteps}/{totalSteps}
          {workflow.steps.map((step) => ` · ${step.title}:${statusLabel[step.status] || step.status}`).join('')}
        </Typography.Text>
      ) : null}

      {toolCalls.length ? (
        <div style={{ display: 'grid', gap: 8 }}>
          <Space wrap size={6}>
            <Tag icon={<SearchOutlined />} color={runningTool ? 'processing' : 'default'}>
              {runningTool ? `正在${toolLabel[runningTool.tool_name] || runningTool.tool_name}` : `工具调用 ${toolCalls.length} 次`}
            </Tag>
            {metadata.repair_attempts !== undefined && metadata.repair_attempts > 0 && (
              <Tag color="orange">修复尝试 {metadata.repair_attempts}/{metadata.max_repair_attempts || 1}</Tag>
            )}
            {metadata.permission_pending && <Tag color="gold">权限审批中</Tag>}
            {executionState === 'repairing' && <Tag color="orange">正在尝试修复</Tag>}
          </Space>
          {latestBlockedTool && (
            <Typography.Text type={latestBlockedTool.permission_decision === 'deny' ? 'danger' : 'secondary'}>
              {latestBlockedTool.permission_decision === 'deny'
                ? `权限拒绝：${toolLabel[latestBlockedTool.tool_name] || latestBlockedTool.tool_name}`
                : `等待权限审批：${toolLabel[latestBlockedTool.tool_name] || latestBlockedTool.tool_name}`}
              {' · '}{latestBlockedTool.blocked_reason || latestBlockedTool.result_summary || '该工具调用被权限策略阻断。'}
            </Typography.Text>
          )}
          <div
            style={{
              display: 'grid',
              gap: 8,
              borderTop: '1px solid var(--border-color)',
              paddingTop: 10,
            }}
          >
            <Space wrap size={6}>
              <Typography.Text strong>执行过程</Typography.Text>
              <Tag color={runningTool ? 'processing' : 'default'}>
                {runningTool ? '实时推进中' : '最近动作'}
              </Tag>
            </Space>
            {recentToolCalls.map((call, index) => {
              const tone = toolTone(call);
              return (
                <div
                  key={`live-${call.id}`}
                  style={{
                    display: 'grid',
                    gap: 3,
                    paddingLeft: 12,
                    borderLeft: `2px solid ${tone.accent}`,
                  }}
                >
                  <Space wrap size={6}>
                    <Typography.Text strong>
                      {index + 1}. {toolLabel[call.tool_name] || call.tool_name}
                    </Typography.Text>
                    <Tag color={tone.color as any}>{tone.label}</Tag>
                    {call.duration_ms !== undefined && (
                      <Typography.Text type="secondary">{call.duration_ms}ms</Typography.Text>
                    )}
                  </Space>
                  <Typography.Text type={call.status === 'failed' ? 'danger' : 'secondary'}>
                    {call.error || call.blocked_reason || call.result_summary || '等待工具结果'}
                  </Typography.Text>
                </div>
              );
            })}
          </div>
          <Collapse
            size="small"
            items={[
              {
                key: 'tools',
                label: '展开工具参数与原始结果',
                children: (
                  <div style={{ display: 'grid', gap: 8 }}>
                    {recentToolCalls.map((call) => (
                      <div key={call.id} style={{ display: 'grid', gap: 4 }}>
                        <Space wrap size={6}>
                          <Tag
                            color={
                              call.status === 'failed'
                                ? 'error'
                                : call.status === 'running'
                                  ? 'processing'
                                  : call.status === 'blocked'
                                    ? 'warning'
                                    : 'success'
                            }
                          >
                            {toolLabel[call.tool_name] || call.tool_name}
                          </Tag>
                          <Typography.Text type="secondary">{statusLabel[call.status] || call.status}</Typography.Text>
                          {call.permission_decision && (
                            <Tag color={call.permission_decision === 'deny' ? 'error' : call.permission_decision === 'ask' ? 'warning' : 'success'}>
                              {call.permission_decision}
                            </Tag>
                          )}
                          {call.protocol_repair_attempted && <Tag color="gold">协议修复</Tag>}
                          {call.duration_ms !== undefined && (
                            <Typography.Text type="secondary">{call.duration_ms}ms</Typography.Text>
                          )}
                        </Space>
                        <Typography.Text type={call.status === 'failed' ? 'danger' : 'secondary'}>
                          {call.error || call.result_summary || '等待工具结果'}
                        </Typography.Text>
                      </div>
                    ))}
                  </div>
                ),
              },
            ]}
          />
        </div>
      ) : null}

      {subagentRuns.length ? (
        <Typography.Text type="secondary">
          子 Agent：{subagentRuns.slice(-2).map((item) => `${item.agent_id}: ${item.summary || item.task || item.status}`).join('；')}
        </Typography.Text>
      ) : null}

      {metadata.kind === 'agent_approval_request' && waitingStep && (
        <div style={{ display: 'grid', gap: 8, borderLeft: '2px solid var(--accent-warning, #faad14)', paddingLeft: 10 }}>
          <Typography.Text strong>等待审批：{waitingStep.title}</Typography.Text>
          <Typography.Text type="secondary">
            {waitingStep.output?.summary || waitingStep.output_data?.summary || 'Agent 已完成当前步骤，请确认是否继续。'}
          </Typography.Text>
          <div>
            <Button size="small" type="primary" onClick={() => onApproveStep?.(waitingStep.step_id)}>
              批准进入下一步
            </Button>
          </div>
        </div>
      )}

      {action && (
        <section
          style={{
            display: 'grid',
            gap: 10,
            borderLeft: `3px solid ${actionTone(action).accent}`,
            paddingLeft: 12,
          }}
          aria-label="Agent 动作"
        >
          <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, alignItems: 'flex-start' }}>
            <div style={{ display: 'grid', gap: 6 }}>
              <Space wrap size={6}>
                <Tag
                  icon={
                    action.action_type === 'patch'
                      ? <CodeOutlined />
                      : action.action_type === 'permission_request'
                        ? <SafetyCertificateOutlined />
                        : <PlayCircleOutlined />
                  }
                  color={action.action_type === 'patch' ? 'blue' : action.action_type === 'permission_request' ? 'gold' : 'cyan'}
                >
                  {actionKindLabel(action)}
                </Tag>
                <Tag color={actionTone(action).color}>{actionTone(action).label}</Tag>
                {action.risk_level && (
                  <Tag color={action.risk_level === 'high' ? 'red' : action.risk_level === 'medium' ? 'orange' : 'green'}>
                    {action.risk_level === 'high' ? '高风险' : action.risk_level === 'medium' ? '中风险' : '低风险'}
                  </Tag>
                )}
              </Space>
              <Typography.Text strong style={{ fontSize: 15 }}>{action.title}</Typography.Text>
              <Typography.Text type="secondary">
                {action.description ||
                  (action.action_type === 'patch'
                    ? 'Agent 生成了一个受控文件补丁。'
                    : action.action_type === 'permission_request'
                      ? 'Agent 请求额外工具权限，批准后将重放本次工具调用。'
                      : 'Agent 生成了一个受控验证命令。')}
              </Typography.Text>
            </div>
            {action.status === 'executed' ? (
              <Tag icon={<CheckCircleOutlined />} color="success">
                {action.execution_mode === 'auto' ? '自动完成' : '执行完成'}
              </Tag>
            ) : null}
          </div>

          <Typography.Text type="secondary">
            执行策略：
            {action.execution_mode === 'auto'
              ? '安全自动'
              : action.execution_mode === 'blocked'
                ? '已阻断'
                : '审批后执行'}
            {' · '}动作状态：{statusLabel[action.status] || action.status}
            {' · '}变更文件：{action.changed_files?.length || 0} 个
            {' · '}补丁块：{action.applied_hunks !== undefined ? action.applied_hunks : '-'}
          </Typography.Text>

          {action.policy_reason && (
            <Typography.Text type={action.status === 'blocked' || action.execution_mode === 'blocked' ? 'danger' : 'secondary'}>
              {action.execution_mode === 'auto'
                ? '已按安全策略自动执行'
                : action.execution_mode === 'blocked'
                  ? '已按安全策略阻断'
                  : '策略要求人工确认'}
              {' · '}{action.policy_reason}
            </Typography.Text>
          )}

          {action.changed_files?.length ? (
            <div style={{ display: 'grid', gap: 6 }}>
              <Typography.Text strong>影响文件</Typography.Text>
              <Space wrap size={6}>
                {action.changed_files.map((file) => (
                  <Tag key={file} icon={<FileTextOutlined />} color="blue">
                    {shortPath(file)}
                  </Tag>
                ))}
              </Space>
            </div>
          ) : null}

          {action.failure_summary && (
            <div style={{ display: 'grid', gap: 4 }}>
              <Typography.Text type="danger" strong>失败摘要</Typography.Text>
              <pre style={{ margin: 0, whiteSpace: 'pre-wrap', color: 'var(--text-secondary)' }}>{action.failure_summary}</pre>
            </div>
          )}

          {preview && (
            <Collapse
              size="small"
              items={[
                {
                  key: 'preview',
                  label: action.action_type === 'patch' ? '查看补丁内容' : '查看命令内容',
                  children: <pre style={{ margin: 0, whiteSpace: 'pre-wrap' }}>{preview}</pre>,
                },
              ]}
            />
          )}
          <Space wrap>
            {actionNeedsDecision && action.execution_mode !== 'auto' && (
              <>
                <Button size="small" type="primary" onClick={() => onApproveAction?.(action.id)}>
                  批准这个动作
                </Button>
                <Button size="small" onClick={() => onRejectAction?.(action.id)}>
                  拒绝
                </Button>
              </>
            )}
            {actionCanExecute && (
              <Button size="small" type="primary" icon={<PlayCircleOutlined />} onClick={() => onExecuteAction?.(action.id)}>
                执行已批准动作
              </Button>
            )}
            {action.status === 'executed' && <Tag icon={<CheckCircleOutlined />} color="success">{action.execution_mode === 'auto' ? '已自动执行' : '已执行'}</Tag>}
            {action.status === 'failed' && <Tag icon={<ExclamationCircleOutlined />} color="error">执行失败</Tag>}
          </Space>
          {lastExecution && (
            <Collapse
              size="small"
              items={[
                {
                  key: 'execution',
                  label: `执行输出：${lastExecution.status}${lastExecution.exit_code !== undefined ? ` / exit ${lastExecution.exit_code}` : ''}`,
                  children: (
                    <pre style={{ margin: 0, whiteSpace: 'pre-wrap' }}>
                      {[lastExecution.stdout, lastExecution.stderr, lastExecution.error, lastExecution.failure_summary].filter(Boolean).join('\n\n')}
                    </pre>
                  ),
                },
              ]}
            />
          )}
        </section>
      )}

      {observability?.step_logs?.length ? (
        <>
          <Divider style={{ margin: '2px 0' }} />
          <Typography.Text type="secondary">
            已记录 {observability.step_logs.length} 条步骤日志，{observability.actions.length} 个动作建议。
          </Typography.Text>
        </>
      ) : null}

      <Collapse
        size="small"
        ghost
        items={[
          {
            key: 'debug',
            label: '排查信息',
            children: (
              <Space direction="vertical" size={4}>
                <Typography.Text type="secondary">Run ID: {metadata.agent_run_id || '-'}</Typography.Text>
                <Typography.Text type="secondary">Workflow ID: {metadata.workflow_id || '-'}</Typography.Text>
                <Typography.Text type="secondary">
                  Last event: {String(diagnosticLatestEvent?.event_type || diagnosticLatestEvent?.message || '-')}
                </Typography.Text>
                <Typography.Text type="secondary">
                  Last tool: {diagnosticLatestTool ? toolLabel[diagnosticLatestTool.tool_name] || diagnosticLatestTool.tool_name : '-'}
                </Typography.Text>
                <Typography.Text type="secondary">Latest action: {diagnosticLatestAction?.title || '-'}</Typography.Text>
                <Typography.Text type="secondary">Protocol: {protocolStatus || '-'}</Typography.Text>
              </Space>
            ),
          },
        ]}
      />
    </div>
  );
}
