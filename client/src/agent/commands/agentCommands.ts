import type {
  AgentAsyncTask,
  AgentExecutionPlanNode,
  AgentExecutionPlanRecoveryResponse,
  AgentHitlDecision,
  AgentSession,
  AgentSessionApprovalResponse,
  AgentSessionCreate,
  AgentWorkspace,
} from '../../services/api';
import type { AgentTransport } from '../transport/agentTransport';

export interface SubmitAgentTaskOptions {
  content: string;
  agentId?: string;
  projectPath?: string;
  provider?: string;
  model?: string;
  autonomyMode?: AgentSessionCreate['autonomy_mode'];
}

export type AgentCommand =
  | { type: 'submit'; currentSession: AgentSession | null; options: SubmitAgentTaskOptions }
  | { type: 'interrupt'; sessionId: string }
  | { type: 'decide_permission'; partId: string; decisions: AgentHitlDecision[] }
  | { type: 'recover_node'; sessionId: string; node: AgentExecutionPlanNode; instruction?: string }
  | { type: 'start_subtask'; sessionId: string; agentName: string; description: string }
  | { type: 'cancel_subtask'; sessionId: string; taskId: string }
  | { type: 'refresh'; sessionId: string };

export type AgentCommandResult =
  | { type: 'submit'; session: AgentSession; created: boolean; restartStream: true; refreshSessionId: string }
  | { type: 'interrupt'; session: AgentSession; restartStream: false; refreshSessionId: string }
  | { type: 'decide_permission'; response: AgentSessionApprovalResponse; restartStream: true; refreshSessionId: string }
  | { type: 'recover_node'; response: AgentExecutionPlanRecoveryResponse; workspace: AgentWorkspace; restartStream: true }
  | { type: 'start_subtask'; task: AgentAsyncTask; restartStream: true; refreshSessionId: string }
  | { type: 'cancel_subtask'; task: AgentAsyncTask; restartStream: false; refreshSessionId: string }
  | { type: 'refresh'; workspace: AgentWorkspace; restartStream: false };

export class AgentCommandFailure extends Error {
  readonly partialSession?: AgentSession;
  readonly originalCause?: unknown;

  constructor(message: string, options?: { cause?: unknown; partialSession?: AgentSession }) {
    super(message);
    this.name = 'AgentCommandFailure';
    this.partialSession = options?.partialSession;
    this.originalCause = options?.cause;
  }
}

export function agentCommandKey(command: AgentCommand): string {
  switch (command.type) {
    case 'submit':
      return `submit:${command.currentSession?.id || 'new'}`;
    case 'interrupt':
      return `interrupt:${command.sessionId}`;
    case 'decide_permission':
      return `permission:${command.partId}`;
    case 'recover_node':
      return `recover:${command.sessionId}:${command.node.id}`;
    case 'start_subtask':
      return `start-subtask:${command.sessionId}`;
    case 'cancel_subtask':
      return `cancel-subtask:${command.sessionId}:${command.taskId}`;
    case 'refresh':
      return `refresh:${command.sessionId}`;
  }
}

export function commandLabel(command: AgentCommand): string {
  switch (command.type) {
    case 'submit':
      return '正在提交任务';
    case 'interrupt':
      return '正在停止运行';
    case 'decide_permission':
      return '正在提交审批决定';
    case 'recover_node':
      return '正在恢复执行节点';
    case 'start_subtask':
      return '正在启动子 Agent';
    case 'cancel_subtask':
      return '正在取消子 Agent';
    case 'refresh':
      return '正在刷新运行';
  }
}

export class AgentCommandExecutor {
  private readonly inFlight = new Map<string, Promise<AgentCommandResult>>();

  constructor(private readonly transport: AgentTransport) {}

  execute(command: AgentCommand): Promise<AgentCommandResult> {
    const key = agentCommandKey(command);
    const existing = this.inFlight.get(key);
    if (existing) return existing;

    const promise = this.executeOnce(command).finally(() => {
      this.inFlight.delete(key);
    });
    this.inFlight.set(key, promise);
    return promise;
  }

  private async executeOnce(command: AgentCommand): Promise<AgentCommandResult> {
    switch (command.type) {
      case 'submit':
        return this.submit(command);
      case 'interrupt': {
        const session = await this.transport.interrupt(command.sessionId);
        return {
          type: 'interrupt',
          session,
          restartStream: false,
          refreshSessionId: session.id,
        };
      }
      case 'decide_permission': {
        if (command.decisions.length === 0) {
          throw new AgentCommandFailure('审批决定不能为空');
        }
        const response = await this.transport.decidePermission(command.partId, command.decisions);
        return {
          type: 'decide_permission',
          response,
          restartStream: true,
          refreshSessionId: response.session.id,
        };
      }
      case 'recover_node': {
        const response = await this.transport.recoverNode(command.sessionId, command.node.id, {
          action: command.node.recovery_action || undefined,
          instruction: command.instruction?.trim() || undefined,
        });
        return {
          type: 'recover_node',
          response,
          workspace: response.workspace,
          restartStream: true,
        };
      }
      case 'start_subtask': {
        const description = command.description.trim();
        if (!description) throw new AgentCommandFailure('子 Agent 任务说明不能为空');
        const task = await this.transport.startAsyncTask(command.sessionId, {
          subagent_type: command.agentName,
          description,
        });
        return {
          type: 'start_subtask',
          task,
          restartStream: true,
          refreshSessionId: command.sessionId,
        };
      }
      case 'cancel_subtask': {
        const task = await this.transport.cancelAsyncTask(command.sessionId, command.taskId, {
          reason: 'Cancelled from Agent Workbench',
        });
        return {
          type: 'cancel_subtask',
          task,
          restartStream: false,
          refreshSessionId: command.sessionId,
        };
      }
      case 'refresh': {
        const workspace = await this.transport.getWorkspace(command.sessionId);
        return { type: 'refresh', workspace, restartStream: false };
      }
    }
  }

  private async submit(command: Extract<AgentCommand, { type: 'submit' }>): Promise<AgentCommandResult> {
    const content = command.options.content.trim();
    if (!content) throw new AgentCommandFailure('任务目标不能为空');
    const created = !command.currentSession;
    const session = command.currentSession || await this.transport.createSession({
      title: content.slice(0, 56),
      agent_id: command.options.agentId || 'build',
      project_path: command.options.projectPath?.trim() || undefined,
      provider: command.options.provider,
      model: command.options.model,
      autonomy_mode: command.options.autonomyMode || 'safe_auto',
    });

    try {
      const prompted = await this.transport.prompt(session.id, {
        content,
        provider: command.options.provider,
        model: command.options.model,
      });
      return {
        type: 'submit',
        session: prompted,
        created,
        restartStream: true,
        refreshSessionId: prompted.id,
      };
    } catch (error) {
      throw new AgentCommandFailure('任务提交失败，会话已保留，可直接重试。', {
        cause: error,
        partialSession: session,
      });
    }
  }
}
