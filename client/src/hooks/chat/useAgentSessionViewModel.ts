import { useMemo } from 'react';
import type {
  AgentPart,
  AgentSession,
  AgentSessionUiPendingPermission,
  AgentSessionUiState,
  AgentSessionUiTimelineItem,
} from '../../services/api';

const LEGACY_PART_TYPES = new Set(['diff', 'command']);

function toolFromPayload(payload: Record<string, any> = {}) {
  const firstRequest = Array.isArray(payload.action_requests) ? payload.action_requests[0] : undefined;
  return payload.tool || payload.name || firstRequest?.name || payload.action?.name;
}

function timelineItemFromPart(part: AgentPart): AgentSessionUiTimelineItem {
  const payload = part.payload || {};
  return {
    id: part.id,
    part_id: part.id,
    session_id: part.session_id,
    type: part.type,
    status: part.status,
    title: part.title,
    content: part.content,
    tool: toolFromPayload(payload),
    created_at: part.created_at,
    updated_at: part.updated_at,
    payload,
    legacy: LEGACY_PART_TYPES.has(part.type),
  };
}

function actionsFromPermission(part: AgentPart): AgentSessionUiPendingPermission['actions'] {
  const payload = part.payload || {};
  const actions = Array.isArray(payload.actions) && payload.actions.length > 0
    ? payload.actions
    : Array.isArray(payload.action_requests)
      ? payload.action_requests
      : [];
  const source = actions.length > 0
    ? actions
    : [{
        name: payload.tool || payload.action?.name || 'tool',
        args: payload.args || payload.action?.args || {},
        allowed_decisions: payload.allowed_decisions || ['approve', 'reject'],
      }];
  return source.map((action: Record<string, any>, index: number) => ({
    index,
    name: String(action.name || `tool_${index + 1}`),
    args: action.args && typeof action.args === 'object' ? action.args : {},
    description: String(action.description || ''),
    allowed_decisions: Array.isArray(action.allowed_decisions)
      ? action.allowed_decisions.map(String)
      : Array.isArray(payload.allowed_decisions)
        ? payload.allowed_decisions.map(String)
        : ['approve', 'reject'],
  }));
}

function fallbackUiState(session: AgentSession): AgentSessionUiState {
  const timeline = (session.parts || []).map(timelineItemFromPart);
  const pendingPart = [...(session.parts || [])].reverse().find((part) => part.type === 'permission' && part.status === 'pending');
  return {
    session_id: session.id,
    agent_id: session.agent_id,
    status: session.status,
    timeline,
    pending_permission: pendingPart
      ? {
          part_id: pendingPart.id,
          status: pendingPart.status,
          title: pendingPart.title,
          content: pendingPart.content,
          actions: actionsFromPermission(pendingPart),
          allowed_decisions: [],
          decisions_payload: pendingPart.payload || {},
        }
      : null,
    latest: {
      tool_call: [...(session.parts || [])].reverse().find((part) => part.type === 'tool_call') as any,
      tool_result: [...(session.parts || [])].reverse().find((part) => part.type === 'tool_result') as any,
      summary: [...(session.parts || [])].reverse().find((part) => part.type === 'summary') as any,
      error: [...(session.parts || [])].reverse().find((part) => part.type === 'error') as any,
      permission: [...(session.parts || [])].reverse().find((part) => part.type === 'permission') as any,
    },
    artifacts: [],
    status_text: {
      current_phase: session.metadata?.diagnostics?.current_phase,
      stop_reason: session.metadata?.diagnostics?.stop_reason,
      next_action: session.metadata?.diagnostics?.next_action,
    },
  };
}

export function getAgentSessionUiState(session: AgentSession): AgentSessionUiState {
  const fallback = fallbackUiState(session);
  const uiState = session.metadata?.ui_state;
  if (uiState && Array.isArray(uiState.timeline)) {
    const timelineById = new Map<string, AgentSessionUiTimelineItem>();
    uiState.timeline.forEach((item) => timelineById.set(item.part_id || item.id, item));
    fallback.timeline.forEach((item) => {
      if (!timelineById.has(item.part_id || item.id)) {
        timelineById.set(item.part_id || item.id, item);
      }
    });
    return {
      ...fallback,
      ...uiState,
      timeline: Array.from(timelineById.values()),
      pending_permission: uiState.pending_permission ?? fallback.pending_permission ?? null,
    };
  }
  return fallback;
}

export function useAgentSessionViewModel(session?: AgentSession | null) {
  return useMemo(() => (session ? getAgentSessionUiState(session) : null), [session]);
}
