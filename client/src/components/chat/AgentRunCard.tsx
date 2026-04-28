import {
  CheckCircleOutlined,
  CodeOutlined,
  ExclamationCircleOutlined,
  LinkOutlined,
  PlayCircleOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons';
import { Alert, Button, Collapse, Space, Tag, Typography } from 'antd';
import type { ChatAgentMetadata } from '../../types';
import type { Workflow, WorkflowAction, WorkflowObservability } from '../../services/api';

interface AgentRunCardProps {
  content: string;
  metadata: ChatAgentMetadata;
  onApproveStep?: (stepId: string) => void | Promise<void>;
  onApproveAction?: (actionId: string) => void | Promise<void>;
  onRejectAction?: (actionId: string) => void | Promise<void>;
  onExecuteAction?: (actionId: string) => void | Promise<void>;
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
  pending_approval: 'warning',
  approved: 'success',
  executed: 'success',
  rejected: 'default',
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
  if (Array.isArray(files)) {
    return files.map((file: any) => `${file.path || file.file_path || 'unknown'}\n${file.content || ''}`).join('\n\n');
  }
  return stringify(action.payload);
}

export default function AgentRunCard({
  content,
  metadata,
  onApproveStep,
  onApproveAction,
  onRejectAction,
  onExecuteAction,
  onOpenDetails,
}: AgentRunCardProps) {
  const workflow = metadata.workflow as Workflow | undefined;
  const observability = metadata.observability as WorkflowObservability | undefined;
  const action = metadata.action as WorkflowAction | undefined;
  const waitingStep = workflow?.steps?.find((step) => step.status === 'awaiting_approval');
  const lastExecution = action?.executions?.[action.executions.length - 1];
  const preview = actionPreview(action);
  const status = action?.status || metadata.status || workflow?.status || 'running';

  return (
    <div style={{ display: 'grid', gap: 12, minWidth: 280 }}>
      <Space wrap>
        <Tag icon={<ThunderboltOutlined />} color="blue">Agent 工作</Tag>
        <Tag color={statusColor[status] || 'default'}>{status}</Tag>
        {workflow?.current_stage && <Tag>{workflow.current_stage}</Tag>}
      </Space>

      <Typography.Text>{content}</Typography.Text>

      {metadata.kind === 'agent_approval_request' && waitingStep && (
        <Alert
          type="warning"
          showIcon
          message={`等待审批：${waitingStep.title}`}
          description={waitingStep.output?.summary || waitingStep.output_data?.summary || 'Agent 已完成当前步骤，请确认是否继续。'}
          action={
            <Button size="small" type="primary" onClick={() => onApproveStep?.(waitingStep.step_id)}>
              批准继续
            </Button>
          }
        />
      )}

      {action && (
        <div style={{ display: 'grid', gap: 10 }}>
          <Alert
            type={action.status === 'failed' ? 'error' : action.status === 'pending_approval' ? 'warning' : 'info'}
            showIcon
            icon={action.action_type === 'patch' ? <CodeOutlined /> : <PlayCircleOutlined />}
            message={action.title}
            description={action.description || `${action.action_type} 动作建议`}
          />
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
            {action.status === 'pending_approval' && (
              <>
                <Button size="small" type="primary" onClick={() => onApproveAction?.(action.id)}>
                  批准
                </Button>
                <Button size="small" onClick={() => onRejectAction?.(action.id)}>
                  拒绝
                </Button>
              </>
            )}
            {action.status === 'approved' && (
              <Button size="small" type="primary" icon={<PlayCircleOutlined />} onClick={() => onExecuteAction?.(action.id)}>
                执行
              </Button>
            )}
            {action.status === 'executed' && <Tag icon={<CheckCircleOutlined />} color="success">已执行</Tag>}
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
                      {[lastExecution.stdout, lastExecution.stderr, lastExecution.error].filter(Boolean).join('\n\n')}
                    </pre>
                  ),
                },
              ]}
            />
          )}
        </div>
      )}

      {observability?.step_logs?.length ? (
        <Typography.Text type="secondary">
          已记录 {observability.step_logs.length} 条步骤日志，{observability.actions.length} 个动作建议。
        </Typography.Text>
      ) : null}

      {metadata.details_url && (
        <Button size="small" icon={<LinkOutlined />} onClick={() => onOpenDetails?.(metadata.details_url!)}>
          查看运行详情
        </Button>
      )}
    </div>
  );
}
