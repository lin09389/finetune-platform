import type { AgentAsyncTask, AgentExecutionPlanNode, AgentWorkspaceRecentEvent } from '../../services/api';
import type { AgentRuntimeState } from '../runtime/agentRuntime';
import type { AgentAttentionItem } from './attentionTypes';

const PERMISSION_TTL_MS = 15 * 60 * 1000;

function eventTime(event: AgentWorkspaceRecentEvent | undefined, fallback: string): string {
  return event?.created_at || fallback;
}

function findEvent(state: AgentRuntimeState, eventTypes: string[]): AgentWorkspaceRecentEvent | undefined {
  return [...(state.workspace?.recent_events || [])]
    .reverse()
    .find((event) => eventTypes.includes(String(event.event_type || '')));
}

function toolFailure(state: AgentRuntimeState): AgentAttentionItem | null {
  const event = findEvent(state, ['tool_call_failed']);
  const success = findEvent(state, ['tool_call_completed', 'node_recovery_completed']);
  const diagnostic = state.workspace?.diagnostics.latest_error;
  if (event && success && success.created_at && event.created_at && success.created_at > event.created_at) {
    return null;
  }
  if (!event && !diagnostic) return null;
  const payload = event?.payload || diagnostic?.payload || {};
  const tool = String(payload.tool || diagnostic?.title || '工具');
  const detail = event?.message || diagnostic?.content || diagnostic?.message || '工具执行失败。';
  return {
    id: `tool-failure:${event?.id || diagnostic?.id || tool}`,
    kind: 'tool_failure',
    severity: 'high',
    status: 'open',
    title: `${tool} 执行失败`,
    occurredAt: eventTime(event, diagnostic?.created_at || state.session?.updated_at || new Date().toISOString()),
    whatHappened: detail,
    impactScope: '当前执行节点可能未完成，后续依赖步骤可能被阻断。',
    recommendedAction: '检查失败摘要和输入参数，刷新权威快照后从可恢复节点继续。',
    actions: [{ id: 'refresh', label: '刷新状态', primary: true }],
    sourceEventId: event?.id,
    sessionId: state.activeSessionId || undefined,
    dedupeKey: `tool-failure:${tool}:${String(payload.failure_signature || detail).slice(0, 120)}`,
  };
}

function loopGuard(state: AgentRuntimeState): AgentAttentionItem | null {
  const event = findEvent(state, ['loop_guard_triggered', 'trajectory_guard_blocked']);
  const guard = state.session?.metadata?.loop_guard;
  if (guard && !guard.blocked) return null;
  if (!event && !guard?.blocked) return null;
  const reason = event?.message || guard?.blocked_reason || '检测到重复失败或无进展循环。';
  return {
    id: `loop-guard:${event?.id || guard?.blocked_signature || 'active'}`,
    kind: 'loop_guard',
    severity: 'critical',
    status: 'open',
    title: '执行循环已阻断',
    occurredAt: eventTime(event, state.session?.updated_at || new Date().toISOString()),
    whatHappened: reason,
    impactScope: '当前 Agent 已停止继续调用工具，避免重复修改、资源浪费或无限循环。',
    recommendedAction: '检查阻断原因，修正任务约束后从对应节点恢复。',
    actions: [{ id: 'refresh', label: '查看最新状态', primary: true }],
    sourceEventId: event?.id,
    sessionId: state.activeSessionId || undefined,
    dedupeKey: `loop-guard:${guard?.blocked_signature || event?.id || reason}`,
  };
}

function recoveryFailure(state: AgentRuntimeState, node: AgentExecutionPlanNode): AgentAttentionItem {
  return {
    id: `recovery:${node.id}`,
    kind: node.recovery_error ? 'recovery_failure' : 'tool_failure',
    severity: node.recovery_error ? 'high' : 'medium',
    status: 'open',
    title: node.recovery_error ? `${node.title} 恢复失败` : `${node.title} 可恢复`,
    occurredAt: node.last_recovery_at || state.session?.updated_at || new Date().toISOString(),
    whatHappened: node.recovery_error || node.recovery_reason || node.blocked_reason || node.error || '节点执行未完成。',
    impactScope: `执行计划节点“${node.title}”及其依赖节点。`,
    recommendedAction: node.recovery_error
      ? '调整恢复指令或修复依赖后重新恢复。'
      : '确认上下文仍有效后恢复该节点。',
    actions: [{
      id: 'recover',
      label: node.recovery_error ? '重新恢复' : '恢复节点',
      primary: true,
      payload: { nodeId: node.id },
    }],
    sessionId: state.activeSessionId || undefined,
    dedupeKey: `recovery:${node.id}:${node.recovery_attempts || 0}:${node.recovery_error || ''}`,
  };
}

function subagentAttention(state: AgentRuntimeState, task: AgentAsyncTask): AgentAttentionItem {
  return {
    id: `subagent:${task.task_id}`,
    kind: 'subagent_manual',
    severity: 'high',
    status: 'open',
    title: `${task.agent_name} 需要人工处理`,
    occurredAt: task.updated_at,
    whatHappened: task.error || String(task.diagnostics?.message || '子 Agent 未能完成任务。'),
    impactScope: `子任务“${String(task.input?.description || task.task_id)}”及父任务汇总结果。`,
    recommendedAction: '检查失败原因，必要时修改任务说明后重新启动。',
    actions: [{
      id: 'restart_subagent',
      label: '重新启动',
      primary: true,
      payload: {
        agentName: task.agent_name,
        description: String(task.input?.description || '重试未完成的子任务'),
      },
    }],
    sessionId: state.activeSessionId || undefined,
    dedupeKey: `subagent:${task.task_id}:${task.restart_count}:${task.error || task.status}`,
  };
}

function subagentPermission(
  state: AgentRuntimeState,
  task: AgentAsyncTask,
  now: number,
): AgentAttentionItem | null {
  const partId = String(task.pending_permission_part_id || '');
  if (!task.has_pending_permission || !partId) return null;
  const occurredAt = task.updated_at || state.session?.updated_at || new Date(now).toISOString();
  const expiresAt = new Date(new Date(occurredAt).getTime() + PERMISSION_TTL_MS).toISOString();
  const expired = new Date(expiresAt).getTime() <= now;
  return {
    id: `subagent-permission:${partId}`,
    kind: expired ? 'expired_permission' : 'permission',
    severity: expired ? 'high' : 'medium',
    status: expired ? 'expired' : 'open',
    title: expired ? `${task.agent_name} 的审批已过期` : `${task.agent_name} 等待审批`,
    occurredAt,
    whatHappened: `子任务“${String(task.input?.description || task.task_id)}”暂停在工具执行前。`,
    impactScope: '该子 Agent 无法继续，父任务的汇总结果可能不完整。',
    recommendedAction: expired ? '刷新会话以获取最新审批状态。' : '核对工具影响后批准或拒绝。',
    actions: expired
      ? [{ id: 'refresh', label: '刷新审批', primary: true }]
      : [
          { id: 'approve', label: '批准', primary: true, payload: { partId, actionCount: 1 } },
          { id: 'reject', label: '拒绝', danger: true, payload: { partId, actionCount: 1 } },
        ],
    sessionId: state.activeSessionId || undefined,
    expiresAt,
    dedupeKey: `permission:${partId}`,
  };
}

export function selectAttentionItems(state: AgentRuntimeState, now = Date.now()): AgentAttentionItem[] {
  const items: AgentAttentionItem[] = [];
  const sessionId = state.activeSessionId || undefined;
  const fallbackTime = state.session?.updated_at || new Date(now).toISOString();
  const permission = state.workspace?.pending_permission;

  if (permission) {
    const permissionEvent = findEvent(state, ['permission_asked']);
    const permissionPart = state.session?.parts.find((part) => part.id === permission.part_id);
    const occurredAt = permissionEvent?.created_at || permissionPart?.created_at || fallbackTime;
    const expiresAt = new Date(new Date(occurredAt).getTime() + PERMISSION_TTL_MS).toISOString();
    const expired = new Date(expiresAt).getTime() <= now;
    items.push({
      id: `permission:${permission.part_id}`,
      kind: expired ? 'expired_permission' : 'permission',
      severity: expired ? 'high' : 'medium',
      status: expired ? 'expired' : 'open',
      title: expired ? '审批请求已过期' : permission.title || '工具执行等待审批',
      occurredAt,
      whatHappened: permission.content || `${permission.actions.length} 个工具动作等待决定。`,
      impactScope: '当前 Agent 暂停在工具执行前，不会继续修改工作区。',
      recommendedAction: expired ? '刷新会话以获取最新审批状态。' : '核对工具、参数和影响范围后批准或拒绝。',
      actions: expired
        ? [{ id: 'refresh', label: '刷新审批', primary: true }]
        : [
            { id: 'approve', label: '批准', primary: true, payload: { partId: permission.part_id } },
            { id: 'reject', label: '拒绝', danger: true, payload: { partId: permission.part_id } },
          ],
      sessionId,
      expiresAt,
      dedupeKey: `permission:${permission.part_id}`,
    });
  }

  const failure = toolFailure(state);
  if (failure) items.push(failure);
  const guard = loopGuard(state);
  if (guard) items.push(guard);

  for (const node of state.workspace?.execution_plan?.nodes || []) {
    if (node.recoverable || node.recovery_error) items.push(recoveryFailure(state, node));
  }
  for (const task of state.workspace?.async_tasks.tasks || []) {
    const pendingPermission = subagentPermission(state, task, now);
    if (pendingPermission) items.push(pendingPermission);
    if (task.status === 'failed' || task.health_status === 'attention') {
      items.push(subagentAttention(state, task));
    }
  }

  if (state.connection === 'error' || (state.connection === 'reconnecting' && state.reconnectAttempt >= 2)) {
    items.push({
      id: `connection:${sessionId || 'none'}`,
      kind: 'connection_interruption',
      severity: state.connection === 'error' ? 'high' : 'medium',
      status: 'open',
      title: '实时连接中断',
      occurredAt: fallbackTime,
      whatHappened: `事件流当前为“${state.connection}”，已尝试重连 ${state.reconnectAttempt} 次。`,
      impactScope: '界面可能暂时缺少最新事件，但后端任务可能仍在运行。',
      recommendedAction: '等待自动重连；若持续失败，刷新权威快照。',
      actions: [{ id: 'refresh', label: '刷新快照', primary: true }],
      sessionId,
      dedupeKey: `connection:${sessionId}`,
    });
  }

  if (state.error) {
    items.push({
      id: `operation-error:${state.error}`,
      kind: 'operation_error',
      severity: 'high',
      status: 'open',
      title: '操作未完成',
      occurredAt: fallbackTime,
      whatHappened: state.error,
      impactScope: '刚才发起的用户操作未完成，其他已保存状态不受影响。',
      recommendedAction: '检查错误详情后重试，或刷新权威快照。',
      actions: [
        { id: 'refresh', label: '刷新状态', primary: true },
        { id: 'dismiss', label: '忽略' },
      ],
      sessionId,
      dedupeKey: `operation-error:${state.error}`,
    });
  }

  if (state.unknownEvents.length) {
    const latest = state.unknownEvents[state.unknownEvents.length - 1];
    if (latest) items.push({
      id: `unknown:${latest.id}`,
      kind: 'protocol_unknown',
      severity: 'low',
      status: 'open',
      title: '收到未知协议事件',
      occurredAt: latest.createdAt,
      whatHappened: `事件类型“${latest.eventType}”尚未被当前前端识别。`,
      impactScope: '事件已隔离保存，核心会话状态继续由权威快照维护。',
      recommendedAction: '刷新快照；若持续出现，应升级前端协议映射。',
      actions: [{ id: 'refresh', label: '刷新快照' }],
      sourceEventId: latest.id,
      sessionId,
      dedupeKey: `unknown:${latest.eventType}`,
    });
  }

  if (state.malformedEvents.length) {
    items.push({
      id: `malformed:${state.malformedEvents.length}`,
      kind: 'protocol_malformed',
      severity: 'medium',
      status: 'open',
      title: '事件数据解析失败',
      occurredAt: fallbackTime,
      whatHappened: `已隔离 ${state.malformedEvents.length} 条无法解析的数据。`,
      impactScope: '损坏事件未写入 Store，可能遗漏部分增量展示。',
      recommendedAction: '刷新权威快照并检查前后端协议版本。',
      actions: [{ id: 'refresh', label: '刷新快照', primary: true }],
      sessionId,
      dedupeKey: `malformed:${sessionId}`,
    });
  }

  const severityOrder = { critical: 0, high: 1, medium: 2, low: 3 };
  const deduped = new Map<string, AgentAttentionItem>();
  for (const item of items) deduped.set(item.dedupeKey, item);
  return [...deduped.values()].sort((left, right) => (
    severityOrder[left.severity] - severityOrder[right.severity]
    || right.occurredAt.localeCompare(left.occurredAt)
  ));
}
