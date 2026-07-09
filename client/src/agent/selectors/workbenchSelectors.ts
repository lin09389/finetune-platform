import type { AgentPart, AgentSessionUiTimelineItem, AgentWorkspace } from '../../services/api';
import { selectAttentionItems } from '../attention/selectAttentionItems';
import type { AgentRuntimeState } from '../runtime/agentRuntime';
import { SESSION_STATUS_LABELS } from './sessionStatus';

const asOptionalString = (value: unknown): string | undefined =>
  typeof value === 'string' ? value : undefined;

function timelineFromPart(part: AgentPart): AgentSessionUiTimelineItem {
  const payload = part.payload || {};
  const action = Array.isArray(payload.action_requests) ? payload.action_requests[0] : undefined;
  const actionName =
    action && typeof action === 'object' && 'name' in action
      ? asOptionalString((action as { name?: unknown }).name)
      : undefined;
  return {
    id: part.id,
    part_id: part.id,
    session_id: part.session_id,
    type: part.type,
    status: part.status,
    title: part.title,
    content: part.content,
    tool: asOptionalString(payload.tool) || asOptionalString(payload.name) || actionName,
    agent_name: asOptionalString(payload.agent_name),
    agent_role: asOptionalString(payload.agent_role),
    task_id: asOptionalString(payload.task_id),
    child_session_id: asOptionalString(payload.child_session_id),
    async_status: asOptionalString(payload.async_status),
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
  const hasPersistedUserMessage = Array.from(byId.values()).some((item) => {
    if (item.type !== 'text') return false;
    const source = asOptionalString(item.payload?.source);
    const title = item.title?.trim().toLowerCase();
    return (
      item.payload?.role === 'user' ||
      source === 'prompt' ||
      source === 'user_prompt' ||
      ['用户任务', '我的消息', 'user prompt'].includes(title || '')
    );
  });
  const legacyGoal =
    asOptionalString(state.session?.metadata?.current_goal)?.trim() || state.session?.title?.trim();
  if (state.session && legacyGoal && !hasPersistedUserMessage) {
    byId.set(`legacy-user-prompt:${state.session.id}`, {
      id: `legacy-user-prompt:${state.session.id}`,
      session_id: state.session.id,
      type: 'text',
      status: 'completed',
      title: '我的消息',
      content: legacyGoal,
      created_at: state.session.created_at,
      payload: { role: 'user', source: 'legacy_current_goal', legacy: true },
      legacy: true,
    });
  }
  const sorted = Array.from(byId.values()).sort((left, right) =>
    String(left.created_at || '').localeCompare(String(right.created_at || '')),
  );
  const finalSummaries = new Set(
    sorted
      .filter((item) => item.type === 'summary' && item.content?.trim())
      .map((item) => item.content!.trim().replace(/\s+/g, ' ')),
  );
  return sorted.filter((item) => {
    if (item.type === 'text' && item.payload?.role !== 'user' && !item.content?.trim()) {
      return false;
    }
    if (item.type !== 'text' || item.payload?.role === 'user' || !item.content?.trim()) return true;
    const normalized = item.content.trim().replace(/\s+/g, ' ');
    return !finalSummaries.has(normalized);
  });
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
  const metadata = state.session?.metadata || {};
  const failureKind = typeof metadata.failure_kind === 'string' ? metadata.failure_kind : '';
  const nextAction = typeof metadata.next_action === 'string' ? metadata.next_action : '';
  if (state.session?.status === 'needs_manual_review' || state.session?.status === 'failed') {
    if (failureKind === 'configuration_error' || nextAction === 'configure_model') return '需要配置模型';
    if (failureKind === 'process_restart') return '进程重启后已停止，可重新运行';
    if (failureKind === 'user_interrupted') return '已中断';
    if (failureKind === 'runtime_error') return '运行失败，需复核';
  }
  const status =
    state.workspace?.status_text.current_phase ||
    state.session?.metadata?.state?.current_phase ||
    state.session?.status ||
    '待命';
  return (
    SESSION_STATUS_LABELS[status] || status
  );
}

export function selectAttentionCount(state: AgentRuntimeState): number {
  return selectAttentionItems(state).length;
}
