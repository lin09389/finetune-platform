import type { AgentPart, AgentSessionUiTimelineItem, AgentWorkspace } from '../../services/api';
import { selectAttentionItems } from '../attention/selectAttentionItems';
import {
  type CodingDiffReviewPayload,
  isTrainingToolName,
  selectCodingDiffReviewPayload,
} from '../protocol/agentProtocol';
import type { AgentRuntimeState } from '../runtime/agentRuntime';
import { SESSION_STATUS_LABELS } from './sessionStatus';

const asOptionalString = (value: unknown): string | undefined =>
  typeof value === 'string' ? value : undefined;

export interface CodingDiffReviewEntry {
  item: AgentSessionUiTimelineItem;
  payload: CodingDiffReviewPayload;
}

export interface CodingDiffReviewGroup {
  path: string;
  entries: CodingDiffReviewEntry[];
}

function chronologicalDiffEntries(entries: CodingDiffReviewEntry[]): CodingDiffReviewEntry[] {
  return [...entries].sort(
    (left, right) =>
      left.payload.writeSequence - right.payload.writeSequence ||
      String(left.item.created_at || '').localeCompare(String(right.item.created_at || '')) ||
      left.item.id.localeCompare(right.item.id),
  );
}

/**
 * Projects persisted diff parts into per-file review records. It is pure over
 * session parts/timeline items, so REST recovery and SSE updates share one
 * projection instead of relying on browser-held diff state.
 */
export function selectCodingDiffReviewGroups(
  items: AgentSessionUiTimelineItem[],
): CodingDiffReviewGroup[] {
  const byPath = new Map<string, CodingDiffReviewEntry[]>();
  for (const item of items) {
    const payload = selectCodingDiffReviewPayload(item);
    if (!payload) continue;
    const entries = byPath.get(payload.path) || [];
    entries.push({ item, payload });
    byPath.set(payload.path, entries);
  }
  return Array.from(byPath, ([path, entries]) => ({
    path,
    entries: chronologicalDiffEntries(entries),
  })).sort((left, right) => {
    const leftLatest = left.entries[left.entries.length - 1]!;
    const rightLatest = right.entries[right.entries.length - 1]!;
    return (
      String(leftLatest.item.created_at || '').localeCompare(
        String(rightLatest.item.created_at || ''),
      ) || left.path.localeCompare(right.path)
    );
  });
}

function timelineFromPart(part: AgentPart): AgentSessionUiTimelineItem {
  const payload = safeTimelinePayload(part.payload || {});
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
    content: safeTimelineContent(part.content, payload),
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

function safeTimelineItem(item: AgentSessionUiTimelineItem): AgentSessionUiTimelineItem {
  const payload = safeTimelinePayload(item.payload || {});
  return { ...item, payload, content: safeTimelineContent(item.content, payload) };
}

const TRAINING_RESULT_FIELDS = new Set([
  'model_id',
  'dataset_id',
  'proposal_id',
  'task_id',
  'status',
  'method',
  'task_goal',
  'required_vram_gb',
  'blockers',
  'warnings',
  'suggestions',
  'started_at',
  'completed_at',
  'final_loss',
  'elapsed_time',
  'error',
  'code',
]);

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

function safeTrainingConfig(value: unknown): Record<string, unknown> {
  const config = asRecord(value);
  if (!config) return {};
  return Object.fromEntries(
    ['model_id', 'dataset_id', 'method'].flatMap((key) =>
      key in config ? [[key, config[key]]] : [],
    ),
  );
}

function safeTrainingResult(value: unknown): Record<string, unknown> {
  const result = asRecord(value);
  if (!result) return {};
  return Object.fromEntries(
    Object.entries(result).filter(([key]) => TRAINING_RESULT_FIELDS.has(key)),
  );
}

function safeTimelinePayload(payload: Record<string, any>): Record<string, any> {
  const tool = asOptionalString(payload.tool) || asOptionalString(payload.name);
  if (!isTrainingToolName(tool)) return payload;
  const input = asRecord(payload.input) || asRecord(payload.args) || {};
  const safeInput = {
    ...safeTrainingResult(input),
    training_config: safeTrainingConfig(input.training_config),
  };
  return {
    tool,
    runtime: payload.runtime,
    run_id: payload.run_id,
    agent_name: payload.agent_name,
    agent_role: payload.agent_role,
    input: safeInput,
  };
}

function safeTimelineContent(
  content: string | undefined,
  payload: Record<string, any>,
): string | undefined {
  if (!isTrainingToolName(payload.tool) || !content) return content;
  try {
    const parsed = JSON.parse(content);
    return JSON.stringify(safeTrainingResult(parsed));
  } catch {
    return '训练工具返回了不可展示的内容。';
  }
}

export function selectTimeline(state: AgentRuntimeState): AgentSessionUiTimelineItem[] {
  const byId = new Map<string, AgentSessionUiTimelineItem>();
  for (const item of state.taskContextTimeline) {
    if (!state.session || item.session_id === state.session.id)
      byId.set(item.id, safeTimelineItem(item));
  }
  for (const item of state.workspace?.timeline || []) {
    byId.set(item.part_id || item.id, safeTimelineItem(item));
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
  const statusName = state.session?.status || '';
  // Plan A: waiting HITL after process restart keeps approval continuity.
  if (
    (statusName === 'waiting_approval' || statusName === 'waiting_permission')
    && (nextAction === 'continue_approval' || metadata.recovered_after_restart === true)
  ) {
    return '服务已恢复，请继续审批';
  }
  if (statusName === 'needs_manual_review' || statusName === 'failed') {
    if (failureKind === 'configuration_error' || nextAction === 'configure_model')
      return '需要配置模型';
    if (failureKind === 'timeout') return '任务超时，可重新运行';
    if (failureKind === 'process_restart') return '进程重启后已停止，可重新运行';
    if (failureKind === 'user_interrupted') return '已中断';
    if (failureKind === 'runtime_error') return '运行失败，需复核';
  }
  const status =
    state.workspace?.status_text.current_phase ||
    state.session?.metadata?.state?.current_phase ||
    state.session?.status ||
    '待命';
  return SESSION_STATUS_LABELS[status] || status;
}

export function selectAttentionCount(state: AgentRuntimeState): number {
  return selectAttentionItems(state).length;
}
