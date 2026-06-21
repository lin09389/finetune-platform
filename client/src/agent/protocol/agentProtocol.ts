import type {
  AgentPart,
  AgentSession,
  AgentSessionEvent,
  AgentWorkspace,
} from '../../services/api';

export type AgentConnectionState = 'idle' | 'connecting' | 'open' | 'reconnecting' | 'closed' | 'error';

export interface AgentUnknownEvent {
  id: string;
  eventType: string;
  message: string;
  payload: Record<string, unknown>;
  createdAt: string;
}

const KNOWN_EVENT_TYPES = new Set([
  'session_snapshot',
  'session_started',
  'session_completed',
  'session_failed',
  'session_blocked',
  'session_interrupted',
  'prompt_queued',
  'prompt_already_running',
  'phase_change',
  'model_stream_started',
  'model_stream_completed',
  'model_stream_failed',
  'part_delta',
  'tool_call_started',
  'tool_call_completed',
  'tool_call_failed',
  'permission_asked',
  'permission_decided',
  'summary_completed',
  'chain_completed',
  'command_started',
  'command_output',
  'command_completed',
  'command_failed',
  'action_proposed',
  'action_approved',
  'action_rejected',
  'action_executed',
  'action_failed',
  'async_subtask_started',
  'async_subtask_updated',
  'async_subtask_completed',
  'async_subtask_failed',
  'async_subtask_cancelled',
  'node_recovery_requested',
  'node_recovery_started',
  'node_recovery_completed',
  'node_recovery_failed',
  'node_recovery_rejected',
  'loop_guard_triggered',
  'trajectory_guard_blocked',
  // Historical events remain readable after the execution-plan migration.
  'task_plan_created',
  'part_created',
  'agent_chain_failed',
]);

export function isAgentSession(value: unknown): value is AgentSession {
  if (!value || typeof value !== 'object') return false;
  const candidate = value as Partial<AgentSession>;
  return typeof candidate.id === 'string'
    && typeof candidate.agent_id === 'string'
    && typeof candidate.status === 'string'
    && Array.isArray(candidate.parts);
}

export function isAgentPart(value: unknown): value is AgentPart {
  if (!value || typeof value !== 'object') return false;
  const candidate = value as Partial<AgentPart>;
  return typeof candidate.id === 'string'
    && typeof candidate.session_id === 'string'
    && typeof candidate.type === 'string'
    && typeof candidate.created_at === 'string';
}

export function isAgentWorkspace(value: unknown): value is AgentWorkspace {
  if (!value || typeof value !== 'object') return false;
  const candidate = value as Partial<AgentWorkspace>;
  return isAgentSession(candidate.session)
    && Array.isArray(candidate.timeline)
    && Array.isArray(candidate.artifacts)
    && Array.isArray(candidate.changed_files)
    && Array.isArray(candidate.next_actions);
}

export function decodeAgentSessionEvent(value: unknown): AgentSessionEvent | null {
  if (!value || typeof value !== 'object') return null;
  const candidate = value as Partial<AgentSessionEvent>;
  if (
    typeof candidate.id !== 'string'
    || typeof candidate.session_id !== 'string'
    || typeof candidate.event_type !== 'string'
  ) {
    return null;
  }
  return {
    id: candidate.id,
    session_id: candidate.session_id,
    event_type: candidate.event_type,
    chunk_type: candidate.chunk_type,
    message: typeof candidate.message === 'string' ? candidate.message : '',
    payload: candidate.payload && typeof candidate.payload === 'object' ? candidate.payload : {},
    created_at: typeof candidate.created_at === 'string' ? candidate.created_at : new Date().toISOString(),
    session_status: candidate.session_status,
    agent_id: candidate.agent_id,
    phase: candidate.phase,
    tool: candidate.tool,
    agent_name: candidate.agent_name,
    agent_role: candidate.agent_role,
    task_id: candidate.task_id,
    child_session_id: candidate.child_session_id,
    async_status: candidate.async_status,
    health_status: candidate.health_status,
    delta: candidate.delta,
    content: candidate.content,
    summary: candidate.summary,
    part: isAgentPart(candidate.part) ? candidate.part : null,
    session_snapshot: candidate.session_snapshot,
  };
}

export function isKnownAgentEvent(eventType: string): boolean {
  return KNOWN_EVENT_TYPES.has(eventType);
}

export function toUnknownAgentEvent(event: AgentSessionEvent): AgentUnknownEvent {
  return {
    id: event.id,
    eventType: event.event_type,
    message: event.message,
    payload: event.payload,
    createdAt: event.created_at,
  };
}

export function mergeAgentPart(parts: AgentPart[], incoming: AgentPart): AgentPart[] {
  const index = parts.findIndex((part) => part.id === incoming.id);
  if (index === -1) return [...parts, incoming];
  const next = [...parts];
  next[index] = {
    ...parts[index],
    ...incoming,
    payload: { ...(parts[index]?.payload || {}), ...(incoming.payload || {}) },
  };
  return next;
}

export function applyEventToSession(session: AgentSession | null, event: AgentSessionEvent): AgentSession | null {
  if (isAgentSession(event.session_snapshot)) return event.session_snapshot;
  if (!session || event.session_id !== session.id) return session;

  let parts = session.parts;
  if (event.part) {
    parts = mergeAgentPart(parts, event.part);
  } else if (event.chunk_type === 'part_delta' && event.payload?.part_id) {
    const partId = String(event.payload.part_id);
    parts = parts.map((part) => part.id === partId
      ? {
          ...part,
          content: `${part.content || ''}${event.delta || event.content || ''}`,
          updated_at: event.created_at,
        }
      : part);
  }

  return {
    ...session,
    status: event.session_status || session.status,
    parts,
    updated_at: event.created_at || session.updated_at,
    metadata: {
      ...session.metadata,
      state: {
        ...session.metadata?.state,
        current_phase: event.phase || session.metadata?.state?.current_phase,
      },
    },
  };
}
