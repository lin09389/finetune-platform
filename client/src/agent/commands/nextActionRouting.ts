import type {
  AgentAsyncTask,
  AgentWorkspaceNextAction,
} from '../../services/api';
import type { AgentWorkspaceTab } from '../components/AgentWorkspaceView';

export type AgentNextActionIntent =
  | { type: 'open_tab'; tab: AgentWorkspaceTab; filePath?: string }
  | { type: 'open_attention' }
  | { type: 'start_subagent'; agentName: string; description: string }
  | { type: 'submit_prompt'; content: string };

export function routeAgentNextAction(
  action: AgentWorkspaceNextAction,
  tasks: AgentAsyncTask[],
): AgentNextActionIntent {
  switch (action.action_type) {
    case 'start_review':
    case 'start_explore': {
      const fallbackAgent = action.action_type === 'start_review' ? 'review' : 'explore';
      return {
        type: 'start_subagent',
        agentName: String(action.payload?.subagent_type || fallbackAgent),
        description: String(action.payload?.description || action.summary || action.title),
      };
    }
    case 'inspect_file':
      return {
        type: 'open_tab',
        tab: 'files',
        filePath: String(action.payload?.path || ''),
      };
    case 'resolve_permission':
      return { type: 'open_attention' };
    case 'review_risks':
      return { type: 'open_tab', tab: 'artifacts' };
    case 'restart_failed_task': {
      const taskId = action.source_task_id || String(action.payload?.task_id || '');
      const task = tasks.find((candidate) => candidate.task_id === taskId);
      return task
        ? {
            type: 'start_subagent',
            agentName: task.agent_name,
            description: String(task.input?.description || action.summary || '重试失败的子任务'),
          }
        : { type: 'open_tab', tab: 'subagents' };
    }
    case 'run_tests':
    case 'continue_build':
      return {
        type: 'submit_prompt',
        content: action.summary || action.title,
      };
  }
}
