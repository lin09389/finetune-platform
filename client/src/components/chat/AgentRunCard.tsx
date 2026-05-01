import {
  CheckCircleOutlined,
  CodeOutlined,
  ExclamationCircleOutlined,
  FileTextOutlined,
  LinkOutlined,
  PlayCircleOutlined,
  SafetyCertificateOutlined,
  SearchOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons';
import { Alert, Button, Collapse, Divider, Progress, Space, Steps, Tag, Typography } from 'antd';
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

const statusColor: Record<string, string> = {
  created: 'default',
  running: 'processing',
  planning: 'processing',
  awaiting_approval: 'warning',
  implementing: 'processing',
  reviewing: 'processing',
  completed: 'success',
  failed: 'error',
  blocked: 'warning',
  pending_approval: 'warning',
  approved: 'success',
  executed: 'success',
  rejected: 'default',
};

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

const stepStatusMap: Record<string, 'wait' | 'process' | 'finish' | 'error'> = {
  draft: 'wait',
  pending: 'wait',
  running: 'process',
  awaiting_approval: 'process',
  approved: 'finish',
  completed: 'finish',
  failed: 'error',
  needs_manual_review: 'error',
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
  const subagentRuns = ((metadata as any).subagent_runs as Array<Record<string, any>> | undefined) || observability?.subagent_runs || [];
  const recentToolCalls = toolCalls.slice(-3).reverse();
  const runningTool = [...toolCalls].reverse().find((call) => call.status === 'running');
  const latestBlockedTool = [...toolCalls]
    .reverse()
    .find((call) => call.status === 'blocked' || call.permission_decision === 'ask' || call.permission_decision === 'deny');
  const action = metadata.action as WorkflowAction | undefined;
  const waitingStep = workflow?.steps?.find((step) => step.status === 'awaiting_approval');
  const lastExecution = action?.executions?.[action.executions.length - 1];
  const preview = actionPreview(action);
  const status = action?.status || executionState || metadata.status || workflow?.status || 'running';
  const completedSteps = workflow?.steps?.filter((step) => ['approved', 'completed'].includes(step.status)).length || 0;
  const totalSteps = workflow?.steps?.length || 0;
  const progressPercent = totalSteps ? Math.round((completedSteps / totalSteps) * 100) : 0;
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

  return (
    <div
      style={{
        display: 'grid',
        gap: 14,
        minWidth: 280,
        border: '1px solid var(--border-color)',
        borderRadius: 10,
        padding: 14,
        background: 'color-mix(in srgb, var(--bg-elevated) 92%, var(--accent-primary) 8%)',
      }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, alignItems: 'flex-start' }}>
        <Space wrap>
          <Tag icon={<ThunderboltOutlined />} color="blue">Agent 工作台</Tag>
          <Tag color={statusColor[status] || 'default'}>{statusLabel[status] || status}</Tag>
          {workflow?.current_stage && <Tag>{workflow.current_stage}</Tag>}
          {activeAgentId && <Tag color="cyan">当前 Agent: {activeAgentId}</Tag>}
        </Space>
        <Space size={4}>
          {metadata.recoverable && (
            <Button size="small" type="text" onClick={() => onRefreshRun?.(metadata.agent_run_id)}>
              刷新
            </Button>
          )}
          {metadata.details_url && (
            <Button size="small" type="text" icon={<LinkOutlined />} onClick={() => onOpenDetails?.(metadata.details_url!)}>
              详情
            </Button>
          )}
        </Space>
      </div>

      <Typography.Text strong>{content}</Typography.Text>

      {executionState && (
        <Alert
          type={executionState === 'failed' || executionState === 'needs_manual_review' ? 'warning' : 'info'}
          showIcon
          message={`当前阶段：${statusLabel[executionState] || executionState}`}
          description={executionMessage || 'Agent 正在推进开发闭环。'}
        />
      )}

      {executionState === 'needs_manual_review' && (
        <Alert
          type="warning"
          showIcon
          message="需要人工确认"
          description={(metadata.blocked_state as any)?.reason || executionMessage || 'Agent 当前无法自动继续，请查看工具调用和动作输出后决定下一步。'}
        />
      )}

      {showFinalOutput && (
        <Alert
          type="success"
          showIcon
          message="最终结果"
          description={
            <div style={{ display: 'grid', gap: 8 }}>
              {finalSummary && (
                <Typography.Paragraph style={{ margin: 0 }}>
                  {finalSummary}
                </Typography.Paragraph>
              )}
              {Array.isArray(finalOutput.risks) && finalOutput.risks.length > 0 && (
                <Typography.Text type="secondary">
                  风险：{finalOutput.risks.join('；')}
                </Typography.Text>
              )}
              {finalOutput.next_action && (
                <Typography.Text type="secondary">
                  下一步：{finalOutput.next_action}
                </Typography.Text>
              )}
            </div>
          }
        />
      )}

      {workflow?.steps?.length ? (
        <div style={{ display: 'grid', gap: 8 }}>
          <Progress percent={progressPercent} size="small" showInfo={false} />
          <Steps
            size="small"
            current={Math.max(0, workflow.steps.findIndex((step) => ['running', 'awaiting_approval'].includes(step.status)))}
            items={workflow.steps.map((step) => ({
              title: step.title,
              description: statusLabel[step.status] || step.status,
              status: stepStatusMap[step.status] || 'wait',
            }))}
          />
        </div>
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
            <Alert
              type={latestBlockedTool.permission_decision === 'deny' ? 'error' : 'warning'}
              showIcon
              message={
                latestBlockedTool.permission_decision === 'deny'
                  ? `权限拒绝：${toolLabel[latestBlockedTool.tool_name] || latestBlockedTool.tool_name}`
                  : `等待权限审批：${toolLabel[latestBlockedTool.tool_name] || latestBlockedTool.tool_name}`
              }
              description={latestBlockedTool.blocked_reason || latestBlockedTool.result_summary || '该工具调用被权限策略阻断。'}
            />
          )}
          <Collapse
            size="small"
            items={[
              {
                key: 'tools',
                label: '最近工具调用',
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
        <Alert
          type="info"
          showIcon
          message="子 Agent 协作"
          description={subagentRuns.slice(-2).map((item) => `${item.agent_id}: ${item.summary || item.task || item.status}`).join('\n')}
        />
      ) : null}

      {metadata.kind === 'agent_approval_request' && waitingStep && (
        <Alert
          type="warning"
          showIcon
          message={`等待审批：${waitingStep.title}`}
          description={waitingStep.output?.summary || waitingStep.output_data?.summary || 'Agent 已完成当前步骤，请确认是否继续。'}
          action={
            <Button size="small" type="primary" onClick={() => onApproveStep?.(waitingStep.step_id)}>
              批准进入下一步
            </Button>
          }
        />
      )}

      {action && (
        <div style={{ display: 'grid', gap: 10 }}>
          <Alert
            type={action.status === 'failed' ? 'error' : action.status === 'pending_approval' ? 'warning' : 'info'}
            showIcon
            icon={
              action.action_type === 'patch'
                ? <CodeOutlined />
                : action.action_type === 'permission_request'
                  ? <SafetyCertificateOutlined />
                  : <PlayCircleOutlined />
            }
            message={action.title}
            description={
              action.description ||
              (action.action_type === 'patch'
                ? 'Agent 建议写入一个受限补丁，执行前需要你批准。'
                : action.action_type === 'permission_request'
                  ? 'Agent 请求额外工具权限，批准后将自动重放本次工具调用。'
                  : 'Agent 建议运行一个白名单命令，执行前需要你批准。')
            }
          />
          <Space wrap size={6}>
            <Tag icon={action.action_type === 'patch' ? <FileTextOutlined /> : <PlayCircleOutlined />}>
              {action.action_type === 'patch' ? '补丁' : action.action_type === 'permission_request' ? '权限请求' : '命令'}
            </Tag>
            <Tag icon={<SafetyCertificateOutlined />} color="green">
              {action.execution_mode === 'auto' ? '策略自动执行' : '审批后执行'}
            </Tag>
            <Tag color={statusColor[action.status] || 'default'}>{statusLabel[action.status] || action.status}</Tag>
            {action.execution_mode === 'auto' && <Tag color="blue">自动执行</Tag>}
            {action.policy_reason && <Tag>{action.policy_reason}</Tag>}
            {action.execution_state && <Tag>{statusLabel[action.execution_state] || action.execution_state}</Tag>}
          </Space>
          {action.changed_files?.length ? (
            <Alert
              type="success"
              showIcon
              message="影响文件"
              description={action.changed_files.join('\n')}
            />
          ) : null}
          {action.failure_summary && (
            <Alert
              type="error"
              showIcon
              message="失败摘要"
              description={<pre style={{ margin: 0, whiteSpace: 'pre-wrap' }}>{action.failure_summary}</pre>}
            />
          )}
          {preview && (
            <Collapse
              size="small"
              items={[
                {
                  key: 'preview',
                  label: action.action_type === 'patch' ? '查看补丁内容' : '查看命令',
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
                  label: `执行结果：${lastExecution.status}${lastExecution.exit_code !== undefined ? ` / exit ${lastExecution.exit_code}` : ''}`,
                  children: (
                    <pre style={{ margin: 0, whiteSpace: 'pre-wrap' }}>
                      {[lastExecution.stdout, lastExecution.stderr, lastExecution.error, lastExecution.failure_summary].filter(Boolean).join('\n\n')}
                    </pre>
                  ),
                },
              ]}
            />
          )}
        </div>
      )}

      {observability?.step_logs?.length ? (
        <>
          <Divider style={{ margin: '2px 0' }} />
          <Typography.Text type="secondary">
            已记录 {observability.step_logs.length} 条步骤日志，{observability.actions.length} 个动作建议。
          </Typography.Text>
        </>
      ) : null}
    </div>
  );
}
