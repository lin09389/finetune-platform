import type { AgentSession, AgentSessionUiTimelineItem, AgentWorkspace } from '../../services/api';
import type { AgentRuntimeState } from '../runtime/agentRuntime';
import { selectTimeline } from '../selectors/workbenchSelectors';

export interface AgentCanonicalProjection {
  sessionId: string | null;
  status: string | null;
  timeline: Array<{ type: string; status: string | null; title: string | null; content: string | null }>;
  pendingPermissionId: string | null;
  plan: Array<{ id: string; status: string; recoverable: boolean }>;
  subagents: Array<{ id: string; status: string }>;
  files: string[];
  artifacts: string[];
  nextActions: string[];
}

function project(
  session: AgentSession | null,
  workspace: AgentWorkspace | null,
  timeline: AgentSessionUiTimelineItem[],
): AgentCanonicalProjection {
  return {
    sessionId: session?.id || null,
    status: session?.status || null,
    timeline: timeline.map((item) => ({
      type: item.type,
      status: item.status || null,
      title: item.title || item.tool || null,
      content: item.content || null,
    })),
    pendingPermissionId: workspace?.pending_permission?.part_id || null,
    plan: (workspace?.execution_plan?.nodes || []).map((node) => ({
      id: node.id,
      status: node.status,
      recoverable: Boolean(node.recoverable),
    })),
    subagents: (workspace?.async_tasks.tasks || []).map((task) => ({
      id: task.task_id,
      status: task.status,
    })),
    files: (workspace?.changed_files || []).map((file) => file.path).sort(),
    artifacts: (workspace?.artifacts || []).map((artifact) => artifact.id).sort(),
    nextActions: (workspace?.next_actions || []).map((action) => action.action_type).sort(),
  };
}

export function projectNewRuntime(state: AgentRuntimeState): AgentCanonicalProjection {
  return project(state.session, state.workspace, selectTimeline(state));
}

export function projectLegacyFixture(session: AgentSession, workspace: AgentWorkspace): AgentCanonicalProjection {
  return project(session, workspace, workspace.timeline);
}
