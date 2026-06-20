import type {
  AgentPart,
  AgentSessionUiTimelineItem,
  AgentWorkspace,
} from '../../services/api';
import type { AgentRuntimeState } from '../runtime/agentRuntime';
import { selectAttentionItems } from '../attention/selectAttentionItems';

function timelineFromPart(part: AgentPart): AgentSessionUiTimelineItem {
  const payload = part.payload || {};
  const action = Array.isArray(payload.action_requests) ? payload.action_requests[0] : undefined;
  return {
    id: part.id,
    part_id: part.id,
    session_id: part.session_id,
    type: part.type,
    status: part.status,
    title: part.title,
    content: part.content,
    tool: payload.tool || payload.name || action?.name,
    agent_name: payload.agent_name,
    agent_role: payload.agent_role,
    task_id: payload.task_id,
    child_session_id: payload.child_session_id,
    async_status: payload.async_status,
    created_at: part.created_at,
    updated_at: part.updated_at,
    payload,
  };
}

export function selectTimeline(state: AgentRuntimeState): AgentSessionUiTimelineItem[] {
  const byId = new Map<string, AgentSessionUiTimelineItem>();
  for (const item of state.workspace?.timeline || []) {
    byId.set(item.part_id || item.id, item);
  }
  for (const part of state.session?.parts || []) {
    const item = timelineFromPart(part);
    byId.set(item.part_id || item.id, {
      ...byId.get(item.part_id || item.id),
      ...item,
    });
  }
  return Array.from(byId.values()).sort((left, right) => (
    String(left.created_at || '').localeCompare(String(right.created_at || ''))
  ));
}

export function selectWorkspaceProjectLabel(workspace: AgentWorkspace | null): string {
  const path = workspace?.session.project_path;
  if (!path) return '默认工作区';
  const segments = path.replace(/\\/g, '/').split('/').filter(Boolean);
  return segments[segments.length - 1] || path;
}

export function selectConnectionLabel(state: AgentRuntimeState): string {
  const labels = {
    idle: '待命',
    connecting: '连接中',
    open: '实时连接',
    reconnecting: `重连中 · ${state.reconnectAttempt}`,
    closed: '已同步',
    error: '连接中断',
  };
  return labels[state.connection];
}

export function selectWorkspaceStatus(state: AgentRuntimeState): string {
  const status = state.workspace?.status_text.current_phase
    || state.session?.metadata?.state?.current_phase
    || state.session?.status
    || '待命';
  return ({
    idle: '待命',
    running: '运行中',
    planning: '规划中',
    executing: '执行中',
    verifying: '验证中',
    repairing: '修复中',
    waiting_permission: '等待审批',
    waiting_approval: '等待审批',
    completed: '已完成',
    failed: '失败',
    interrupted: '已停止',
    needs_manual_review: '需要复核',
  } as Record<string, string>)[status] || status;
}

export function selectAttentionCount(state: AgentRuntimeState): number {
  return selectAttentionItems(state).length;
}
